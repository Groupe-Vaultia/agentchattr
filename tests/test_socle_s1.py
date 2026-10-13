"""S1 contract tests for project migration and per-trigger memory isolation.

v0.3 (2026-10-12, codex): keep ID-only v2 mutations distinct from legacy name routes.
v0.2 (2026-10-12, codex): distinguish a legacy name from another project's slug.
v0.1 (2026-10-12, codex): synthetic v1 migration, compatibility, and
multi-project trigger coverage for SOCLE-SHOP.md v0.3.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import projects
from agents import AgentTrigger
from store import MessageStore


class _Registry:
    def is_registered(self, _name):
        return True


class SocleS1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "projects.json"
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def _v1(self, projects_by_name=None, active="Alpha"):
        data = {
            "projets": projects_by_name or {
                "Alpha": {"memoire": "MEMO_ALPHA_ONLY", "cree": 100, "channels": ["legacy-alpha"]},
                "Beta": {"memoire": "MEMO_BETA_ONLY", "cree": 200, "channels": ["legacy-beta"]},
            },
            "actif": active,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        projects.configurer(self.path)
        return data

    def _v2(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _queue(self):
        return [json.loads(line) for line in (self.root / "codex_queue.jsonl").read_text().splitlines()]

    def test_migrates_synthetic_v1_without_losing_projects_memory_or_channels(self):
        old = self._v1()
        new = self._v2()
        backup = self.root / "projects.v1.json"

        self.assertEqual(new["version"], 2)
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), old)
        self.assertEqual(new["defaut"], "alpha")
        self.assertEqual(new["projets"]["alpha"]["nom"], "Alpha")
        self.assertEqual(new["projets"]["alpha"]["memoire"], "MEMO_ALPHA_ONLY")
        self.assertEqual(new["projets"]["alpha"]["channels"], ["legacy-alpha"])
        self.assertEqual(new["projets"]["beta"]["memoire"], "MEMO_BETA_ONLY")
        self.assertEqual(new["projets"]["beta"]["channels"], ["legacy-beta"])
        self.assertTrue(all(p["statut"] == "actif" for p in new["projets"].values()))

    def test_restart_reloads_v2_without_running_migration_again(self):
        self._v1()
        before = self.path.read_bytes()
        backup = self.root / "projects.v1.json"
        backup_before = backup.read_bytes()

        projects.configurer(self.path)

        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(backup.read_bytes(), backup_before)

    def test_interleaved_triggers_in_one_channel_keep_their_own_project(self):
        self._v1()
        messages = MessageStore(str(self.root / "messages.jsonl"))
        trigger = AgentTrigger(_Registry(), str(self.root))
        first = messages.add("user", "Work on Alpha", channel="atelier", projet_id="alpha")
        second = messages.add("user", "Work on Beta", channel="atelier", projet_id="beta")
        trigger.trigger_sync("codex", "user: Work on Alpha", channel="atelier", projet_id=first["projet_id"])
        trigger.trigger_sync("codex", "user: Work on Beta", channel="atelier", projet_id=second["projet_id"])

        self.assertEqual([m["projet_id"] for m in messages.get_recent(2)], ["alpha", "beta"])
        self.assertEqual([item["projet_id"] for item in self._queue()], ["alpha", "beta"])
        a = self.client.get("/api/projects/alpha/memory")
        b = self.client.get("/api/projects/beta/memory")
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(a.json()["memoire"], "MEMO_ALPHA_ONLY")
        self.assertEqual(b.json()["memoire"], "MEMO_BETA_ONLY")
        self.assertNotIn("MEMO_BETA_ONLY", a.text)
        self.assertNotIn("MEMO_ALPHA_ONLY", b.text)

    def test_unknown_project_is_404_and_untagged_trigger_has_no_fallback(self):
        self._v1(active="Alpha")
        response = self.client.get("/api/projects/missing/memory")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("MEMO_ALPHA_ONLY", response.text)

        trigger = AgentTrigger(_Registry(), str(self.root))
        trigger.trigger_sync("codex", "user: Untagged work", channel="atelier")
        self.assertNotIn("projet_id", self._queue()[0])
        # The legacy display default must not become the trigger's project.
        self.assertNotIn("MEMO_ALPHA_ONLY", json.dumps(self._queue()))

    def test_v1_api_shape_and_name_based_routes_still_work(self):
        self._v1()
        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["actif"], "Alpha")
        self.assertEqual(body["projets"]["Alpha"]["memoire"], "MEMO_ALPHA_ONLY")
        self.assertIn("v2", body)

        response = self.client.post("/api/projects/Beta/memory", json={"memory": "UPDATED_BETA"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/projects").json()["projets"]["Beta"]["memoire"], "UPDATED_BETA")

    def test_colliding_slugs_get_stable_numeric_suffixes(self):
        self._v1({
            "Café": {"memoire": "ONE", "cree": 1, "channels": []},
            "Cafe": {"memoire": "TWO", "cree": 2, "channels": []},
            "CAFE": {"memoire": "THREE", "cree": 3, "channels": []},
        }, active="Café")
        values = self._v2()["projets"]
        self.assertEqual(set(values), {"cafe", "cafe-2", "cafe-3"})
        self.assertEqual({p["memoire"] for p in values.values()}, {"ONE", "TWO", "THREE"})
        self.assertEqual(len({p["nom"] for p in values.values()}), 3)

    def test_creating_name_equal_to_another_projects_slug_creates_distinct_project(self):
        self._v1({"Café": {"memoire": "FIRST", "cree": 1, "channels": []}}, active="Café")

        created_id = projects.creer("cafe", "SECOND")

        self.assertEqual(created_id, "cafe-2")
        projects_by_name = projects.lister()["projets"]
        self.assertEqual(projects_by_name["Café"]["memoire"], "FIRST")
        self.assertEqual(projects_by_name["cafe"]["memoire"], "SECOND")

    def test_legacy_name_route_updates_exact_name_when_it_matches_another_id(self):
        self._v1({
            "Café": {"memoire": "FIRST", "cree": 1, "channels": []},
            "cafe": {"memoire": "SECOND", "cree": 2, "channels": []},
        }, active="Café")

        response = self.client.post("/api/projects/cafe/memory", json={"memory": "UPDATED_SECOND"})

        self.assertEqual(response.status_code, 200)
        projects_by_name = self.client.get("/api/projects").json()["projets"]
        self.assertEqual(projects_by_name["Café"]["memoire"], "FIRST")
        self.assertEqual(projects_by_name["cafe"]["memoire"], "UPDATED_SECOND")

    def test_v2_mutations_use_strict_id_when_a_name_collides(self):
        self._v1({
            "Café": {"memoire": "FIRST", "cree": 1, "channels": []},
            "cafe": {"memoire": "SECOND", "cree": 2, "channels": []},
        }, active="Café")

        self.assertEqual(self.client.post("/api/projects/cafe/status", json={"status": "veille"}).status_code, 200)
        self.assertEqual(self.client.post("/api/v2/projects/cafe/status", json={"status": "arrete"}).status_code, 200)
        self.assertEqual(self.client.post("/api/v2/projects/cafe/memory", json={"memory": "UPDATED_FIRST"}).status_code, 200)
        self.assertEqual(self.client.post("/api/v2/projects/assign", json={"channel": "atelier", "projet_id": "cafe"}).status_code, 200)

        by_id = self.client.get("/api/projects").json()["v2"]["projets"]
        self.assertEqual((by_id["cafe"]["nom"], by_id["cafe"]["statut"], by_id["cafe"]["memoire"]),
                         ("Café", "arrete", "UPDATED_FIRST"))
        self.assertEqual(by_id["cafe"]["channels"], ["atelier"])
        self.assertEqual((by_id["cafe-2"]["nom"], by_id["cafe-2"]["statut"], by_id["cafe-2"]["memoire"]),
                         ("cafe", "veille", "SECOND"))
        self.assertEqual(self.client.post("/api/v2/projects/Café/status", json={"status": "actif"}).status_code, 404)

        self.assertEqual(self.client.delete("/api/v2/projects/cafe-2").status_code, 200)
        self.assertEqual(set(self.client.get("/api/projects").json()["v2"]["projets"]), {"cafe"})


if __name__ == "__main__":
    unittest.main()
