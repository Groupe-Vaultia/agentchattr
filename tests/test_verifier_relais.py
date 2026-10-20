"""Détecteur de relais morts (scripts/verifier_relais.py), sans tmux ni serveur.

v1.0 (2026-10-19, claude-2) : les relais de qwencode-3 et qwencode-4 étaient morts depuis 17 h 10 sans que rien ne le signale
(claude-1 #tache-22 msg 5596).
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verifier_relais", ROOT / "scripts" / "verifier_relais.py")
V = importlib.util.module_from_spec(SPEC)
sys.modules["verifier_relais"] = V
SPEC.loader.exec_module(V)

JETON = "0123456789abcdef0123456789abcdef"
CLE = "sk-cle-secrete-de-test"
SESSIONS = [("ac-claude", 100), ("ac-qwencode3", 300), ("agentchattr-claude", 110), ("agentchattr-qwencode-3", 310),
            ("agentchattr-grok", 410)]
PS = [
    "100 1 bash bash -c env PATH=/x .venv/bin/python wrapper.py claude --dangerously-skip-permissions; read",
    "101 100 python .venv/bin/python wrapper.py claude --dangerously-skip-permissions",
    f"300 1 bash bash -c env .venv/bin/python wrapper.py qwencode --openai-api-key {CLE}; read",
]


def _registre(dossier: Path) -> None:
    (dossier / "registry.json").write_text(json.dumps({
        "instances": {"claude-1": {"name": "claude-1", "state": "active", "token": JETON}},
        "reclaimable": {"qwencode-4": {"name": "qwencode-4", "state": "active", "token": JETON}},
    }), "utf-8")


class TestCalcul(unittest.TestCase):
    def test_un_relais_est_un_python_wrapper(self):
        self.assertEqual(V.analyser_ps(PS[0]), (100, 1, False))               # le bash -c du volet n'est pas le relais
        self.assertEqual(V.analyser_ps(PS[1]), (101, 100, True))
        self.assertEqual(V.analyser_ps("7 1 python3 python3 /opt/a/wrapper.py codex"), (7, 1, True))
        self.assertEqual(V.analyser_ps("8 1 python3 python3 autre.py wrapper.pyc"), (8, 1, False))

    def test_relais_sous_le_volet(self):
        procs = [p for p in map(V.analyser_ps, PS) if p]
        self.assertEqual(V.relais_sous(100, procs), 101)
        self.assertIsNone(V.relais_sous(300, procs))                            # le volet attend sur `read`

    def test_nom_agent_famille_renumerotee(self):
        self.assertEqual(V.nom_agent("agentchattr-claude", {"claude-1": "actif"}), "claude-1")
        self.assertEqual(V.nom_agent("agentchattr-grok", {"grok": "actif"}), "grok")
        self.assertEqual(V.nom_agent("agentchattr-qwencode-3", {}), "qwencode-3")

    def test_battements_interpoles(self):
        fin = time.mktime((2026, 10, 19, 22, 0, 30, 0, 0, -1))
        lignes = [
            "21:59:00 [app] INFO: x",
            'INFO:     127.0.0.1:1 - "POST /api/heartbeat/qwencode-3 HTTP/1.1" 200 OK',
            "22:00:00 [app] INFO: y",
            'INFO:     127.0.0.1:1 - "POST /api/heartbeat/claude-1 HTTP/1.1" 200 OK',
            'INFO:     127.0.0.1:1 - "POST /api/heartbeat/grok HTTP/1.1" 200 OK',
        ]
        t = V.battements(lignes, fin)
        self.assertAlmostEqual(fin - t["qwencode-3"], 60.0)                  # à mi-chemin entre 21:59:00 et 22:00:00
        self.assertAlmostEqual(fin - t["claude-1"], 15.0)                    # entre 22:00:00 et la fin (22:00:30)
        self.assertAlmostEqual(fin - t["grok"], 0.0)

    def test_battements_veille(self):
        fin = time.mktime((2026, 10, 20, 0, 0, 10, 0, 0, -1))
        lignes = ["23:59:50 [app] INFO: x", 'INFO: "POST /api/heartbeat/codex-1 HTTP/1.1" 200 OK', "00:00:00 [app] INFO: y", "z"]
        self.assertAlmostEqual(fin - V.battements(lignes, fin)["codex-1"], 15.0)

    def test_tableau_et_verdicts(self):
        procs = [p for p in map(V.analyser_ps, PS) if p]
        reg = {"claude-1": "actif", "grok": "récupérable"}
        lignes = {l.agent: l for l in V.tableau(SESSIONS, procs, reg, {"claude-1": 3.0, "qwencode-3": 19680.0})}
        self.assertEqual((lignes["claude-1"].relais, lignes["claude-1"].pid, lignes["claude-1"].verdict), ("vivant", 101, "ok"))
        self.assertEqual((lignes["qwencode-3"].relais, lignes["qwencode-3"].registre, lignes["qwencode-3"].verdict),
                         ("mort", "absent", "RELAIS MORT"))
        self.assertEqual(lignes["qwencode-3"].battement, "≈ 5 h 28")
        self.assertEqual((lignes["grok"].relais, lignes["grok"].verdict), ("sans ac-*", "RELAIS INTROUVABLE"))


class TestLectureSeuleEtSecrets(unittest.TestCase):
    def _main(self, sessions, ps, avec_registre=True):
        with tempfile.TemporaryDirectory() as d:
            if avec_registre:
                _registre(Path(d))
            Path(d, "server.log").write_text("22:00:00 [app] INFO: x\n" 'INFO: "POST /api/heartbeat/claude-1 HTTP/1.1" 200 OK\n', "utf-8")
            sortie = io.StringIO()
            with mock.patch.object(V, "lire_tmux", return_value=sessions), \
                    mock.patch.object(V, "lire_processus", return_value=[p for p in map(V.analyser_ps, ps) if p]), \
                    contextlib.redirect_stdout(sortie):
                code = V.main(["--data", d])
        return code, sortie.getvalue()

    def test_code_de_sortie(self):
        code, out = self._main(SESSIONS, PS)
        self.assertEqual(code, 1)
        self.assertIn("2 sans relais vivant : qwencode-3, grok", out)
        code, _ = self._main(SESSIONS[:1] + SESSIONS[2:3], PS)
        self.assertEqual(code, 0)
        code, out = self._main(SESSIONS, PS, avec_registre=False)
        self.assertEqual(code, 2)

    def test_aucun_jeton_ni_ligne_de_commande(self):
        code, out = self._main(SESSIONS, PS)
        for secret in (JETON, CLE, "--openai-api-key", "wrapper.py", "--dangerously"):
            self.assertNotIn(secret, out)
        with tempfile.TemporaryDirectory() as d:
            _registre(Path(d))
            reg = V.lire_registre(Path(d) / "registry.json")
        self.assertEqual(reg, {"claude-1": "actif", "qwencode-4": "récupérable"})
        self.assertNotIn(JETON, repr(reg))

    def test_lecture_seule(self):
        """Les seules commandes lancées sont des lectures : `tmux list-panes` et `ps`."""
        lancees = []

        def faux_run(cmd, **kw):
            lancees.append(cmd[:2])
            return mock.Mock(returncode=0, stdout="")
        with mock.patch.object(V.subprocess, "run", side_effect=faux_run):
            V.lire_tmux()
            V.lire_processus()
        self.assertEqual(lancees, [["tmux", "list-panes"], ["ps", "-eo"]])


if __name__ == "__main__":
    unittest.main()
