"""Contrat du gabarit CAO N2b.

v0.5 (2026-10-14, codex) : place les fichiers de sortie hors du dépôt.
v0.4 : compare le volume commun avec tolérance flottante.
v0.3 : expose FreeCAD dans le runner pour TechDraw.
v0.2 : place les fixtures temporaires sous le worktree pour FreeCAD Snap.
v0.1 : contrôle du rapport de niveau 1, les exports,
les révisions et le calcul d'interférence sur des solides qui se croisent.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cao import controles


class CaoN2bContractTests(unittest.TestCase):
    def test_level_one_rejects_invalid_geometry(self):
        errors = controles.niveau1({
            "brep_valide": False,
            "solides": 0,
            "volume_mm3": 0,
            "encombrement_mm": {"x": 10, "y": 0, "z": 2},
        })

        self.assertIn("brep invalide", errors)
        self.assertIn("aucun solide", errors)
        self.assertIn("volume nul", errors)
        self.assertIn("encombrement y nul", errors)

    @unittest.skipUnless(shutil.which("freecad.cmd"), "freecad.cmd unavailable")
    def test_headless_exports_and_report_match_the_contract(self):
        with tempfile.TemporaryDirectory(prefix=".codex-n2b-", dir=ROOT) as temp, \
                tempfile.TemporaryDirectory(prefix=".codex-n2b-out-", dir=ROOT.parent) as output:
            temp_path = Path(temp)
            output_path = Path(output)
            runner = temp_path / "run_n2b.py"
            runner.write_text(textwrap.dedent(f"""
                import json, sys
                from pathlib import Path
                import FreeCAD as App
                import Part
                import TechDraw
                sys.path.insert(0, {str(ROOT)!r})
                from cao import gabarit_piece as gp
                report = gp.produire(gp.ESSAI, Path({str(output_path)!r}))
                a = gp.Part.makeBox(10, 10, 10)
                b = gp.Part.makeBox(10, 10, 10)
                b.translate(gp.App.Vector(5, 0, 0))
                overlap = gp._volumes_communs(gp.Part.makeCompound([a, b]))
                print('N2B_JSON:' + json.dumps({{'report': report, 'overlap': overlap}}))
            """), encoding="utf-8")

            command = [
                shutil.which("freecad.cmd"), "-c",
                f"import runpy; runpy.run_path({str(runner)!r}, run_name='__main__')",
            ]
            result = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_line = next(
                (line for line in result.stdout.splitlines() if line.startswith("N2B_JSON:")),
                None,
            )
            self.assertIsNotNone(report_line, result.stdout + result.stderr)
            data = json.loads(report_line.removeprefix("N2B_JSON:"))
            report = data["report"]

            self.assertEqual(controles.juger(report), [])
            self.assertTrue(report["brep_valide"])
            self.assertEqual(report["solides"], 1)
            self.assertAlmostEqual(report["volume_mm3"], 2400.0)
            self.assertEqual(report["cotes_mm"], {"L": 40.0, "W": 20.0, "T": 3.0})
            self.assertEqual(len(data["overlap"]), 1)
            self.assertAlmostEqual(data["overlap"][0], 500.0)

            piece_file = Path(report["fichier"])
            step_file = Path(report["step"])
            pdf_value = report["pdf"]
            self.assertTrue(piece_file.is_file(), report["fichier"])
            self.assertTrue(step_file.is_file(), report["step"])
            self.assertIn("214", report["step_schema"])
            self.assertEqual(report["empreinte"], hashlib.sha256(piece_file.read_bytes()).hexdigest())
            self.assertIn("VLT-10001", piece_file.parts)
            self.assertIn("P01", piece_file.parts)
            self.assertTrue(Path(report["svg"]).is_file(), report["svg"])
            self.assertTrue(Path(report["dxf"]).is_file(), report["dxf"])
            self.assertTrue(Path(pdf_value).is_file(), f"PDF absent : {pdf_value}")


if __name__ == "__main__":
    unittest.main()
