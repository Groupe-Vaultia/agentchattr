"""Visualiseur de livrables : l'endpoint GET /api/v2/livrable sert le CONTENU d'un livrable.

v1 (14 oct. 2026, claude ; Charles, 13 oct.) : une preuve de tâche n'était qu'une ligne de texte,
sans accès au document. Cet endpoint sert le contenu, borné à racine_livrables par le même garde-fou
que S5 (RevisionStore.resoudre). On vérifie : texte servi, traversée refusée (« .. », absolu, lien),
fichier absent = 404, image en FileResponse, autre type en téléchargement, et la limite de taille.

Patron du test : identique à test_socle_s5 (TestClient(app.app) sans configure(), app.revisions patché).
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

import app
from revisions import RevisionStore

# PNG 1x1 minimal (signature + IHDR + IDAT + IEND) — contenu réellement servi tel quel.
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


class LivrableContenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.racine = root / "deliverables"
        self.racine.mkdir()
        self.revisions = RevisionStore(str(root / "revisions.json"), str(self.racine))
        patcher = mock.patch.object(app, "revisions", self.revisions)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Une requête via TestClient construit app.middleware_stack (« application démarrée ») : on
        # restaure l'état d'origine pour qu'un test suivant puisse encore appeler configure()/add_middleware
        # (sinon « Cannot add middleware after an application has started »). Même garde que test_pieces_contract.
        mw_stack = app.app.middleware_stack
        self.addCleanup(lambda: setattr(app.app, "middleware_stack", mw_stack))
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)

    # (a) sert un .md sous la racine : JSON texte avec le contenu intact.
    def test_sert_markdown_sous_racine(self):
        (self.racine / "normes.md").write_text("# Titre\n\nUn **gras** et `code`.\n", encoding="utf-8")
        r = self.client.get("/api/v2/livrable", params={"chemin": "normes.md"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["type"], "texte")
        self.assertEqual(d["ext"], "md")
        self.assertEqual(d["chemin"], "normes.md")
        self.assertIn("**gras**", d["contenu"])

    # csv et json sont aussi servis comme texte lisible inline.
    def test_sert_csv_et_json_comme_texte(self):
        (self.racine / "mesures.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (self.racine / "config.json").write_text('{"k": 1}\n', encoding="utf-8")
        for nom, ext in (("mesures.csv", "csv"), ("config.json", "json")):
            r = self.client.get("/api/v2/livrable", params={"chemin": nom})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["type"], "texte")
            self.assertEqual(r.json()["ext"], ext)

    # (b) refuse « ../etc/passwd », un chemin absolu hors racine, et un lien symbolique qui s'échappe.
    def test_refuse_traversee_et_chemin_absolu(self):
        self.assertEqual(self.client.get("/api/v2/livrable", params={"chemin": "../etc/passwd"}).status_code, 403)
        self.assertEqual(self.client.get("/api/v2/livrable", params={"chemin": "/etc/passwd"}).status_code, 403)
        self.assertEqual(self.client.get("/api/v2/livrable", params={"chemin": ""}).status_code, 403)

        dehors = Path(self.tmp.name) / "dehors.md"
        dehors.write_text("secret hors racine", encoding="utf-8")
        try:
            (self.racine / "evasion.md").symlink_to(dehors)
        except OSError:
            self.skipTest("création de lien symbolique indisponible")
        self.assertEqual(self.client.get("/api/v2/livrable", params={"chemin": "evasion.md"}).status_code, 403)

    # (c) fichier absent sous la racine : 404 avec message.
    def test_fichier_absent_404(self):
        r = self.client.get("/api/v2/livrable", params={"chemin": "introuvable.md"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.json())

    # (d) image : FileResponse inline, bon type, octets intacts, nosniff.
    def test_image_en_fileresponse(self):
        (self.racine / "plan.png").write_bytes(PNG_1x1)
        r = self.client.get("/api/v2/livrable", params={"chemin": "plan.png"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertIn("inline", r.headers.get("content-disposition", ""))
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.content, PNG_1x1)

    # Tout autre type (PDF, STEP, binaire inconnu) : téléchargement (attachment), jamais rendu.
    def test_autre_type_en_telechargement(self):
        (self.racine / "piece.step").write_text("ISO-10303-21;\n", encoding="utf-8")
        r = self.client.get("/api/v2/livrable", params={"chemin": "piece.step"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers.get("content-disposition", ""))
        self.assertEqual(r.headers["content-type"], "application/step")

        (self.racine / "donnee.bin").write_bytes(b"\x00\x01\x02\x03")
        r2 = self.client.get("/api/v2/livrable", params={"chemin": "donnee.bin"})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("attachment", r2.headers.get("content-disposition", ""))
        self.assertTrue(r2.headers["content-type"].startswith("application/octet-stream"))

    # Texte trop gros : pas de contenu servi, message clair (type « trop_volumineux »).
    def test_texte_trop_volumineux(self):
        gros = self.racine / "journal.txt"
        gros.write_text("x" * (app._LIVR_MAX_TEXTE + 1), encoding="utf-8")
        r = self.client.get("/api/v2/livrable", params={"chemin": "journal.txt"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["type"], "trop_volumineux")
        self.assertNotIn("contenu", d)
        self.assertIn("message", d)


if __name__ == "__main__":
    unittest.main()
