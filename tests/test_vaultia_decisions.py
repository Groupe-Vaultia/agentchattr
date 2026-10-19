"""« Répondu autrement » : fermer une carte de décision sans choisir ni publier de message.

Charles répond souvent en écrivant plutôt qu'en cliquant ; ses cartes restaient ouvertes pour
toujours (15 dans #general) et le rappel « décision en attente » les comptait. Le bouton ferme la
carte en silence. Le dual : un vrai choix publie toujours « @agent choix » (l'agent en a besoin),
et un choix hors liste reste refusé.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402
from store import MessageStore  # noqa: E402


class _Requete:
    def __init__(self, corps):
        self._corps = corps

    async def json(self):
        return self._corps


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MessageStore(str(Path(self.tmp.name) / "log.jsonl"))
        for nom, valeur in (("store", self.store), ("room_settings", {"username": "charles"})):
            self.addCleanup(setattr, app, nom, getattr(app, nom))
            setattr(app, nom, valeur)

        async def _rien(_):
            return None
        self.addCleanup(setattr, app, "_broadcast", app._broadcast)
        app._broadcast = _rien
        self.carte = self.store.add("claude", "Je publie ?", msg_type="decision",
                                    metadata={"choices": ["Oui, publie", "Pas encore"]})

    def resoudre(self, corps):
        return asyncio.run(app.resolve_decision(self.carte["id"], _Requete(corps)))

    def test_repondu_autrement_ferme_la_carte_sans_publier_de_message(self):
        avant = len(self.store.get_recent(100))
        r = self.resoudre({"autrement": True})
        self.assertEqual(r, {"ok": True, "chosen": "Répondu autrement"})
        meta = self.store.get_by_id(self.carte["id"])["metadata"]
        self.assertTrue(meta["resolved"])
        self.assertTrue(meta["autrement"])
        self.assertEqual(len(self.store.get_recent(100)), avant, "aucun « @claude … » publié : l'agent n'est pas relancé")

    def test_le_dual_un_vrai_choix_publie_toujours_sa_reponse(self):
        r = self.resoudre({"choice": "Oui, publie"})
        self.assertEqual(r["chosen"], "Oui, publie")
        dernier = self.store.get_recent(1)[0]
        self.assertEqual(dernier["text"], "@claude Oui, publie")
        self.assertNotIn("autrement", self.store.get_by_id(self.carte["id"])["metadata"])

    def test_un_choix_hors_liste_reste_refuse(self):
        r = self.resoudre({"choice": "Répondu autrement"})
        self.assertEqual(r.status_code, 400)

    # « Autre réponse… » : Charles écrit sa propre réponse au lieu des choix proposés.
    def test_autre_reponse_part_a_l_agent_et_ferme_la_carte(self):
        r = self.resoudre({"texte": "  Ni l'un ni l'autre : attends lundi  "})
        self.assertEqual(r["chosen"], "Ni l'un ni l'autre : attends lundi")
        dernier = self.store.get_recent(1)[0]
        self.assertEqual(dernier["text"], "@claude Ni l'un ni l'autre : attends lundi")
        self.assertEqual(dernier["reply_to"], self.carte["id"])
        meta = self.store.get_by_id(self.carte["id"])["metadata"]
        self.assertTrue(meta["resolved"])
        self.assertTrue(meta["autre"])

    def test_le_dual_une_reponse_vide_est_refusee_et_la_carte_reste_ouverte(self):
        r = self.resoudre({"texte": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.store.get_by_id(self.carte["id"])["metadata"].get("resolved"))


class TacheLibereeTests(unittest.TestCase):
    """Trancher la dernière carte ouverte d'une tâche « attend_charles » la remet « en_cours » : la t22 est restée
    quatre jours à « t'attend » dans l'atelier après le choix de Charles, sans rien à trancher."""

    def setUp(self):
        from jobs import JobStore
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MessageStore(str(Path(self.tmp.name) / "log.jsonl"))
        self.jobs = JobStore(str(Path(self.tmp.name) / "jobs.json"))
        for nom, valeur in (("store", self.store), ("jobs", self.jobs), ("room_settings", {"username": "charles"})):
            self.addCleanup(setattr, app, nom, getattr(app, nom))
            setattr(app, nom, valeur)

        async def _rien(_):
            return None
        self.addCleanup(setattr, app, "_broadcast", app._broadcast)
        app._broadcast = _rien
        self.tache, err = self.jobs.create_tache("quad", "Style", "conception", "claude", "claude",
                                                 equipe=[{"agent": "claude", "role": "producteur"}])
        self.assertEqual(err, "")
        self.mettre("attend_charles")

    def mettre(self, etat):
        _, err = self.jobs.update_tache(self.tache["id"], {"etat": etat})
        self.assertEqual(err, "")

    def etat(self):
        return self.jobs.get(self.tache["id"])["etat"]

    def carte(self, tache_id=None):
        return self.store.add("claude", "Quelle piste ?", msg_type="decision", channel="tache-%d" % self.tache["id"],
                              metadata={"choices": ["Piste 1", "Piste 2"]},
                              tache_id=self.tache["id"] if tache_id is None else tache_id)

    def resoudre(self, carte, corps=None):
        return asyncio.run(app.resolve_decision(carte["id"], _Requete(corps or {"choice": "Piste 1"})))

    def test_la_derniere_carte_tranchee_remet_la_tache_en_cours(self):
        self.resoudre(self.carte())
        self.assertEqual(self.etat(), "en_cours")

    def test_repondu_autrement_libere_aussi_la_tache(self):
        self.resoudre(self.carte(), {"autrement": True})
        self.assertEqual(self.etat(), "en_cours")

    def test_le_dual_une_autre_carte_ouverte_garde_la_tache_en_attente(self):
        a = self.carte()
        self.carte()
        self.resoudre(a)
        self.assertEqual(self.etat(), "attend_charles")

    def test_le_dual_une_tache_qui_n_attend_pas_charles_ne_change_pas(self):
        self.mettre("bloque")
        self.resoudre(self.carte())
        self.assertEqual(self.etat(), "bloque")

    def test_le_dual_une_carte_sans_tache_ne_touche_a_rien(self):
        self.resoudre(self.carte(tache_id=0))
        self.assertEqual(self.etat(), "attend_charles")


class RemplacementTests(unittest.TestCase):
    """La dernière carte d'un agent fait foi : une nouvelle carte ferme ses anciennes du même canal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MessageStore(str(Path(self.tmp.name) / "log.jsonl"))
        self.addCleanup(setattr, app, "store", app.store)
        app.store = self.store

    def carte(self, qui="claude", canal="general"):
        return self.store.add(qui, "Je fais quoi ?", msg_type="decision", channel=canal,
                              metadata={"choices": ["A", "B"], "resolved": False})

    def meta(self, m):
        return self.store.get_by_id(m["id"])["metadata"]

    def test_la_nouvelle_carte_ferme_les_anciennes_du_meme_agent_et_du_meme_canal(self):
        a, b = self.carte(), self.carte()
        c = self.carte()
        fermees = app._remplacer_decisions(c)
        self.assertEqual(sorted(m["id"] for m in fermees), [a["id"], b["id"]])
        for vieille in (a, b):
            self.assertTrue(self.meta(vieille)["resolved"])
            self.assertEqual(self.meta(vieille)["remplacee_par"], c["id"])
        self.assertFalse(self.meta(c)["resolved"], "la dernière reste à trancher")
        relu = MessageStore(str(Path(self.tmp.name) / "log.jsonl"))
        self.assertTrue(relu.get_by_id(a["id"])["metadata"]["resolved"], "écrit sur disque")

    def test_le_dual_autre_agent_autre_canal_ou_deja_tranchee_ne_bougent_pas(self):
        codex = self.carte(qui="codex")
        ailleurs = self.carte(canal="projet")
        tranchee = self.carte()
        self.store.get_by_id(tranchee["id"])["metadata"].update(resolved=True, chosen="A")
        nouvelle = self.carte()
        self.assertEqual(app._remplacer_decisions(nouvelle), [])
        self.assertFalse(self.meta(codex)["resolved"])
        self.assertFalse(self.meta(ailleurs)["resolved"])
        self.assertEqual(self.meta(tranchee)["chosen"], "A")

    def test_un_message_ordinaire_ne_ferme_rien(self):
        a = self.carte()
        self.assertEqual(app._remplacer_decisions(self.store.add("claude", "Fait.")), [])
        self.assertFalse(self.meta(a)["resolved"])


if __name__ == "__main__":
    unittest.main()
