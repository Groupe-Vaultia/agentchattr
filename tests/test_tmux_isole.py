"""Preuve de l'isolation tmux des tests (tests/_tmux_isole.py).

Scénario de l'incident (un test a tapé dans le panneau de qwencode-1) : la
suite est lancée dans le panneau tmux d'un agent, donc TMUX désigne le serveur
réel. On ne crée RIEN sur le serveur réel de l'usager : on démarre un serveur
« réel » de leurre sur un socket explicite (-S), on fait pointer TMUX dessus
comme dans un panneau d'agent, on constate que tmux le suit bien sans
isolation (TMUX a priorité sur TMUX_TMPDIR), puis on isole et on crée une
session de test. Elle doit exister sur le serveur isolé et nulle part
ailleurs : ni sur le leurre, ni sur les serveurs réels d'avant l'isolation
(consultés en lecture seule, list-sessions).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)

import _tmux_isole  # noqa: E402

HAVE_TMUX = shutil.which("tmux") is not None


def setUpModule():
    _tmux_isole.isoler()


def tearDownModule():
    _tmux_isole.restaurer()


def _sessions(socket: str) -> list[str]:
    """Sessions du serveur désigné par son socket ([] s'il ne tourne pas)."""
    if not os.path.exists(socket):
        return []
    result = subprocess.run(
        ["tmux", "-S", socket, "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.split() if result.returncode == 0 else []


class IsolementEnvironnementTests(unittest.TestCase):
    """Ce que setUpModule garantit, sans démarrer de serveur."""

    def test_module_isole_quel_que_soit_le_lancement(self):
        dossier = _tmux_isole.exiger_isolement()
        self.assertNotIn("TMUX", os.environ)
        self.assertNotIn("TMUX_PANE", os.environ)
        self.assertEqual(os.environ["TMUX_TMPDIR"], dossier)
        self.assertLess(len(_tmux_isole.socket_isole(dossier)), 100,
                        "un socket unix est limité à ~100 caractères")

    def test_restaurer_remet_l_environnement_a_l_identique(self):
        avant = {nom: os.environ.get(nom) for nom in _tmux_isole.VARIABLES}
        with mock.patch.dict(os.environ, {"TMUX": "/x/y,1,0", "TMUX_PANE": "%3"}):
            with _tmux_isole.tmux_isole() as dossier:
                self.assertNotIn("TMUX", os.environ)
                self.assertNotIn("TMUX_PANE", os.environ)
                self.assertTrue(os.path.isdir(dossier))
            self.assertEqual(os.environ["TMUX"], "/x/y,1,0")
            self.assertEqual(os.environ["TMUX_PANE"], "%3")
            self.assertFalse(os.path.exists(dossier), "dossier isolé effacé")
        self.assertEqual({nom: os.environ.get(nom) for nom in _tmux_isole.VARIABLES}, avant)

    def test_garde_fou_refuse_un_TMUX_herite(self):
        with mock.patch.dict(os.environ, {"TMUX": "/x/y,1,0"}):
            with self.assertRaises(AssertionError):
                _tmux_isole.exiger_isolement()


@unittest.skipIf(sys.platform == "win32", "tmux est propre à Mac/Linux")
@unittest.skipUnless(HAVE_TMUX, "tmux not installed")
class IsolementServeurReelTests(unittest.TestCase):
    """Vrai tmux : la session de test ne quitte jamais le serveur isolé."""

    def test_session_de_test_sur_serveur_isole_malgre_TMUX_reel(self):
        _tmux_isole.exiger_isolement()
        # 1. Serveur « réel » de leurre, sur un socket explicite et court.
        leurre_dir = tempfile.mkdtemp(prefix="act-l-", dir="/tmp")
        self.addCleanup(shutil.rmtree, leurre_dir, ignore_errors=True)
        leurre = os.path.join(leurre_dir, "s")
        cree = subprocess.run(
            ["tmux", "-S", leurre, "new-session", "-d", "-s", "agentchattr-leurre", "sleep 120"],
            capture_output=True, timeout=10,
        )
        self.assertEqual(cree.returncode, 0, cree.stderr)
        self.addCleanup(subprocess.run, ["tmux", "-S", leurre, "kill-server"],
                        capture_output=True, timeout=5)
        pid = subprocess.run(
            ["tmux", "-S", leurre, "display-message", "-p", "-t", "agentchattr-leurre", "#{pid}"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        self.assertTrue(pid.isdigit(), pid)
        tmux_agent = f"{leurre},{pid},0"
        session = f"agentchattr-test-isole-{os.getpid()}"

        # 2. Comme dans un panneau d'agent : TMUX et TMUX_PANE désignent ce serveur.
        with mock.patch.dict(os.environ, {"TMUX": tmux_agent, "TMUX_PANE": "%0"}):
            temoin = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                                    capture_output=True, text=True, timeout=5)
            self.assertIn("agentchattr-leurre", temoin.stdout.split(),
                          "témoin : sans isolation, tmux suit TMUX malgré TMUX_TMPDIR")

            # 3. Isolé, la session se crée comme dans les tests : sans -S.
            with _tmux_isole.tmux_isole() as dossier:
                isole = _tmux_isole.socket_isole(dossier)
                cree = subprocess.run(["tmux", "new-session", "-d", "-s", session, "sleep 60"],
                                      capture_output=True, timeout=10)
                self.assertEqual(cree.returncode, 0, cree.stderr)
                self.assertIn(session, _sessions(isole), "créée sur le serveur isolé")
                self.assertNotIn(session, _sessions(leurre), "absente du serveur de l'agent")
                for reel in _tmux_isole.sockets_reels():
                    self.assertNotIn(session, _sessions(reel), f"absente du serveur réel {reel}")

            # 4. restaurer() : serveur isolé parti, TMUX du « panneau » rendu.
            self.assertFalse(os.path.exists(isole))
            self.assertEqual(os.environ["TMUX"], tmux_agent)
        self.assertEqual(_sessions(leurre), ["agentchattr-leurre"], "leurre intact")


if __name__ == "__main__":
    unittest.main()
