"""Livrables et revisions figees par empreintes (SOCLE-SHOP.md S5). 12 octobre 2026.

v1 (12 oct. 2026, claude ; lot reassigne de gemini, dont le lanceur a plante, msg 2118) : contrat de FICHES-LOTS.md v0.1.
- Un livrable est un fichier sous `racine`, identifie par (projet_id, chemin), avec son sha256 et une version.
- « Approuver » relit les octets presents A CET INSTANT, enregistre une nouvelle version si le fichier a change, puis
  fige ces empreintes dans la revision P01, P02… Une revision figee n'est jamais modifiee (critere de codex, msg 2107).
- Un chemin absolu, ou qui sort de la racine une fois resolu (« .. », lien symbolique), est refuse.
"""

import hashlib
import json
import os
import threading
import time
from pathlib import Path


def _sha256(fichier: Path) -> str:
    h = hashlib.sha256()
    with open(fichier, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class RevisionStore:
    def __init__(self, path: str, racine: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._racine = Path(racine).resolve()
        self._lock = threading.Lock()
        self._etat = {"livrables": [], "revisions": []}
        if self._path.exists():
            raw = json.loads(self._path.read_text("utf-8"))  # illisible = ValueError, jamais d'effacement
            if not isinstance(raw, dict) or not isinstance(raw.get("livrables"), list) \
                    or not isinstance(raw.get("revisions"), list):
                raise ValueError(f"{self._path} : forme inattendue")
            self._etat = raw

    def _sauver(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._etat, ensure_ascii=False), "utf-8")
        os.replace(tmp, self._path)

    def _fichier(self, chemin: str) -> Path:
        if not chemin or Path(chemin).is_absolute():
            raise ValueError(f"chemin relatif a la racine attendu : {chemin!r}")
        f = (self._racine / chemin).resolve()
        if not f.is_relative_to(self._racine):
            raise ValueError(f"chemin hors de la racine : {chemin!r}")
        return f

    def resoudre(self, chemin: str) -> Path:
        """Chemin absolu d'un livrable sous la racine, ou ValueError (chemin absolu, « .. » ou lien
        qui sort de la racine une fois resolu). Meme garde-fou que ajouter_livrable/approuver/verifier
        (un seul endroit a durcir), expose pour servir le contenu d'un livrable au visualiseur."""
        return self._fichier(chemin)

    def _derniere(self, projet_id: str, chemin: str) -> dict | None:
        versions = [l for l in self._etat["livrables"] if l["projet_id"] == projet_id and l["chemin"] == chemin]
        return max(versions, key=lambda l: l["version"]) if versions else None

    def _enregistrer(self, projet_id: str, tache_id: str, chemin: str, empreinte: str, t: float) -> dict:
        """Sous _lock. Meme empreinte que la derniere version = l'existant ; sinon version + 1."""
        der = self._derniere(projet_id, chemin)
        if der and der["empreinte"] == empreinte:
            return der
        l = {"id": f"{projet_id}:{chemin}:v{(der['version'] + 1) if der else 1}", "projet_id": projet_id,
             "tache_id": str(tache_id) if tache_id is not None else (der or {}).get("tache_id", ""),
             "chemin": chemin, "empreinte": empreinte, "version": (der["version"] + 1) if der else 1, "heure": t}
        self._etat["livrables"].append(l)
        return l

    def ajouter_livrable(self, projet_id: str, tache_id: str, chemin: str) -> dict:
        f = self._fichier(chemin)
        if not f.is_file():
            raise FileNotFoundError(chemin)
        empreinte = _sha256(f)
        with self._lock:
            l = self._enregistrer(projet_id, tache_id, chemin, empreinte, time.time())
            self._sauver()
            return dict(l)

    def livrables(self, projet_id: str) -> list[dict]:
        with self._lock:
            chemins = sorted({l["chemin"] for l in self._etat["livrables"] if l["projet_id"] == projet_id})
            return [dict(self._derniere(projet_id, c)) for c in chemins]

    def approuver(self, projet_id: str, approuvee_par: str) -> dict:
        with self._lock:
            chemins = sorted({l["chemin"] for l in self._etat["livrables"] if l["projet_id"] == projet_id})
            if not chemins:
                raise ValueError(f"aucun livrable pour {projet_id}")
            t = time.time()
            figes = []
            for c in chemins:
                f = self._fichier(c)
                if not f.is_file():
                    raise FileNotFoundError(c)  # on ne fige pas un livrable disparu
                l = self._enregistrer(projet_id, None, c, _sha256(f), t)
                figes.append({"chemin": c, "empreinte": l["empreinte"], "version": l["version"]})
            n = sum(1 for r in self._etat["revisions"] if r["projet_id"] == projet_id) + 1
            r = {"projet_id": projet_id, "numero": f"P{n:02d}", "livrables": figes,
                 "approuvee_par": approuvee_par, "heure": t}
            self._etat["revisions"].append(r)
            self._sauver()
            return json.loads(json.dumps(r))

    def revisions(self, projet_id: str) -> list[dict]:
        with self._lock:
            return [json.loads(json.dumps(r)) for r in self._etat["revisions"] if r["projet_id"] == projet_id]

    def verifier(self, projet_id: str, numero: str) -> list[dict]:
        with self._lock:
            r = next((r for r in self._etat["revisions"]
                      if r["projet_id"] == projet_id and r["numero"] == numero), None)
            if r is None:
                raise KeyError(numero)
            out = []
            for l in r["livrables"]:
                f = self._fichier(l["chemin"])
                actuelle = _sha256(f) if f.is_file() else None
                out.append({"chemin": l["chemin"], "empreinte_figee": l["empreinte"],
                            "empreinte_actuelle": actuelle, "intact": actuelle == l["empreinte"]})
            return out
