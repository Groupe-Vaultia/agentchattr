"""S1 project pause must stop agent triggers while keeping messages visible.

v0.2 (2026-10-12, codex): isolate app.store in the temporary test directory.
v0.1 (2026-10-12, codex): exercise the project status rule in
SOCLE-SHOP.md through the message router.
"""

import asyncio
import json
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
import projects
from store import MessageStore


class _Router:
    def get_targets(self, sender, text, channel):
        return ["codex"]

    def is_paused(self, channel):
        return False


class _Agents:
    def __init__(self):
        self.trigger = mock.AsyncMock()

    def is_available(self, name):
        return True


class ProjectStatusTests(unittest.TestCase):
    def test_paused_project_message_is_visible_but_does_not_wake_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.json"
            path.write_text(json.dumps({"projets": {
                "Alpha": {"memoire": "SYNTHETIC", "cree": 1, "channels": []},
            }, "actif": "Alpha"}), encoding="utf-8")
            projects.configurer(path)
            self.assertTrue(projects.definir_statut("alpha", "veille"))

            agents = _Agents()
            store = MessageStore(str(Path(directory) / "messages.jsonl"))
            message = {"id": 7, "sender": "user", "text": "@codex Please review",
                       "channel": "atelier", "type": "chat", "projet_id": "alpha"}
            with mock.patch.object(app, "agents", agents), \
                    mock.patch.object(app, "store", store), \
                    mock.patch.object(app, "router", _Router()), \
                    mock.patch.object(app, "registry", None), \
                    mock.patch.object(app, "config", {"agents": {"codex": {}}}), \
                    mock.patch.object(app, "session_engine", None), \
                    mock.patch.object(app, "broadcast", new_callable=mock.AsyncMock) as broadcast, \
                    mock.patch.object(mcp_bridge, "is_online", return_value=True):
                asyncio.run(app._handle_new_message(message))

            broadcast.assert_awaited_once_with(message)
            agents.trigger.assert_not_awaited()
            self.assertIn("aucun agent déclenché", store.get_recent(1)[0]["text"])


if __name__ == "__main__":
    unittest.main()
