"""Gabarit CAO v2.0 (14 oct. 2026). Cotes TechDraw du trou et de l'entraxe.

v1.4 : sans densité sourcée, masse_g reste vide et le cartouche écrit « ? ».
v2.0 : hors-tout, diamètre et entraxe sont des cotes TechDraw ; 0 ou absente échoue.
Remplacer solide() pour la vraie géométrie. Lancer depuis ce dépôt :
    freecad.cmd -c "import runpy; runpy.run_path('cao/gabarit_piece.py', run_name='__main__')"
"""

import hashlib
import os
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
    "/snap/freecad/current/usr/share/Mod/TechDraw/Templates/ASME/"
    "ANSIA_Landscape.svg"
)
PAGE_H = 215.9

# Pas de masse volumique ici. Elle vient de la fiche matière, avec sa source.
ESSAI = {
    "numero": "VLT-10001",
    "nom": "plaque-gabarit",
    "revision": "P01",
    "matiere": "essai",
    "procede": "impression_3d",
    "L": 40.0,
    "W": 20.0,
    "T": 3.0,
    "D": 4.0,
    "trous": ((12.0, 10.0), (28.0, 10.0)),
    "E": 16.0,
}

NOTE_UNITES = "COTES EN POUCES [MILLIMÈTRES]. LES POUCES GOUVERNENT."

# Centres des vues, mm, origine en bas à gauche. 3e angle : dessus au-dessus,
# droite à droite. L'iso n'est pas cotée.
VUES = {
    "Face": ((0, -1, 0), (1, 0, 0), 80, 90),
    "Dessus": ((0, 0, -1), (1, 0, 0), 80, 130),
    "Droite": ((-1, 0, 0), (0, -1, 0), 150, 90),
    "Iso": ((1, -1, 1), (1, 1, 0), 210, 145),
}


def solide(part, piece):
    """Plaque L x W x T, avec les trous traversants de l'essai."""
    plaque = part.makeBox(piece["L"], piece["W"], piece["T"])
    for x, y in piece.get("trous") or ():
        outil = part.makeCylinder(
            piece["D"] / 2.0, piece["T"] + 2.0, App.Vector(x, y, -1.0)
        )
        plaque = plaque.cut(outil)
    return plaque


def _double_cote(mm):
    """Pouce affiché, mm entre crochets. Le modèle reste en mm."""
    pouces = float(mm) / 25.4
    texte = f"{pouces:.3f}"
    if texte.startswith("0"):
        texte = texte[1:]
    return f"{texte} [{float(mm):.2f}]"


def _textes(piece, masse_g):
    return {
        "CompanyName": "Vaultia",
        "CompanyAddress": "Atelier",
        "DrawingTitle1": piece["nom"],
        "DrawingTitle2": piece["matiere"],
        "DrawingTitle3": piece["procede"],
        "drawing_number": piece["numero"],
        "revision_index": piece["revision"],
        "DrawnBy": "grok",
        "CheckedBy": "-",
        "Approved1": "-",
        "Approved2": "-",
        "scale": "1:1",
        "Code": "-",
        "Weight": "?" if masse_g is None else f"{masse_g:.2f} g",
        "Sheet": "1 DE 1",
    }


def _poser(vues):
    for nom, (_direction, _xdir, x, y) in VUES.items():
        vues[nom].X = x
        vues[nom].Y = y


def _vue(doc, page, feature, nom):
    direction, xdir, _x, _y = VUES[nom]
    obj = doc.addObject("TechDraw::DrawViewPart", nom)
    obj.Source = [feature]
    obj.Direction = App.Vector(*direction)
    obj.XDirection = App.Vector(*xdir)
    obj.Scale = 1
    page.addView(obj)
    return obj


def _cotes(doc, dessus, face, piece):
    """Cotes TechDraw. Pas de cote sur la vue de droite ni sur l'iso.
    Le diamètre est une distance 3D : TechDraw n'a pas de cote de diamètre."""
    (x1, y1), (x2, y2) = piece["trous"]
    rayon = piece["D"] / 2.0
    haut = piece["T"]
    specs = (
        (dessus, "L", "DistanceX", App.Vector(0, 0, 0), App.Vector(piece["L"], 0, 0)),
        (dessus, "W", "DistanceY", App.Vector(0, 0, 0), App.Vector(0, piece["W"], 0)),
        (face, "T", "DistanceY", App.Vector(0, 0, 0), App.Vector(0, 0, haut)),
        (dessus, "D", "Distance", App.Vector(x1 - rayon, y1, haut), App.Vector(x1 + rayon, y1, haut)),
        (dessus, "E", "Distance", App.Vector(x1, y1, haut), App.Vector(x2, y2, haut)),
    )
    mesures = {}
    textes = {}
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
        valeur = float(cote.getRawValue())
        mesures[nom] = valeur
        if hasattr(cote, "Arbitrary"):
            cote.Arbitrary = True
        cote.FormatSpec = _double_cote(valeur)
        doc.recompute()
        textes[nom] = str(cote.getText())
    return mesures, textes


def _volumes_communs(shape):
    """Volume commun des solides de cette pièce. Une pièce seule : aucune paire."""
    solides = list(shape.Solids)
    volumes = []
    for i, gauche in enumerate(solides):
        for droite in solides[i + 1:]:
            volumes.append(gauche.common(droite).Volume)
    return volumes


def _xy(vue):
    return {"x": float(vue.X.Value), "y": float(vue.Y.Value)}


def _maison():
    """Le snap FreeCAD remplace $HOME. cao/ est dans ~/atelier/wt-… ."""
    return ICI.parent.parent.parent


def racine_sortie():
    """Hors du dépôt. VAULTIA_CAO_SORTIE remplace ~/atelier/cao-pieces."""
    brut = os.environ.get("VAULTIA_CAO_SORTIE", "").strip()
    if not brut:
        racine = _maison() / "atelier" / "cao-pieces"
    elif brut.startswith("~/"):
        racine = _maison() / brut[2:]
    else:
        racine = Path(brut)
    racine = racine.resolve()
    depot = ICI.parent.resolve()
    if racine == depot or depot in racine.parents:
        raise RuntimeError(f"sortie dans le dépôt refusée : {racine}")
    return racine


def produire(piece, dossier):
    if App is None:
        raise RuntimeError("lancer avec freecad.cmd, pas python3")
    dossier = dossier / piece["numero"] / piece["revision"]
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
    vues = {nom: _vue(doc, page, feature, nom) for nom in VUES}
    _poser(vues)
    doc.recompute()
    mesures, cotes_texte = _cotes(doc, vues["Dessus"], vues["Face"], piece)
    note = doc.addObject("TechDraw::DrawViewAnnotation", "NoteUnites")
    note.Text = [NOTE_UNITES]
    note.TextSize = 2.5
    page.addView(note)
    note.X = 55
    note.Y = 40
    _poser(vues)

    volume = float(feature.Shape.Volume)
    masse_g, fiche = controles.masse_calculee(
        volume,
        piece.get("masse_volumique_g_mm3"),
        piece.get("masse_volumique_source"),
    )
    textes = _textes(piece, masse_g)
    template.EditableTexts = textes
    doc.recompute()
    _poser(vues)

    chemin = dossier / f"{nom_fichier}.FCStd"
    doc.saveAs(str(chemin))
    step = _exporter_step(feature, dossier / f"{nom_fichier}.step")
    dxf = _exporter_dxf(page, dossier / f"{nom_fichier}.dxf")
    svg = dossier / f"{nom_fichier}.svg"
    _composer_svg(textes, vues, cotes_texte, svg)
    pdf = _exporter_pdf(svg, svg.with_suffix(".pdf"))

    boite = feature.Shape.BoundBox
    rapport = {
        "numero": piece["numero"],
        "revision": piece["revision"],
        "fichier": str(chemin),
        "step": step,
        "step_schema": _schema(dossier / f"{nom_fichier}.step"),
        "pdf": pdf,
        "svg": str(svg),
        "dxf": dxf,
        "gabarit_svg": str(GABARIT),
        "cartouche": {cle: str(valeur) for cle, valeur in template.EditableTexts.items()},
        "cartouche_attendu": textes,
        "cotes": list(mesures),
        "cotes_mm": mesures,
        "cotes_texte": cotes_texte,
        "attendu_mm": {
            "L": piece["L"],
            "W": piece["W"],
            "T": piece["T"],
            "D": piece["D"],
            "E": piece["E"],
        },
        "brep_valide": bool(feature.Shape.isValid()),
        "solides": len(feature.Shape.Solids),
        "volume_mm3": volume,
        "encombrement_mm": {
            "x": float(boite.XLength),
            "y": float(boite.YLength),
            "z": float(boite.ZLength),
        },
        "masse_g": masse_g,
        "fiche_matiere": fiche,
        "masse_volumique_g_mm3": piece.get("masse_volumique_g_mm3"),
        "masse_volumique_source": piece.get("masse_volumique_source") or "",
        "interferences_mm3": _volumes_communs(feature.Shape),
        "procede": piece["procede"],
        "mesures": {"epaisseur_min_mm": piece["T"]},
        "vues": {
            "face": _xy(vues["Face"]),
            "dessus": _xy(vues["Dessus"]),
            "droite": _xy(vues["Droite"]),
            "iso": _xy(vues["Iso"]),
        },
    }
    App.closeDocument(doc.Name)
    rapport["empreinte"] = hashlib.sha256(chemin.read_bytes()).hexdigest()
    rapport["payload"] = {
        "masse_g": rapport["masse_g"],
        "fichier": rapport["fichier"],
        "empreinte": rapport["empreinte"],
    }
    return rapport


def _exporter_step(feature, chemin):
    import Import

    reglage = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Import")
    reglage.SetInt("WriteSchema", 3)
    try:
        Import.export([feature], str(chemin))
    except Exception as exc:
        return f"echec: {exc}"
    return str(chemin) if chemin.is_file() else "echec: fichier absent"


def _schema(chemin):
    if not chemin.is_file():
        return ""
    for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if "FILE_SCHEMA" in ligne:
            return ligne.strip()
    return ""


def _exporter_dxf(page, chemin):
    try:
        TechDraw.writeDXFPage(page, str(chemin))
    except Exception as exc:
        return f"echec: {exc}"
    return str(chemin) if chemin.is_file() else "echec: fichier absent"


def _xml(texte):
    return (str(texte).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _remplir(svg, textes):
    for cle, valeur in textes.items():
        marque = f'freecad:editable="{cle}"'
        debut = svg.find(marque)
        if debut < 0:
            continue
        ouvre = svg.find("<tspan", debut)
        if ouvre < 0:
            continue
        contenu = svg.find(">", ouvre)
        ferme = svg.find("</tspan>", contenu)
        if contenu < 0 or ferme < 0:
            continue
        svg = svg[:contenu + 1] + _xml(valeur) + svg[ferme:]
    return svg


def _composer_svg(textes, vues, cotes_texte, chemin):
    """La page TechDraw ne s'exporte pas en PDF sans fenêtre. On pose les vues
    sur le gabarit ASME, puis l'hôte le convertit."""
    svg = _remplir(GABARIT.read_text(encoding="utf-8"), textes)
    blocs = []
    for nom, (_direction, _xdir, x, y) in VUES.items():
        fragment = TechDraw.viewPartAsSvg(vues[nom])
        blocs.append(
            f'<g transform="translate({x:.2f},{PAGE_H - y:.2f}) scale(1,-1)">{fragment}</g>'
        )
    etiquettes = (
        (80, 148, cotes_texte.get("L", "")),
        (48, 130, cotes_texte.get("W", "")),
        (48, 90, cotes_texte.get("T", "")),
        (112, 136, cotes_texte.get("D", "")),
        (112, 128, cotes_texte.get("E", "")),
        (55, 40, NOTE_UNITES),
    )
    for x, y, ligne in etiquettes:
        if not ligne:
            continue
        blocs.append(
            f'<text x="{x:.2f}" y="{PAGE_H - y:.2f}" font-size="2.5" '
            f'font-family="sans-serif" text-anchor="middle">{_xml(ligne)}</text>'
        )
    indice = svg.rfind("</svg>")
    chemin.write_text(svg[:indice] + "\n".join(blocs) + "\n" + svg[indice:], encoding="utf-8")


def _pdf_qt(svg, chemin):
    """Le snap ne voit pas rsvg-convert. Qt, livré avec FreeCAD, écrit le PDF."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        return False
    writer = QPdfWriter(str(chemin))
    writer.setPageSize(QPageSize(QSizeF(279.4, 215.9), QPageSize.Unit.Millimeter))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    if not painter.isActive():
        return False
    renderer.render(painter)
    painter.end()
    return chemin.is_file() and chemin.stat().st_size > 0


def _exporter_pdf(svg, chemin):
    try:
        if _pdf_qt(svg, chemin):
            return str(chemin)
    except Exception:
        pass
    import subprocess

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


def essai():
    rapport = produire(ESSAI, racine_sortie())
    ecarts = controles.juger(rapport)
    lignes = [
        f"fichier {rapport['fichier']}",
        f"step {rapport['step']}",
        f"step_schema {rapport['step_schema']}",
        f"pdf {rapport['pdf']}",
        f"dxf {rapport['dxf']}",
        f"masse_g {rapport['masse_g']}",
        f"empreinte {rapport['empreinte']}",
        f"cotes {rapport['cotes_mm']}",
        f"cotes_texte {rapport['cotes_texte']}",
        f"brep {rapport['brep_valide']} solides {rapport['solides']} volume {rapport['volume_mm3']}",
        f"encombrement {rapport['encombrement_mm']}",
        f"interferences {rapport['interferences_mm3']}",
        f"vues {rapport['vues']}",
        f"payload {rapport['payload']}",
    ]
    if ecarts:
        lignes.append("ecarts")
        lignes.extend(f"- {ecart}" for ecart in ecarts)
        code = 1
    else:
        lignes.append("gabarit: ok")
        code = 0
    sortie = Path(rapport["fichier"]).parent / "resultat.txt"
    sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(essai())
