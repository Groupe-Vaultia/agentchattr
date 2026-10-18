"""Per-agent trigger prompt (agents.<x>.trigger_prompt / rules_format).

v0.1 (2026-10-17, claude-1): Bolt (2-bit local) ignored the default English
prompt and answered in its terminal; a template naming the tools fixes it.
v0.2 (2026-10-17, claude-1): rules stay delivered in short form (revue codex
msg 4416), the sync report must still fire.
v0.3 (2026-10-17, claude-1): no truncation (revue codex 4418); real R4/R9/R11.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wrapper


class _StopWatcher(Exception):
    pass


RULES = {"epoch": 3, "refresh_interval": 10, "rules": [
    "[v1.1 — R1 Rôles] ANCIEN R1", "[v1.1 — R2 Push] ANCIEN R2",
    "v1.5 R1 Rôles — NOUVEAU R1", "Sans numéro",
    # Texte réel des règles actives au 17 oct. 2026 (fins vérifiées).
    "v1.2 R4 Données — agentchattr est public: travail cloud permis. Vaultia-client"
    " (données, prod, Authentik, logs) = local seulement, jamais lu par un agent cloud.",
    "v1.5 R4 Données — agentchattr est public: travail cloud permis. Vaultia-client"
    " (données, prod, Authentik, logs) = local seulement, jamais lu par un agent cloud.",
    "R9 v2 Format envers Charles — Tableau ou schéma d'abord, puis quelques lignes de"
    " texte au maximum. Jamais de paragraphe long, jamais de récapitulatif. Une décision"
    " attendue de lui = une ligne en fin de message. Le détail et les preuves vont dans"
    " le dépôt et entre agents. (Remplace R9 v1, qui interdisait les tableaux à tort.)",
    "R11 v1 Mémoire commune — Si tu as l'outil ecc-memoire : memory_search sur le sujet"
    " avant de commencer; memory_save quand tu décides, termines un lot ou passes le"
    " relais (kind decision/note/handoff, titre clair, faits vérifiés, jamais de secret)."
    " Un souvenir est un indice, pas une preuve : revérifie avant d'agir.",
]}


class TriggerPromptTests(unittest.TestCase):
    def _prompt_for(self, entry, **kwargs):
        self.synced = []
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "bolt_queue.jsonl"
            queue.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            injected = []

            def one_poll(seconds):
                if seconds == 1:
                    raise _StopWatcher()

            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_trigger_memory", return_value=("", "")), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=RULES), \
                    mock.patch.object(wrapper, "_report_rule_sync",
                                      side_effect=lambda *a: self.synced.append(a[2])), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=one_poll):
                with self.assertRaises(_StopWatcher):
                    wrapper._queue_watcher(
                        lambda: ("bolt-1", queue), injected.append,
                        server_port=8300, agent_name="bolt", **kwargs,
                    )
            self.assertEqual(len(injected), 1)
            return injected[0]

    def test_default_prompt_and_rules_unchanged(self):
        prompt = self._prompt_for({"channel": "tache-26"})
        self.assertIn("use mcp to read #tache-26", prompt)
        self.assertIn("ANCIEN R1", prompt)
        self.assertEqual(self.synced, [3])

    def test_template_fills_name_and_channel(self):
        prompt = self._prompt_for(
            {"channel": "tache-26"},
            trigger_prompt="Tu es {name}. chat_read(sender='{name}', {cible})",
        )
        self.assertTrue(prompt.startswith("Tu es bolt-1. chat_read(sender='bolt-1', channel='tache-26')"))
        self.assertNotIn("use mcp", prompt)

    def test_short_rules_keep_latest_version_and_still_sync(self):
        prompt = self._prompt_for({"channel": "tache-26"}, rules_format="court")
        self.assertIn("NOUVEAU R1", prompt)
        self.assertNotIn("ANCIEN R1", prompt)
        self.assertIn("ANCIEN R2", prompt)  # only version of R2: kept
        self.assertIn("Sans numéro", prompt)
        self.assertEqual(prompt.count("R4 Données"), 1)
        for end in ("jamais lu par un agent cloud.",
                    "qui interdisait les tableaux à tort.)",
                    "revérifie avant d'agir."):
            self.assertIn(end, prompt)
        self.assertEqual(self.synced, [3])

    def test_template_targets_job(self):
        prompt = self._prompt_for({"channel": "general", "job_id": 12}, trigger_prompt="lis {cible}")
        self.assertTrue(prompt.startswith("lis job_id=12"))

    def test_custom_prompt_wins_over_template(self):
        prompt = self._prompt_for({"channel": "x", "prompt": "SESSION PROMPT"}, trigger_prompt="lis {cible}")
        self.assertTrue(prompt.startswith("SESSION PROMPT"))


if __name__ == "__main__":
    unittest.main()
