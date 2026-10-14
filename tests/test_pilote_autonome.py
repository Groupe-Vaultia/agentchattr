"""Tests ciblés du pilote autonome, contrat SOCLE-SHOP.md v1.1.

v0.3 (2026-10-14, codex) : couvre les reprises après recycle et l’acceptation des formats CAO à l’upload.
v0.2 (2026-10-13, codex) : ajoute les routes P1, la fiche projet P2 et le moteur de ronde P4.
v0.1 (2026-10-13, codex) : règles de stockage, validation et décision des jalons P1.
"""

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jalons
import projects
import ronde
import app
from executions import ExecutionStore
from jobs import JobStore
from store import MessageStore


class JalonStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "jalons.json"
        self.store = jalons.JalonStore(str(self.path))

    def _preparer(self, projet_id="alpha", **overrides):
        champs = {
            "jalon": "J1",
            "resultats": "Prototype mesuré",
            "criteres": [{"nom": "masse", "cible": "< 2 kg", "mesure": "1.8 kg", "etat": "atteint"}],
            "risques": ["masse", ""],
            "reste": "Essai thermique",
            "recommandation": "go",
            "raison": "Les critères prioritaires sont atteints.",
        }
        champs.update(overrides)
        return self.store.preparer(projet_id, champs)

    def test_preparation_normalizes_fields_persists_and_records_history_events(self):
        jalon, erreur = self._preparer()

        self.assertEqual(erreur, "")
        self.assertEqual(jalon["projet_id"], "alpha")
        self.assertEqual(jalon["criteres"], [{"nom": "masse", "cible": "< 2 kg",
                                                 "mesure": "1.8 kg", "etat": "atteint"}])
        self.assertEqual(jalon["risques"], ["masse"])

        decided, erreur = self.store.decider(jalon["id"], "go", note="J1 validé")
        self.assertEqual(erreur, "")
        self.assertEqual(decided["decision"], "go")

        reloaded = jalons.JalonStore(str(self.path))
        self.assertEqual(reloaded.lister("alpha"), [decided])
        history = jalons.pour_historique(reloaded.lister())
        self.assertEqual(len(history), 2)
        self.assertIn("recommandation go", history[0]["decision"])
        self.assertIn("décision de Charles : go (J1 validé)", history[1]["decision"])

    def test_only_one_undecided_jalon_per_project_and_projects_are_isolated(self):
        first, erreur = self._preparer("alpha")
        self.assertEqual(erreur, "")

        blocked, message = self._preparer("alpha", jalon="J2")
        self.assertIsNone(blocked)
        self.assertIn("en attente", message)

        other, erreur = self._preparer("beta", jalon="J2")
        self.assertEqual(erreur, "")
        self.assertEqual([j["projet_id"] for j in self.store.lister()], ["alpha", "beta"])

        self.store.decider(first["id"], "hold")
        next_jalon, erreur = self._preparer("alpha", jalon="J2")
        self.assertEqual(erreur, "")
        self.assertEqual(next_jalon["jalon"], "J2")

    def test_invalid_recommendation_reason_criteria_and_risk_shapes_are_rejected(self):
        invalid_cases = [
            ({"recommandation": "ship"}, "recommandation"),
            ({"raison": "  "}, "raison requise"),
            ({"criteres": [{"nom": "", "etat": "atteint"}]}, "criteres"),
            ({"criteres": [{"nom": "masse", "etat": "inconnu"}]}, "criteres"),
            ({"risques": "masse"}, "risques"),
        ]
        for overrides, expected in invalid_cases:
            with self.subTest(overrides=overrides):
                jalon, erreur = self._preparer(**overrides)
                self.assertIsNone(jalon)
                self.assertIn(expected, erreur)

    def test_recycle_requires_a_stage_before_the_jalon_and_decisions_are_final(self):
        jalon, erreur = self._preparer("alpha", jalon="J1", recommandation="recycle")
        self.assertEqual(erreur, "")

        rejected, message = self.store.decider(jalon["id"], "recycle", recycle_etape="essais")
        self.assertIsNone(rejected)
        self.assertIn("recycle_etape", message)

        decided, erreur = self.store.decider(jalon["id"], "recycle", note="reprendre", recycle_etape="concepts")
        self.assertEqual(erreur, "")
        self.assertEqual(decided["recycle_etape"], "concepts")

        second, message = self.store.decider(jalon["id"], "go")
        self.assertIsNone(second)
        self.assertIn("deja decide", message)

        # recycle_etape n'a de sens que pour recycle; les autres décisions l'effacent.
        other, erreur = self._preparer("beta", jalon="J2")
        self.assertEqual(erreur, "")
        decided, erreur = self.store.decider(other["id"], "hold", recycle_etape="essais")
        self.assertEqual(erreur, "")
        self.assertEqual(decided["recycle_etape"], "")


class ProjectFicheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "projects.json"
        projects.configurer(self.path)
        self.projet_id = projects.creer("Synthetic Pilot")

    def test_valid_fiche_is_normalized_persisted_and_keeps_project_identity(self):
        fields = {
            "objectif": "  Réduire la masse  ",
            "livrable_attendu": "Prototype",
            "code": "PILOT-01",
            "niveau": "lourd",
            "trl": 4,
            "horizon": "H2",
            "type": "mécanique",
            "ambition": "Tester une structure légère",
            "criteres": [{"nom": "masse", "cible": "< 2 kg"}],
            "hypotheses": [{"texte": "L'alliage suffit", "source": "claude", "etat": "a_verifier"}],
            "risques": [{"texte": "Fragilité", "type": "technique", "etape": "conception"}],
            "questions": [{"texte": "Quel usage?", "reponse": "Prototype de table"}],
        }

        project, error = projects.definir_fiche(self.projet_id, fields)

        self.assertEqual(error, "")
        self.assertEqual(project["nom"], "Synthetic Pilot")
        self.assertEqual(project["objectif"], "Réduire la masse")
        self.assertEqual(project["niveau"], "lourd")
        self.assertEqual(project["trl"], 4)
        self.assertEqual(project["criteres"], fields["criteres"])
        self.assertEqual(project["hypotheses"], fields["hypotheses"])
        self.assertEqual(projects.lister()["v2"]["projets"][self.projet_id]["risques"], fields["risques"])

    def test_unknown_fields_invalid_enums_and_out_of_range_trl_are_rejected_without_mutation(self):
        projects.definir_fiche(self.projet_id, {"objectif": "Initial"})
        invalid = [
            ({"unexpected": "x"}, "inconnus"),
            ({"niveau": "urgent"}, "niveau"),
            ({"horizon": "H4"}, "horizon"),
            ({"trl": 10}, "trl"),
            ({"trl": True}, "trl"),
            ({"risques": [{"texte": "x", "type": "politique"}]}, "risques"),
            ({"hypotheses": [{"texte": "x", "source": "user"}]}, "hypotheses"),
            ({"criteres": [{"nom": "", "cible": "x"}]}, "criteres"),
        ]
        for fields, expected in invalid:
            with self.subTest(fields=fields):
                result, error = projects.definir_fiche(self.projet_id, fields)
                self.assertIsNone(result)
                self.assertIn(expected, error)
                self.assertEqual(projects.lister()["v2"]["projets"][self.projet_id]["objectif"], "Initial")


class RondeMoteurTests(unittest.TestCase):
    def test_due_jalon_blocks_next_work_and_pending_decision_waits_for_charles(self):
        projects_by_id = {"alpha": {"nom": "Alpha", "statut": "actif", "niveau": "moyen"}}
        tasks = [
            {"id": 1, "projet_id": "alpha", "etape": "probleme", "etat": "fait"},
            {"id": 2, "projet_id": "alpha", "etape": "etat_art", "etat": "fait"},
            {"id": 3, "projet_id": "alpha", "etape": "concepts", "etat": "fait"},
            {"id": 4, "projet_id": "alpha", "etape": "conception", "etat": "a_faire", "titre": "Dessiner",
             "responsable": "gemini"},
        ]

        due = ronde.ronde(projects_by_id, tasks, [], methodes={"conception": "Dimensionner puis contrôler."})
        self.assertEqual(due["jalons_dus"], [{"projet_id": "alpha", "jalon": "J1"}])
        self.assertEqual(due["prochaines"], [])

        pending = ronde.ronde(projects_by_id, tasks, [],
                              jalons=[{"id": 1, "projet_id": "alpha", "jalon": "J1",
                                        "recommandation": "go", "decision": ""}])
        self.assertEqual(pending["jalons_en_attente"], [{"jalon_id": 1, "projet_id": "alpha", "jalon": "J1",
                                                           "recommandation": "go"}])
        self.assertEqual(pending["jalons_dus"], [])
        self.assertEqual(pending["prochaines"], [])

    def test_recycle_requests_rework_then_reopens_jalon_after_all_rework_is_done(self):
        projects_by_id = {"alpha": {"nom": "Alpha", "statut": "actif", "niveau": "moyen"}}
        tasks = [
            {"id": 1, "projet_id": "alpha", "etape": "probleme", "etat": "fait", "created_at": 10},
            {"id": 2, "projet_id": "alpha", "etape": "etat_art", "etat": "fait", "created_at": 20},
            {"id": 3, "projet_id": "alpha", "etape": "concepts", "etat": "fait", "created_at": 30},
            {"id": 4, "projet_id": "alpha", "etape": "conception", "etat": "a_faire", "responsable": "gemini",
             "created_at": 40},
        ]
        recycle = [{"id": 1, "projet_id": "alpha", "jalon": "J1", "decision": "recycle",
                    "decision_date": 100, "recycle_etape": "concepts"}]

        without_rework = ronde.ronde(projects_by_id, tasks, [], recycle)
        self.assertEqual(without_rework["jalons_dus"], [])
        self.assertEqual(without_rework["recyclages"], [{"projet_id": "alpha", "jalon": "J1",
                                                          "etape": "concepts", "jalon_id": 1}])
        self.assertEqual(without_rework["prochaines"], [])

        rework = {"id": 5, "projet_id": "alpha", "etape": "concepts", "etat": "a_faire",
                  "responsable": "gemini", "titre": "Reprendre les concepts", "created_at": 101}
        with_rework = ronde.ronde(projects_by_id, tasks + [rework], [], recycle)
        self.assertEqual(with_rework["recyclages"], [])
        self.assertEqual(with_rework["jalons_dus"], [])
        self.assertEqual([t["tache_id"] for t in with_rework["prochaines"]], [5])

        rework["etat"] = "fait"
        after_rework = ronde.ronde(projects_by_id, tasks + [rework], [], recycle)
        self.assertEqual(after_rework["recyclages"], [])
        self.assertEqual(after_rework["jalons_dus"], [{"projet_id": "alpha", "jalon": "J1"}])
        self.assertEqual(after_rework["prochaines"], [])

        after_go = ronde.ronde(projects_by_id, tasks + [rework], [], recycle + [
            {"id": 2, "projet_id": "alpha", "jalon": "J1", "decision": "go", "decision_date": 200},
        ])
        self.assertEqual(after_go["jalons_dus"], [])
        self.assertEqual([t["tache_id"] for t in after_go["prochaines"]], [4])

    def test_go_opens_next_stage_and_assigns_method_only_to_eligible_responsible(self):
        projects_by_id = {"alpha": {"nom": "Alpha", "statut": "actif", "niveau": "moyen"}}
        tasks = [
            {"id": 1, "projet_id": "alpha", "etape": "probleme", "etat": "fait"},
            {"id": 2, "projet_id": "alpha", "etape": "etat_art", "etat": "fait"},
            {"id": 3, "projet_id": "alpha", "etape": "concepts", "etat": "fait"},
            {"id": 4, "projet_id": "alpha", "etape": "conception", "etat": "a_faire", "titre": "Dessiner",
             "responsable": "gemini"},
            {"id": 5, "projet_id": "alpha", "etape": "conception", "etat": "a_faire", "titre": "Analyser",
             "responsable": "grok"},
        ]
        open_execution = [{"id": "e1", "projet_id": "alpha", "agent": "grok", "etat": "actif"}]
        result = ronde.ronde(projects_by_id, tasks, open_execution,
                             jalons=[{"id": 1, "projet_id": "alpha", "jalon": "J1", "decision": "go"}],
                             methodes={"conception": "Dimensionner puis contrôler."})

        self.assertEqual(result["jalons_dus"], [])
        self.assertEqual(result["prochaines"], [{"projet_id": "alpha", "tache_id": 4, "titre": "Dessiner",
                                                  "etape": "conception", "responsable": "gemini",
                                                  "methode_etape": "Dimensionner puis contrôler."}])


class PiloteRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        projects.configurer(self.root / "projects.json")
        self.alpha = projects.creer("Synthetic Alpha")
        stores = {
            "store": MessageStore(str(self.root / "messages.jsonl")),
            "jalons": jalons.JalonStore(str(self.root / "jalons.json")),
            "jobs": JobStore(str(self.root / "jobs.json")),
            "executions": ExecutionStore(str(self.root / "executions.json")),
        }
        for name, value in stores.items():
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(app, "_methodes_etapes", return_value={
            "probleme": "Définir le problème puis ses critères de sortie."})
        patcher.start()
        self.addCleanup(patcher.stop)
        channels = mock.patch.dict(app.room_settings, {"channels": ["general", "developpement-de-pro"]})
        channels.start()
        self.addCleanup(channels.stop)
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    def test_jalon_routes_enforce_single_pending_and_user_only_final_decisions(self):
        created = self.client.post(f"/api/v2/projects/{self.alpha}/jalons", json={
            "jalon": "J1", "recommandation": "hold", "raison": "Le coût dépasse le budget.",
            "criteres": [], "risques": ["coût"],
        })
        self.assertEqual(created.status_code, 200, created.text)
        jalon_id = created.json()["id"]
        self.assertEqual(self.client.get(f"/api/v2/projects/{self.alpha}/jalons").json()["jalons"][0]["id"], jalon_id)
        self.assertEqual(self.client.post(f"/api/v2/projects/{self.alpha}/jalons", json={
            "jalon": "J2", "recommandation": "go", "raison": "Second jalon", "criteres": [],
        }).status_code, 409)

        self.assertEqual(self.client.post(f"/api/v2/jalons/{jalon_id}/decision", json={
            "par": "claude", "decision": "hold",
        }).status_code, 403)
        decided = self.client.post(f"/api/v2/jalons/{jalon_id}/decision", json={
            "par": "user", "decision": "hold", "note": "Attendre un devis.",
        })
        self.assertEqual(decided.status_code, 200, decided.text)
        self.assertEqual(projects.lister()["v2"]["projets"][self.alpha]["statut"], "veille")
        self.assertEqual(self.client.post(f"/api/v2/jalons/{jalon_id}/decision", json={
            "par": "user", "decision": "go",
        }).status_code, 409)

    def test_project_fiche_route_validates_fields_and_unknown_project(self):
        response = self.client.patch(f"/api/v2/projects/{self.alpha}/fiche", json={
            "objectif": "Réduire la masse", "niveau": "leger", "trl": 3,
            "horizon": "H1", "criteres": [{"nom": "masse", "cible": "< 2 kg"}],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["objectif"], "Réduire la masse")
        self.assertEqual(self.client.patch(f"/api/v2/projects/{self.alpha}/fiche", json={
            "niveau": "urgent",
        }).status_code, 400)
        self.assertEqual(self.client.patch("/api/v2/projects/no-project/fiche", json={
            "objectif": "Missing",
        }).status_code, 404)

    def test_project_launch_posts_attributed_claude_prompt_and_rejects_duplicate_name(self):
        response = self.client.post("/api/v2/projects", json={
            "nom": "Prototype Alpha", "objectif": "Réduire la masse de 20 %",
        })
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual((data["projet_id"], data["channel"]), ("prototype-alpha", "developpement-de-pro"))
        messages = [m for m in app.store.get_recent(10) if m.get("projet_id") == "prototype-alpha"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["sender"], "user")
        self.assertIn("@claude Lancement guidé", messages[0]["text"])
        self.assertEqual(messages[0]["channel"], "developpement-de-pro")
        self.assertEqual(self.client.post("/api/v2/projects", json={
            "nom": "Prototype Alpha", "objectif": "Autre objectif",
        }).status_code, 409)

    def test_upload_accepts_cad_exchange_and_native_formats_advertised_by_launch_form(self):
        with mock.patch.object(app, "config", {"images": {"upload_dir": str(self.root / "uploads")}}):
            for extension in (".dxf", ".step", ".stp", ".stl", ".3mf", ".fcstd"):
                with self.subTest(extension=extension):
                    response = self.client.post(
                        "/api/upload", files={"file": (f"part{extension}", b"synthetic CAD data")},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["name"], f"part{extension}")
                    self.assertTrue(response.json()["url"].startswith("/uploads/"))

    def test_round_route_returns_next_task_with_method_for_current_stage(self):
        task, error = app.jobs.create_tache(
            self.alpha, "Cadrer le problème", "probleme", "gemini", "claude",
            equipe=[{"agent": "gemini", "role": "producteur"}], critere="Problème validé",
        )
        self.assertEqual(error, "")
        response = self.client.get("/api/v2/ronde")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["prochaines"], [{"projet_id": self.alpha, "tache_id": task["id"],
                                                   "titre": "Cadrer le problème", "etape": "probleme",
                                                   "responsable": "gemini",
                                                   "methode_etape": "Définir le problème puis ses critères de sortie."}])




if __name__ == "__main__":
    unittest.main()
