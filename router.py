"""Message routing based on @mentions with per-channel loop guard."""

import re

# Code dans un message (21 oct. 2026, #tache-26 msg 6772) : une mention citée entre accents graves, ou dans un bloc
# délimité par trois accents graves, n'est pas une mention. Sinon un message qui parle de la règle (« `@all` »)
# réveille tout le monde. Un bloc non refermé court jusqu'à la fin du message.
_CODE_RE = re.compile(r"```.*?(?:```|\Z)|``[^\n]*?``|`[^`\n]*`", re.DOTALL)


def sans_code(text: str) -> str:
    """Le texte sans le code en ligne ni les blocs de code (remplacés par une espace)."""
    return _CODE_RE.sub(" ", text or "")


class Router:
    def __init__(self, agent_names: list[str], default_mention: str = "both",
                 max_hops: int = 4, online_checker=None, anti_spin_ticks: int = 3):
        self.agent_names = set(n.lower() for n in agent_names)
        self.default_mention = default_mention
        self.max_hops = max_hops
        # Anti-tournage-a-vide : apres ce nombre de battements de ronde recurrente consecutifs
        # SANS progres reel (note_progress), on cesse de relancer claude dans ce canal.
        self.anti_spin_ticks = anti_spin_ticks
        self._online_checker = online_checker  # callable() -> set of online agent names
        # Per-channel state: { channel: { hop_count, paused, guard_emitted, heartbeats, paire } }
        self._channels: dict[str, dict] = {}
        self._build_pattern()

    def _get_ch(self, channel: str) -> dict:
        if channel not in self._channels:
            self._channels[channel] = {
                "hop_count": 0,
                "paused": False,
                "guard_emitted": False,
                # battements de ronde recurrente depuis le dernier progres reel (anti-spin)
                "heartbeats": 0,
                # loop guard par groupe : les participants du dernier relais adresse (None apres une remise a zero)
                "paire": None,
            }
        return self._channels[channel]

    def _build_pattern(self):
        # Sort longest-first so "gemini-2" is tried before "gemini"
        names = [re.escape(n) for n in sorted(self.agent_names, key=len, reverse=True)]
        alternatives = "|".join(names + ["both", "all"])
        self._mention_re = re.compile(
            rf"@({alternatives})(?![\w-])", re.IGNORECASE
        )
        self._diffusion_re = re.compile(r"@(both|all)(?![\w-])", re.IGNORECASE)

    def parse_mentions(self, text: str) -> list[str]:
        mentions = set()
        for match in self._mention_re.finditer(sans_code(text)):
            name = match.group(1).lower()
            if name in ("both", "all"):
                # Only tag online agents when using @all
                if self._online_checker:
                    online = self._online_checker()
                    mentions.update(n for n in self.agent_names if n in online)
                else:
                    mentions.update(self.agent_names)
            else:
                mentions.add(name)
        return list(mentions)

    def _is_agent(self, sender: str) -> bool:
        return sender.lower() in self.agent_names

    def get_targets(self, sender: str, text: str, channel: str = "general") -> list[str]:
        """Determine which agents should receive this message."""
        ch = self._get_ch(channel)
        mentions = self.parse_mentions(text)

        if not self._is_agent(sender):
            # Human message resets hop counter and unpauses
            ch["hop_count"] = 0
            ch["paused"] = False
            ch["guard_emitted"] = False
            ch["paire"] = None
            if not mentions:
                if self.default_mention in ("both", "all"):
                    return list(self.agent_names)
                elif self.default_mention == "none":
                    return []
                return [self.default_mention]
            return mentions
        else:
            # Agent message: blocked while loop guard is active
            if ch["paused"]:
                return []
            # Only route if explicit @mention
            if not mentions:
                return []
            # Don't route back to self ; a self-mention alone routes nothing, and neither counts nor resets
            cibles = [m for m in mentions if m != sender.lower()]
            if not cibles:
                return []
            # Loop guard par groupe (21 oct. 2026, mesure de #tache-26 msgs 6751 et 6769) : une boucle, c'est le meme
            # groupe d'agents (expediteur + destinataires : deux agents qui se relancent, ou trois qui se mettent en
            # copie) qui revient a chaque relais, ou des messages d'agent a @all/@both. Seuls ces relais comptent ; un
            # relais vers un autre groupe repart a 1. L'orchestration du chef (« chef -> a + b », puis « a -> chef » :
            # deux groupes) ne s'accumule plus, et un agent ne leve toujours pas une pause (seul un humain).
            diffusion = bool(self._diffusion_re.search(sans_code(text)))
            paire = frozenset([sender.lower(), *cibles])
            if diffusion or paire == ch["paire"]:
                ch["hop_count"] += 1
            else:
                ch["hop_count"] = 1
            if not diffusion:
                ch["paire"] = paire
            if ch["hop_count"] > self.max_hops:
                ch["paused"] = True
                return []
            return cibles

    def continue_routing(self, channel: str = "general"):
        """Resume after loop guard pause."""
        ch = self._get_ch(channel)
        ch["hop_count"] = 0
        ch["paused"] = False
        ch["guard_emitted"] = False
        ch["paire"] = None

    def derniere_paire(self, channel: str = "general") -> list[str]:
        """Les agents du dernier relais adresse (le groupe qui boucle), tries ; [] apres une remise a zero."""
        return sorted(self._get_ch(channel)["paire"] or [])

    def is_paused(self, channel: str = "general") -> bool:
        return self._get_ch(channel)["paused"]

    def is_guard_emitted(self, channel: str = "general") -> bool:
        return self._get_ch(channel)["guard_emitted"]

    def set_guard_emitted(self, channel: str = "general"):
        self._get_ch(channel)["guard_emitted"] = True

    def note_progress(self, channel: str = "general", reprendre: bool = True):
        """Un progres reel sur ce canal (tache qui avance, execution terminee, revue rendue,
        jalon franchi). Remet le compteur de relais agent->agent ET le compteur anti-tournage-a-vide
        a zero, comme un message humain, mais SANS router de message.
        reprendre=False (salle sobre, progres declare par un agent) : un canal en pause le reste, seul
        le /continue d'un humain le relance; hors pause, les compteurs sont remis a zero comme avant."""
        ch = self._get_ch(channel)
        if not reprendre and ch["paused"]:
            return
        ch["hop_count"] = 0
        ch["paused"] = False
        ch["guard_emitted"] = False
        ch["heartbeats"] = 0
        ch["paire"] = None

    def note_heartbeat(self, channel: str = "general") -> tuple[int, bool]:
        """Compte un battement de ronde recurrente (une planification qui relance claude) dans ce
        canal. Rend (nombre de battements depuis le dernier progres, seuil tout juste franchi).
        « franchi » n'est vrai qu'au battement qui atteint anti_spin_ticks, pour n'avertir qu'une fois."""
        ch = self._get_ch(channel)
        ch["heartbeats"] += 1
        franchi = ch["heartbeats"] == self.anti_spin_ticks
        return ch["heartbeats"], franchi

    def heartbeats_since_progress(self, channel: str = "general") -> int:
        return self._get_ch(channel)["heartbeats"]

    def update_agents(self, names: list[str]):
        """Replace the agent name set and rebuild the mention regex."""
        self.agent_names = set(n.lower() for n in names)
        self._build_pattern()
