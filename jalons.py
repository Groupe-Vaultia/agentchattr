"""Jalons J1/J2 du skill pilote-rd (SOCLE-SHOP.md v1.1, P1). 13 octobre 2026.

v1 (13 oct. 2026, claude) : claude prepare un jalon (resultats, criteres, risques, reste, recommandation et raison) ;
seul Charles le decide (go, recycle, hold, kill). Une decision est definitive. Un seul jalon sans decision par
projet. Les effets sur le statut du projet (hold = veille, kill = arrete) sont appliques par app.py.
"""

import json
import os
import threading
import time
from pathlib import Path

JALONS = ("J1", "J2", "revue")
ISSUES = ("go", "recycle", "hold", "kill")
ETATS_CRITERE = ("atteint", "partiel", "rate", "a_mesurer")
# Etapes qu'un recycle peut viser, par jalon (pilote-rd : J1 suit concepts, J2 suit essais).
RECYCLE = {
    "J1": ("probleme", "etat_art", "concepts", "design_initial"),
    "J2": ("probleme", "etat_art", "concepts", "design_initial", "conception", "prototype", "essais"),
    "revue": ("probleme", "etat_art", "concepts", "design_initial", "conception", "prototype", "essais", "industrialisation"),
}


def _criteres(valeur) -> list[dict] | None:
    if not isinstance(valeur, list):
        return None
    out = []
    for c in valeur:
        if not isinstance(c, dict) or not str(c.get("nom", "")).strip():
            return None
        etat = str(c.get("etat", "a_mesurer"))
        if etat not in ETATS_CRITERE:
            return None
        out.append({"nom": str(c["nom"]).strip(), "cible": str(c.get("cible", "")),
                    "mesure": str(c.get("mesure", "")), "etat": etat})
    return out


class JalonStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jalons: list[dict] = []
        if self._path.exists():
            raw = json.loads(self._path.read_text("utf-8"))  # illisible = ValueError, jamais d'effacement
            if not isinstance(raw, list):
                raise ValueError(f"{self._path} : liste attendue")
            self._jalons = raw

    def _sauver(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._jalons, ensure_ascii=False), "utf-8")
        os.replace(tmp, self._path)

    def lister(self, projet_id: str | None = None) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jalons if projet_id is None or j["projet_id"] == projet_id]

    def get(self, jalon_id: int) -> dict | None:
        with self._lock:
            return next((dict(j) for j in self._jalons if j["id"] == jalon_id), None)

    def preparer(self, projet_id: str, champs: dict) -> tuple[dict | None, str]:
        """Rend (jalon, '') ou (None, erreur). 'en attente' en tete de l'erreur = conflit (409)."""
        jalon = str(champs.get("jalon", ""))
        if jalon not in JALONS:
            return None, f"jalon parmi {', '.join(JALONS)}"
        reco = str(champs.get("recommandation", ""))
        if reco not in ISSUES:
            return None, f"recommandation parmi {', '.join(ISSUES)}"
        raison = str(champs.get("raison", "")).strip()
        if not raison:
            return None, "raison requise"
        crit = _criteres(champs.get("criteres", []))
        if crit is None:
            return None, f"criteres : [{{nom, cible, mesure, etat}}], etat parmi {', '.join(ETATS_CRITERE)}"
        risques = champs.get("risques", [])
        if not isinstance(risques, list) or not all(isinstance(r, str) for r in risques):
            return None, "risques : liste de textes"
        with self._lock:
            if any(j["projet_id"] == projet_id and not j["decision"] for j in self._jalons):
                return None, "en attente : un jalon de ce projet attend deja la decision de Charles"
            j = {"id": max((x["id"] for x in self._jalons), default=0) + 1, "projet_id": projet_id,
                 "jalon": jalon, "date": time.time(), "resultats": str(champs.get("resultats", "")),
                 "criteres": crit, "risques": [r.strip() for r in risques if r.strip()],
                 "reste": str(champs.get("reste", "")), "recommandation": reco, "raison": raison,
                 "decision": "", "decision_date": None, "decision_note": "", "recycle_etape": ""}
            self._jalons.append(j)
            self._sauver()
            return dict(j), ""

    def decider(self, jalon_id: int, decision: str, note: str = "",
                recycle_etape: str = "") -> tuple[dict | None, str]:
        """Rend (jalon, '') ou (None, erreur). 'inconnu' = 404, 'deja' = 409."""
        if decision not in ISSUES:
            return None, f"decision parmi {', '.join(ISSUES)}"
        with self._lock:
            j = next((x for x in self._jalons if x["id"] == jalon_id), None)
            if j is None:
                return None, "inconnu"
            if j["decision"]:
                return None, "deja decide"
            if decision == "recycle":
                if recycle_etape not in RECYCLE[j["jalon"]]:
                    return None, f"recycle_etape parmi {', '.join(RECYCLE[j['jalon']])}"
            else:
                recycle_etape = ""
            j.update(decision=decision, decision_date=time.time(), decision_note=str(note),
                     recycle_etape=recycle_etape)
            self._sauver()
            return dict(j), ""


def pour_historique(jalons: list[dict]) -> list[dict]:
    """Une ligne par preparation et une par decision, dans la forme que lit historique._jalon."""
    out = []
    for j in jalons:
        out.append({"id": f"{j['id']}", "projet_id": j["projet_id"], "date": j["date"], "jalon": j["jalon"],
                    "decision": f"préparé, recommandation {j['recommandation']} : {j['raison']}"})
        if j["decision"]:
            quoi = j["decision"] + (f" vers {j['recycle_etape']}" if j["recycle_etape"] else "")
            note = f" ({j['decision_note']})" if j["decision_note"] else ""
            out.append({"id": f"{j['id']}-d", "projet_id": j["projet_id"], "date": j["decision_date"],
                        "jalon": j["jalon"], "decision": f"décision de Charles : {quoi}{note}"})
    return out
