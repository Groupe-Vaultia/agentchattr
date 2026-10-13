"""S3 execution contract.

v0.1 (2026-10-12, codex): exercise project gates, RS&DE prerequisites,
restart/silence/finalization, and memory/event minimization.
"""

import hashlib
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
import projects
from executions import ExecutionStore
from jobs import JobStore


class SocleS3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha", "MEMORY_ALPHA_ONLY")
        projects.creer("Synthetic Beta", "MEMORY_BETA_ONLY")
        self.jobs = JobStore(str(root / "jobs.json"))
        self.executions = ExecutionStore(str(root / "executions.json"))
        for name, value in (("jobs", self.jobs), ("executions", self.executions)):
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def _task(self, project="synthetic-alpha", stage="prototype", **fields):
        task, error = self.jobs.create_tache(project, "Synthetic task", stage, "claude", "user",
                                             equipe=[{"agent": "claude", "role": "producteur"}], **fields)
        self.assertEqual(error, "")
        return task

    def _start(self, task, **fields):
        body = {"tache_id": task["id"], "agent": "claude", "role": "producteur", "consigne": "Build"}
        body.update(fields)
        return self.client.post("/api/v2/executions", json=body)

    def test_start_rejects_paused_project_and_unprepared_experiment(self):
        task = self._task(stage="essais", incertitude="unknown", hypothese="may work", methode="measure")
        self.assertEqual(self._start(task).status_code, 409)
        self.jobs.update_tache(task["id"], {"critere": "under 10 seconds"})
        projects.definir_statut("synthetic-alpha", "veille", par_id=True)
        self.assertEqual(self._start(task).status_code, 409)
        self.assertEqual(self.client.get("/api/v2/executions", params={"projet_id": "synthetic-alpha"}).json()["executions"], [])

        projects.definir_statut("synthetic-alpha", "actif", par_id=True)
        started = self._start(task)
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["projet_id"], "synthetic-alpha")
        self.assertEqual(started.json()["etat"], "actif")

    def test_memory_is_bound_to_task_project_without_raw_copy(self):
        task = self._task(project="synthetic-beta")
        started = self._start(task)
        self.assertEqual(started.status_code, 200)
        body = started.json()
        self.assertEqual(body["memoire_projet_id"], "synthetic-beta")
        self.assertEqual(body["memoire_empreinte"], hashlib.sha256(b"MEMORY_BETA_ONLY").hexdigest())
        self.assertNotIn("MEMORY_ALPHA_ONLY", str(body))
        self.assertNotIn("MEMORY_BETA_ONLY", str(body))
        self.assertNotIn("MEMORY_BETA_ONLY", (Path(self.tmp.name) / "executions.json").read_text())

    def test_silence_survives_restart_and_finished_execution_stays_finished(self):
        path = Path(self.tmp.name) / "executions.json"
        run = self.executions.demarrer(7, "synthetic-alpha", "claude", "producteur", "Build",
                                       maintenant=100.0)
        reloaded = ExecutionStore(str(path), silence_s=600)
        self.assertEqual(reloaded.lister(maintenant=701.0)[0]["etat"], "silencieux")
        finished = reloaded.terminer(run["id"], "reussie", maintenant=702.0)
        self.assertEqual((finished["etat"], finished["fin"], finished["issue"]),
                         ("fini", 702.0, "reussie"))
        self.assertEqual(reloaded.terminer(run["id"], "echouee", maintenant=703.0)["issue"], "reussie")
        self.assertEqual(reloaded.signe(run["id"], resume="late", maintenant=704.0)["etat"], "fini")
        again = ExecutionStore(str(path), silence_s=600)
        saved = again.lister(maintenant=2000.0)[0]
        self.assertEqual((saved["etat"], saved["fin"], saved["issue"], saved["nb_evenements"]),
                         ("fini", 702.0, "reussie", 0))

    def test_events_are_one_line_bounded_and_unknown_execution_is_404(self):
        task = self._task()
        run_id = self._start(task).json()["id"]
        response = self.client.post(f"/api/v2/executions/{run_id}/signe", json={
            "outil": "pytest", "resume": "first line\n" + "x" * 400})
        self.assertEqual(response.status_code, 200)
        event = self.client.get(f"/api/v2/executions/{run_id}/evenements").json()["evenements"][0]
        self.assertNotIn("\n", event["resume"])
        self.assertLessEqual(len(event["resume"]), 200)
        self.assertEqual(self.client.post("/api/v2/executions/missing/signe", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
