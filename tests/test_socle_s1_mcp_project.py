"""MCP chat_send project-tag contract.

v0.1 (2026-10-12, codex): cover explicit and inherited project tags,
unknown IDs, and untagged messages with synthetic projects only.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_bridge
import projects
from store import MessageStore


class McpProjectTagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        path = root / "projects.json"
        path.write_text(json.dumps({
            "projets": {
                "Alpha": {"memoire": "SYNTHETIC_ALPHA", "cree": 1, "channels": []},
                "Beta": {"memoire": "SYNTHETIC_BETA", "cree": 2, "channels": []},
            },
            "actif": "Alpha",
        }), encoding="utf-8")
        projects.configurer(path)
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.patches = [
            mock.patch.object(mcp_bridge, "store", self.store),
            mock.patch.object(mcp_bridge, "registry", None),
            mock.patch.object(mcp_bridge, "jobs", None),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity", side_effect=lambda sender, *_a, **_k: (sender, None)),
            mock.patch.object(mcp_bridge, "_update_cursor"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _send(self, **kwargs):
        return mcp_bridge.chat_send(sender="codex", message="Reviewed", choices=[], channel="atelier", **kwargs)

    def test_reply_inherits_parent_project(self):
        parent = self.store.add("user", "Review Alpha", channel="atelier", projet_id="alpha")
        result = self._send(reply_to=parent["id"])
        self.assertIn("Sent (id=", result)
        reply = self.store.get_recent(1)[0]
        self.assertEqual(reply["reply_to"], parent["id"])
        self.assertEqual(reply["projet_id"], "alpha")

    def test_explicit_project_overrides_parent_when_intended(self):
        parent = self.store.add("user", "Compare", channel="atelier", projet_id="alpha")
        self._send(reply_to=parent["id"], projet_id="beta")
        self.assertEqual(self.store.get_recent(1)[0]["projet_id"], "beta")

    def test_unknown_project_rejects_without_creating_message(self):
        before = len(self.store.get_recent())
        result = self._send(projet_id="missing")
        self.assertIn("Unknown projet_id", result)
        self.assertEqual(len(self.store.get_recent()), before)

    def test_untagged_message_does_not_inherit_display_default(self):
        self._send()
        self.assertNotIn("projet_id", self.store.get_recent(1)[0])


if __name__ == "__main__":
    unittest.main()
