"""Per-instance working dir (agents.<x>.cwd_instances).

v0.1 (2026-10-17, claude-1): two Bolt instances shared cad-bolt/.qwen/settings.json
and the room signed bolt-2's reply as bolt-1 (msg 4427).
v0.2 (2026-10-17, claude-1): unmapped extra instance refused (revue codex 4429).
v0.3 (2026-10-17, claude-1): same guard on a rename mid-session (revue codex 4431).
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

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



class _Exited(Exception):
    pass


class GuardRenameTests(unittest.TestCase):
    CFG = InstanceCwdTests.CFG

    def _guard(self, cwd, new_name):
        with mock.patch.object(wrapper, "_refuse_instance") as refuse, \
                mock.patch.object(wrapper.subprocess, "run") as run, \
                mock.patch.object(wrapper.os, "_exit", side_effect=_Exited):
            try:
                wrapper._guard_rename(self.CFG, "bolt", cwd, new_name, 8300, "tok", "agentchattr-bolt")
                exited = False
            except _Exited:
                exited = True
        return exited, refuse, run

    def test_rename_409_to_bolt3_stops_and_deregisters(self):
        exited, refuse, run = self._guard("../cad-bolt", "bolt-3")
        self.assertTrue(exited)
        refuse.assert_called_once_with(8300, "bolt", "bolt-3", "tok")
        if sys.platform != "win32":
            self.assertEqual(run.call_args[0][0], ["tmux", "kill-session", "-t", "agentchattr-bolt"])

    def test_rename_into_other_instance_dir_stops(self):
        # first instance (in cad-bolt) handed bolt-2, whose dir is cad-bolt-2
        exited, _, _ = self._guard("../cad-bolt", "bolt-2")
        self.assertTrue(exited)

    def test_normal_rename_bolt_to_bolt1_passes(self):
        exited, refuse, run = self._guard("../cad-bolt", "bolt-1")
        self.assertFalse(exited)
        refuse.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
