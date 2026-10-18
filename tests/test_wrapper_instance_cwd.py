"""Per-instance working dir (agents.<x>.cwd_instances).

v0.1 (2026-10-17, claude-1): two Bolt instances shared cad-bolt/.qwen/settings.json
and the room signed bolt-2's reply as bolt-1 (msg 4427).
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
        self.assertEqual(wrapper._instance_cwd(self.CFG, "bolt-2"), "../cad-bolt-2")

    def test_first_instance_and_unmapped_keep_cwd(self):
        for name in ("bolt", "bolt-1", "bolt-3"):
            self.assertEqual(wrapper._instance_cwd(self.CFG, name), "../cad-bolt")

    def test_no_mapping_and_no_cwd(self):
        self.assertEqual(wrapper._instance_cwd({}, "qwencode-2"), ".")


if __name__ == "__main__":
    unittest.main()
