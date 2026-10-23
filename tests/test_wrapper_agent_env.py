"""Table `env` d'un agent : passée au processus de l'agent, sans écraser les variables du MCP."""

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wrapper import _agent_env, _build_provider_launch  # noqa: E402


class AgentEnvTests(unittest.TestCase):
    def test_sans_table_rien(self):
        self.assertEqual(_agent_env({"command": "claude"}), {})

    def test_valeurs_converties_en_texte(self):
        cfg = {"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": 200000, "X_Y": "a b"}}
        self.assertEqual(_agent_env(cfg), {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000", "X_Y": "a b"})

    def test_nom_invalide_ignore(self):
        cfg = {"env": {"BON": "1", "1MAUVAIS": "2", "A-B": "3", "A;rm": "4"}}
        self.assertEqual(_agent_env(cfg), {"BON": "1"})

    def test_table_mal_formee_ignoree(self):
        self.assertEqual(_agent_env({"env": "CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000"}), {})


class BuildProviderLaunchEnvTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def _lancer(self, agent_cfg, agent="claude"):
        return _build_provider_launch(
            agent=agent, agent_cfg=agent_cfg, instance_name=agent, data_dir=Path(self._dir.name),
            proxy_url=None, extra_args=[], env={},
        )

    def test_env_de_config_dans_inject_env(self):
        _, _, inject_env, _ = self._lancer({"command": "claude", "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000"}})
        self.assertEqual(inject_env.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"), "200000")

    def test_variable_du_mcp_garde_la_priorite(self):
        # gemini écrit son fichier de settings et l'expose par une variable : la config ne doit pas l'écraser
        _, _, sans, _ = self._lancer({"command": "gemini"}, agent="gemini")
        nom_mcp = next(iter(sans), None)
        if nom_mcp is None:
            self.skipTest("ce mode MCP n'expose aucune variable")
        _, _, avec, _ = self._lancer({"command": "gemini", "env": {nom_mcp: "/ailleurs"}}, agent="gemini")
        self.assertEqual(avec[nom_mcp], sans[nom_mcp])
        self.assertNotEqual(avec[nom_mcp], "/ailleurs")


class ConfigDuDepotTests(unittest.TestCase):
    def test_claude_plafonne_a_200k(self):
        cfg = tomllib.loads((ROOT / "config.toml").read_text("utf-8"))
        self.assertEqual(_agent_env(cfg["agents"]["claude"]), {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200000"})

    def test_codex_sans_env(self):
        cfg = tomllib.loads((ROOT / "config.toml").read_text("utf-8"))
        self.assertEqual(_agent_env(cfg["agents"]["codex"]), {})


if __name__ == "__main__":
    unittest.main()
