"""S6 manager round summary contract.

v0.1 (2026-10-12, codex): cover active-project filtering and each actionable queue.
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
import projects
from executions import ExecutionStore
from jobs import JobStore
from ronde import ronde


class SocleS6Tests(unittest.TestCase):
    def test_round_only_reports_active_projects_and_sets_empty_state(self):
        projects_data = {
            "alpha": {"nom": "Alpha", "statut": "actif"},
            "paused": {"nom": "Paused", "statut": "veille"},
            "done": {"nom": "Done", "statut": "termine"},
        }
        tasks = [
            {"id": 1, "projet_id": "alpha", "titre": "Wait", "responsable": "claude", "etat": "attend_charles"},
            {"id": 2, "projet_id": "alpha", "titre": "Blocked", "responsable": "codex", "etat": "bloque"},
            {"id": 3, "projet_id": "alpha", "titre": "Experiment", "responsable": "claude", "etape": "essais",
             "etat": "a_faire", "incertitude": "", "hypothese": "h", "methode": "m", "critere": "c"},
            {"id": 4, "projet_id": "paused", "titre": "Paused task", "etat": "bloque"},
            {"id": 5, "projet_id": "done", "titre": "Done task", "etat": "fait"},
        ]
        executions = [
            {"id": "e1", "projet_id": "alpha", "tache_id": 1, "agent": "qwen", "etat": "silencieux", "dernier_signe": 1},
            {"id": "e2", "projet_id": "paused", "tache_id": 4, "agent": "qwen", "etat": "silencieux", "dernier_signe": 2},
        ]
        result = ronde(projects_data, tasks, executions)
        self.assertEqual([x["execution_id"] for x in result["silencieuses"]], ["e1"])
        self.assertEqual([x["tache_id"] for x in result["attend_charles"]], [1])
        self.assertEqual([x["tache_id"] for x in result["bloquees"]], [2])
        self.assertEqual([x["tache_id"] for x in result["essais_incomplets"]], [3])
        self.assertEqual(result["projets_sans_tache"], [])
        self.assertFalse(result["rien_a_faire"])
        self.assertTrue(ronde({}, [], []) ["rien_a_faire"])

    def test_round_route_combines_project_jobs_and_executions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects.configurer(root / "projects.json")
            alpha = projects.creer("Synthetic Alpha")
            paused = projects.creer("Synthetic Paused")
            projects.definir_statut(paused, "veille", par_id=True)
            jobs = JobStore(str(root / "jobs.json"))
            executions = ExecutionStore(str(root / "executions.json"))
            task, err = jobs.create_tache(alpha, "Blocked", "prototype", "claude", "user",
                                          equipe=[{"agent": "claude", "role": "producteur"}])
            self.assertEqual(err, "")
            jobs.update_tache(task["id"], {"etat": "bloque"})
            for name, value in (("jobs", jobs), ("executions", executions)):
                patcher = mock.patch.object(app, name, value)
                patcher.start()
                self.addCleanup(patcher.stop)
            client = TestClient(app.app)
            self.addCleanup(client.close)
            response = client.get("/api/v2/ronde")
            self.assertEqual(response.status_code, 200)
            self.assertEqual([t["tache_id"] for t in response.json()["bloquees"]], [task["id"]])
            self.assertEqual(response.json()["projets_sans_tache"], [])


if __name__ == "__main__":
    unittest.main()
