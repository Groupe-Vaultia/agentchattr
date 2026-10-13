"""Server wiring for S3 execution recovery and task switching.

v0.1 (2026-10-13, codex): cover persisted open runs and a new task while the agent is active.
"""

import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import mcp_bridge
import projects
from executions import ExecutionStore
from jobs import JobStore


class _Router:
    def get_targets(self, _sender, _text, _channel):
        return ["claude"]

    def is_paused(self, _channel):
        return False


class _Agents:
    def __init__(self):
        self.trigger = AsyncMock()

    def is_available(self, _agent):
        return True


class SocleS3WiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha", "MEMORY_ALPHA_ONLY")
        self.jobs = JobStore(str(root / "jobs.json"))
        self.exec_path = root / "executions.json"
        self.executions = ExecutionStore(str(self.exec_path))
        self.agents = _Agents()
        self.patchers = [
            mock.patch.object(app, "jobs", self.jobs),
            mock.patch.object(app, "executions", self.executions),
            mock.patch.object(app, "store", None),
            mock.patch.object(app, "config", {"agents": {"claude": {}}}),
            mock.patch.object(app, "registry", None),
            mock.patch.object(app, "router", _Router()),
            mock.patch.object(app, "agents", self.agents),
            mock.patch.object(app, "broadcast", new=AsyncMock()),
            mock.patch.object(mcp_bridge, "is_online", return_value=True),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _task(self, title):
        task, error = self.jobs.create_tache(
            "synthetic-alpha", title, "prototype", "claude", "user",
            equipe=[{"agent": "claude", "role": "producteur"}],
        )
        self.assertEqual(error, "")
        return task

    def _trigger(self, task):
        return {
            "sender": "user",
            "text": "@claude continue",
            "channel": "synthetic-room",
            "projet_id": "synthetic-alpha",
            "tache_id": task["id"],
        }

    def test_open_execution_is_reused_after_store_restart(self):
        task = self._task("Persisted task")
        previous = self.executions.demarrer(
            task["id"], "synthetic-alpha", "claude", "producteur", "original",
        )

        # A fresh store models server startup loading executions.json from disk.
        reloaded = ExecutionStore(str(self.exec_path))
        with mock.patch.object(app, "executions", reloaded):
            asyncio.run(app._handle_new_message(self._trigger(task)))

        runs = reloaded.lister("synthetic-alpha")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], previous["id"])
        self.assertIsNone(runs[0]["fin"])
        self.agents.trigger.assert_awaited_once()

    def test_new_task_replaces_open_execution_for_agent_already_active(self):
        first = self._task("Current task")
        second = self._task("Queued next task")
        old = self.executions.demarrer(
            first["id"], "synthetic-alpha", "claude", "producteur", "current work",
        )
        with mock.patch.object(mcp_bridge, "_activity", {"claude": True}), \
             mock.patch.object(mcp_bridge, "_activity_ts", {"claude": time.time()}):
            asyncio.run(app._handle_new_message(self._trigger(second)))

        runs = self.executions.lister("synthetic-alpha")
        old_run = next(run for run in runs if run["id"] == old["id"])
        open_runs = [run for run in runs if run.get("fin") is None]
        self.assertEqual((old_run["etat"], old_run["issue"]), ("fini", "terminee"))
        self.assertEqual(len(open_runs), 1)
        self.assertEqual(open_runs[0]["tache_id"], second["id"])
        self.agents.trigger.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
