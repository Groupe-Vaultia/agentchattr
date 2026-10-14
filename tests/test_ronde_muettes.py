"""Ronde v4 : taches en_cours sans message depuis une heure (msg 2647)."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402
import projects  # noqa: E402
from executions import ExecutionStore  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jobs import JobStore  # noqa: E402
from ronde import taches_muettes  # noqa: E402

T0 = 1_000_000.0


def _tache(tid, etat="en_cours", projet="quad"):
    return {"id": tid, "projet_id": projet, "titre": f"t{tid}", "responsable": "grok", "etat": etat}


class TachesMuettesTests(unittest.TestCase):
    def test_un_message_recent_n_est_pas_signale(self):
        msgs = {"tache-7": T0 - 3599}
        self.assertEqual(taches_muettes([_tache(7)], msgs, T0), [])

    def test_une_heure_pile_est_signalee(self):
        msgs = {"tache-7": T0 - 3600}
        self.assertEqual(taches_muettes([_tache(7)], msgs, T0), [{
            "tache_id": 7, "projet_id": "quad", "titre": "t7",
            "responsable": "grok", "silence_s": 3600,
        }])

    def test_sans_message_la_tache_n_est_pas_datee(self):
        self.assertEqual(taches_muettes([_tache(7)], {}, T0), [])

    def test_seul_en_cours_compte(self):
        msgs = {f"tache-{i}": T0 - 7200 for i in (1, 2, 3, 4, 5)}
        taches = [
            _tache(1, "a_faire"), _tache(2, "attend_charles"),
            _tache(3, "bloque"), _tache(4, "fait"), _tache(5, "en_cours"),
        ]
        r = taches_muettes(taches, msgs, T0)
        self.assertEqual([x["tache_id"] for x in r], [5])

    def test_le_seuil_se_regle_et_le_tri_est_par_id(self):
        msgs = {"tache-9": T0 - 50, "tache-2": T0 - 80}
        r = taches_muettes([_tache(9), _tache(2)], msgs, T0, seuil=60)
        self.assertEqual([x["tache_id"] for x in r], [2])
        self.assertEqual(r[0]["silence_s"], 80)


class RondeMuettesRouteTests(unittest.TestCase):
    def test_la_route_compte_la_tache_muette_et_ignore_un_projet_en_veille(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ancien = projects._FILE
            projects.configurer(root / "projects.json")
            if ancien:
                self.addCleanup(lambda: projects.configurer(ancien))
            actif = projects.creer("Quad actif")
            veille = projects.creer("Quad veille")
            projects.definir_statut(veille, "veille", par_id=True)
            jobs = JobStore(str(root / "jobs.json"))
            executions = ExecutionStore(str(root / "executions.json"))
            equipe = [{"agent": "grok", "role": "producteur"}]
            muette, err = jobs.create_tache(actif, "Dessiner", "conception", "grok", "claude", equipe=equipe)
            self.assertEqual(err, "")
            jobs.update_tache(muette["id"], {"etat": "en_cours"})
            autre, err = jobs.create_tache(veille, "Dormir", "conception", "grok", "claude", equipe=equipe)
            self.assertEqual(err, "")
            jobs.update_tache(autre["id"], {"etat": "en_cours"})
            vieux = time.time() - 7200
            messages = [
                {"channel": f"tache-{muette['id']}", "timestamp": vieux},
                {"channel": f"tache-{autre['id']}", "timestamp": vieux},
                {"channel": "developpement-de-pro", "timestamp": vieux},
            ]
            for name, value in (("jobs", jobs), ("executions", executions), ("pieces", None), ("jalons", None)):
                patcher = mock.patch.object(app, name, value)
                patcher.start()
                self.addCleanup(patcher.stop)
            inactifs = mock.patch.object(app, "_agents_inactifs", return_value=[])
            inactifs.start()
            self.addCleanup(inactifs.stop)
            class _Journal:
                def get_since(self, since_id=0):
                    return messages

            journal = mock.patch.object(app, "store", _Journal())
            journal.start()
            self.addCleanup(journal.stop)
            client = TestClient(app.app)
            self.addCleanup(client.close)
            corps = client.get("/api/v2/ronde").json()
            self.assertEqual([t["tache_id"] for t in corps["taches_muettes"]], [muette["id"]])
            self.assertGreaterEqual(corps["taches_muettes"][0]["silence_s"], 7200)
            self.assertFalse(corps["rien_a_faire"])

            messages[0]["timestamp"] = time.time()
            corps = client.get("/api/v2/ronde").json()
            self.assertEqual(corps["taches_muettes"], [])
            self.assertTrue(corps["rien_a_faire"])


if __name__ == "__main__":
    unittest.main()
