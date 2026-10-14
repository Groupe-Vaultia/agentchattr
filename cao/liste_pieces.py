"""Liste de pièces ASME v1.0 (14 oct. 2026).

v1.0 : enfants directs de GET /api/v2/pieces/{id}/nomenclature, au-dessus du cartouche.
Pas de prix ni de fournisseur. Lancer :
    freecad.cmd -c "import runpy; runpy.run_path('cao/liste_pieces.py', run_name='__main__')"
"""

import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

import gabarit_piece as gabarit  # noqa: E402

COLONNES = (
    ("repere", "REPÈRE", 22, 16),
    ("qte", "QTÉ", 38, 22),
    ("numero", "NUMÉRO", 60, 42),
    ("rev", "RÉV", 102, 16),
    ("designation", "DÉSIGNATION", 118, 88),
    ("matiere", "MATIÈRE", 206, 50),
)
HAUTEUR = 6.0
BAS = 64.4  # juste au-dessus du cartouche (SVG y = 153,5)
PLAFOND = 200.0
MAX_LIGNES = int((PLAFOND - BAS) / HAUTEUR) - 1

ESSAI = {
    "id": 1,
    "numero": "VLT-10010",
    "revision": "P01",
    "nom": "assemblage-essai",
    "matiere": "",
    "procede": "",
    "quantite": 1.0,
    "quantite_cumulee": 1.0,
    "unite": "u",
    "enfants": [
        {
            "id": 3,
            "numero": "VLT-10011",
            "revision": "P01",
            "nom": "suspension",
            "matiere": "",
            "quantite": 2,
            "quantite_cumulee": 2,
            "unite": "u",
            "prix": 12.5,
            "enfants": [
                {
                    "id": 4,
                    "numero": "VLT-10012",
                    "revision": "A",
                    "nom": "roulement",
                    "matiere": "acier",
                    "quantite": 3,
                    "quantite_cumulee": 6,
                    "unite": "u",
                    "enfants": [],
                }
            ],
        },
        {
            "id": 2,
            "numero": "VLT-10001",
            "revision": "P01",
            "nom": "plaque-gabarit",
            "matiere": "PETG",
            "quantite": 1,
            "quantite_cumulee": 1,
            "unite": "u",
            "enfants": [],
        },
    ],
}


def juger(arbre):
    """Écarts. Les petits-enfants ne sont pas des lignes de cette feuille."""
    if not isinstance(arbre, dict):
        return ["nomenclature illisible"]
    enfants = arbre.get("enfants")
    if not isinstance(enfants, list) or not enfants:
        return ["liste vide"]
    if len(enfants) > MAX_LIGNES:
        return [f"liste trop longue : {len(enfants)}"]
    ecarts = []
    for noeud in enfants:
        if not isinstance(noeud, dict):
            ecarts.append("ligne illisible")
            continue
        numero = str(noeud.get("numero") or "").strip()
        if not numero:
            ecarts.append("numero absent")
            continue
        qte = noeud.get("quantite")
        if isinstance(qte, bool) or not isinstance(qte, (int, float)) or not math.isfinite(float(qte)) or float(qte) <= 0:
            ecarts.append(f"quantite illisible : {numero}")
    return ecarts


def lignes(arbre):
    """Un repère par enfant direct, trié par numéro. Quantité du lien, pas le cumul."""
    ecarts = juger(arbre)
    if ecarts:
        raise ValueError("; ".join(ecarts))
    resultat = []
    for i, noeud in enumerate(sorted(arbre["enfants"], key=lambda n: str(n.get("numero"))), start=1):
        qte = float(noeud["quantite"])
        texte = str(int(qte)) if qte.is_integer() else f"{qte:g}"
        unite = str(noeud.get("unite") or "u")
        if unite != "u":
            texte = f"{texte} {unite}"
        resultat.append({
            "repere": str(i),
            "qte": texte,
            "numero": str(noeud["numero"]).strip(),
            "rev": str(noeud.get("revision") or ""),
            "designation": str(noeud.get("nom") or ""),
            "matiere": str(noeud.get("matiere") or ""),
        })
    return resultat


def lire(url):
    """GET de la nomenclature. Le jeton reste dans VAULTIA_SESSION, jamais dans un fichier."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("url http requise")
    jeton = os.environ.get("VAULTIA_SESSION", "").strip()
    if not jeton:
        raise RuntimeError("jeton absent")
    req = urllib.request.Request(
        url,
        headers={"X-Session-Token": jeton, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as rep:
            corps = rep.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"nomenclature http {exc.code}") from None
    arbre = json.loads(corps)
    if not isinstance(arbre, dict):
        raise RuntimeError("nomenclature illisible")
    return arbre


def _texte(x, y, ligne, ancre="start"):
    return (
        f'<text x="{x:.2f}" y="{gabarit.PAGE_H - y:.2f}" font-size="2.6" '
        f'font-family="sans-serif" text-anchor="{ancre}">{gabarit._xml(ligne)}</text>'
    )


def ecrire_svg(arbre, chemin):
    """Table au-dessus du cartouche. Le repère 1 est le plus près du cartouche."""
    rangs = lignes(arbre)
    svg = gabarit._remplir(gabarit.GABARIT.read_text(encoding="utf-8"), {
        "DrawingTitle1": str(arbre.get("nom") or ""),
        "DrawingTitle2": "LISTE DE PIÈCES",
        "drawing_number": str(arbre.get("numero") or ""),
        "revision_index": str(arbre.get("revision") or ""),
    })
    blocs = []
    droite = COLONNES[-1][2] + COLONNES[-1][3]
    bas = BAS
    haut = BAS + HAUTEUR * (len(rangs) + 1)
    blocs.append(
        f'<rect x="22" y="{gabarit.PAGE_H - haut:.2f}" width="{droite - 22:.2f}" '
        f'height="{haut - bas:.2f}" fill="none" stroke="#000" stroke-width="0.3"/>'
    )
    for i in range(len(rangs) + 2):
        y = bas + HAUTEUR * i
        blocs.append(
            f'<line x1="22" y1="{gabarit.PAGE_H - y:.2f}" x2="{droite:.2f}" '
            f'y2="{gabarit.PAGE_H - y:.2f}" stroke="#000" stroke-width="0.2"/>'
        )
    for _cle, _titre, x, largeur in COLONNES[1:]:
        blocs.append(
            f'<line x1="{x:.2f}" y1="{gabarit.PAGE_H - haut:.2f}" x2="{x:.2f}" '
            f'y2="{gabarit.PAGE_H - bas:.2f}" stroke="#000" stroke-width="0.2"/>'
        )
    for cle, titre, x, _largeur in COLONNES:
        blocs.append(_texte(x + 1.2, bas + 1.8, titre))
        for i, rang in enumerate(rangs):
            blocs.append(_texte(x + 1.2, bas + HAUTEUR * (i + 1) + 1.8, rang[cle]))
    indice = svg.rfind("</svg>")
    chemin.write_text(svg[:indice] + "\n".join(blocs) + "\n" + svg[indice:], encoding="utf-8")
    return rangs


def produire(arbre, dossier):
    ecarts = juger(arbre)
    if ecarts:
        raise ValueError("; ".join(ecarts))
    dossier = Path(dossier) / arbre["numero"] / arbre["revision"]
    dossier.mkdir(parents=True, exist_ok=True)
    nom = f"{arbre['numero']}_{arbre['nom']}_{arbre['revision']}_liste"
    svg = dossier / f"{nom}.svg"
    rangs = ecrire_svg(arbre, svg)
    pdf = gabarit._exporter_pdf(svg, svg.with_suffix(".pdf"))
    return {"lignes": rangs, "svg": str(svg), "pdf": pdf, "ecarts": []}


def essai():
    assert juger({"enfants": []}) == ["liste vide"]
    assert "numero absent" in juger({"enfants": [{"quantite": 1}]})
    assert any(e.startswith("quantite illisible") for e in juger({
        "enfants": [{"numero": "VLT-10001", "quantite": float("nan")}],
    }))
    rangs = lignes(ESSAI)
    assert [r["numero"] for r in rangs] == ["VLT-10001", "VLT-10011"]
    assert rangs[0]["qte"] == "1" and rangs[1]["qte"] == "2"
    ancien = os.environ.pop("VAULTIA_SESSION", None)
    try:
        try:
            lire("http://127.0.0.1/api/v2/pieces/1/nomenclature")
        except RuntimeError as exc:
            assert str(exc) == "jeton absent"
        else:
            raise AssertionError("lire sans jeton")
    finally:
        if ancien is not None:
            os.environ["VAULTIA_SESSION"] = ancien
    assert all("prix" not in r and "12.5" not in "".join(r.values()) for r in rangs)
    assert "VLT-10012" not in {r["numero"] for r in rangs}
    rapport = produire(ESSAI, gabarit.racine_sortie())
    texte = Path(rapport["svg"]).read_text(encoding="utf-8")
    ajouts = texte[texte.rfind("REPÈRE"):]
    assert "VLT-10001" in ajouts and "plaque-gabarit" in ajouts and "PETG" in ajouts
    assert "VLT-10012" not in ajouts and "12.5" not in ajouts
    print(f"svg {rapport['svg']}")
    print(f"pdf {rapport['pdf']}")
    print(f"lignes {rapport['lignes']}")
    print("liste: ok")
    return 0


if __name__ == "__main__":
    sys.exit(essai())
