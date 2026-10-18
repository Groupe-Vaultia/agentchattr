"""Per-instance working dir (agents.<x>.cwd_instances).

v0.1 (2026-10-17, claude-1): two Bolt instances shared cad-bolt/.qwen/settings.json
and the room signed bolt-2's reply as bolt-1 (msg 4427).
v0.2 (2026-10-17, claude-1): unmapped extra instance refused (revue codex 4429).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wrapper


class InstanceCwdTests(unittest.TestCase):
    CFG = {"cwd": "../cad-bolt", "cwd_instances": {"bolt-2": "../cad-bolt-2"}}

    def test_mapped_instance_gets_its_own_dir(self):
        self.assertEqual(wrapper._instance_cwd(self.CFG, "bolt-2", "bolt"), "../cad-bolt-2")

    def test_base_instance_keeps_cwd(self):
        for name in ("bolt", "bolt-1"):
            self.assertEqual(wrapper._instance_cwd(self.CFG, name, "bolt"), "../cad-bolt")

    def test_unmapped_extra_instance_is_refused(self):
        self.assertIsNone(wrapper._instance_cwd(self.CFG, "bolt-3", "bolt"))

    def test_no_mapping_keeps_old_behaviour(self):
        self.assertEqual(wrapper._instance_cwd({}, "qwencode-2", "qwencode"), ".")
        self.assertEqual(wrapper._instance_cwd({"cwd": "x"}, "qwencode-3", "qwencode"), "x")


if __name__ == "__main__":
    unittest.main()
