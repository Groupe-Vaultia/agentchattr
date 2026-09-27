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


if __name__ == "__main__":
    unittest.main()
