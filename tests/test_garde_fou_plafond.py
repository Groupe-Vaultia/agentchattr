"""Plafond du réglage « Loop guard » : `update_settings` accepte max_agent_hops jusqu'à MAX_AGENT_HOPS_PLAFOND.

v1.0 (2026-10-27, claude-code, demande de Charles : essai d'autonomie du 27 oct. au 10 nov.) : avant, le WebSocket
bornait le réglage à 50 et la salle attendait un humain cinq fois par semaine. Données synthétiques seulement ;
connexion WebSocket réelle par TestClient, comme tests/test_continue_ws.py.
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

DEPART = 4


class PlafondGardeFouTests(unittest.TestCase):

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
            app.configure({"server": {"data_dir": str(root / "data")}, "agents": {"claude": {}, "codex": {}},
                           "routing": {"max_agent_hops": DEPART, "chef": "claude-1"}, "images": {}},
                          session_token="sess")
        self.assertEqual(app.router.max_hops, DEPART)

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

    def _regler(self, hops):
        """Envoie le réglage par le WebSocket du navigateur (cookie de session) et rend la valeur retenue."""
        client = TestClient(app.app)
        self.addCleanup(client.close)
        entetes = {"origin": "http://127.0.0.1:8300", "cookie": f"{app.cookie_session}=sess"}
        with client.websocket_connect("/ws", headers=entetes) as ws:
            ws.send_json({"type": "update_settings", "data": {"max_agent_hops": hops}})
            fin = time.monotonic() + 5
            while time.monotonic() < fin and app.router.max_hops == DEPART:
                time.sleep(0.02)
        return app.router.max_hops

    def test_deux_cents_relais_passent(self):
        self.assertEqual(self._regler(200), 200)
        self.assertEqual(app.room_settings["max_agent_hops"], 200)

    def test_au_dela_du_plafond_le_reglage_reste_au_plafond(self):
        self.assertEqual(app.MAX_AGENT_HOPS_PLAFOND, 500)
        self.assertEqual(self._regler(10_000), app.MAX_AGENT_HOPS_PLAFOND)
        self.assertEqual(app.room_settings["max_agent_hops"], app.MAX_AGENT_HOPS_PLAFOND)

    def test_le_plancher_reste_a_un(self):
        self.assertEqual(self._regler(0), 1)


if __name__ == "__main__":
    unittest.main()
