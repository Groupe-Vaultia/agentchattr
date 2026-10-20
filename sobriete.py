"""Salle sobre : ce qu'un agent lit du fil d'une tache, et la preuve qu'il lit la base plutot que le fil.

v1.0 (20 oct. 2026, claude, lots 2 et 3) :
- `filtrer_pour` : dans un canal `tache-N`, un agent ne recoit que les messages des humains et ceux qui le
  @mentionnent (lui, son nom de base, @all, @both). Le travail des autres agents vit dans la fiche de la tache
  (`jobs.fiche`), pas dans sa lecture. Les autres canaux (ronde, annonces) ne sont pas filtres.
- `Compteur` : par agent, lectures de fiche contre lectures du fil (filtrees ou completes), messages et caracteres
  masques. Persiste en JSON dans le dossier de donnees, lu par GET /api/v2/sobriete.
"""

import json
import re
import threading
import time
from pathlib import Path

from jobs import tache_du_canal

_SLOT = re.compile(r"-\d+$")


def est_canal_tache(canal: str | None) -> bool:
    return bool(canal) and tache_du_canal(str(canal)) is not None


def _noms(agent: str) -> set[str]:
    agent = str(agent or "").strip().lower()
    return {n for n in (agent, _SLOT.sub("", agent)) if n}


def mentionne(texte: str, agent: str) -> bool:
    """Vrai si `texte` @mentionne l'agent (nom d'instance ou de base) ou tout le monde (@all, @both)."""
    noms = _noms(agent) | {"all", "both"}
    motif = "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True))
    return re.search(rf"@({motif})(?![\w-])", str(texte or ""), re.IGNORECASE) is not None


def filtrer_pour(msgs: list[dict], agent: str, humains: set[str]) -> tuple[list[dict], list[dict]]:
    """Rend (gardes, masques). Garde : messages d'un humain, et messages qui @mentionnent l'agent.
    Masque : tout le reste, y compris les messages systeme et ceux de l'agent lui-meme (il les connait)."""
    humains = {str(h).strip().lower() for h in humains if h}
    gardes, masques = [], []
    for m in msgs:
        expediteur = str(m.get("sender", "")).strip().lower()
        if expediteur in humains or (expediteur not in _noms(agent) and expediteur != "system"
                                      and mentionne(m.get("text", ""), agent)):
            gardes.append(m)
        else:
            masques.append(m)
    return gardes, masques


def note_masques(masques: list[dict], canal: str) -> str:
    """Une ligne pour l'agent : ce qui a ete masque, et ou trouver l'etat."""
    if not masques:
        return ""
    n = tache_du_canal(canal)
    return (f"[salle sobre] {len(masques)} message(s) d'autres agents masque(s) dans #{canal}. "
            f"L'etat de la tache est dans tache_lire(tache_id={n}). "
            f"Lecture complete seulement si necessaire : chat_read(channel='{canal}', complet=True), en disant pourquoi.")


class Compteur:
    """Compteurs par agent. Ecriture atomique (temporaire + renommage), tolerante aux erreurs d'ecriture."""

    CLES = ("tache_lire", "fiche_au_reveil", "lecture_filtree", "lecture_complete",
            "messages_masques", "caracteres_masques")

    def __init__(self, chemin: str | Path | None = None):
        self._chemin = Path(chemin) if chemin else None
        self._lock = threading.Lock()
        self._etat: dict = {"depuis": time.time(), "agents": {}}
        if self._chemin and self._chemin.exists():
            try:
                charge = json.loads(self._chemin.read_text(encoding="utf-8"))
                if isinstance(charge.get("agents"), dict):
                    self._etat = charge
            except (OSError, ValueError):
                pass

    def ajouter(self, agent: str, **increments: int) -> None:
        agent = str(agent or "").strip() or "inconnu"
        with self._lock:
            a = self._etat["agents"].setdefault(agent, {k: 0 for k in self.CLES})
            for k, v in increments.items():
                if k in self.CLES and v:
                    a[k] = a.get(k, 0) + int(v)
            a["derniere"] = time.time()
            self._sauver()

    def masquer(self, agent: str, masques: list[dict]) -> None:
        self.ajouter(agent, lecture_filtree=1, messages_masques=len(masques),
                     caracteres_masques=sum(len(str(m.get("text", ""))) for m in masques))

    def _sauver(self) -> None:
        if not self._chemin:
            return
        try:
            tmp = self._chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._etat, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._chemin)
        except OSError:
            pass

    def rapport(self) -> dict:
        """Par agent : compteurs + part de lectures « base » (fiche) sur l'ensemble des lectures."""
        with self._lock:
            agents = {}
            for nom, a in sorted(self._etat["agents"].items()):
                base = a.get("tache_lire", 0) + a.get("fiche_au_reveil", 0)
                fil = a.get("lecture_filtree", 0) + a.get("lecture_complete", 0)
                total = base + fil
                agents[nom] = dict(a, part_base=round(base / total, 2) if total else None,
                                   jetons_evites_approx=a.get("caracteres_masques", 0) // 4)
            return {"depuis": self._etat.get("depuis"), "agents": agents,
                    "note": "jetons_evites_approx = caracteres masques / 4 (approximation)."}
