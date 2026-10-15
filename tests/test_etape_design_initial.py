"""Étape design_initial entre concepts et conception (PILOTE.md v1.1, décision de Charles msg 2945)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jalons  # noqa: E402
import jobs  # noqa: E402
import ronde  # noqa: E402


class EtapeDesignInitialTests(unittest.TestCase):
    def test_ordre_identique_partout(self):
        self.assertEqual(jobs.ETAPES, ronde.ETAPES)
        self.assertEqual(jobs.ETAPES[2:5], ("concepts", "design_initial", "conception"))
        self.assertIn("design_initial", jalons.RECYCLE["J1"])
        self.assertNotIn("conception", jalons.RECYCLE["J1"])

    def test_j1_attend_les_taches_de_design(self):
        taches = [{"etape": "concepts", "etat": "fait"}, {"etape": "design_initial", "etat": "en_cours"}]
        dus, _ = ronde._jalons_dus("p", "moyen", taches, [])
        self.assertNotIn("J1", dus)
        taches[1]["etat"] = "fait"
        dus, _ = ronde._jalons_dus("p", "moyen", taches, [])
        self.assertIn("J1", dus)

    def test_j1_jamais_du_sans_tache_de_design(self):
        taches = [{"etape": e, "etat": "fait"} for e in ("probleme", "etat_art", "concepts")]
        dus, _ = ronde._jalons_dus("p", "moyen", taches, [])
        self.assertNotIn("J1", dus)

    def test_j1_recycle_exige_un_nouveau_design(self):
        taches = [{"etape": "concepts", "etat": "fait", "created_at": 10},
                  {"etape": "design_initial", "etat": "fait", "created_at": 20},
                  {"etape": "concepts", "etat": "fait", "created_at": 40}]
        jal = [{"id": 1, "jalon": "J1", "decision": "recycle", "decision_date": 30, "recycle_etape": "concepts"}]
        self.assertNotIn("J1", ronde._jalons_dus("p", "moyen", taches, jal)[0])
        taches.append({"etape": "design_initial", "etat": "fait", "created_at": 50})
        self.assertIn("J1", ronde._jalons_dus("p", "moyen", taches, jal)[0])

    def test_methode_de_l_etape_presente_dans_pilote(self):
        texte = (Path(__file__).resolve().parents[1] / "docs" / "PILOTE.md").read_text("utf-8")
        section = texte.split("## design_initial", 1)[1].split("\n## ", 1)[0]
        for mot in ("designer-produit", "Critère de sortie", "Charles a choisi"):
            self.assertIn(mot, section)


if __name__ == "__main__":
    unittest.main()
