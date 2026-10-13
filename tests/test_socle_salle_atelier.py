"""Server and MCP channel labels for Shop task conversations.

v0.4 (2026-10-13, codex): preserve project labels for orphaned task channels.
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import mcp_bridge
import projects
from jobs import JobStore, canal_tache
from store import MessageStore


class _Registry:
    def resolve_token(self, token):
        return {"name": "codex"} if token == "test-agent-token" else None


class SocleSalleAtelierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        self.alpha = projects.creer("Synthetic Alpha")
        self.beta = projects.creer("Synthetic Beta")
        self.jobs = JobStore(str(root / "jobs.json"))
        patcher = mock.patch.object(app, "jobs", self.jobs)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.messages = MessageStore(str(root / "messages.jsonl"))
        self.task, error = self.jobs.create_tache(
            self.alpha,
            "Synthetic task",
            "prototype",
            "claude",
            "user",
            equipe=[{"agent": "claude", "role": "producteur"}],
        )
        self.assertEqual(error, "")
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def test_task_and_project_channels_add_their_labels_but_general_does_not(self):
        task_channel = canal_tache(self.task["id"])
        projects.assigner_canal("project-room", self.alpha, par_id=True)

        self.assertEqual(app._etiquettes(None, None, task_channel),
                         (self.alpha, self.task["id"], ""))
        self.assertEqual(app._etiquettes(None, None, "project-room"),
                         (self.alpha, None, ""))
        self.assertEqual(app._etiquettes(None, None, "general"), (None, None, ""))

    def test_explicit_project_keeps_priority_over_channel_task(self):
        self.assertEqual(app._etiquettes(self.beta, None, canal_tache(self.task["id"])),
                         (self.beta, None, ""))
        self.assertIn("projet inconnu", app._etiquettes("missing", None, canal_tache(self.task["id"]))[2])

    def test_orphan_task_channel_stays_untagged_even_if_a_project_is_assigned(self):
        projects.assigner_canal("tache-99", self.alpha, par_id=True)
        self.assertEqual(app._etiquettes(None, None, "tache-99"), (self.alpha, None, ""))

    def test_mcp_send_in_orphan_task_channel_stays_untagged(self):
        projects.assigner_canal("tache-99", self.alpha, par_id=True)
        patchers = [
            mock.patch.object(mcp_bridge, "store", self.messages),
            mock.patch.object(mcp_bridge, "jobs", self.jobs),
            mock.patch.object(mcp_bridge, "registry", None),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity", side_effect=lambda sender, *_a, **_k: (sender, None)),
            mock.patch.object(mcp_bridge, "_update_cursor"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        result = mcp_bridge.chat_send(sender="codex", message="orphan task", choices=[], channel="tache-99")
        self.assertIn("Sent (id=", result)
        saved = self.messages.get_recent(1)[0]
        self.assertEqual(saved["projet_id"], self.alpha)
        self.assertNotIn("tache_id", saved)

    def test_mcp_send_in_task_channel_gets_project_and_task(self):
        patchers = [
            mock.patch.object(mcp_bridge, "store", self.messages),
            mock.patch.object(mcp_bridge, "jobs", self.jobs),
            mock.patch.object(mcp_bridge, "registry", None),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity", side_effect=lambda sender, *_a, **_k: (sender, None)),
            mock.patch.object(mcp_bridge, "_update_cursor"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        result = mcp_bridge.chat_send(sender="codex", message="task message", choices=[],
                                      channel=canal_tache(self.task["id"]))
        self.assertIn("Sent (id=", result)
        saved = self.messages.get_recent(1)[0]
        self.assertEqual((saved["projet_id"], saved["tache_id"]),
                         (self.alpha, self.task["id"]))

    def test_api_send_uses_channel_task_label(self):
        with mock.patch.object(app, "jobs", self.jobs), \
             mock.patch.object(app, "registry", _Registry()), \
             mock.patch.object(app, "store", self.messages):
            response = self.client.post(
                "/api/send",
                headers={"Authorization": "Bearer test-agent-token"},
                json={"text": "task channel message", "channel": canal_tache(self.task["id"])},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["projet_id"], response.json()["tache_id"]),
                         (self.alpha, self.task["id"]))

    def test_task_conversation_route_is_idempotent_and_rejects_unknown_task(self):
        room_settings = {"channels": ["general"]}
        save = mock.Mock()
        broadcast = AsyncMock()
        with mock.patch.object(app, "jobs", self.jobs), \
             mock.patch.object(app, "room_settings", room_settings), \
             mock.patch.object(app, "_save_settings", save), \
             mock.patch.object(app, "broadcast_settings", broadcast):
            response = self.client.post(f"/api/v2/taches/{self.task['id']}/conversation", json={})
            first = asyncio.run(app.tache_conversation(self.task["id"]))
            second = asyncio.run(app.tache_conversation(self.task["id"]))
            missing = asyncio.run(app.tache_conversation(999))

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"channel": canal_tache(self.task["id"]),
                                           "projet_id": self.alpha, "tache_id": self.task["id"]})
        first_body = json.loads(first.body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first_body, {"channel": canal_tache(self.task["id"]),
                                      "projet_id": self.alpha, "tache_id": self.task["id"]})
        self.assertEqual(json.loads(second.body), first_body)
        self.assertEqual(room_settings["channels"].count(canal_tache(self.task["id"])), 1)
        save.assert_called_once()
        broadcast.assert_awaited_once()
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
