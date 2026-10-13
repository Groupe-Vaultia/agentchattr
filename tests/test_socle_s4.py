"""S4 project/task message filters and task-tag inheritance.

v0.1 (2026-10-12, codex): cover message labels, filtering, and reply propagation.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import mcp_bridge
import projects
from jobs import JobStore
from store import MessageStore


class SocleS4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha")
        projects.creer("Synthetic Beta")
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.jobs = JobStore(str(root / "jobs.json"))
        self.task, err = self.jobs.create_tache("synthetic-alpha", "Task", "prototype", "claude", "user",
                                                equipe=[{"agent": "claude", "role": "producteur"}])
        self.assertEqual(err, "")
        for name, value in (("store", self.store), ("jobs", self.jobs)):
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def test_labels_require_valid_project_and_matching_task(self):
        self.assertEqual(app._etiquettes("synthetic-alpha", self.task["id"]),
                         ("synthetic-alpha", self.task["id"], ""))
        self.assertEqual(app._etiquettes(None, self.task["id"]),
                         ("synthetic-alpha", self.task["id"], ""))
        self.assertIn("n'appartient pas", app._etiquettes("synthetic-beta", self.task["id"])[2])
        self.assertIn("tache inconnue", app._etiquettes("synthetic-alpha", 999)[2])
        self.assertIn("projet inconnu", app._etiquettes("missing", None)[2])

    def test_filters_include_message_zero_and_reject_unbounded_queries(self):
        first = self.store.add("user", "task message", channel="room", projet_id="synthetic-alpha",
                               tache_id=self.task["id"])
        self.store.add("user", "other project", channel="room", projet_id="synthetic-beta")
        self.store.add("user", "untagged", channel="room")
        self.assertEqual(first["id"], 0)

        self.assertEqual(self.client.get("/api/v2/messages", params={"projet_id": "synthetic-alpha"}).json()["messages"],
                         [first])
        self.assertEqual(self.client.get("/api/v2/messages", params={"tache_id": self.task["id"]}).json()["messages"],
                         [first])
        self.assertEqual(self.client.get("/api/v2/messages", params={"projet_id": "missing"}).status_code, 404)
        self.assertEqual(self.client.get("/api/v2/messages").status_code, 400)

    def test_mcp_reply_keeps_task_only_while_project_stays_the_same(self):
        parent = self.store.add("user", "parent", channel="room", projet_id="synthetic-alpha",
                                tache_id=self.task["id"])
        patchers = [
            mock.patch.object(mcp_bridge, "store", self.store),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity", side_effect=lambda sender, *_a, **_k: (sender, None)),
            mock.patch.object(mcp_bridge, "_update_cursor"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        mcp_bridge.chat_send(sender="codex", message="same project", choices=[], channel="room",
                             reply_to=parent["id"])
        same = self.store.get_recent(1)[0]
        self.assertEqual((same["projet_id"], same["tache_id"]), ("synthetic-alpha", self.task["id"]))

        mcp_bridge.chat_send(sender="codex", message="other project", choices=[], channel="room",
                             reply_to=parent["id"], projet_id="synthetic-beta")
        other = self.store.get_recent(1)[0]
        self.assertEqual(other["projet_id"], "synthetic-beta")
        self.assertNotIn("tache_id", other)


if __name__ == "__main__":
    unittest.main()
