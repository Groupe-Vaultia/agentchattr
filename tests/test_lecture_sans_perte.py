"""Lecture sans perte : chat_read ne doit jamais sauter un message que l'agent n'a pas recu.

v1.0 (2026-11-09, claude) : donnees synthetiques seulement. Trois pertes reproduites :
- une lecture incrementale (curseur ou since_id) qui depasse `limit` rendait les plus RECENTS et avancait le curseur
  au dernier : les plus anciens etaient perdus (salle sobre ou non);
- une lecture complete (complet=True) qui ne couvre pas tout le non-lu avancait le curseur par-dessus le trou;
- chat_send avancait le curseur jusqu'au message envoye, par-dessus ce qui etait arrive depuis la derniere lecture.
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

import mcp_bridge
import sobriete
from store import MessageStore


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.compteur = sobriete.Compteur(root / "sobriete.json")
        for p in (
            mock.patch.object(mcp_bridge, "store", self.store),
            mock.patch.object(mcp_bridge, "registry", None),
            mock.patch.object(mcp_bridge, "jobs", None),
            mock.patch.object(mcp_bridge, "router", None),
            mock.patch.object(mcp_bridge, "sobriete", self.compteur),
            mock.patch.object(mcp_bridge, "config", {"routing": {"chef": "claude-1"}}),
            mock.patch.object(mcp_bridge, "room_settings", {"username": "Charles"}),
            mock.patch.object(mcp_bridge, "_cursors", {}),
            mock.patch.object(mcp_bridge, "_save_cursors"),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity",
                              side_effect=lambda sender, *_a, **_k: (sender, None)),
        ):
            p.start()
            self.addCleanup(p.stop)
        # Un store neuf numerote a partir de 0, et un curseur ou un since_id a 0 veut dire « aucun » : on decale.
        self.store.add("system", "ouverture", channel="hors-test")

    def _ajout(self, sender, text, canal="general"):
        return self.store.add(sender, text, channel=canal)

    @staticmethod
    def _textes(brut):
        tete = brut.split("\n\n")[0]
        if not tete.startswith("["):
            return []
        return [m["text"] for m in json.loads(tete)]

    def _lire_jusqu_au_bout(self, sender, canal, limit, maximum=20):
        """Relit jusqu'a « rien de neuf »; rend tous les textes recus, dans l'ordre."""
        recus = []
        for _ in range(maximum):
            brut = mcp_bridge.chat_read(sender=sender, channel=canal, limit=limit)
            textes = self._textes(brut)
            if not textes:
                return recus
            recus += textes
        self.fail("la lecture ne converge pas")


class CurseurPagineTests(_Base):
    def test_canal_ordinaire_rien_de_perdu(self):
        self._ajout("Charles", "debut")
        mcp_bridge.chat_read(sender="claude-2", channel="general", limit=5)   # pose le curseur
        attendus = [f"m{i}" for i in range(12)]
        for t in attendus:
            self._ajout("codex", t)
        brut = mcp_bridge.chat_read(sender="claude-2", channel="general", limit=5)
        self.assertEqual(self._textes(brut), attendus[:5])          # les plus anciens d'abord
        self.assertIn("7 message(s) de plus", brut)                  # l'agent sait qu'il doit relire
        self.assertEqual(self._lire_jusqu_au_bout("claude-2", "general", 5), attendus[5:])

    def test_salle_sobre_rien_de_perdu_et_masques_comptes_une_fois(self):
        self._ajout("Charles", "go", canal="tache-7")
        mcp_bridge.chat_read(sender="qwen", channel="tache-7", limit=5)      # pose le curseur
        adresses = []
        for i in range(9):
            t = f"@qwen consigne {i}"
            adresses.append(t)
            self._ajout("codex", t, canal="tache-7")
            self._ajout("grok", f"bruit {i}", canal="tache-7")                # masque pour qwen
        brut = mcp_bridge.chat_read(sender="qwen", channel="tache-7", limit=4)
        self.assertEqual(self._textes(brut), adresses[:4])
        self.assertIn("5 message(s) de plus", brut)
        self.assertEqual(self._lire_jusqu_au_bout("qwen", "tache-7", 4), adresses[4:])
        r = self.compteur.rapport()["agents"]["qwen"]
        self.assertEqual(r["messages_masques"], 9)                           # ni perdu ni compte deux fois

    def test_since_id_rend_la_suite_et_dit_comment_continuer(self):
        premier = self._ajout("Charles", "debut")
        ids = [self._ajout("codex", f"m{i}")["id"] for i in range(8)]
        brut = mcp_bridge.chat_read(sender="claude-2", channel="general", since_id=premier["id"], limit=3)
        self.assertEqual(self._textes(brut), ["m0", "m1", "m2"])
        self.assertIn(f"since_id={ids[2]}", brut)
        brut = mcp_bridge.chat_read(sender="claude-2", channel="general", since_id=ids[2], limit=3)
        self.assertEqual(self._textes(brut), ["m3", "m4", "m5"])

    def test_since_id_ne_recule_pas_le_curseur(self):
        premier = self._ajout("Charles", "debut")
        for i in range(6):
            self._ajout("codex", f"m{i}")
        mcp_bridge.chat_read(sender="claude-2", channel="general", limit=50)  # a tout lu
        mcp_bridge.chat_read(sender="claude-2", channel="general", since_id=premier["id"], limit=2)  # relit le debut
        self.assertIn("No new messages", mcp_bridge.chat_read(sender="claude-2", channel="general"))

    def test_premiere_lecture_garde_le_contexte_recent(self):
        for i in range(30):
            self._ajout("codex", f"m{i}")
        brut = mcp_bridge.chat_read(sender="claude-2", channel="general", limit=5)
        self.assertEqual(self._textes(brut), [f"m{i}" for i in range(25, 30)])
        self.assertNotIn("de plus", brut)


class LectureCompleteTests(_Base):
    def test_complet_ne_saute_pas_le_non_lu_hors_fenetre(self):
        self._ajout("Charles", "go", canal="tache-7")
        mcp_bridge.chat_read(sender="qwen", channel="tache-7")                # pose le curseur
        self._ajout("codex", "@qwen NO-GO : paroi trop mince", canal="tache-7")
        for i in range(6):
            self._ajout("grok", f"bruit {i}", canal="tache-7")
        brut = mcp_bridge.chat_read(sender="qwen", channel="tache-7", complet=True, limit=3)
        self.assertEqual(self._textes(brut), ["bruit 3", "bruit 4", "bruit 5"])
        self.assertIn("plus ancien", brut)
        # La lecture suivante rend encore le NO-GO, qui n'etait pas dans la fenetre.
        self.assertIn("@qwen NO-GO : paroi trop mince",
                      self._textes(mcp_bridge.chat_read(sender="qwen", channel="tache-7")))

    def test_complet_qui_couvre_tout_avance_le_curseur(self):
        self._ajout("Charles", "go", canal="tache-7")
        mcp_bridge.chat_read(sender="qwen", channel="tache-7")
        self._ajout("grok", "bruit", canal="tache-7")
        mcp_bridge.chat_read(sender="qwen", channel="tache-7", complet=True)
        self.assertIn("No new messages", mcp_bridge.chat_read(sender="qwen", channel="tache-7"))


class EnvoiTests(_Base):
    def test_envoi_ne_saute_pas_ce_qui_est_arrive_entre_temps(self):
        self._ajout("Charles", "debut")
        mcp_bridge.chat_read(sender="claude-2", channel="general")            # curseur sur « debut »
        self._ajout("codex", "NO-GO sur le lot 23")                           # arrive pendant que l'agent travaille
        self.assertTrue(mcp_bridge.chat_send(sender="claude-2", message="GO lot 23", channel="general")
                        .startswith("Sent"))
        self.assertIn("NO-GO sur le lot 23",
                      self._textes(mcp_bridge.chat_read(sender="claude-2", channel="general")))

    def test_envoi_sans_rien_entre_temps_ne_se_relit_pas(self):
        self._ajout("Charles", "debut")
        mcp_bridge.chat_read(sender="claude-2", channel="general")
        mcp_bridge.chat_send(sender="claude-2", message="vu", channel="general")
        self.assertIn("No new messages", mcp_bridge.chat_read(sender="claude-2", channel="general"))

    def test_proposition_de_tache_ne_saute_rien(self):
        self._ajout("Charles", "debut")
        mcp_bridge.chat_read(sender="claude-2", channel="general")
        self._ajout("codex", "attention : base de la PR fausse")
        mcp_bridge.chat_propose_job(sender="claude-2", title="Lot 24", channel="general")
        self.assertIn("attention : base de la PR fausse",
                      self._textes(mcp_bridge.chat_read(sender="claude-2", channel="general")))


if __name__ == "__main__":
    unittest.main()
