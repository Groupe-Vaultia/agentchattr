"""CLI wrapper prompt checks for project-scoped queue batches.

v0.1 (2026-10-12, codex): verify the injected text for a tagged trigger
and reject project memory in mixed batches.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wrapper


class _StopWatcher(Exception):
    pass


class WrapperPromptTests(unittest.TestCase):
    def _prompt_for(self, entries):
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "codex_queue.jsonl"
            queue.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
            injected = []

            def fake_urlopen(request, timeout=3):
                url = request.full_url
                if "/projects/alpha/memory" in url:
                    data = {"nom": "Alpha", "memoire": "MEMO_ALPHA_ONLY"}
                elif "/projects/beta/memory" in url:
                    data = {"nom": "Beta", "memoire": "MEMO_BETA_ONLY"}
                else:
                    data = {"nom": "", "memoire": ""}
                return io.BytesIO(json.dumps(data).encode())

            def one_poll(seconds):
                if seconds == 1:
                    raise _StopWatcher()

            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=None), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=one_poll), \
                    mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with self.assertRaises(_StopWatcher):
                    wrapper._queue_watcher(
                        lambda: ("codex", queue), injected.append,
                        server_port=8300, agent_name="codex",
                    )
            self.assertEqual(len(injected), 1)
            return injected[0]

    def test_single_project_trigger_injects_only_its_memory(self):
        prompt = self._prompt_for([
            {"channel": "atelier", "text": "Alpha work", "projet_id": "alpha"},
        ])
        self.assertIn("MEMO_ALPHA_ONLY", prompt)
        self.assertNotIn("MEMO_BETA_ONLY", prompt)

    def test_tagged_and_untagged_triggers_do_not_inject_one_projects_memory(self):
        prompt = self._prompt_for([
            {"channel": "atelier", "text": "Alpha work", "projet_id": "alpha"},
            {"channel": "atelier", "text": "General work"},
        ])
        self.assertNotIn("MEMO_ALPHA_ONLY", prompt)

    def test_two_projects_in_one_batch_inject_no_project_memory(self):
        prompt = self._prompt_for([
            {"channel": "atelier", "text": "Alpha work", "projet_id": "alpha"},
            {"channel": "atelier", "text": "Beta work", "projet_id": "beta"},
        ])
        self.assertNotIn("MEMO_ALPHA_ONLY", prompt)
        self.assertNotIn("MEMO_BETA_ONLY", prompt)


if __name__ == "__main__":
    unittest.main()
