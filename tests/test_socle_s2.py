"""S2 project task contract.

v0.1 (2026-10-12, codex): validate ownership, evidence, stages, and legacy jobs.
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
from jobs import JobStore


class SocleS2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha")
        projects.creer("Synthetic Beta")
        self.jobs = JobStore(str(root / "jobs.json"))
        patcher = mock.patch.object(app, "jobs", self.jobs)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def _create(self, **changes):
        body = {"projet_id": "synthetic-alpha", "titre": "Prototype", "etape": "prototype",
                "responsable": "claude", "equipe": [{"agent": "claude", "role": "producteur"}]}
        body.update(changes)
        return self.client.post("/api/v2/taches", json=body)

    def test_task_requires_existing_project_and_responsible_team_member(self):
        self.assertEqual(self._create(projet_id="missing").status_code, 404)
        self.assertEqual(self._create(etape="inventee").status_code, 400)
        self.assertEqual(self._create(equipe=[{"agent": "codex", "role": "verificateur"}]).status_code, 400)
        self.assertEqual(self._create(equipe=[{"agent": "claude", "role": "producteur"},
                                              {"agent": "claude", "role": "producteur"}]).status_code, 400)
        self.assertEqual(self.client.get("/api/v2/taches", params={"projet_id": "synthetic-alpha"}).json()["taches"], [])

    def test_done_requires_evidence_and_stage_is_first_unfinished(self):
        later = self._create().json()
        earlier = self._create(titre="Define need", etape="probleme").json()
        self.assertEqual(self.client.get("/api/v2/taches", params={"projet_id": "synthetic-alpha"}).json()["etape"], "probleme")

        refused = self.client.patch(f"/api/v2/taches/{earlier['id']}", json={"etat": "fait"})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(self.jobs.get(earlier["id"])["etat"], "a_faire")

        done = self.client.patch(f"/api/v2/taches/{earlier['id']}", json={
            "etat": "fait", "preuve": "python -m unittest: OK"})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()["responsable"], "claude")
        self.assertEqual(self.client.get("/api/v2/taches", params={"projet_id": "synthetic-alpha"}).json()["etape"], "prototype")
        self.assertEqual(self.jobs.get(later["id"])["etat"], "a_faire")

    def test_updating_responsible_agent_must_preserve_team_membership(self):
        task = self._create().json()
        response = self.client.patch(f"/api/v2/taches/{task['id']}", json={"responsable": "gemini"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.jobs.get(task["id"])["responsable"], "claude")

    def test_legacy_job_stays_without_project_after_reload(self):
        legacy = self.jobs.create("Old card", "task", "general", "user")
        project = self._create().json()
        reloaded = JobStore(str(Path(self.tmp.name) / "jobs.json"))
        self.assertNotIn("projet_id", reloaded.get(legacy["id"]))
        self.assertEqual([t["id"] for t in reloaded.taches("synthetic-alpha")], [project["id"]])
        self.assertEqual(reloaded.taches("synthetic-beta"), [])

    def test_unreadable_job_store_is_reported_without_erasing_file(self):
        path = Path(self.tmp.name) / "damaged-jobs.json"
        path.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(ValueError):
            JobStore(str(path))
        self.assertEqual(path.read_text(encoding="utf-8"), "{bad json")


if __name__ == "__main__":
    unittest.main()
