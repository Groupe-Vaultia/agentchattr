"""Registre, comportements propres a Vaultia : une relance reprend le nom de base.

Le fork evince une instance morte (inscrite depuis plus de EVICT_GRACE et silencieuse) avant
d'attribuer un slot, et leve la reservation d'un nom quand plus aucun exemplaire de l'agent
n'est vivant. Sans ces deux regles, la relance d'un agent par le watchdog prenait `<base>-2`
(claude-2, grok-2) et les @mentions ne lui parvenaient plus. Le dual : une instance qui vient
de s'inscrire n'est jamais evincee (multi-instance et jetons vivants, test_identity_contract).
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from registry import RuntimeRegistry  # noqa: E402


class VaultiaRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = RuntimeRegistry(data_dir=self.tmp.name)
        self.reg.seed({"claude": {"label": "Claude", "color": "#da7756"},
                       "grok": {"label": "Grok", "color": "#e11d48"}})

    def _vieillir(self, nom, secondes=60):
        self.reg._instances[nom].registered_at = time.time() - secondes

    def test_une_relance_reprend_le_nom_d_une_instance_morte(self):
        mort = self.reg.register("claude")
        self._vieillir("claude")
        with mock.patch("mcp_bridge.is_online", return_value=False):
            relance = self.reg.register("claude")
        self.assertEqual(relance["name"], "claude")
        self.assertIsNone(self.reg.resolve_token(mort["token"]), "le jeton de l'instance morte ne vaut plus")

    def test_le_dual_une_instance_qui_vient_de_s_inscrire_n_est_pas_evincee(self):
        premiere = self.reg.register("claude")
        with mock.patch("mcp_bridge.is_online", return_value=False):
            seconde = self.reg.register("claude")
        self.assertEqual(seconde["name"], "claude-2")
        self.assertEqual(self.reg.resolve_token(premiere["token"])["name"], "claude-1")

    def test_une_instance_vivante_n_est_pas_evincee_meme_ancienne(self):
        self.reg.register("claude")
        self._vieillir("claude")
        with mock.patch("mcp_bridge.is_online", return_value=True):
            seconde = self.reg.register("claude")
        self.assertEqual(seconde["name"], "claude-2")

    def test_la_reservation_du_nom_est_levee_quand_plus_aucun_exemplaire_ne_vit(self):
        # grok tombe (crash timeout -> desinscription = nom reserve GRACE_PERIOD), puis la
        # relance du watchdog arrive apres 15 s : elle doit reprendre « grok », pas « grok-2 ».
        self.reg.register("grok")
        self.reg.deregister("grok")
        self.assertIn("grok", self.reg._reserved)
        with mock.patch("mcp_bridge.is_online", return_value=False):
            relance = self.reg.register("grok")
        self.assertEqual(relance["name"], "grok")

    def test_le_dual_la_reservation_tient_si_un_exemplaire_vit_encore(self):
        self.reg.register("claude")
        self.reg.register("claude")                   # claude-1 + claude-2
        self.reg.deregister("claude-2")               # claude-2 reserve ; claude-1 vit encore
        with mock.patch("mcp_bridge.is_online", return_value=True):
            troisieme = self.reg.register("claude")
        self.assertNotEqual(troisieme["name"], "claude-2", "le nom reserve n'est pas repris tant qu'un exemplaire vit")


if __name__ == "__main__":
    unittest.main()
