"""Retrait d'une offre fausse ou perimee, avec motif et historique (schema v2, msg 2896)."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pieces  # noqa: E402
import tests.test_pieces_contract as _contrat  # noqa: E402  (module, pour ne pas recollecter ses tests)


class OffresRetraitTests(unittest.TestCase):
    setUp = _contrat.PiecesContractTests.setUp
    _restore_globals = _contrat.PiecesContractTests._restore_globals
    _create_piece = _contrat.PiecesContractTests._create_piece

    def _offre(self, pid, prix=10.0):
        r = self.client.post(f"/api/v2/pieces/{pid}/offres", json={
            "prix": prix, "devise": "CAD", "source": "https://exemple.ca/produit", "par": "qwencode"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_retrait_sort_l_offre_de_la_fiche_et_garde_l_historique(self):
        pid = self._create_piece("Jante", origine="acheter")["id"]
        fausse, bonne = self._offre(pid, 0.0), self._offre(pid, 25.0)
        r = self.client.post(f"/api/v2/offres/{fausse['id']}/retrait",
                             json={"motif": "source non ouverte (msg 2896)", "par": "claude"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(r.json()["retiree"])
        fiche = self.client.get(f"/api/v2/pieces/{pid}").json()
        self.assertEqual([o["id"] for o in fiche["offres"]], [bonne["id"]])
        histo = [h for h in fiche["historique"] if h["champ"] == "offre_retiree"]
        self.assertEqual((histo[0]["avant"], histo[0]["apres"], histo[0]["qui"]),
                         (str(fausse["id"]), "source non ouverte (msg 2896)", "claude"))

    def test_refus_sans_motif_sans_par_inconnue_et_double_retrait(self):
        pid = self._create_piece("Disque", origine="acheter")["id"]
        oid = self._offre(pid)["id"]
        self.assertEqual(self.client.post(f"/api/v2/offres/{oid}/retrait", json={"par": "claude"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/v2/offres/{oid}/retrait", json={"motif": "x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v2/offres/999/retrait",
                                          json={"motif": "x", "par": "claude"}).status_code, 404)
        ok = {"motif": "doublon", "par": "claude"}
        self.assertEqual(self.client.post(f"/api/v2/offres/{oid}/retrait", json=ok).status_code, 200)
        self.assertEqual(self.client.post(f"/api/v2/offres/{oid}/retrait", json=ok).status_code, 409)


class MigrationV2Tests(unittest.TestCase):
    def test_base_v1_existante_recoit_les_colonnes_sans_perdre_ses_offres(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = str(Path(d) / "pieces.db")
            db = sqlite3.connect(chemin)
            db.executescript(pieces._SCHEMA)
            db.execute("INSERT INTO pieces (numero, revision, nom, origine, type, statut, cree, maj) VALUES ('VLT-10001', 'P01', 'Jante', 'acheter', 'piece', 'a_commander', 0, 0)")
            db.execute("INSERT INTO offres (piece_id, prix, devise, source, date) VALUES (1, 5, 'CAD', 'https://x.ca', 0)")
            db.execute("PRAGMA user_version = 1")
            db.commit()
            db.close()
            store = pieces.PieceStore(chemin)
            cols = {r[1] for r in store._db.execute("PRAGMA table_info(offres)")}
            self.assertTrue({"retiree", "motif_retrait"} <= cols)
            self.assertEqual(store._db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(len(store.offres(1)), 1)


if __name__ == "__main__":
    unittest.main()
