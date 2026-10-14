"""Contrôles de niveau 1, v1.4 (14 oct. 2026).

v1.3 : tout nombre non fini (NaN, infini) dans le rapport est refusé.
v1.4 : une cote absente ou nulle est refusée.
Aucune géométrie ici : le script FreeCAD mesure, ce module juge.
"""

import math
import re
from pathlib import Path

REQUIS_CARTOUCHE = (
    "CompanyName",
    "drawing_number",
    "revision_index",
    "DrawingTitle1",
    "DrawingTitle2",
    "scale",
    "Weight",
    "Sheet",
)

# Seuils du gabarit, pas une norme. La fiche procédé les remplace.
SEUILS_DFM = {
    "impression_3d": {"epaisseur_min_mm": 1.2},
    "laser": {"trou_min_mm": 1.0},
}


def cartouche(textes, attendu=None):
    ecarts = []
    for cle in REQUIS_CARTOUCHE:
        if not str(textes.get(cle, "")).strip():
            ecarts.append(f"cartouche vide : {cle}")
    for cle, valeur in (attendu or {}).items():
        if str(textes.get(cle, "")) != str(valeur):
            ecarts.append(f"cartouche {cle} : {textes.get(cle)!r} != {valeur!r}")
    return ecarts


def cotes(noms):
    ecarts = []
    if not noms:
        return ["aucune cote"]
    vus = {}
    for nom in noms:
        vus[nom] = vus.get(nom, 0) + 1
    for nom, n in vus.items():
        if n > 1:
            ecarts.append(f"cote en double : {nom}")
    return ecarts


def masse_calculee(volume_mm3, densite_g_mm3, source):
    """La masse n'existe qu'avec une densité et la source de la fiche matière."""
    if densite_g_mm3 is None or not str(source or "").strip():
        return None, False
    return float(volume_mm3) * float(densite_g_mm3), True


def masse(grammes):
    if grammes is None:
        return ["masse absente"]
    try:
        valeur = float(grammes)
    except (TypeError, ValueError):
        return ["masse illisible"]
    if valeur <= 0:
        return ["masse nulle"]
    return []


def interferences(volumes_mm3, seuil=1e-3):
    ecarts = []
    for i, volume in enumerate(volumes_mm3, start=1):
        if volume > seuil:
            ecarts.append(f"interference paire {i} : {volume:.3f} mm3")
    return ecarts


def dfm(procede, mesures):
    seuils = SEUILS_DFM.get(procede)
    if seuils is None:
        return []
    ecarts = []
    for cle, minimum in seuils.items():
        if cle not in mesures:
            ecarts.append(f"dfm : mesure absente ({cle})")
            continue
        if float(mesures[cle]) < minimum:
            ecarts.append(f"dfm : {cle} {mesures[cle]} < {minimum}")
    return ecarts


def cotes_valeurs(mesures, attendu, tolerance=0.05):
    ecarts = []
    for nom, cible in attendu.items():
        valeur = mesures.get(nom)
        if valeur is None:
            ecarts.append(f"cote absente : {nom}")
            continue
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            ecarts.append(f"cote illisible : {nom}")
            continue
        if not math.isfinite(nombre) or nombre == 0.0:
            ecarts.append(f"cote nulle : {nom}")
            continue
        if abs(nombre - float(cible)) > tolerance:
            ecarts.append(f"cote {nom} : {valeur} != {cible}")
    return ecarts


def niveau1(rapport):
    """Solide valide, un volume, un encombrement sur les trois axes."""
    if "brep_valide" not in rapport:
        return []
    ecarts = []
    if rapport.get("brep_valide") is not True:
        ecarts.append("brep invalide")
    if int(rapport.get("solides") or 0) < 1:
        ecarts.append("aucun solide")
    try:
        volume = float(rapport.get("volume_mm3"))
    except (TypeError, ValueError):
        volume = 0.0
    if volume <= 0:
        ecarts.append("volume nul")
    boite = rapport.get("encombrement_mm") or {}
    for axe in ("x", "y", "z"):
        try:
            taille = float(boite.get(axe, 0))
        except (TypeError, ValueError):
            taille = 0.0
        if taille <= 0:
            ecarts.append(f"encombrement {axe} nul")
    return ecarts


def vues_3e_angle(placement):
    """Dessus au-dessus de la face, droite à droite, iso présente."""
    if not placement:
        return []
    ecarts = []
    face = placement.get("face") or {}
    dessus = placement.get("dessus") or {}
    droite = placement.get("droite") or {}
    if float(dessus.get("y", 0)) <= float(face.get("y", 0)):
        ecarts.append("3e angle : dessus pas au-dessus de la face")
    if float(droite.get("x", 0)) <= float(face.get("x", 0)):
        ecarts.append("3e angle : droite pas a droite de la face")
    if "iso" not in placement:
        ecarts.append("isometrique absente")
    return ecarts


def symbole_3e_angle(chemin):
    """Le gabarit ANSI A dessine le cône, puis le cercle à sa droite."""
    texte = Path(chemin).read_text(encoding="utf-8", errors="replace")
    poly = re.search(r'id="polygon5123"[^>]*matrix\(([^)]*)\)', texte)
    cercle = re.search(r'id="circle5127"[^>]*cx="([\d.]+)"', texte)
    if not poly or not cercle:
        return ["symbole 3e angle absent"]
    nombres = [float(x) for x in re.split(r"[\s,]+", poly.group(1).strip()) if x]
    if len(nombres) < 5 or float(cercle.group(1)) <= nombres[4]:
        return ["symbole 3e angle : cercle pas a droite du cone"]
    return []


def empreinte(valeur):
    if not isinstance(valeur, str) or len(valeur) != 64:
        return ["empreinte absente"]
    if any(c not in "0123456789abcdef" for c in valeur):
        return ["empreinte illisible"]
    return []


def step_ap214(schema):
    if schema and "214" in str(schema):
        return []
    return ["step pas AP214"]


def dossier_revision(chemin, numero, revision):
    chemin = Path(chemin)
    if numero not in chemin.parts or revision not in chemin.parts:
        return ["dossier de revision absent"]
    if not chemin.name.startswith(f"{numero}_") or f"_{revision}." not in chemin.name:
        return ["nom de fichier hors regle"]
    return []


def nombres_non_finis(valeur, chemin=""):
    """NaN et infini passent les comparaisons « > 0 ». On les nomme à part."""
    if isinstance(valeur, bool) or valeur is None or isinstance(valeur, str):
        return []
    if isinstance(valeur, (int, float)):
        if not math.isfinite(valeur):
            return [f"nombre non fini : {chemin or 'rapport'}"]
        return []
    if isinstance(valeur, dict):
        ecarts = []
        for cle, item in valeur.items():
            suite = f"{chemin}.{cle}" if chemin else str(cle)
            ecarts += nombres_non_finis(item, suite)
        return ecarts
    if isinstance(valeur, (list, tuple)):
        ecarts = []
        for i, item in enumerate(valeur):
            ecarts += nombres_non_finis(item, f"{chemin}[{i}]")
        return ecarts
    return []


def juger(rapport):
    ecarts = []
    ecarts += nombres_non_finis(rapport)
    ecarts += cartouche(rapport.get("cartouche", {}), rapport.get("cartouche_attendu"))
    ecarts += cotes(rapport.get("cotes", []))
    if "attendu_mm" in rapport:
        ecarts += cotes_valeurs(rapport.get("cotes_mm", {}), rapport["attendu_mm"])
    if rapport.get("fiche_matiere") is False:
        if rapport.get("masse_g") is not None:
            ecarts.append("masse inventee")
    else:
        ecarts += masse(rapport.get("masse_g"))
    ecarts += interferences(rapport.get("interferences_mm3", []))
    ecarts += dfm(rapport.get("procede", ""), rapport.get("mesures", {}))
    ecarts += niveau1(rapport)
    if "vues" in rapport:
        ecarts += vues_3e_angle(rapport["vues"])
    if rapport.get("gabarit_svg"):
        ecarts += symbole_3e_angle(rapport["gabarit_svg"])
    if "empreinte" in rapport:
        ecarts += empreinte(rapport["empreinte"])
    if "step_schema" in rapport:
        ecarts += step_ap214(rapport["step_schema"])
    if rapport.get("fichier") and rapport.get("numero") and rapport.get("revision"):
        ecarts += dossier_revision(
            rapport["fichier"], rapport["numero"], rapport["revision"]
        )
    return ecarts


if __name__ == "__main__":
    bon = juger({
        "cartouche": {cle: "x" for cle in REQUIS_CARTOUCHE},
        "cotes": ["L", "W", "T"],
        "masse_g": 3.0,
        "interferences_mm3": [0.0],
        "procede": "impression_3d",
        "mesures": {"epaisseur_min_mm": 3.0},
    })
    mauvais = juger({
        "cartouche": {"DrawingTitle1": "x"},
        "cotes": ["L", "L"],
        "masse_g": 0,
        "interferences_mm3": [2.0],
        "procede": "impression_3d",
        "mesures": {"epaisseur_min_mm": 0.4},
        "brep_valide": False,
        "solides": 0,
        "volume_mm3": 0,
        "encombrement_mm": {"x": 0, "y": 1, "z": 1},
        "vues": {
            "face": {"x": 80, "y": 90},
            "dessus": {"x": 80, "y": 40},
        },
        "empreinte": "zz",
        "step_schema": "AP203",
        "fichier": "/tmp/plat.FCStd",
        "numero": "VLT-10001",
        "revision": "P01",
    })
    plein = {
        "cartouche": {cle: "x" for cle in REQUIS_CARTOUCHE},
        "cotes": ["L", "W", "T"],
        "masse_g": 2.4,
        "interferences_mm3": [],
        "procede": "impression_3d",
        "mesures": {"epaisseur_min_mm": 3.0},
        "brep_valide": True,
        "solides": 1,
        "volume_mm3": 2400.0,
        "encombrement_mm": {"x": 40.0, "y": 20.0, "z": 3.0},
        "vues": {
            "face": {"x": 80, "y": 90},
            "dessus": {"x": 80, "y": 130},
            "droite": {"x": 150, "y": 90},
            "iso": {"x": 210, "y": 145},
        },
        "empreinte": "ab" * 32,
        "step_schema": "AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }",
        "fichier": "/cao/VLT-10001/P01/VLT-10001_plaque-gabarit_P01.FCStd",
        "numero": "VLT-10001",
        "revision": "P01",
    }
    assert bon == [], bon
    assert juger(plein) == [], juger(plein)
    vide = {
        "cartouche": {cle: "x" for cle in REQUIS_CARTOUCHE},
        "cotes": ["L"],
        "masse_g": None,
        "fiche_matiere": False,
        "interferences_mm3": [],
        "procede": "",
        "mesures": {},
    }
    assert juger(vide) == [], juger(vide)
    vide["masse_g"] = 2.4
    assert "masse inventee" in juger(vide)
    assert masse_calculee(2400, None, "") == (None, False)
    assert masse_calculee(2400, 0.001, "") == (None, False)
    calculee, fiche = masse_calculee(2400, 0.001, "fiche PETG")
    assert fiche is True and abs(calculee - 2.4) < 1e-9
    non_fini = {
        "cartouche": {cle: "x" for cle in REQUIS_CARTOUCHE},
        "cotes": ["L"],
        "masse_g": float("nan"),
        "interferences_mm3": [float("inf")],
        "procede": "",
        "mesures": {"epaisseur_min_mm": float("inf")},
        "brep_valide": True,
        "solides": 1,
        "volume_mm3": float("inf"),
        "encombrement_mm": {"x": 1.0, "y": 1.0, "z": float("-inf")},
    }
    ecarts_finis = juger(non_fini)
    assert any(e == "nombre non fini : masse_g" for e in ecarts_finis), ecarts_finis
    assert any("interferences_mm3" in e for e in ecarts_finis)
    assert any("volume_mm3" in e for e in ecarts_finis)
    assert any("encombrement_mm.z" in e for e in ecarts_finis)
    assert any("epaisseur_min_mm" in e for e in ecarts_finis)
    assert "cote nulle : D" in cotes_valeurs({"D": 0.0}, {"D": 4.0})
    assert "cote absente : E" in cotes_valeurs({}, {"E": 16.0})
    assert any(e.startswith("cartouche vide") for e in mauvais)
    assert any(e.startswith("cote en double") for e in mauvais)
    assert "masse nulle" in mauvais
    assert any(e.startswith("interference") for e in mauvais)
    assert any(e.startswith("dfm") for e in mauvais)
    assert "brep invalide" in mauvais
    assert "volume nul" in mauvais
    assert any(e.startswith("3e angle") for e in mauvais)
    assert any(e.startswith("empreinte") for e in mauvais)
    assert "step pas AP214" in mauvais
    assert any("revision" in e or "fichier" in e for e in mauvais)
    gabarit = Path(
        "/snap/freecad/current/usr/share/Mod/TechDraw/Templates/ASME/"
        "ANSIA_Landscape.svg"
    )
    if gabarit.is_file():
        assert symbole_3e_angle(gabarit) == [], symbole_3e_angle(gabarit)
    print("controles: ok")
