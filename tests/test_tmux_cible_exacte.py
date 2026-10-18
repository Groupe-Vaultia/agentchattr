"""Cibles tmux exactes dans wrapper_unix (=nom, =nom:).

v0.1 (2026-10-18, claude-1) : sans « = », tmux résout -t par préfixe quand
la session exacte n'existe pas. Le démarrage de qwencode (slot 1) a tué
agentchattr-qwencode-2, celui de bolt a tué agentchattr-bolt-3, et un
wrapper pouvait voir sa CLI « vivante » grâce à une session voisine.
Testé sur un serveur tmux isolé (tests/_tmux_isole.py).
"""
import os
import shutil
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
for chemin in (TESTS, ROOT):
    if chemin not in sys.path:
        sys.path.insert(0, chemin)

import _tmux_isole  # noqa: E402
import wrapper_unix  # noqa: E402


def setUpModule():
    _tmux_isole.isoler()


def tearDownModule():
    _tmux_isole.restaurer()


@unittest.skipUnless(shutil.which("tmux"), "tmux absent")
class CibleExacteTests(unittest.TestCase):
    VOISINE = "agentchattr-essai-2"
    ABSENTE = "agentchattr-essai"

    @classmethod
    def setUpClass(cls):
        # garde le serveur isolé en vie entre les tests (il s'arrête avec sa dernière session)
        subprocess.run(["tmux", "new-session", "-d", "-s", "zz-garde", "sleep 600"], check=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["tmux", "kill-session", "-t", "=zz-garde"], capture_output=True)

    def setUp(self):
        subprocess.run(["tmux", "new-session", "-d", "-s", self.VOISINE, "sleep 120"], check=True)
        self.addCleanup(subprocess.run, ["tmux", "kill-session", "-t", f"={self.VOISINE}"],
                        capture_output=True)

    def _sessions(self):
        r = subprocess.run(["tmux", "ls", "-F", "#S"], capture_output=True, text=True)
        return r.stdout.split()

    def test_absent_session_is_not_found_through_its_neighbour(self):
        self.assertFalse(wrapper_unix._session_exists(self.ABSENTE))
        self.assertTrue(wrapper_unix._session_exists(self.VOISINE))

    def test_cleanup_kill_spares_the_neighbour(self):
        subprocess.run(["tmux", "kill-session", "-t", wrapper_unix._exact_session(self.ABSENTE)],
                       capture_output=True)
        self.assertIn(self.VOISINE, self._sessions())

    def test_pane_lookup_does_not_resolve_to_the_neighbour(self):
        self.assertIsNone(wrapper_unix._pane_id(self.ABSENTE))
        self.assertTrue(wrapper_unix._pane_id(self.VOISINE).startswith("%"))

    def test_pane_ids_stay_as_they_are(self):
        self.assertEqual(wrapper_unix._exact_pane("%7"), "%7")


if __name__ == "__main__":
    unittest.main()
