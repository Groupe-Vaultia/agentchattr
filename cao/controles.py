"""Contrôles de niveau 1, v1.0 (13 oct. 2026).

Cotes, cartouche, interférences, masse, DFM. Aucune géométrie ici :
le script FreeCAD mesure, ce module juge.
"""

REQUIS_CARTOUCHE = (
    "drawing_number",
    "revision_index",
    "title",
    "part_material",
    "supplementary_title_1",
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
            ecarts.append(f"cote illisible : {nom}")
        elif abs(float(valeur) - float(cible)) > tolerance:
            ecarts.append(f"cote {nom} : {valeur} != {cible}")
    return ecarts


def juger(rapport):
    ecarts = []
    ecarts += cartouche(rapport.get("cartouche", {}), rapport.get("cartouche_attendu"))
    ecarts += cotes(rapport.get("cotes", []))
    if "attendu_mm" in rapport:
        ecarts += cotes_valeurs(rapport.get("cotes_mm", {}), rapport["attendu_mm"])
    ecarts += masse(rapport.get("masse_g"))
    ecarts += interferences(rapport.get("interferences_mm3", []))
    ecarts += dfm(rapport.get("procede", ""), rapport.get("mesures", {}))
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
        "cartouche": {"title": "x"},
        "cotes": ["L", "L"],
        "masse_g": 0,
        "interferences_mm3": [2.0],
        "procede": "impression_3d",
        "mesures": {"epaisseur_min_mm": 0.4},
    })
    assert bon == [], bon
    assert any(e.startswith("cartouche vide") for e in mauvais)
    assert any(e.startswith("cote en double") for e in mauvais)
    assert "masse nulle" in mauvais
    assert any(e.startswith("interference") for e in mauvais)
    assert any(e.startswith("dfm") for e in mauvais)
    print("controles: ok")
