"""Historique d'un projet, en lecture seule.

Fonction pure : elle fusionne les listes que les autres modules rendent.
Aucun stockage, aucun import hors de la bibliothèque standard.
Contrat : FICHES-LOTS.md v0.1.
"""

import time

_TYPES = ("message", "execution", "revision", "jalon", "decision")
_LIMITE_RESUME = 200


def _nombre(valeur):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return None
    return float(valeur)


def _texte(valeur):
    if not isinstance(valeur, str):
        return None
    return valeur


def _resume(texte):
    une_ligne = texte.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if len(une_ligne) <= _LIMITE_RESUME:
        return une_ligne
    return une_ligne[: _LIMITE_RESUME - 1] + "…"


def _ligne(heure, type_, ref, acteur, resume):
    return {
        "heure": heure,
        "type": type_,
        "ref": ref,
        "acteur": acteur,
        "resume": _resume(resume),
    }


def _projet(entree, projet_id):
    if not isinstance(entree, dict):
        return False
    return entree.get("projet_id") == projet_id


def _message(entree):
    heure = _nombre(entree.get("timestamp"))
    ident = _texte(entree.get("id"))
    acteur = _texte(entree.get("sender"))
    texte = _texte(entree.get("text"))
    if heure is None or ident is None or acteur is None or texte is None:
        return None
    return _ligne(heure, "message", ident, acteur, texte)


def _execution(entree):
    ident = _texte(entree.get("id"))
    acteur = _texte(entree.get("agent"))
    consigne = _texte(entree.get("consigne"))
    fin = _nombre(entree.get("fin"))
    debut = _nombre(entree.get("debut"))
    heure = fin if fin is not None else debut
    if heure is None or ident is None or acteur is None or consigne is None:
        return None
    return _ligne(heure, "execution", ident, acteur, consigne)


def _revision(entree):
    heure = _nombre(entree.get("heure"))
    numero = _texte(entree.get("numero"))
    acteur = _texte(entree.get("approuvee_par"))
    livrables = entree.get("livrables")
    if heure is None or numero is None or acteur is None or not isinstance(livrables, list):
        return None
    n = len(livrables)
    mot = "livrable" if n == 1 else "livrables"
    return _ligne(heure, "revision", numero, acteur, f"{numero} approuvée, {n} {mot}")


def _jalon(entree):
    heure = _nombre(entree.get("date"))
    ident = _texte(entree.get("id"))
    jalon = _texte(entree.get("jalon"))
    if "decision" in entree:
        decision = entree.get("decision")
        if decision is None:
            decision = ""
        if not isinstance(decision, str):
            return None
    else:
        decision = ""
    if heure is None or ident is None or jalon is None:
        return None
    resume = f"{jalon} en attente" if decision == "" else f"{jalon} : {decision}"
    return _ligne(heure, "jalon", ident, "", resume)


def _decision(entree):
    heure = _nombre(entree.get("heure"))
    ident = _texte(entree.get("id"))
    acteur = _texte(entree.get("acteur"))
    quoi = _texte(entree.get("quoi"))
    if heure is None or ident is None or acteur is None or quoi is None:
        return None
    return _ligne(heure, "decision", ident, acteur, quoi)


_LECTEURS = {
    "message": _message,
    "execution": _execution,
    "revision": _revision,
    "jalon": _jalon,
    "decision": _decision,
}


def historique(
    projet_id,
    *,
    messages=(),
    executions=(),
    revisions=(),
    jalons=(),
    decisions=(),
    limite=200,
):
    """Fusionne les listes d'un projet, du plus récent au plus ancien."""
    if not isinstance(projet_id, str):
        return []
    if isinstance(limite, bool) or not isinstance(limite, int):
        limite = 200
    if limite < 0:
        limite = 0
    sources = (
        ("message", messages),
        ("execution", executions),
        ("revision", revisions),
        ("jalon", jalons),
        ("decision", decisions),
    )
    lignes = []
    for type_, suite in sources:
        if not isinstance(suite, (list, tuple)):
            continue
        lire = _LECTEURS[type_]
        for entree in suite:
            if not _projet(entree, projet_id):
                continue
            ligne = lire(entree)
            if ligne is not None and ligne["type"] in _TYPES:
                lignes.append(ligne)
    lignes.sort(key=lambda ligne: ligne["heure"], reverse=True)
    return lignes[:limite]


def par_jour(entrees):
    """Regroupe par date locale AAAA-MM-JJ, jours du plus récent au plus ancien."""
    if not isinstance(entrees, list):
        return []
    groupes = {}
    for entree in entrees:
        if not isinstance(entree, dict):
            continue
        heure = _nombre(entree.get("heure"))
        if heure is None:
            continue
        jour = time.strftime("%Y-%m-%d", time.localtime(heure))
        groupes.setdefault(jour, []).append(entree)
    return [(jour, groupes[jour]) for jour in sorted(groupes, reverse=True)]


def _essai():
    projet = "sx1"
    long = "a" * 205
    lignes = historique(
        projet,
        messages=[
            {"id": "m1", "projet_id": projet, "sender": "charles", "text": "bonjour\nmonde", "timestamp": 100.0},
            {"id": "m2", "projet_id": "autre", "sender": "x", "text": "hors projet", "timestamp": 999.0},
            {"sender": "x", "text": "sans id", "timestamp": 50.0, "projet_id": projet},
            {"id": "m3", "projet_id": projet, "sender": "claude", "text": long, "timestamp": 300},
            "pas-un-dict",
        ],
        executions=[
            {"id": "e1", "projet_id": projet, "agent": "qwen", "role": "producteur",
             "consigne": "trancher", "debut": 10.0, "fin": 20.0, "issue": "ok"},
            {"id": "e2", "projet_id": projet, "agent": "qwen", "consigne": "reprendre", "debut": 40.0},
        ],
        revisions=[
            {"projet_id": projet, "numero": "P01", "approuvee_par": "charles",
             "heure": 200.0, "livrables": [{}, {}, {}]},
        ],
        jalons=[
            {"id": "j1", "projet_id": projet, "jalon": "J1", "decision": "", "date": 150.0},
        ],
        decisions=[
            {"id": "d1", "projet_id": projet, "acteur": "claude", "quoi": "mise en veille", "heure": 20.0},
        ],
        limite=4,
    )
    assert [ligne["ref"] for ligne in lignes] == ["m3", "P01", "j1", "m1"], lignes
    assert lignes[0]["resume"] == ("a" * 199) + "…"
    assert lignes[3]["resume"] == "bonjour monde"
    assert lignes[1]["resume"] == "P01 approuvée, 3 livrables"
    assert lignes[2]["resume"] == "J1 en attente"
    assert all(ligne["type"] in _TYPES for ligne in lignes)
    jours = par_jour(historique(
        projet,
        messages=[
            {"id": "a", "projet_id": projet, "sender": "c", "text": "récent", "timestamp": 1_700_000_000.0},
            {"id": "b", "projet_id": projet, "sender": "c", "text": "ancien", "timestamp": 1_600_000_000.0},
        ],
    ))
    assert len(jours) == 2, jours
    assert jours[0][0] > jours[1][0]
    assert jours[0][1][0]["ref"] == "a"
    assert historique(projet, messages=None, limite=-3) == []
    assert historique(12, messages=[{"id": "a", "projet_id": "12", "sender": "c", "text": "x", "timestamp": 1}]) == []
    print("historique: ok")


if __name__ == "__main__":
    _essai()
