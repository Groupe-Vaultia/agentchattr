"""Fichiers CAO d'une piece (lot A1, 14 oct. 2026, claude ; Charles msg 2557).

v1 : liste et sert les sorties de cao/gabarit_piece.py rangees sous <racine>/<numero>/<revision>/ (par defaut
~/atelier/cao-pieces, hors du depot ; VAULTIA_CAO_SORTIE la remplace). Les fichiers restent sur la tour. Seuls les
noms sans separateur, sous une revision valide, avec une extension permise, sont servis, et le chemin resolu doit
rester sous la racine (un lien symbolique vers l'exterieur est refuse).
"""

import os
import re
from pathlib import Path

_NUMERO = re.compile(r"^VLT-\d{5}$")
_REVISION = re.compile(r"^(P(0[1-9]|[1-9][0-9])|[A-HJ-NPRTUVWY]{1,2})$")
TYPES = {".svg": "image/svg+xml", ".pdf": "application/pdf", ".png": "image/png",
         ".step": "application/step", ".stp": "application/step", ".dxf": "image/vnd.dxf",
         ".glb": "model/gltf-binary", ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


def racine() -> Path:
    brut = os.environ.get("VAULTIA_CAO_SORTIE", "").strip()
    return Path(brut).expanduser() if brut else Path.home() / "atelier" / "cao-pieces"


def _dedans(chemin: Path, base: Path) -> bool:
    try:
        chemin.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def lister(numero: str, base: Path | None = None) -> list[dict]:
    """Fichiers servables d'une piece, revision la plus recente d'abord. Numero illisible ou absent = []."""
    base = base or racine()
    if not _NUMERO.match(numero or ""):
        return []
    dossier = base / numero
    if not dossier.is_dir() or not _dedans(dossier, base):
        return []
    out = []
    revs = [d for d in dossier.iterdir() if d.is_dir() and _REVISION.match(d.name) and _dedans(d, base)]
    for rev in sorted(revs, key=lambda d: (not d.name.startswith("P"), len(d.name), d.name), reverse=True):
        for f in sorted(rev.iterdir()):
            ext = f.suffix.lower()
            if f.is_file() and ext in TYPES and _dedans(f, base):
                out.append({"revision": rev.name, "nom": f.name, "type": ext[1:], "octets": f.stat().st_size})
    return out


def chemin(numero: str, revision: str, nom: str, base: Path | None = None) -> Path | None:
    """Chemin d'un fichier servable, ou None (404)."""
    base = base or racine()
    if not _NUMERO.match(numero or "") or not _REVISION.match(revision or ""):
        return None
    if not nom or "/" in nom or "\\" in nom or nom.startswith(".") or Path(nom).suffix.lower() not in TYPES:
        return None
    f = base / numero / revision / nom
    return f if f.is_file() and _dedans(f, base) else None
