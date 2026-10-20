"""Salle sobre : ce qu'un agent lit du fil d'une tache, et la preuve qu'il lit la base plutot que le fil.

v1.1 (20 oct. 2026, claude, revue independante) :
- un message de l'agent qui le @mentionne lui-meme (rappel auto-adresse du chef, R14) est garde;
- `base` : nom de base fourni par le registre (instance renommee, ex. claude-music, reconnue sur @claude);
- `garder_siens` : les agents sans memoire entre deux reveils (API, cli_print) gardent leurs propres messages;
- Compteur : ecritures groupees (au plus une toutes les `intervalle` s), fichier JSON non-objet tolere;
- note : « messages masques » (autres agents et systeme), sans pretendre qu'ils viennent tous d'agents.
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


def _noms(agent: str, base: str = "") -> set[str]:
    agent = str(agent or "").strip().lower()
    return {n for n in (agent, _SLOT.sub("", agent), str(base or "").strip().lower()) if n}


def mentionne(texte: str, agent: str, base: str = "") -> bool:
    """Vrai si `texte` @mentionne l'agent (nom d'instance ou de base) ou tout le monde (@all, @both)."""
    noms = _noms(agent, base) | {"all", "both"}
    motif = "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True))
    return re.search(rf"@({motif})(?![\w-])", str(texte or ""), re.IGNORECASE) is not None


def filtrer_pour(msgs: list[dict], agent: str, humains: set[str], *, base: str = "",
                 garder_siens: bool = False) -> tuple[list[dict], list[dict]]:
    """Rend (gardes, masques). Seuls les messages d'un canal `tache-N` sont filtres; les autres passent tels quels.
    Garde : messages d'un humain; messages qui @mentionnent l'agent (y compris ceux qu'il s'adresse a lui-meme);
    ses propres messages si `garder_siens`. Masque : le reste, dont les messages systeme."""
    humains = {str(h).strip().lower() for h in humains if h}
    gardes, masques = [], []
    for m in msgs:
        canal = m.get("channel")
        expediteur = str(m.get("sender", "")).strip().lower()
        if canal is not None and not est_canal_tache(canal):
            gardes.append(m)
        elif expediteur in humains:
            gardes.append(m)
        elif expediteur == "system":
            masques.append(m)
        elif garder_siens and expediteur == str(agent or "").strip().lower():
            gardes.append(m)
        elif mentionne(m.get("text", ""), agent, base):
            gardes.append(m)
        else:
            masques.append(m)
    return gardes, masques


def note_masques(masques: list[dict], canal: str | None) -> str:
    """Une ligne pour l'agent : ce qui a ete masque, et ou trouver l'etat."""
    if not masques:
        return ""
    canaux = sorted({str(m.get("channel") or canal or "") for m in masques} - {""})
    ids = [f"tache_lire(tache_id={tache_du_canal(c)})" for c in canaux if tache_du_canal(c)]
    ou = ", ".join(ids) if ids else "tache_lire"
    lieu = f"#{canaux[0]}" if len(canaux) == 1 else "les canaux de tache"
    complet = (f"chat_read(channel='{canaux[0]}', complet=True)" if len(canaux) == 1
               else "chat_read(channel='tache-N', complet=True)")
    return (f"[salle sobre] {len(masques)} message(s) masque(s) dans {lieu} (autres agents, systeme). "
            f"L'etat de la tache est dans {ou}. "
            f"Lecture complete seulement si necessaire : {complet}, en disant pourquoi.")


class Compteur:
    """Compteurs par agent. Ecriture atomique (temporaire + renommage), groupee : au plus une ecriture toutes les
    `intervalle` secondes (vider() force l'ecriture). Tolerant aux erreurs de lecture et d'ecriture."""

    CLES = ("tache_lire", "fiche_au_reveil", "lecture_filtree", "lecture_complete",
            "messages_masques", "caracteres_masques")

    def __init__(self, chemin: str | Path | None = None, intervalle: float = 5.0):
        self._chemin = Path(chemin) if chemin else None
        self._intervalle = float(intervalle)
        self._lock = threading.Lock()
        self._dernier_ecrit = 0.0
        self._sale = False
        self._etat: dict = {"depuis": time.time(), "agents": {}}
        if self._chemin and self._chemin.exists():
            try:
                charge = json.loads(self._chemin.read_text(encoding="utf-8"))
                if isinstance(charge, dict) and isinstance(charge.get("agents"), dict):
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
            self._sale = True
            if time.time() - self._dernier_ecrit >= self._intervalle:
                self._sauver()

    def masquer(self, agent: str, masques: list[dict]) -> None:
        self.ajouter(agent, lecture_filtree=1, messages_masques=len(masques),
                     caracteres_masques=sum(len(str(m.get("text", ""))) for m in masques))

    def vider(self) -> None:
        with self._lock:
            if self._sale:
                self._sauver()

    def _sauver(self) -> None:
        """Sous _lock."""
        self._dernier_ecrit = time.time()
        if not self._chemin:
            self._sale = False
            return
        try:
            tmp = self._chemin.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._etat, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._chemin)
            self._sale = False
        except OSError:
            pass

    def rapport(self) -> dict:
        """Par agent : compteurs + part de lectures « base » (fiche) sur l'ensemble des lectures."""
        self.vider()
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
