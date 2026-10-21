"""/continue sur le chemin WebSocket (revue N3 de codex-2, #tache-26 msg 6777).

v1.0 (2026-10-21, claude-2) : l'invariant « seul un humain leve une pause » valait sur le chemin MCP mais pas sur le
WebSocket, ou l'expediteur vient de l'evenement et ou /continue relancait « general » quel que soit le canal vise.
Donnees synthetiques seulement ; connexion WebSocket reelle par TestClient.
"""

import copy
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app


class ContinueWebSocketTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self._app_state = app.__dict__.copy()
        self._room = copy.deepcopy(app.room_settings)
        self._mw = list(app.app.user_middleware)
        self.addCleanup(self._restore)
        app.app.middleware_stack = None
        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({"server": {"data_dir": str(root / "data")}, "agents": {"claude": {}, "codex": {}, "qwen": {}},
                           "routing": {"max_agent_hops": 1, "chef": "claude-1"}, "images": {}}, session_token="sess")
        for canal in ("tache-9", "general"):                     # deux canaux en pause
            app.router.get_targets("codex", "@qwen a toi", canal)
            app.router.get_targets("qwen", "@codex non a toi", canal)
            self.assertTrue(app.router.is_paused(canal))

    def _restore(self):
        for key in list(app.__dict__):
            if key not in self._app_state:
                delattr(app, key)
        for key, value in self._app_state.items():
            setattr(app, key, value)
        app.room_settings.clear()
        app.room_settings.update(self._room)
        app.app.user_middleware = self._mw
        app.app.middleware_stack = None

    def _continue(self, sender, canal):
        """Envoie /continue par le WebSocket et attend l'avis système du canal visé."""
        avant = len(app.store.get_recent(1000, channel=canal))
        client = TestClient(app.app)
        self.addCleanup(client.close)
        with client.websocket_connect("/ws?token=sess") as ws:
            ws.send_json({"type": "message", "text": "/continue", "sender": sender, "channel": canal})
            fin = time.monotonic() + 5
            while time.monotonic() < fin and len(app.store.get_recent(1000, channel=canal)) == avant:
                time.sleep(0.02)
        nouveaux = app.store.get_recent(1000, channel=canal)[avant:]
        self.assertTrue(nouveaux, "aucun avis système")
        return nouveaux[-1]["text"]

    def test_un_agent_ne_leve_pas_la_pause_par_le_websocket(self):
        for sender in ("codex", "Qwen", "claude-1"):              # nom de famille, autre casse, instance du chef
            avis = self._continue(sender, "tache-9")
            self.assertIn("only humans can /continue", avis)
            self.assertTrue(app.router.is_paused("tache-9"))

    def test_un_humain_ne_relance_que_le_canal_vise(self):
        avis = self._continue("user", "tache-9")
        self.assertIn("Resuming", avis)
        self.assertFalse(app.router.is_paused("tache-9"))
        self.assertTrue(app.router.is_paused("general"))         # avant : continue_routing() relançait « general »


if __name__ == "__main__":
    unittest.main()
