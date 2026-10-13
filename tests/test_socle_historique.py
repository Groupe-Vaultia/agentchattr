"""Project history merge contract.

v0.1 (2026-10-12, codex): cover filtering, ordering, shape, and bounded summaries.
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

import historique
import app
import projects
from executions import ExecutionStore
from revisions import RevisionStore
from store import MessageStore


class SocleHistoryTests(unittest.TestCase):
    def test_merges_only_project_entries_newest_first_with_one_line_summaries(self):
        rows = historique.historique("alpha", messages=[
            {"id": "m1", "projet_id": "alpha", "sender": "user", "text": "one\ntwo", "timestamp": 10},
            {"id": "m2", "projet_id": "beta", "sender": "user", "text": "private elsewhere", "timestamp": 99},
            {"id": 3, "projet_id": "alpha", "sender": "bad", "text": "bad id", "timestamp": 8},
            {"id": "m-long", "projet_id": "alpha", "sender": "user", "text": "x" * 250, "timestamp": 20},
        ], executions=[
            {"id": "e1", "projet_id": "alpha", "agent": "claude", "consigne": "run", "debut": 11, "fin": 13},
        ], revisions=[
            {"projet_id": "alpha", "numero": "P01", "approuvee_par": "user", "heure": 15,
             "livrables": [{}, {}]},
        ], jalons=[
            {"id": "j1", "projet_id": "alpha", "jalon": "J1", "decision": "", "date": 14},
        ], decisions=[
            {"id": "d1", "projet_id": "alpha", "acteur": "claude", "quoi": "recycle", "heure": 12},
        ])

        self.assertEqual([r["ref"] for r in rows], ["m-long", "P01", "j1", "e1", "d1", "m1"])
        self.assertEqual([r["type"] for r in rows], ["message", "revision", "jalon", "execution", "decision", "message"])
        self.assertEqual(rows[-1]["resume"], "one two")
        self.assertEqual(rows[0]["resume"], "x" * 199 + "…")
        self.assertTrue(all(len(r["resume"]) <= 200 and "\n" not in r["resume"] for r in rows))
        self.assertTrue(all(set(r) == {"heure", "type", "ref", "acteur", "resume"} for r in rows))

    def test_malformed_records_and_limits_are_safe(self):
        rows = historique.historique("alpha", messages=[None, {},
            {"id": "ok", "projet_id": "alpha", "sender": "user", "text": "x", "timestamp": 1}], limite=1)
        self.assertEqual([r["ref"] for r in rows], ["ok"])
        self.assertEqual(historique.historique("alpha", messages=[
            {"id": "ok", "projet_id": "alpha", "sender": "user", "text": "x", "timestamp": 1}], limite=0), [])
        self.assertEqual(historique.historique("alpha", messages=None), [])
        self.assertEqual(historique.historique(1, messages=[]), [])
        self.assertEqual(historique.par_jour([None, {"heure": "bad"}, {"heure": 0, "ref": "old"}])[0][1][0]["ref"], "old")

    def test_project_history_route_converts_integer_message_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects.configurer(root / "projects.json")
            alpha = projects.creer("Synthetic Alpha")
            beta = projects.creer("Synthetic Beta")
            messages = MessageStore(str(root / "messages.jsonl"))
            messages.add("user", "alpha message", projet_id=alpha)
            messages.add("user", "beta message", projet_id=beta)
            executions = ExecutionStore(str(root / "executions.json"))
            revisions = RevisionStore(str(root / "revisions.json"), str(root / "deliverables"))
            patchers = [mock.patch.object(app, "store", messages),
                        mock.patch.object(app, "executions", executions),
                        mock.patch.object(app, "revisions", revisions)]
            for patcher in patchers:
                patcher.start()
                self.addCleanup(patcher.stop)
            client = TestClient(app.app)
            self.addCleanup(client.close)

            rows = client.get(f"/api/v2/projects/{alpha}/historique").json()
            flattened = [entry for _, entries in rows for entry in entries]
            self.assertEqual(len(flattened), 1)
            self.assertEqual(flattened[0]["ref"], "0")
            self.assertEqual(flattened[0]["resume"], "alpha message")
            self.assertEqual(client.get("/api/v2/projects/missing/historique").status_code, 404)


if __name__ == "__main__":
    unittest.main()
