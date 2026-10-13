"""Fichiers televerses : jamais servis comme une page de la salle.

Un SVG ouvert directement executait son script avec les droits de la salle (qui injecte le jeton de
session dans « / ») ; un .txt pouvait etre devine comme du HTML. La route pose `nosniff` partout et
une CSP sandbox sans script sur les SVG. Le dual : une image ordinaire garde son type, sans CSP, et
un chemin qui sort du dossier reste refuse.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402


class UploadHeadersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / "piege.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        (d / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (d / "notes.txt").write_text("<html><script>alert(1)</script></html>")
        self._config = app.config
        app.config = {"images": {"upload_dir": str(d)}}
        self.addCleanup(setattr, app, "config", self._config)

    def servir(self, nom):
        return asyncio.run(app.serve_upload(nom))

    def test_un_svg_est_servi_sans_pouvoir_executer_de_script(self):
        r = self.servir("piege.svg")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        csp = r.headers.get("content-security-policy", "")
        self.assertIn("sandbox", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("script-src", csp)

    def test_un_texte_n_est_jamais_devine_comme_du_html(self):
        self.assertEqual(self.servir("notes.txt").headers.get("x-content-type-options"), "nosniff")

    def test_le_dual_une_image_ordinaire_garde_son_type_sans_csp(self):
        r = self.servir("photo.png")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertIsNone(r.headers.get("content-security-policy"))
        self.assertEqual(r.media_type, "image/png")

    def test_un_chemin_qui_sort_du_dossier_reste_refuse(self):
        self.assertEqual(self.servir("../etc/passwd").status_code, 400)


if __name__ == "__main__":
    unittest.main()
