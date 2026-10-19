"""Le loop guard qui coupe un canal reveille le chef une fois par pause.

v0.2 (2026-10-19, claude-1) : la consigne ne recopie plus le texte bloque (revue codex-1, msg 5067).
v0.1 (2026-10-19, claude-1) : #tache-21 est reste 2 h 45 sans suite apres le loop guard (msg 5040).
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import mcp_bridge
from router import Router
from store import MessageStore


class _Agents:
    def __init__(self):
        self.trigger = mock.AsyncMock()

    def is_available(self, name):
        return True


class GardeReveilChefTests(unittest.TestCase):
    def _envoyer(self, routing, messages):
        with tempfile.TemporaryDirectory() as directory:
            agents = _Agents()
            store = MessageStore(str(Path(directory) / "messages.jsonl"))
            router = Router(["claude-1", "codex-2"], max_hops=1)
            with mock.patch.object(app, "agents", agents), \
                    mock.patch.object(app, "store", store), \
                    mock.patch.object(app, "router", router), \
                    mock.patch.object(app, "registry", None), \
                    mock.patch.object(app, "session_engine", None), \
                    mock.patch.object(app, "config", {"agents": {}, "routing": routing}), \
                    mock.patch.object(app, "broadcast", new_callable=mock.AsyncMock), \
                    mock.patch.object(mcp_bridge, "is_online", return_value=True):
                for i, (sender, text) in enumerate(messages, 1):
                    asyncio.run(app._handle_new_message(
                        {"id": i, "sender": sender, "text": text, "channel": "tache-21", "type": "chat"}))
            return agents.trigger

    def test_garde_reveille_le_chef_une_fois(self):
        trigger = self._envoyer({"chef": "claude-1"}, [
            ("codex-2", "@claude-1 revue livree"),      # hop 1 : route
            ("claude-1", "@codex-2 relis le delta"),    # hop 2 : pause -> chef reveille
            ("codex-2", "@claude-1 encore"),            # toujours en pause : pas de second reveil
        ])
        appels_chef = [c for c in trigger.await_args_list
                       if c.args[0] == "claude-1" and "Loop guard" in c.kwargs.get("prompt", "")]
        self.assertEqual(len(appels_chef), 1)
        self.assertIn("#tache-21", appels_chef[0].kwargs["prompt"])
        self.assertIn("n° 2, de claude-1", appels_chef[0].kwargs["prompt"])
        # R3 : le texte du message bloque n'est jamais recopie dans la consigne
        self.assertNotIn("relis le delta", appels_chef[0].kwargs["prompt"])
        self.assertNotIn("relis le delta", appels_chef[0].kwargs["message"])

    def test_sans_chef_configure_personne_n_est_reveille(self):
        trigger = self._envoyer({}, [
            ("codex-2", "@claude-1 revue livree"),
            ("claude-1", "@codex-2 relis le delta"),
        ])
        self.assertFalse(any("Loop guard" in c.kwargs.get("prompt", "") for c in trigger.await_args_list))


if __name__ == "__main__":
    unittest.main()
