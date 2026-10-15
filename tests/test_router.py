import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from router import Router


class RouterMentionTests(unittest.TestCase):
    def test_hyphenated_agent_name_is_parsed_as_full_mention(self):
        router = Router(["telegram-bridge"], default_mention="none")

        self.assertEqual(
            set(router.parse_mentions("please ask @telegram-bridge to check")),
            {"telegram-bridge"},
        )

    def test_shorter_agent_name_does_not_match_prefix_of_hyphenated_unknown(self):
        router = Router(["telegram"], default_mention="none")

        self.assertEqual(router.parse_mentions("@telegram-bridge check"), [])
        self.assertEqual(router.get_targets("ben", "@telegram-bridge check"), [])

    def test_longest_hyphenated_name_wins_when_prefix_agent_also_exists(self):
        router = Router(["telegram", "telegram-bridge"], default_mention="none")

        self.assertEqual(
            set(router.parse_mentions("@telegram-bridge check")),
            {"telegram-bridge"},
        )

    def test_unknown_exact_handle_still_does_not_route(self):
        router = Router(["telegram-bridge"], default_mention="none")

        self.assertEqual(router.parse_mentions("@telegram-bot check"), [])
        self.assertEqual(router.get_targets("ben", "@telegram-bot check"), [])


class RouterProgressGuardTests(unittest.TestCase):
    """Garde-fou conscient du progrès : note_progress remet le canal à zéro comme un message
    humain, sans router de message ; sans progrès le loop guard pause toujours à max_hops."""

    def _pause_le_canal(self, router, a, b, canal):
        """Fait relayer a<->b jusqu'à la pause du loop guard sur `canal`. Rend le nombre de relais."""
        relais = 0
        for _ in range(router.max_hops + 5):
            expediteur, mention = (a, b) if relais % 2 == 0 else (b, a)
            router.get_targets(expediteur, f"@{mention} suite", canal)
            relais += 1
            if router.is_paused(canal):
                break
        return relais

    def test_note_progress_remet_le_compteur_et_depause(self):
        # (a) : après une pause, note_progress dépause et remet hop_count à zéro.
        router = Router(["a", "b"], default_mention="none", max_hops=2)
        self._pause_le_canal(router, "a", "b", "tache-1")
        self.assertTrue(router.is_paused("tache-1"))

        router.note_progress("tache-1")

        self.assertFalse(router.is_paused("tache-1"))
        self.assertFalse(router.is_guard_emitted("tache-1"))
        self.assertEqual(router.heartbeats_since_progress("tache-1"), 0)
        # hop_count repart de zéro : un relais d'agent route de nouveau au lieu d'être bloqué.
        self.assertEqual(router.get_targets("a", "@b reprends", "tache-1"), ["b"])

    def test_progres_intercale_ne_pause_jamais_meme_au_dela_de_max_hops(self):
        # (b) : alternance agent↔agent avec un progrès intercalé → jamais de pause, même bien
        # au-delà de max_hops.
        router = Router(["a", "b"], default_mention="none", max_hops=2)
        for i in range(20):  # 20 >> max_hops
            expediteur, mention = ("a", "b") if i % 2 == 0 else ("b", "a")
            cibles = router.get_targets(expediteur, f"@{mention} suite", "tache-7")
            self.assertEqual(cibles, [mention])
            self.assertFalse(router.is_paused("tache-7"))
            router.note_progress("tache-7")  # chaque tour a fait avancer la tâche

    def test_sans_progres_pause_toujours_a_max_hops(self):
        # (c) : sans progrès, le comportement classique est intact : pause dès que hop_count > max_hops.
        router = Router(["a", "b"], default_mention="none", max_hops=4)
        # 4 relais acceptés (hop_count 1..4), le 5e dépasse max_hops et pause.
        sequence = [("a", "b"), ("b", "a"), ("a", "b"), ("b", "a")]
        for expediteur, mention in sequence:
            self.assertEqual(router.get_targets(expediteur, f"@{mention} x", "general"), [mention])
            self.assertFalse(router.is_paused("general"))
        self.assertEqual(router.get_targets("a", "@b x", "general"), [])
        self.assertTrue(router.is_paused("general"))

    def test_anti_spin_declenche_apres_k_battements_et_se_rearme(self):
        # (d) : après K battements sans progrès, en veille ; un progrès réarme le compteur.
        router = Router(["a", "b"], default_mention="none", anti_spin_ticks=3)
        self.assertEqual(router.note_heartbeat("general"), (1, False))
        self.assertEqual(router.note_heartbeat("general"), (2, False))
        self.assertEqual(router.note_heartbeat("general"), (3, True))  # seuil franchi (une seule fois)
        # Au-delà du seuil : toujours en veille, mais « franchi » ne redevient pas vrai.
        compte, franchi = router.note_heartbeat("general")
        self.assertEqual(compte, 4)
        self.assertFalse(franchi)
        self.assertGreaterEqual(router.heartbeats_since_progress("general"), router.anti_spin_ticks)

        router.note_progress("general")  # un progrès réel réarme la ronde
        self.assertEqual(router.heartbeats_since_progress("general"), 0)
        self.assertEqual(router.note_heartbeat("general"), (1, False))  # repart de zéro

    def test_anti_spin_est_par_canal(self):
        # Les battements d'un canal n'affectent pas un autre.
        router = Router(["a", "b"], default_mention="none", anti_spin_ticks=2)
        router.note_heartbeat("tache-1")
        router.note_heartbeat("tache-1")
        self.assertEqual(router.heartbeats_since_progress("tache-1"), 2)
        self.assertEqual(router.heartbeats_since_progress("tache-2"), 0)
        router.note_progress("tache-1")
        self.assertEqual(router.heartbeats_since_progress("tache-1"), 0)

    def test_message_humain_reel_depause_toujours_comme_avant(self):
        # Rétro-compatibilité : un vrai message humain remet hop_count et dépause (inchangé).
        router = Router(["a", "b"], default_mention="none", max_hops=2)
        self._pause_le_canal(router, "a", "b", "general")
        self.assertTrue(router.is_paused("general"))
        router.get_targets("charles", "@a on reprend", "general")
        self.assertFalse(router.is_paused("general"))


if __name__ == "__main__":
    unittest.main()
