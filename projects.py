"""Projets Vaultia : chaque projet porte sa propre memoire (contexte persistant), injectee aux
agents quand il est actif -- comme un projet Claude. 21 septembre 2026.

Un seul projet actif a la fois ; sa memoire est prependee au contexte de chaque agent (le pont API
l'ajoute au system prompt, le wrapper CLI au message de declenchement). Persiste dans projects.json.
"""
from __future__ import annotations
import json, os, threading
from pathlib import Path

_LOCK = threading.Lock()
_FILE: Path | None = None
_state: dict = {"projets": {}, "actif": ""}   # projets: {nom: {"memoire": str, "cree": ts}}


def configurer(fichier: Path) -> None:
    global _FILE
    _FILE = fichier
    _charger()


def _charger() -> None:
    global _state
    if _FILE and _FILE.exists():
        try:
            _state = json.loads(_FILE.read_text("utf-8"))
            _state.setdefault("projets", {})
            _state.setdefault("actif", "")
        except Exception:
            pass


def _sauver() -> None:
    if not _FILE:
        return
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, ensure_ascii=False), "utf-8")
    os.replace(tmp, _FILE)


def lister() -> dict:
    with _LOCK:
        return {"projets": dict(_state["projets"]), "actif": _state["actif"]}


def creer(nom: str, memoire: str = "") -> None:
    import time
    with _LOCK:
        _state["projets"][nom] = {"memoire": memoire, "cree": time.time()}
        if not _state["actif"]:
            _state["actif"] = nom
        _sauver()


def definir_memoire(nom: str, memoire: str) -> bool:
    with _LOCK:
        if nom not in _state["projets"]:
            return False
        _state["projets"][nom]["memoire"] = memoire
        _sauver()
        return True


def activer(nom: str) -> bool:
    with _LOCK:
        if nom and nom not in _state["projets"]:
            return False
        _state["actif"] = nom
        _sauver()
        return True


def supprimer(nom: str) -> None:
    with _LOCK:
        _state["projets"].pop(nom, None)
        if _state["actif"] == nom:
            _state["actif"] = ""
        _sauver()


def memoire_active() -> str:
    with _LOCK:
        nom = _state["actif"]
        if nom and nom in _state["projets"]:
            return _state["projets"][nom].get("memoire", "") or ""
        return ""


def nom_actif() -> str:
    with _LOCK:
        return _state["actif"]
