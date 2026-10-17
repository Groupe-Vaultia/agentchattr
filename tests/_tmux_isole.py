"""Isolation tmux des tests : aucun test ne doit parler au serveur tmux réel.

Incident : un test a déjà tapé dans le panneau de l'agent qwencode-1. Lancée
depuis le panneau tmux d'un agent, la suite hérite de TMUX (socket du serveur
réel) et de TMUX_PANE (panneau courant) : toute commande tmux sans -S/-L vise
alors ce serveur, et une commande sans -t vise le panneau de l'agent. TMUX a
priorité sur TMUX_TMPDIR : poser seulement TMUX_TMPDIR ne suffit pas.

isoler() retire TMUX et TMUX_PANE de os.environ et pointe TMUX_TMPDIR vers un
dossier neuf et COURT (un chemin de socket unix est limité à ~100 caractères
et tmux y ajoute « tmux-UID/default »). Les commandes tmux des tests, et
celles de wrapper_unix qui héritent de os.environ, démarrent donc leur propre
serveur jetable, quelle que soit la façon de lancer la suite
(« discover -s tests », « python -m unittest tests.test_x », etc.).

Usage, au niveau du module de test :

    def setUpModule():
        _tmux_isole.isoler()

    def tearDownModule():
        _tmux_isole.restaurer()

ou, pour un bloc : « with _tmux_isole.tmux_isole() as dossier: ... ».

Les appels s'empilent : chaque isoler() a son restaurer(), qui tue le serveur
isolé par son socket explicite (-S ; jamais un « tmux kill-server » nu, qui
viserait le serveur réel si l'isolation avait échoué), efface le dossier et
remet l'environnement d'avant à l'identique.
"""
import contextlib
import os
import shutil
import subprocess
import tempfile

VARIABLES = ("TMUX", "TMUX_PANE", "TMUX_TMPDIR")

# Pile des isolations en cours : (environnement sauvegardé, dossier isolé).
_pile = []


def _uid() -> int:
    return os.getuid() if hasattr(os, "getuid") else 0


def socket_par_defaut(tmpdir: str | None) -> str:
    """Socket du serveur « default » de tmux pour un TMUX_TMPDIR donné."""
    return os.path.join(tmpdir or "/tmp", f"tmux-{_uid()}", "default")


def socket_isole(dossier: str) -> str:
    """Socket du serveur que démarre une commande tmux sous TMUX_TMPDIR=dossier."""
    return socket_par_defaut(dossier)


def isoler() -> str:
    """Retire TMUX/TMUX_PANE et pointe TMUX_TMPDIR vers un dossier court et neuf."""
    sauvegarde = {nom: os.environ.get(nom) for nom in VARIABLES}
    racine = "/tmp" if os.path.isdir("/tmp") else None  # court, sauf Windows
    dossier = tempfile.mkdtemp(prefix="act-", dir=racine)
    os.environ.pop("TMUX", None)
    os.environ.pop("TMUX_PANE", None)
    os.environ["TMUX_TMPDIR"] = dossier
    _pile.append((sauvegarde, dossier))
    return dossier


def restaurer() -> None:
    """Défait le dernier isoler() : serveur isolé tué, dossier effacé, env remis."""
    if not _pile:
        return
    sauvegarde, dossier = _pile.pop()
    socket = socket_isole(dossier)
    if shutil.which("tmux") and os.path.exists(socket):
        subprocess.run(["tmux", "-S", socket, "kill-server"],
                       capture_output=True, timeout=5)
    shutil.rmtree(dossier, ignore_errors=True)
    for nom, valeur in sauvegarde.items():
        if valeur is None:
            os.environ.pop(nom, None)
        else:
            os.environ[nom] = valeur


@contextlib.contextmanager
def tmux_isole():
    dossier = isoler()
    try:
        yield dossier
    finally:
        restaurer()


def exiger_isolement() -> str:
    """Refuse (AssertionError) de continuer si l'environnement n'est pas isolé.

    À appeler avant toute commande tmux réelle : si un jour le setUpModule
    disparaît, le test échoue au lieu de viser le serveur de l'usager.
    """
    if not _pile:
        raise AssertionError("tmux non isolé : appeler _tmux_isole.isoler() d'abord")
    dossier = _pile[-1][1]
    if os.environ.get("TMUX") or os.environ.get("TMUX_PANE"):
        raise AssertionError("tmux non isolé : TMUX/TMUX_PANE encore présents")
    if os.environ.get("TMUX_TMPDIR") != dossier:
        raise AssertionError("tmux non isolé : TMUX_TMPDIR ne pointe pas le dossier isolé")
    return dossier


def sockets_reels() -> list[str]:
    """Sockets des serveurs « réels » d'avant toute isolation (lecture seule).

    Celui que désignait TMUX (le serveur du panneau qui a lancé la suite) et
    le serveur par défaut de l'usager. Sert à vérifier qu'aucune session de
    test n'y apparaît.
    """
    env = _pile[0][0] if _pile else {nom: os.environ.get(nom) for nom in VARIABLES}
    sockets = []
    if env.get("TMUX"):
        sockets.append(env["TMUX"].split(",", 1)[0])
    sockets.append(socket_par_defaut(env.get("TMUX_TMPDIR")))
    return list(dict.fromkeys(s for s in sockets if s))
