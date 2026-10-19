"""Progression des taches pour l'atelier (lot claude2/atelier-progression, tache-22 msg 4925-4926). 19 oct. 2026.

Charles : « le tableau de l'atelier n'est pas live que ça... Je ne vois pas vraiment les progressions ». Les cartes
datent de `updated_at`, qui ne bouge qu'au changement d'un champ de la tache ; on y ajoute le dernier message.

Une progression est un message `chat` ou `decision` d'un agent ou de Charles, rattache a une tache (son `tache_id`,
sinon son canal `tache-<id>`). Ne comptent pas : le systeme, join/leave/resumes/cartes de job, et le rappel qu'un
agent s'adresse a lui-meme (« @claude-1 Point d'etape du chef (R14) … » envoye par claude-1, msg 4888, 4903, 4915).
Le silence d'une tache ne compte que les messages d'agents : un message de Charles n'est pas un signe de vie.

Les memes regles existent cote navigateur (static/progression.js) ; tests/progression_cas.json les eprouve toutes
les deux.
"""

import re

import jobs as _jobs_mod

TYPES = ("chat", "decision")
EXTRAIT_MAX = 160
_MENTION = re.compile(r"@([\w.-]+)", re.ASCII)
_MENTIONS_TETE = re.compile(r"^(?:@[\w.-]+[\s,:]*)+", re.ASCII)
_MARQUE_TETE = re.compile(r"^(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)+")
_SEPARATEUR = re.compile(r"^\|[\s|:-]*$")


def auto_adresse(msg: dict) -> bool:
    """Vrai si toutes les mentions de tete du message nomment son auteur (un rappel a soi-meme)."""
    tete = _MENTIONS_TETE.match(str(msg.get("text") or "").lstrip())
    if not tete:
        return False
    auteur = str(msg.get("sender") or "").lower()
    return all(nom.rstrip(".").lower() == auteur for nom in _MENTION.findall(tete.group(0)))


def tache_du_message(msg: dict) -> int | None:
    tid = msg.get("tache_id")
    if isinstance(tid, int) and not isinstance(tid, bool) and tid > 0:
        return tid
    return _jobs_mod.tache_du_canal(msg.get("channel") or "")


def est_progression(msg: dict) -> bool:
    sender = str(msg.get("sender") or "")
    return ((msg.get("type") or "chat") in TYPES and bool(sender) and sender != "system"
            and not auto_adresse(msg))


def extrait(texte: str, n: int = EXTRAIT_MAX) -> str:
    """Premiere ligne de prose, sans mentions de tete ni marques markdown ; les lignes de tableau et de code sautent.
    Un message fait seulement d'un tableau donne sa premiere rangee, cellules separees par « · »."""
    def nettoyer(ligne: str) -> str:
        ligne = _MENTIONS_TETE.sub("", ligne.strip())
        ligne = _MARQUE_TETE.sub("", ligne)
        ligne = ligne.replace("**", "").replace("__", "").replace("`", "")
        return " ".join(ligne.split())

    lignes = [b.strip() for b in str(texte or "").split("\n")]
    choisi = next((c for c in (nettoyer(b) for b in lignes if b and not b.startswith(("|", "```"))) if c), "")
    if not choisi:
        rangee = next((b for b in lignes if b.startswith("|") and not _SEPARATEUR.match(b)), "")
        choisi = nettoyer(" · ".join(c.strip() for c in rangee.strip("|").split("|") if c.strip()))
    return choisi if len(choisi) <= n else choisi[: n - 1] + "…"


def activites(messages: list[dict], humains: set[str]) -> dict[int, dict]:
    """Par tache, la derniere progression : {id, ts, par, extrait, agent, agent_ts}. `agent_ts` est l'heure du
    dernier message d'un agent (pas de Charles) ; None si aucun agent n'a encore ecrit."""
    out: dict[int, dict] = {}
    textes: dict[int, str] = {}  # l'extrait n'est calcule qu'une fois par tache, sur son dernier message
    for msg in messages:
        ts = msg.get("timestamp")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not est_progression(msg):
            continue
        tid = tache_du_message(msg)
        if not tid:
            continue
        a = out.setdefault(tid, {"agent": "", "agent_ts": None})
        sender = str(msg["sender"])
        if a.get("ts") is None or ts >= a["ts"]:
            a.update(id=msg.get("id"), ts=float(ts), par=sender)
            textes[tid] = msg.get("text") or ""
        if sender not in humains and (a["agent_ts"] is None or ts >= a["agent_ts"]):
            a["agent"], a["agent_ts"] = sender, float(ts)
    for tid, texte in textes.items():
        out[tid]["extrait"] = extrait(texte)
    return out


def derniers_messages_agents(messages: list[dict], humains: set[str]) -> dict[str, float]:
    """`tache-<id>` -> heure du dernier message d'agent de la tache, pour `ronde.taches_muettes`."""
    return {_jobs_mod.canal_tache(tid): a["agent_ts"] for tid, a in activites(messages, humains).items()
            if a["agent_ts"] is not None}


def au_travail(execs: list[dict]) -> dict[int, list[str]]:
    """Par tache, les agents dont l'execution est active (signe de vie de moins de 10 min, pas finie)."""
    out: dict[int, list[str]] = {}
    for e in execs:
        if e.get("etat") == "actif" and e.get("tache_id"):
            noms = out.setdefault(e["tache_id"], [])
            if e.get("agent") and e["agent"] not in noms:
                noms.append(e["agent"])
    return {tid: sorted(noms) for tid, noms in out.items()}
