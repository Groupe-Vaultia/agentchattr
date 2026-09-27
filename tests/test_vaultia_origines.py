"""Origines de confiance propres à une machine : lues de config.local.toml, jamais du code.

Le dépôt est public ; l'adresse du tunnel privé de la personne (son nom de machine, l'identifiant
de son réseau Tailscale) vivait en dur dans app.py. Elle vit désormais dans config.local.toml
(ignoré par git), section [server] allowed_origins. Le dual : sans config locale, aucune origine
de plus ; une valeur qui n'est pas une chaîne est ignorée.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_config  # noqa: E402


class OriginesLocalesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.racine = Path(self.tmp.name)
        (self.racine / "config.toml").write_text('[server]\nport = 8300\n', encoding="utf-8")

    def test_les_origines_de_la_config_locale_sont_ajoutees(self):
        (self.racine / "config.local.toml").write_text(
            '[server]\nallowed_origins = ["https://salle.exemple.ts.net", 42]\n', encoding="utf-8")
        cfg = load_config(self.racine)
        self.assertEqual(cfg["server"]["allowed_origins"], ["https://salle.exemple.ts.net"])
        self.assertEqual(cfg["server"]["port"], 8300)

    def test_le_dual_sans_config_locale_aucune_origine_de_plus(self):
        cfg = load_config(self.racine)
        self.assertNotIn("allowed_origins", cfg["server"])

    def test_le_depot_ne_porte_plus_d_adresse_de_tunnel(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertNotIn(".ts.net", source)


if __name__ == "__main__":
    unittest.main()
