"""Projets Vaultia : chaque projet porte sa propre memoire (contexte persistant). 21 septembre 2026.

v2 (12 octobre 2026, socle de la Shop, SOCLE-SHOP.md S1) : plusieurs projets actifs a la fois.
- Chaque projet a un identifiant stable (slug du nom a la creation) ; le nom peut changer.
- La memoire injectee a un agent est celle du projet de SON declenchement (projet_id porte par le
  message et la file), jamais celle d'un projet « actif » global. `defaut` (l'ancien `actif`) ne sert
  plus qu'a l'affichage des anciens clients.
- Le fichier v1 ({"projets": {nom: ...}, "actif": nom}) est migre au premier chargement ; l'original est
  garde en projects.v1.json. L'API v1 (projets indexes par nom, `actif`) reste servie par lister().
- Routes v1 : le nom exact passe avant l'identifiant ; creer() ne cherche que le nom exact (revue codex e49c86e).
"""
from __future__ import annotations
import json, os, re, threading, time, unicodedata
from pathlib import Path

_LOCK = threading.Lock()
_FILE: Path | None = None
# Jalons du skill pilote-rd : Go = actif, Hold = veille, Kill = arrete, livre = termine.
STATUTS = ("actif", "veille", "arrete", "termine")
_state: dict = {"version": 2, "projets": {}, "defaut": ""}


def slug(nom: str) -> str:
    s = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "projet"


def _slug_libre(nom: str, pris) -> str:
    base = slug(nom)
    pid, n = base, 1
    while pid in pris:
        n += 1
        pid = f"{base}-{n}"
    return pid


def _projet(nom: str, memoire: str = "", cree: float | None = None, channels=None) -> dict:
    t = cree if cree is not None else time.time()
    return {"nom": nom, "objectif": "", "livrable_attendu": "", "statut": "actif",
            "memoire": memoire or "", "cree": t, "maj": t, "channels": list(channels or [])}


def _migrer(v1: dict) -> dict:
    projets, ids_par_nom = {}, {}
    for nom, p in (v1.get("projets") or {}).items():
        pid = _slug_libre(nom, projets)
        p = p if isinstance(p, dict) else {}
        projets[pid] = _projet(nom, p.get("memoire", ""), p.get("cree"), p.get("channels"))
        ids_par_nom[nom] = pid
    return {"version": 2, "projets": projets, "defaut": ids_par_nom.get(v1.get("actif", ""), "")}


def configurer(fichier: Path) -> None:
    global _FILE
    _FILE = Path(fichier)
    _charger()


def _charger() -> None:
    global _state
    if not (_FILE and _FILE.exists()):
        _state = {"version": 2, "projets": {}, "defaut": ""}
        return
    try:
        brut = _FILE.read_text("utf-8")
        data = json.loads(brut)
    except Exception:
        return
    if data.get("version") == 2:
        data.setdefault("projets", {})
        data.setdefault("defaut", "")
        _state = data
        return
    sauvegarde = _FILE.with_name(_FILE.stem + ".v1.json")
    if not sauvegarde.exists():
        sauvegarde.write_text(brut, "utf-8")
    _state = _migrer(data)
    _sauver()


def _sauver() -> None:
    if not _FILE:
        return
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, ensure_ascii=False), "utf-8")
    os.replace(tmp, _FILE)


def _par_nom(nom: str) -> str:
    """Nom exact -> identifiant ; '' si aucun. Appeler sous _LOCK."""
    for pid, p in _state["projets"].items():
        if p.get("nom") == nom:
            return pid
    return ""


def _resoudre(cle: str) -> str:
    """Nom exact (routes v1) d'abord, puis identifiant ; '' si inconnu. Appeler sous _LOCK.

    Le nom passe avant l'identifiant : apres migration, `Café` a l'ID `cafe`, et un autre projet
    peut s'appeler exactement `cafe` ; la route v1 /api/projects/cafe vise alors ce dernier."""
    if not cle:
        return ""
    return _par_nom(cle) or (cle if cle in _state["projets"] else "")


def lister() -> dict:
    """Forme v1 (indexee par nom, `actif`) pour les anciens clients, plus la forme v2 complete."""
    with _LOCK:
        par_nom = {p["nom"]: {"memoire": p.get("memoire", ""), "cree": p.get("cree"),
                              "channels": list(p.get("channels", [])), "id": pid,
                              "statut": p.get("statut", "actif")}
                   for pid, p in _state["projets"].items()}
        d = _state["defaut"]
        actif = _state["projets"][d]["nom"] if d in _state["projets"] else ""
        v2 = {"projets": json.loads(json.dumps(_state["projets"])), "defaut": d}
        return {"projets": par_nom, "actif": actif, "v2": v2}


def creer(nom: str, memoire: str = "") -> str:
    """Cree le projet (ou met a jour la memoire d'un projet de meme nom) ; rend son identifiant."""
    with _LOCK:
        pid = _par_nom(nom)
        if pid:
            _state["projets"][pid]["memoire"] = memoire
            _state["projets"][pid]["maj"] = time.time()
        else:
            pid = _slug_libre(nom, _state["projets"])
            _state["projets"][pid] = _projet(nom, memoire)
        if not _state["defaut"]:
            _state["defaut"] = pid
        _sauver()
        return pid


def definir_memoire(cle: str, memoire: str) -> bool:
    with _LOCK:
        pid = _resoudre(cle)
        if not pid:
            return False
        _state["projets"][pid]["memoire"] = memoire
        _state["projets"][pid]["maj"] = time.time()
        _sauver()
        return True


def definir_statut(cle: str, statut: str) -> bool:
    if statut not in STATUTS:
        return False
    with _LOCK:
        pid = _resoudre(cle)
        if not pid:
            return False
        _state["projets"][pid]["statut"] = statut
        _state["projets"][pid]["maj"] = time.time()
        _sauver()
        return True


def activer(cle: str) -> bool:
    """Route v1 : choisit le projet par defaut (affichage seulement, n'injecte plus de memoire)."""
    with _LOCK:
        pid = _resoudre(cle)
        if cle and not pid:
            return False
        _state["defaut"] = pid
        _sauver()
        return True


def supprimer(cle: str) -> None:
    with _LOCK:
        pid = _resoudre(cle)
        if not pid:
            return
        _state["projets"].pop(pid, None)
        if _state["defaut"] == pid:
            _state["defaut"] = ""
        _sauver()


def assigner_canal(canal: str, projet: str) -> bool:
    """Rattache un canal a un projet ; projet vide = le detacher. Un canal n'appartient qu'a un projet."""
    with _LOCK:
        pid = _resoudre(projet)
        if projet and not pid:
            return False
        for autre, p in _state["projets"].items():
            p.setdefault("channels", [])
            if canal in p["channels"] and autre != pid:
                p["channels"].remove(canal)
        if pid:
            ch = _state["projets"][pid].setdefault("channels", [])
            if canal not in ch:
                ch.append(canal)
        _sauver()
        return True


def existe(pid: str) -> bool:
    with _LOCK:
        return pid in _state["projets"]


def memoire_projet(pid: str) -> dict | None:
    """{"projet_id", "nom", "statut", "memoire"} du projet, ou None s'il est inconnu (pas de repli)."""
    with _LOCK:
        p = _state["projets"].get(pid)
        if p is None:
            return None
        return {"projet_id": pid, "nom": p["nom"], "statut": p.get("statut", "actif"),
                "memoire": p.get("memoire", "") or ""}


def projet_du_canal(canal: str) -> str:
    """Le projet auquel un canal d'avant la Shop est rattache, ou '' (aucune memoire)."""
    with _LOCK:
        for pid, p in _state["projets"].items():
            if canal in p.get("channels", []):
                return pid
        return ""


def memoire_active() -> str:
    """Conserve pour compatibilite : `defaut` n'injecte plus de memoire (SOCLE-SHOP v0.3)."""
    return ""


def nom_actif() -> str:
    with _LOCK:
        d = _state["defaut"]
        return _state["projets"][d]["nom"] if d in _state["projets"] else ""
