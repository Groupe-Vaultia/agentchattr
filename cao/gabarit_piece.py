"""Gabarit N2b v1.0 (13 oct. 2026). Une pièce, un processus freecad.cmd.

Remplacer solide() pour la vraie géométrie. Le fichier, le plan et les
contrôles restent. Lancer depuis ce dépôt :
    freecad.cmd -c "import runpy; runpy.run_path('cao/gabarit_piece.py', run_name='__main__')"
Le snap ne voit pas rsvg-convert. Le PDF se finit sur l'hôte :
    /usr/bin/rsvg-convert -f pdf -o cao/sortie/VLT-10001_plaque-gabarit_P01.pdf cao/sortie/VLT-10001_plaque-gabarit_P01.svg
"""

import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

import controles  # noqa: E402

try:
    import FreeCAD as App
    import Part
    import TechDraw
except ImportError:
    App = Part = TechDraw = None

GABARIT = Path(
    "/snap/freecad/current/usr/share/Mod/TechDraw/Templates/ISO/"
    "A4_Landscape_ISO5457_advanced.svg"
)

# Valeur d'essai seulement. Une vraie pièce cite la fiche matière.
ESSAI = {
    "numero": "VLT-10001",
    "nom": "plaque-gabarit",
    "revision": "P01",
    "matiere": "essai",
    "procede": "impression_3d",
    "masse_volumique_g_mm3": 0.001,
    "L": 40.0,
    "W": 20.0,
    "T": 3.0,
}


def solide(part, piece):
    """Plaque L x W x T. A remplacer par la pièce."""
    return part.makeBox(piece["L"], piece["W"], piece["T"])


def _cartouche(template, piece):
    template.EditableTexts = {
        "drawing_number": piece["numero"],
        "revision_index": piece["revision"],
        "title": piece["nom"],
        "part_material": piece["matiere"],
        "supplementary_title_1": piece["procede"],
    }


def _cotes(doc, dessus, face, piece):
    """Trois cotes 3D. DistanceZ n'existe pas : T est lu sur la vue de face."""
    specs = (
        (dessus, "L", "DistanceX", App.Vector(0, 0, 0), App.Vector(piece["L"], 0, 0)),
        (dessus, "W", "DistanceY", App.Vector(0, 0, 0), App.Vector(0, piece["W"], 0)),
        (face, "T", "DistanceY", App.Vector(0, 0, 0), App.Vector(0, 0, piece["T"])),
    )
    mesures = {}
    for vue, nom, genre, debut, fin in specs:
        avant = {o.Name for o in doc.Objects}
        cote = TechDraw.makeDistanceDim3d(vue, genre, debut, fin)
        doc.recompute()
        if cote is None:
            nouveaux = [o for o in doc.Objects if o.Name not in avant
                        and o.TypeId == "TechDraw::DrawViewDimension"]
            cote = nouveaux[-1] if nouveaux else None
        if cote is None:
            mesures[nom] = None
            continue
        cote.Label = nom
        doc.recompute()
        mesures[nom] = float(cote.getRawValue())
    return mesures


def produire(piece, dossier):
    if App is None:
        raise RuntimeError("lancer avec freecad.cmd, pas python3")
    dossier.mkdir(parents=True, exist_ok=True)
    nom_fichier = f"{piece['numero']}_{piece['nom']}_{piece['revision']}"
    doc = App.newDocument(nom_fichier)
    feature = doc.addObject("Part::Feature", "Solide")
    feature.Shape = solide(Part, piece)
    doc.recompute()

    page = doc.addObject("TechDraw::DrawPage", "Page")
    template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    template.Template = str(GABARIT)
    page.Template = template
    _cartouche(template, piece)

    dessus = doc.addObject("TechDraw::DrawViewPart", "Dessus")
    dessus.Source = [feature]
    dessus.Direction = App.Vector(0, 0, 1)
    page.addView(dessus)
    face = doc.addObject("TechDraw::DrawViewPart", "Face")
    face.Source = [feature]
    face.Direction = App.Vector(0, -1, 0)
    face.X = 180
    page.addView(face)
    doc.recompute()
    mesures = _cotes(doc, dessus, face, piece)
    doc.recompute()

    chemin = dossier / f"{nom_fichier}.FCStd"
    doc.saveAs(str(chemin))
    pdf = _exporter_pdf(feature, piece, dossier / f"{nom_fichier}.pdf")
    dxf = _exporter_dxf(page, dossier / f"{nom_fichier}.dxf")

    volume = feature.Shape.Volume
    rapport = {
        "fichier": str(chemin),
        "pdf": pdf,
        "dxf": dxf,
        "cartouche": dict(template.EditableTexts),
        "cartouche_attendu": {
            "drawing_number": piece["numero"],
            "revision_index": piece["revision"],
            "title": piece["nom"],
            "part_material": piece["matiere"],
            "supplementary_title_1": piece["procede"],
        },
        "cotes": list(mesures),
        "cotes_mm": mesures,
        "attendu_mm": {"L": piece["L"], "W": piece["W"], "T": piece["T"]},
        "masse_g": volume * float(piece["masse_volumique_g_mm3"]),
        "interferences_mm3": _paires(piece),
        "procede": piece["procede"],
        "mesures": {"epaisseur_min_mm": piece["T"]},
    }
    App.closeDocument(doc.Name)
    return rapport


def _paires(piece):
    """Deux boîtes écartées : volume commun nul. Le contrôle sait échouer."""
    import Part

    import FreeCAD as App

    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(10, 10, 10)
    b.translate(App.Vector(30, 0, 0))
    return [a.common(b).Volume]


def _exporter_pdf(feature, piece, chemin):
    """TechDrawGui ne charge pas sans fenêtre. Le PDF vient du SVG projeté."""
    import subprocess

    projection = TechDraw.projectToSVG(feature.Shape)
    svg = chemin.with_suffix(".svg")
    svg.write_text(
        "\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">',
            f'<text x="12" y="16" font-size="4">{piece["numero"]} {piece["revision"]}</text>',
            f'<text x="12" y="22" font-size="3">{piece["nom"]} — {piece["matiere"]} — {piece["procede"]}</text>',
            '<g transform="translate(40,120) scale(1,-1)">',
            projection,
            "</g></svg>",
        ]),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["/usr/bin/rsvg-convert", "-f", "pdf", "-o", str(chemin), str(svg)],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        if svg.is_file():
            return (
                f"svg pret ({svg}) ; pdf hors du snap : "
                f"/usr/bin/rsvg-convert -f pdf -o {chemin} {svg}"
            )
        return "echec: svg absent"
    return str(chemin) if chemin.is_file() else "echec: fichier absent"


def _exporter_dxf(page, chemin):
    try:
        import TechDraw
        TechDraw.writeDXFPage(page, str(chemin))
    except Exception as exc:
        return f"echec: {exc}"
    return str(chemin) if chemin.is_file() else "echec: fichier absent"


def essai():
    dossier = ICI / "sortie"
    rapport = produire(ESSAI, dossier)
    ecarts = controles.juger(rapport)
    print("fichier", rapport["fichier"])
    print("pdf", rapport["pdf"])
    print("dxf", rapport["dxf"])
    lignes = [
        f"fichier {rapport['fichier']}",
        f"pdf {rapport['pdf']}",
        f"dxf {rapport['dxf']}",
        f"masse_g {rapport['masse_g']}",
        f"cotes {rapport['cotes_mm']}",
    ]
    if ecarts:
        lignes.append("ecarts")
        lignes.extend(f"- {ecart}" for ecart in ecarts)
        code = 1
    else:
        lignes.append("gabarit: ok")
        code = 0
    (dossier / "resultat.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(essai())
