"""Delai des appels cli_print : `cli_timeout` de l'agent, borne de 60 a 1800 s, 180 par defaut."""

import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wrapper_api import delai_cli  # noqa: E402


class DelaiCliTests(unittest.TestCase):
    def test_defaut_180(self):
        self.assertEqual(delai_cli({}), 180)

    def test_valeur_de_la_config(self):
        self.assertEqual(delai_cli({"cli_timeout": 900}), 900)

    def test_bornes_et_valeur_illisible(self):
        self.assertEqual(delai_cli({"cli_timeout": 5}), 60)
        self.assertEqual(delai_cli({"cli_timeout": 99999}), 1800)
        self.assertEqual(delai_cli({"cli_timeout": "beaucoup"}), 180)

    def test_gemini_a_un_delai_long(self):
        cfg = tomllib.loads((Path(__file__).resolve().parents[1] / "config.toml").read_text("utf-8"))
        self.assertEqual(delai_cli(cfg["agents"]["gemini"]), 900)


if __name__ == "__main__":
    unittest.main()
