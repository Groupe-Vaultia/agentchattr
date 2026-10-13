"""Executions et evenements (SOCLE-SHOP.md S3). 12 octobre 2026.

v1 (12 oct. 2026, claude) : une execution = un agent qui travaille sur une tache. Elle porte un uuid, son projet, le
dernier signe de vie et une issue. Sans signe depuis `silence_s` (10 min), elle est `silencieux`, jamais `actif`.
Une fin tardive ou recue en double ne la ressuscite pas, et un signe recu apres la fin est ignore. Les evenements
ne gardent qu'un resume d'une ligne (200 caracteres), jamais de journal brut (R3). La memoire injectee n'est pas
recopiee : on garde son projet et son empreinte sha256, pour prouver laquelle a ete donnee.

v2 (13 oct. 2026, claude) : issue « terminee » ajoutee, posee par le serveur quand l'agent retourne au repos (app.py).
"""

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

SILENCE_S = 600
ISSUES = ("reussie", "echouee", "abandonnee", "terminee")  # terminee : tour fini, non juge (v2)
_MAX_EVENEMENTS = 200


def _ligne(texte: str, n: int = 200) -> str:
    t = " ".join(str(texte or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


class ExecutionStore:
    def __init__(self, path: str, silence_s: float = SILENCE_S):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._silence = silence_s
        self._lock = threading.Lock()
        self._execs: dict[str, dict] = {}
        if self._path.exists():
            raw = json.loads(self._path.read_text("utf-8"))  # illisible = ValueError, jamais d'effacement
            if not isinstance(raw, dict):
                raise ValueError(f"{self._path} : objet attendu")
            self._execs = raw

    def _sauver(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._execs, ensure_ascii=False), "utf-8")
        os.replace(tmp, self._path)

    def _vue(self, e: dict, maintenant: float) -> dict:
        v = {k: val for k, val in e.items() if k != "evenements"}
        if e.get("fin"):
            v["etat"] = "fini"
        elif maintenant - e["dernier_signe"] > self._silence:
            v["etat"] = "silencieux"
        else:
            v["etat"] = "actif"
        v["nb_evenements"] = len(e.get("evenements", []))
        return v

    def demarrer(self, tache_id: int, projet_id: str, agent: str, role: str, consigne: str,
                 memoire_injectee: str = "", maintenant: float | None = None) -> dict:
        t = time.time() if maintenant is None else maintenant
        e = {
            "id": str(uuid.uuid4()), "tache_id": tache_id, "projet_id": projet_id, "agent": agent,
            "role": role, "consigne": _ligne(consigne, 500),
            "memoire_projet_id": projet_id if memoire_injectee else "",
            "memoire_empreinte": hashlib.sha256(memoire_injectee.encode()).hexdigest() if memoire_injectee else "",
            "debut": t, "dernier_signe": t, "fin": None, "issue": "", "evenements": [],
        }
        with self._lock:
            self._execs[e["id"]] = e
            self._sauver()
            return self._vue(e, t)

    def signe(self, exec_id: str, outil: str = "", resume: str = "",
              maintenant: float | None = None) -> dict | None:
        """Signe de vie, avec un evenement si `resume` est donne. Ignore apres la fin. None si inconnue."""
        t = time.time() if maintenant is None else maintenant
        with self._lock:
            e = self._execs.get(exec_id)
            if e is None:
                return None
            if not e.get("fin"):
                e["dernier_signe"] = max(e["dernier_signe"], t)
                if resume:
                    e["evenements"].append({"heure": t, "outil": _ligne(outil, 60), "resume": _ligne(resume)})
                    del e["evenements"][:-_MAX_EVENEMENTS]
                self._sauver()
            return self._vue(e, t)

    def terminer(self, exec_id: str, issue: str, maintenant: float | None = None) -> dict | None:
        """Fin idempotente : la premiere fin compte, une seconde ne change rien."""
        if issue not in ISSUES:
            raise ValueError(f"issue parmi {', '.join(ISSUES)}")
        t = time.time() if maintenant is None else maintenant
        with self._lock:
            e = self._execs.get(exec_id)
            if e is None:
                return None
            if not e.get("fin"):
                e["fin"], e["issue"] = t, issue
                self._sauver()
            return self._vue(e, t)

    def lister(self, projet_id: str | None = None, tache_id: int | None = None,
               maintenant: float | None = None) -> list[dict]:
        t = time.time() if maintenant is None else maintenant
        with self._lock:
            out = [self._vue(e, t) for e in self._execs.values()
                   if (projet_id is None or e["projet_id"] == projet_id)
                   and (tache_id is None or e["tache_id"] == tache_id)]
        return sorted(out, key=lambda v: v["debut"], reverse=True)

    def evenements(self, exec_id: str, limite: int = 50) -> list[dict] | None:
        with self._lock:
            e = self._execs.get(exec_id)
            return None if e is None else [dict(x) for x in e["evenements"][-limite:]]
