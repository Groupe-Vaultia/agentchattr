"""Message routing based on @mentions with per-channel loop guard.

Loop guard par groupe (21 oct. 2026) : seuls comptent les relais d'agent consecutifs du meme groupe de participants
(expediteur + destinataires) et les messages d'agent a @all/@both ; un relais vers un autre groupe repart a 1 ; seul un
humain leve une pause. Limites connues de la regle « meme groupe » :
- un cycle a trois sans copie (A -> B, B -> C, C -> A) change de groupe a chaque relais et n'est jamais compte ;
- une boucle A <-> B qui met C en copie un relais sur quatre alterne les groupes ({A, B} trois fois, puis {A, B, C}) :
  la suite ne depasse pas 3, et 60 relais passent sans pause au seuil 4 (revue N3 de codex-2, #tache-26 msg 6777).
Toutes deux supposent des agents qui changent de destinataires a dessein ; aucune n'a ete vue dans le journal depuis le
21 sept. 2026.
"""

import re

# Code dans un message (21 oct. 2026, #tache-26 msgs 6772 et 6789) : une mention citée dans du code n'est pas une
# mention. Sinon un message qui parle de la règle réveille tout le monde. Lecture à la CommonMark :
# - bloc : une ligne qui commence (au plus 3 espaces) par au moins trois accents graves ; il court jusqu'à une ligne de
#   clôture d'au moins autant d'accents graves, ou jusqu'à la fin du message ; une ligne d'ouverture qui contient un autre
#   accent grave n'ouvre pas de bloc (« ```code``` » en tête de ligne est du code en ligne) ;
# - code en ligne : une suite de N accents graves s'ouvre et se ferme à la prochaine suite d'exactement N, même sur
#   plusieurs lignes, mais pas au-delà d'une ligne vide ; sans fermeture, les accents graves restent du texte (un
#   accent grave isolé ne coupe donc pas le reste du message) ;
# - un accent grave précédé d'une barre oblique inverse est du texte, pas une ouverture ; deux barres obliques inverses
#   sont une barre échappée, et l'accent grave qui les suit ouvre du code.
# Non lus (re-N3 de claude-3, msg 6823 ; aucun cas dans le journal) : blocs en tildes, code indenté de 4 espaces (ses
# accents graves peuvent former du code en ligne avec les suivants), fins de ligne CRLF.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,})", re.MULTILINE)
_LIGNE_VIDE_RE = re.compile(r"\n[ \t]*\n")


def _fin_de_bloc(text: str, debut: int, n: int) -> int:
    """Fin (exclue) du bloc ouvert à `debut` par n accents graves : fin de sa ligne de clôture, ou fin du texte."""
    fin_ligne = text.find("\n", debut)
    if fin_ligne < 0:
        return len(text)
    for m in _FENCE_RE.finditer(text, fin_ligne + 1):
        fin = text.find("\n", m.end())
        fin = len(text) if fin < 0 else fin
        if len(m.group(1)) >= n and not text[m.end():fin].strip(" \t"):   # clôture : rien d'autre sur la ligne
            return fin
    return len(text)


def sans_code(text: str) -> str:
    """Le texte sans les blocs de code ni le code en ligne (remplacés par une espace)."""
    text = text or ""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in "\\`":
            out.append(text[i:i + 2])                         # accent grave ou barre échappés : du texte
            i += 2
            continue
        if c != "`":
            out.append(c)
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        k = j - i
        debut_ligne = text.rfind("\n", 0, i) + 1
        fin_ligne = text.find("\n", j)
        info = text[j:fin_ligne if fin_ligne >= 0 else n]
        if k >= 3 and len(text[debut_ligne:i]) <= 3 and not text[debut_ligne:i].strip(" ") and "`" not in info:
            i = _fin_de_bloc(text, i, k)                      # bloc de code
            out.append(" ")
            continue
        limite = _LIGNE_VIDE_RE.search(text, j)
        borne = limite.start() if limite else n
        fermeture = re.compile(rf"(?<!`)`{{{k}}}(?!`)").search(text, j, borne)
        if fermeture:
            out.append(" ")                                   # code en ligne
            i = fermeture.end()
        else:
            out.append(text[i:j])                             # pas de fermeture : du texte
            i = j
    return "".join(out)


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
