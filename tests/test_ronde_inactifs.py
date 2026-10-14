"""Ronde v3 : agents en ligne sans activite depuis 20 min (msg 2475-2477)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ronde import SEUIL_INACTIF, agents_inactifs  # noqa: E402

T0 = 1_000_000.0


class AgentsInactifsTests(unittest.TestCase):
    def test_actif_recemment_n_est_pas_signale(self):
        self.assertEqual(agents_inactifs({"grok"}, {"grok": T0 - 60}, T0, T0 - 7200), [])

    def test_inactif_depuis_le_seuil_est_signale(self):
        r = agents_inactifs({"grok"}, {"grok": T0 - SEUIL_INACTIF}, T0, T0 - 7200)
        self.assertEqual(r, [{"agent": "grok", "inactif_min": 20}])

    def test_sans_activite_connue_on_compte_depuis_le_demarrage(self):
        self.assertEqual(agents_inactifs({"gemini"}, {}, T0, T0 - 300), [])
        self.assertEqual(agents_inactifs({"gemini"}, {}, T0, T0 - 3600)[0]["inactif_min"], 60)

    def test_le_gestionnaire_et_les_absents_sont_exclus(self):
        self.assertEqual(agents_inactifs({"claude"}, {}, T0, T0 - 7200), [])
        self.assertEqual(agents_inactifs(set(), {"codex": T0 - 7200}, T0, T0 - 7200), [])


if __name__ == "__main__":
    unittest.main()
