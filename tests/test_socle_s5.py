"""S5 deliverables, approvals, and immutable revision fingerprints.

v0.1 (2026-10-12, codex): verify on-disk bytes at approval and preserve old revisions.
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
from revisions import RevisionStore


class SocleS5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.root = root / "deliverables"
        self.root.mkdir()
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha")
        self.revisions = RevisionStore(str(root / "revisions.json"), str(self.root))
        patcher = mock.patch.object(app, "revisions", self.revisions)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def test_approval_hashes_current_bytes_and_leaves_previous_revision_immutable(self):
        artifact = self.root / "result.txt"
        artifact.write_bytes(b"captured at add time")
        first = self.revisions.ajouter_livrable("synthetic-alpha", "1", "result.txt")
        self.assertEqual(self.revisions.ajouter_livrable("synthetic-alpha", "1", "result.txt"), first)

        artifact.write_bytes(b"changed before approval")
        p01 = self.revisions.approuver("synthetic-alpha", "user")
        self.assertEqual(p01["numero"], "P01")
        expected_p01 = hashlib.sha256(b"changed before approval").hexdigest()
        self.assertEqual(p01["livrables"][0]["empreinte"], expected_p01)
        self.assertEqual(p01["livrables"][0]["version"], 2)

        artifact.write_bytes(b"changed after approval")
        p02 = self.revisions.approuver("synthetic-alpha", "user")
        self.assertEqual(p02["numero"], "P02")
        self.assertEqual(self.revisions.revisions("synthetic-alpha")[0], p01)
        self.assertEqual(self.revisions.verifier("synthetic-alpha", "P01"), [{
            "chemin": "result.txt", "empreinte_figee": expected_p01,
            "empreinte_actuelle": hashlib.sha256(b"changed after approval").hexdigest(), "intact": False}])

        reloaded = RevisionStore(str(Path(self.tmp.name) / "revisions.json"), str(self.root))
        self.assertEqual([r["numero"] for r in reloaded.revisions("synthetic-alpha")], ["P01", "P02"])

    def test_routes_limit_approval_and_reject_paths_outside_deliverable_root(self):
        artifact = self.root / "result.txt"
        artifact.write_text("approved", encoding="utf-8")
        added = self.client.post("/api/v2/projects/synthetic-alpha/livrables", json={"chemin": "result.txt"})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(self.client.post("/api/v2/projects/synthetic-alpha/revisions",
                                          json={"approuvee_par": "codex"}).status_code, 403)
        approved = self.client.post("/api/v2/projects/synthetic-alpha/revisions",
                                    json={"approuvee_par": "user"})
        self.assertEqual((approved.status_code, approved.json()["numero"]), (200, "P01"))

        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            (self.root / "escape.txt").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation unavailable")
        self.assertEqual(self.client.post("/api/v2/projects/synthetic-alpha/livrables",
                                          json={"chemin": "escape.txt"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v2/projects/synthetic-alpha/livrables",
                                          json={"chemin": "../outside.txt"}).status_code, 400)
        self.assertEqual(self.client.get("/api/v2/projects/synthetic-alpha/revisions/P99/verifier").status_code, 404)

    def test_missing_file_and_empty_approval_do_not_create_a_revision(self):
        with self.assertRaises(FileNotFoundError):
            self.revisions.ajouter_livrable("synthetic-alpha", "1", "missing.txt")
        with self.assertRaises(ValueError):
            self.revisions.approuver("synthetic-alpha", "user")
        self.assertEqual(self.revisions.revisions("synthetic-alpha"), [])


if __name__ == "__main__":
    unittest.main()
