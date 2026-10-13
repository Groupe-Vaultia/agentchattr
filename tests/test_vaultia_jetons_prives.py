"""Les fichiers qui portent un jeton sont lisibles par ce compte seul (0600).

registry.json porte les jetons de TOUS les agents ; les configs MCP generees (claude-mcp.json,
.qwen/settings.json…) portent le jeton Bearer d'un agent. Ils sortaient en 0664, lisibles par tout
compte de la machine -- qui pouvait alors se faire passer pour n'importe quel agent. Le dual : le
contenu ecrit ne change pas.
"""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wrapper  # noqa: E402
from registry import RuntimeRegistry  # noqa: E402


def mode(chemin):
    return stat.S_IMODE(os.stat(chemin).st_mode)


class JetonsPrivesTests(unittest.TestCase):
    def setUp(self):
        self._umask = os.umask(0o002)          # le umask courant de la machine : 664 par defaut
        self.addCleanup(os.umask, self._umask)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dossier = Path(self.tmp.name)

    def test_le_registre_des_jetons_est_prive(self):
        reg = RuntimeRegistry(data_dir=str(self.dossier))
        reg.seed({"claude": {"label": "Claude", "color": "#da7756"}})
        inst = reg.register("claude")
        reg._save_instances()
        fichier = reg._instances_path()
        self.assertEqual(mode(fichier), 0o600)
        self.assertIn(inst["token"], fichier.read_text())      # le dual : le contenu est intact

    def test_la_config_mcp_de_claude_est_privee(self):
        f = wrapper._write_claude_mcp_config(self.dossier / "claude-mcp.json", "http://127.0.0.1:8200/mcp", token="abc123")
        self.assertEqual(mode(f), 0o600)
        self.assertEqual(json.loads(f.read_text())["mcpServers"]["agentchattr"]["headers"]["Authorization"], "Bearer abc123")

    def test_une_config_de_type_settings_est_privee(self):
        f = wrapper._write_json_mcp_settings(self.dossier / ".qwen" / "settings.json", "http://127.0.0.1:8200/mcp", token="abc123")
        self.assertEqual(mode(f), 0o600)


if __name__ == "__main__":
    unittest.main()
