"""Lot A1 : plans et modeles d'une piece servis depuis la tour (fichiers_pieces.py, msg 2557)."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tests.test_pieces_contract as _contrat  # noqa: E402  (module, pour ne pas recollecter ses tests)


class PiecesFichiersTests(unittest.TestCase):
    setUp = _contrat.PiecesContractTests.setUp
    _restore_globals = _contrat.PiecesContractTests._restore_globals
    _create_piece = _contrat.PiecesContractTests._create_piece

    def _preparer(self):
        piece = self._create_piece("Plaque")
        numero = self.client.get(f"/api/v2/pieces/{piece['id']}").json()["numero"]
        cao = self.root / "cao"
        for rev in ("P01", "A"):
            (cao / numero / rev).mkdir(parents=True)
            (cao / numero / rev / f"{numero}_plaque_{rev}.svg").write_text("<svg><script>x()</script></svg>")
        (cao / numero / "A" / f"{numero}_plaque_A.step").write_text("ISO-10303-21;")
        (cao / numero / "A" / "secret.key").write_text("non")
        (cao / numero / "../../hors").mkdir(parents=True, exist_ok=True)
        os.symlink(self.root / "hors", cao / numero / "B")
        (self.root / "hors" / "fuite.svg").write_text("<svg/>")
        env = mock.patch.dict(os.environ, {"VAULTIA_CAO_SORTIE": str(cao)})
        env.start()
        self.addCleanup(env.stop)
        return piece["id"], numero

    def test_liste_revision_recente_d_abord_et_extensions_permises(self):
        pid, numero = self._preparer()
        r = self.client.get(f"/api/v2/pieces/{pid}/fichiers").json()
        self.assertEqual(r["numero"], numero)
        self.assertEqual([(f["revision"], f["type"]) for f in r["fichiers"]],
                         [("A", "step"), ("A", "svg"), ("P01", "svg")])

    def test_svg_servi_sans_droit_d_executer(self):
        pid, numero = self._preparer()
        r = self.client.get(f"/api/v2/pieces/{pid}/fichiers/A/{numero}_plaque_A.svg")
        self.assertEqual(r.status_code, 200)
        self.assertIn("default-src 'none'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")

    def test_refus_extension_traversee_et_lien_vers_l_exterieur(self):
        pid, numero = self._preparer()
        for chemin in ("A/secret.key", "B/fuite.svg", "P00/x.svg", "A/..%2F..%2Fhors%2Ffuite.svg"):
            self.assertEqual(self.client.get(f"/api/v2/pieces/{pid}/fichiers/{chemin}").status_code, 404, chemin)

    def test_piece_inconnue_404_et_sans_dossier_liste_vide(self):
        self.assertEqual(self.client.get("/api/v2/pieces/999/fichiers").status_code, 404)
        piece = self._create_piece("Sans plan")
        with mock.patch.dict(os.environ, {"VAULTIA_CAO_SORTIE": str(self.root / "vide")}):
            self.assertEqual(self.client.get(f"/api/v2/pieces/{piece['id']}/fichiers").json()["fichiers"], [])


if __name__ == "__main__":
    unittest.main()
