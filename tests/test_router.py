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


class RouterMentionsDansLeCodeTests(unittest.TestCase):
    """Une mention citée dans du code n'est pas une mention (#tache-26 msg 6772 : un message qui citait la règle entre
    accents graves a réveillé tous les agents et fait sauter le Loop guard)."""

    def test_mention_en_code_en_ligne_ignoree(self):
        router = Router(["a", "b", "c"], default_mention="none")
        self.assertEqual(router.parse_mentions("La règle compte les messages à `@all` et `@both`."), [])
        self.assertEqual(router.parse_mentions("Cite ``@b`` sans le réveiller."), [])
        self.assertEqual(router.get_targets("a", "Seuls comptent les relais à `@all`.", "general"), [])

    def test_mention_dans_un_bloc_de_code_ignoree(self):
        router = Router(["a", "b", "c"], default_mention="none")
        bloc = "Exemple :\n```\nrouter.get_targets('a', '@b merci', 'general')\n@all\n```\nFin."
        self.assertEqual(router.parse_mentions(bloc), [])
        self.assertEqual(router.parse_mentions("Bloc non refermé :\n```\n@c relance"), [])

    def test_mention_ordinaire_compte_toujours(self):
        router = Router(["a", "b", "c"], default_mention="none")
        self.assertEqual(router.parse_mentions("@b relis `@c` puis réponds"), ["b"])
        self.assertEqual(router.parse_mentions("Après le bloc ```@c``` : @a, à toi."), ["a"])
        self.assertEqual(sorted(router.get_targets("a", "@b et @c, voyez `@all`", "general")), ["b", "c"])
        self.assertFalse(router.is_paused("general"))

    def test_all_en_code_ne_compte_pas_comme_diffusion(self):
        # Trois groupes différents, chacun citant la règle entre accents graves : aucune diffusion, donc aucune pause.
        router = Router(["a", "b", "c"], default_mention="none", max_hops=2)
        for de, vers in (("a", "b"), ("b", "c"), ("c", "a")):
            self.assertEqual(router.get_targets(de, f"@{vers} voir `@all`", "general"), [vers])
        self.assertFalse(router.is_paused("general"))


class RouterPaireTests(unittest.TestCase):
    """Loop guard par groupe (21 oct. 2026) : seuls comptent les relais consécutifs du même groupe d'agents (expéditeur et
    destinataires) et les messages d'agent à @all/@both ; un relais vers un autre groupe repart à 1. Mesure sur le journal
    réel (#tache-26 msgs 6751 et 6769, noms de famille compris) : 1 261 relais sur 1 263 passent par le chef ; plus
    longues suites identiques depuis le 21 sept. : 14 relais à deux, 7 à trois, 4 à quatre et plus."""

    def test_orchestration_du_chef_ne_pause_jamais(self):
        # Le chef passe d'un agent à l'autre (consigne, livraison, consigne suivante) : 300 relais, aucune pause.
        router = Router(["chef", "a", "b", "c"], default_mention="none", max_hops=4)
        agents = ["a", "b", "c"]
        for i in range(150):
            agent = agents[i % 3]
            self.assertEqual(router.get_targets("chef", f"@{agent} lot {i}", "tache-21"), [agent])
            self.assertEqual(router.get_targets(agent, f"@chef livré {i}", "tache-21"), ["chef"])
        self.assertFalse(router.is_paused("tache-21"))

    def test_boucle_entre_deux_agents_pause_apres_max_hops(self):
        router = Router(["a", "b"], default_mention="none", max_hops=4)
        for i in range(4):
            de, vers = ("a", "b") if i % 2 == 0 else ("b", "a")
            self.assertEqual(router.get_targets(de, f"@{vers} merci", "general"), [vers])
        self.assertEqual(router.get_targets("a", "@b merci", "general"), [])
        self.assertTrue(router.is_paused("general"))
        self.assertEqual(router.derniere_paire("general"), ["a", "b"])

    def test_le_chef_n_est_pas_exempte(self):
        # Une boucle chef <-> agent est une boucle comme une autre.
        router = Router(["chef", "a"], default_mention="none", max_hops=4)
        for i in range(5):
            de, vers = ("chef", "a") if i % 2 == 0 else ("a", "chef")
            router.get_targets(de, f"@{vers} relance", "tache-21")
        self.assertTrue(router.is_paused("tache-21"))

    def test_un_tiers_remet_la_suite_a_un(self):
        router = Router(["a", "b", "c"], default_mention="none", max_hops=4)
        for _ in range(3):
            for de, vers in (("a", "b"), ("b", "a"), ("a", "b")):
                router.get_targets(de, f"@{vers} x", "general")
            router.get_targets("c", "@a avis", "general")          # tiers : la suite a<->b repart de zéro
        self.assertFalse(router.is_paused("general"))

    def test_messages_a_all_comptent_toujours(self):
        # Une avalanche de @all entre agents est une boucle, même si l'expéditeur change à chaque message.
        router = Router(["a", "b", "c"], default_mention="none", max_hops=4)
        for i, de in enumerate(["a", "b", "c", "a"]):
            self.assertNotEqual(router.get_targets(de, "@all point", "general"), [])
        self.assertEqual(router.get_targets("b", "@all point", "general"), [])
        self.assertTrue(router.is_paused("general"))

    def test_mention_de_soi_seul_neutre(self):
        # Une mention de soi seul ne route rien, ne compte pas et ne remet pas la suite à zéro.
        router = Router(["a", "b"], default_mention="none", max_hops=4)
        for de, vers in (("a", "b"), ("b", "a"), ("a", "a"), ("a", "b"), ("b", "a")):
            router.get_targets(de, f"@{vers} x", "general")
        self.assertFalse(router.is_paused("general"))
        self.assertEqual(router.get_targets("a", "@b x", "general"), [])      # 5e relais de la paire
        self.assertTrue(router.is_paused("general"))

    def test_trois_agents_qui_se_mettent_en_copie_pausent(self):
        # msg 6769 : A -> B + C, B -> A + C, C -> A + B... le même groupe de trois revient à chaque relais.
        router = Router(["a", "b", "c"], default_mention="none", max_hops=4)
        tours = [("a", "@b @c"), ("b", "@a @c"), ("c", "@a @b"), ("a", "@b @c")]
        for de, texte in tours:
            self.assertNotEqual(router.get_targets(de, f"{texte} merci", "general"), [])
        self.assertEqual(router.get_targets("b", "@a @c merci", "general"), [])
        self.assertTrue(router.is_paused("general"))
        self.assertEqual(router.derniere_paire("general"), ["a", "b", "c"])

    def test_consigne_a_plusieurs_puis_reponse_au_chef_sont_deux_groupes(self):
        # « chef -> a + b », puis « a -> chef », puis « b -> chef » : jamais le même groupe deux fois de suite.
        router = Router(["chef", "a", "b"], default_mention="none", max_hops=2)
        for i in range(50):
            self.assertEqual(sorted(router.get_targets("chef", f"@a @b lot {i}", "tache-21")), ["a", "b"])
            self.assertEqual(router.get_targets("a", f"@chef livré {i}", "tache-21"), ["chef"])
            self.assertEqual(router.get_targets("b", f"@chef revu {i}", "tache-21"), ["chef"])
        self.assertFalse(router.is_paused("tache-21"))

    def test_seul_un_humain_leve_la_pause(self):
        router = Router(["a", "b", "c"], default_mention="none", max_hops=2)
        for de, vers in (("a", "b"), ("b", "a"), ("a", "b")):
            router.get_targets(de, f"@{vers} x", "general")
        self.assertTrue(router.is_paused("general"))
        self.assertEqual(router.get_targets("c", "@a autre sujet", "general"), [])   # un tiers ne lève pas la pause
        router.note_progress("general", reprendre=False)                            # un progrès d'agent non plus
        self.assertTrue(router.is_paused("general"))
        router.get_targets("charles", "@a on reprend", "general")
        self.assertFalse(router.is_paused("general"))
        self.assertEqual(router.derniere_paire("general"), [])
        self.assertEqual(router.get_targets("a", "@b reprends", "general"), ["b"])


if __name__ == "__main__":
    unittest.main()
