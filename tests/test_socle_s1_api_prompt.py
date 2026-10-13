"""API wrapper model-input checks for project-scoped queue batches.

v0.1 (2026-10-12, codex): verify the system prompt sent to the model
contains only the memory allowed by the trigger batch.
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

import config_loader
import wrapper
import wrapper_api


class ApiPromptTests(unittest.TestCase):
    def _model_input_for(self, entries):
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "qwen_queue.jsonl"
            queue.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
            model_inputs = []
            original_write_text = Path.write_text
            first_clear = [True]

            def keep_initial_queue(path, text, *args, **kwargs):
                # The wrapper normally drops a stale queue on startup. Keep
                # this synthetic queue for its first poll, then clear normally.
                if path == queue and text == "" and first_clear[0]:
                    first_clear[0] = False
                    return 0
                return original_write_text(path, text, *args, **kwargs)

            def fake_urlopen(request, timeout=3):
                url = request.full_url
                if url.endswith("/api/status"):
                    result = {}
                elif "/api/projects/alpha/memory" in url:
                    result = {"nom": "Alpha", "memoire": "MEMO_ALPHA_ONLY"}
                elif "/api/projects/channel/" in url:
                    result = {"nom": "", "memoire": ""}
                elif "/api/messages?" in url:
                    result = [{"sender": "user", "text": "Please reply"}]
                elif url.endswith("/chat/completions"):
                    model_inputs.append(json.loads(request.data))
                    result = {"choices": [{"message": {"content": "Done"}}]}
                elif url.endswith("/api/send") or "/api/deregister/" in url:
                    result = {"ok": True}
                else:
                    raise AssertionError(url)
                return io.BytesIO(json.dumps(result).encode())

            config = {
                "agents": {"qwen": {"type": "api", "base_url": "http://model", "context_messages": 2}},
                "server": {"data_dir": directory, "port": 8300},
            }
            with mock.patch.object(config_loader, "apply_cli_overrides"), \
                    mock.patch.object(config_loader, "load_config", return_value=config), \
                    mock.patch.object(wrapper, "_register_instance", return_value={"name": "qwen", "token": ""}), \
                    mock.patch.object(wrapper_api.threading, "Thread") as thread, \
                    mock.patch.object(Path, "write_text", keep_initial_queue), \
                    mock.patch.object(wrapper_api.time, "sleep", side_effect=KeyboardInterrupt), \
                    mock.patch.object(wrapper_api.urllib.request, "urlopen", side_effect=fake_urlopen), \
                    mock.patch.object(sys, "argv", ["wrapper_api.py", "qwen"]):
                thread.return_value.start.return_value = None
                wrapper_api.main()

            self.assertEqual(len(model_inputs), 1)
            return model_inputs[0]["messages"][0]["content"]

    def test_tagged_trigger_sends_its_memory_to_model(self):
        prompt = self._model_input_for([
            {"channel": "atelier", "text": "Alpha work", "projet_id": "alpha"},
        ])
        self.assertIn("MEMO_ALPHA_ONLY", prompt)

    def test_tagged_and_untagged_batch_sends_no_project_memory_to_model(self):
        prompt = self._model_input_for([
            {"channel": "atelier", "text": "Alpha work", "projet_id": "alpha"},
            {"channel": "atelier", "text": "General work"},
        ])
        self.assertNotIn("MEMO_ALPHA_ONLY", prompt)


if __name__ == "__main__":
    unittest.main()
