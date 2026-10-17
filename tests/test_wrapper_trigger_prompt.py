"""Per-agent trigger prompt (agents.<x>.trigger_prompt / inject_rules).

v0.1 (2026-10-17, claude-1): Bolt (2-bit local) ignored the default English
prompt and answered in its terminal; a template naming the tools fixes it.
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

import wrapper


class _StopWatcher(Exception):
    pass


RULES = {"epoch": 3, "rules": ["R1 LONG RULE"], "refresh_interval": 10}


class TriggerPromptTests(unittest.TestCase):
    def _prompt_for(self, entry, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "bolt_queue.jsonl"
            queue.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            injected = []

            def one_poll(seconds):
                if seconds == 1:
                    raise _StopWatcher()

            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_trigger_memory", return_value=("", "")), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=RULES), \
                    mock.patch.object(wrapper, "_report_rule_sync"), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=one_poll):
                with self.assertRaises(_StopWatcher):
                    wrapper._queue_watcher(
                        lambda: ("bolt-1", queue), injected.append,
                        server_port=8300, agent_name="bolt", **kwargs,
                    )
            self.assertEqual(len(injected), 1)
            return injected[0]

    def test_default_prompt_and_rules_unchanged(self):
        prompt = self._prompt_for({"channel": "tache-26"})
        self.assertIn("use mcp to read #tache-26", prompt)
        self.assertIn("R1 LONG RULE", prompt)

    def test_template_fills_name_and_channel_and_drops_rules(self):
        prompt = self._prompt_for(
            {"channel": "tache-26"},
            trigger_prompt="Tu es {name}. chat_read(sender='{name}', {cible})",
            inject_rules=False,
        )
        self.assertTrue(prompt.startswith("Tu es bolt-1. chat_read(sender='bolt-1', channel='tache-26')"))
        self.assertNotIn("use mcp", prompt)
        self.assertNotIn("R1 LONG RULE", prompt)

    def test_template_targets_job(self):
        prompt = self._prompt_for({"channel": "general", "job_id": 12}, trigger_prompt="lis {cible}")
        self.assertTrue(prompt.startswith("lis job_id=12"))

    def test_custom_prompt_wins_over_template(self):
        prompt = self._prompt_for({"channel": "x", "prompt": "SESSION PROMPT"}, trigger_prompt="lis {cible}")
        self.assertTrue(prompt.startswith("SESSION PROMPT"))


if __name__ == "__main__":
    unittest.main()
