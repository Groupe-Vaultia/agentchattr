"""Salle sobre, lots 2 et 3 : la fiche au reveil, le fil filtre dans les canaux de tache, et le compteur.

v1.1 (2026-10-20, claude) : revue independante — compteur a ecritures groupees (vider), libelle de la note.
v1.0 (2026-10-20, claude) : donnees synthetiques seulement.
- Lot 3 : sobriete.filtrer_pour; chat_read filtre dans tache-N (complet=True explicite); /api/messages filtre pour
  un jeton d'agent (Gemini cli_print, agents API) et pas pour l'interface; compteur et GET /api/v2/sobriete.
- Lot 2 : GET /api/v2/taches/{id}/fiche (jeton d'agent accepte); le wrapper CLI injecte la fiche au reveil dans un
  canal de tache, et revient a l'ancienne invite si la fiche est inaccessible.
"""

import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import mcp_bridge
import projects
import sobriete
import wrapper
from jobs import JobStore
from store import MessageStore


def _msg(sender, text, i=0):
    return {"id": i, "sender": sender, "text": text}


class FiltreTests(unittest.TestCase):
    HUMAINS = {"user", "Charles"}

    def test_garde_humains_et_mentions_masque_le_reste(self):
        msgs = [
            _msg("Charles", "On vise du PETG", 1),
            _msg("codex", "@claude-1 revue faite, 2 constats", 2),
            _msg("codex", "@qwen corrige la paroi", 3),
            _msg("grok", "J'ai relu le tableau de motricite", 4),
            _msg("system", "qwen joined", 5),
            _msg("claude-1", "@codex merci", 6),
            _msg("gemini", "@all pause de 5 min", 7),
        ]
        gardes, masques = sobriete.filtrer_pour(msgs, "claude-1", self.HUMAINS)
        self.assertEqual([m["id"] for m in gardes], [1, 2, 7])
        self.assertEqual([m["id"] for m in masques], [3, 4, 5, 6])

    def test_nom_de_base_et_frontieres(self):
        self.assertTrue(sobriete.mentionne("@claude regarde", "claude-1"))
        self.assertFalse(sobriete.mentionne("@claude-2 regarde", "claude-1"))
        self.assertFalse(sobriete.mentionne("@claude-10 regarde", "claude-1"))
        self.assertFalse(sobriete.mentionne("courriel claude@x.ca", "claude-1"))
        self.assertTrue(sobriete.mentionne("@Codex ok", "codex"))

    def test_canal_tache(self):
        self.assertTrue(sobriete.est_canal_tache("tache-42"))
        self.assertFalse(sobriete.est_canal_tache("general"))
        self.assertFalse(sobriete.est_canal_tache(None))


class CompteurTests(unittest.TestCase):
    def test_persistance_et_rapport(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "sobriete.json"
            c = sobriete.Compteur(chemin)
            c.ajouter("codex", tache_lire=2, fiche_au_reveil=1)
            c.masquer("codex", [_msg("grok", "x" * 400), _msg("qwen", "y" * 400)])
            c.ajouter("codex", lecture_complete=1)
            c.vider()
            r = sobriete.Compteur(chemin).rapport()["agents"]["codex"]  # relu depuis le disque
            self.assertEqual((r["tache_lire"], r["fiche_au_reveil"]), (2, 1))
            self.assertEqual((r["lecture_filtree"], r["lecture_complete"]), (1, 1))
            self.assertEqual((r["messages_masques"], r["caracteres_masques"]), (2, 800))
            self.assertEqual(r["jetons_evites_approx"], 200)
            self.assertEqual(r["part_base"], 0.6)  # 3 lectures base / 5 lectures

    def test_fichier_illisible_ne_plante_pas(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "sobriete.json"
            chemin.write_text("{pas du json", encoding="utf-8")
            self.assertEqual(sobriete.Compteur(chemin).rapport()["agents"], {})


class ChatReadFiltreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.compteur = sobriete.Compteur(root / "sobriete.json")
        for p in (
            mock.patch.object(mcp_bridge, "store", self.store),
            mock.patch.object(mcp_bridge, "registry", None),
            mock.patch.object(mcp_bridge, "sobriete", self.compteur),
            mock.patch.object(mcp_bridge, "room_settings", {"username": "Charles"}),
            mock.patch.object(mcp_bridge, "_cursors", {}),
            mock.patch.object(mcp_bridge, "_save_cursors"),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity",
                              side_effect=lambda sender, *_a, **_k: (sender, None)),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.store.add("Charles", "Go pour la tache", channel="tache-7")
        self.store.add("codex", "@qwen ta paroi est trop mince " + "z" * 300, channel="tache-7")
        self.store.add("grok", "Tableau de couples " + "w" * 300, channel="tache-7")
        self.store.add("codex", "@claude-1 revue rendue", channel="tache-7")
        self.store.add("grok", "ronde : rien a faire", channel="general")

    def _textes(self, brut):
        return [m["text"] for m in json.loads(brut.split("\n\n")[0])]

    def test_canal_tache_filtre_et_note(self):
        brut = mcp_bridge.chat_read(sender="claude-1", channel="tache-7")
        self.assertEqual(self._textes(brut), ["Go pour la tache", "@claude-1 revue rendue"])
        self.assertIn("2 message(s) masque(s) dans #tache-7", brut)
        self.assertIn("tache_lire(tache_id=7)", brut)
        r = self.compteur.rapport()["agents"]["claude-1"]
        self.assertEqual((r["lecture_filtree"], r["messages_masques"]), (1, 2))

    def test_masques_ne_reviennent_pas(self):
        mcp_bridge.chat_read(sender="claude-1", channel="tache-7")
        self.assertIn("No new messages", mcp_bridge.chat_read(sender="claude-1", channel="tache-7"))

    def test_lecture_complete_explicite(self):
        brut = mcp_bridge.chat_read(sender="claude-1", channel="tache-7", complet=True)
        self.assertEqual(len(self._textes(brut)), 4)
        self.assertNotIn("masque", brut)
        self.assertEqual(self.compteur.rapport()["agents"]["claude-1"]["lecture_complete"], 1)

    def test_autres_canaux_non_filtres(self):
        brut = mcp_bridge.chat_read(sender="claude-1", channel="general")
        self.assertEqual(self._textes(brut), ["ronde : rien a faire"])
        self.assertEqual(self.compteur.rapport()["agents"], {})

    def test_humain_voit_tout(self):
        brut = mcp_bridge.chat_read(sender="Charles", channel="tache-7")
        self.assertEqual(len(self._textes(brut)), 4)

    def test_resync_comptee_comme_lecture_complete(self):
        mcp_bridge.chat_resync(sender="qwen", channel="tache-7")
        self.assertEqual(self.compteur.rapport()["agents"]["qwen"]["lecture_complete"], 1)

    def test_tache_lire_comptee(self):
        jobs = JobStore(str(Path(self.tmp.name) / "jobs.json"))
        t, _ = jobs.create_tache("alpha", "T", "conception", "qwen", created_by="user",
                                 equipe=[{"agent": "qwen", "role": "producteur"}])
        with mock.patch.object(mcp_bridge, "jobs", jobs), mock.patch.object(mcp_bridge, "revisions", None):
            mcp_bridge.tache_lire(sender="qwen", tache_id=t["id"])
        self.assertEqual(self.compteur.rapport()["agents"]["qwen"]["tache_lire"], 1)


class RoutesTests(unittest.TestCase):
    """/api/messages filtre pour un jeton d'agent; la fiche se lit avec ce jeton; /api/v2/sobriete rapporte."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._app_state = app.__dict__.copy()
        self._room_settings = copy.deepcopy(app.room_settings)
        self._middleware = list(app.app.user_middleware)
        self._projects_state = (projects._state, projects._FILE)
        self.addCleanup(self._restore)
        # Un test precedent de la suite peut laisser l'app « demarree » : sans ceci, configure() ne peut pas
        # reinstaller le middleware (« Cannot add middleware after an application has started »).
        app.app.middleware_stack = None
        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({"server": {"data_dir": str(self.root / "data")}, "agents": {}, "routing": {},
                           "images": {}, "socle": {"racine_livrables": str(self.root)}},
                          session_token="sess-sobre")
        projects.configurer(self.root / "projects.json")
        self.pid = projects.creer("Projet synthetique")
        p = mock.patch.object(app.registry, "resolve_token",
                              side_effect=lambda t: {"name": "gemini"} if t == "tok-gemini" else None)
        p.start()
        self.addCleanup(p.stop)
        self.ui = TestClient(app.app, headers={"x-session-token": "sess-sobre"})
        self.agent = TestClient(app.app, headers={"authorization": "Bearer tok-gemini"})
        self.addCleanup(self.ui.close)
        self.addCleanup(self.agent.close)
        r = self.ui.post("/api/v2/taches", json={
            "projet_id": self.pid, "titre": "Collier", "etape": "conception", "responsable": "gemini",
            "equipe": [{"agent": "gemini", "role": "producteur"}], "critere": "paroi >= 1,2 mm"})
        self.assertEqual(r.status_code, 200, r.text)
        self.tid = r.json()["id"]
        canal = f"tache-{self.tid}"
        app.store.add("user", "Go", channel=canal)
        app.store.add("codex", "Revue de grok " + "x" * 200, channel=canal)
        app.store.add("codex", "@gemini a toi", channel=canal)

    def _restore(self):
        for key in list(app.__dict__):
            if key not in self._app_state:
                delattr(app, key)
        for key, value in self._app_state.items():
            setattr(app, key, value)
        app.room_settings.clear()
        app.room_settings.update(self._room_settings)
        app.app.user_middleware = self._middleware
        app.app.middleware_stack = None
        projects._state, projects._FILE = self._projects_state

    def test_agent_recoit_le_fil_filtre(self):
        r = self.agent.get(f"/api/messages?channel=tache-{self.tid}&limit=20")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([m["text"] for m in r.json()], ["Go", "@gemini a toi"])
        rap = self.ui.get("/api/v2/sobriete").json()["agents"]["gemini"]
        self.assertEqual((rap["lecture_filtree"], rap["messages_masques"]), (1, 1))

    def test_interface_voit_tout(self):
        r = self.ui.get(f"/api/messages?channel=tache-{self.tid}&limit=20")
        self.assertEqual(len(r.json()), 3)

    def test_agent_lecture_complete_explicite(self):
        r = self.agent.get(f"/api/messages?channel=tache-{self.tid}&limit=20&complet=true")
        self.assertEqual(len(r.json()), 3)

    def test_fiche_avec_jeton_d_agent_comptee_au_reveil(self):
        r = self.agent.get(f"/api/v2/taches/{self.tid}/fiche?reveil=1&pour=quelqu-un-d-autre")
        self.assertEqual(r.status_code, 200, r.text)
        f = r.json()
        self.assertEqual((f["tache_id"], f["critere"], f["ton_role"]), (self.tid, "paroi >= 1,2 mm", "producteur"))
        self.assertEqual(self.ui.get("/api/v2/sobriete").json()["agents"]["gemini"]["fiche_au_reveil"], 1)

    def test_jeton_d_agent_refuse_ailleurs(self):
        self.assertEqual(self.agent.get("/api/v2/sobriete").status_code, 403)
        self.assertEqual(self.agent.patch(f"/api/v2/taches/{self.tid}", json={"etat": "fait"}).status_code, 403)

    def test_fiche_tache_inconnue(self):
        self.assertEqual(self.agent.get("/api/v2/taches/9999/fiche").status_code, 404)


class _Stop(Exception):
    pass


class ReveilWrapperTests(unittest.TestCase):
    FICHE = {"tache_id": 7, "titre": "Collier", "etat": "en_cours", "ton_role": "verificateur",
             "prochaine_action": "Relire la paroi", "decisions": [], "livrables": []}

    def _prompt(self, entry, fiche):
        with tempfile.TemporaryDirectory() as d:
            queue = Path(d) / "q.jsonl"
            queue.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            injecte, appels = [], []

            def poll(sec):
                if sec == 1:
                    raise _Stop()

            def fetch(port, tid, token=""):
                appels.append((tid, token))
                return fiche

            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_trigger_memory", return_value=("", "")), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=None), \
                    mock.patch.object(wrapper, "_fetch_fiche", side_effect=fetch), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=poll):
                with self.assertRaises(_Stop):
                    wrapper._queue_watcher(lambda: ("codex-1", queue), injecte.append, server_port=8300,
                                           agent_name="codex", get_token_fn=lambda: "tok")
            return injecte[0], appels

    def test_fiche_injectee_dans_un_canal_de_tache(self):
        prompt, appels = self._prompt({"channel": "tache-7"}, self.FICHE)
        self.assertEqual(appels, [(7, "tok")])
        self.assertIn("FICHE DE LA TACHE", prompt)
        self.assertIn("Relire la paroi", prompt)
        self.assertIn("tache_maj", prompt)
        self.assertNotIn("use mcp to read #tache-7", prompt)
        self.assertNotIn("\n", prompt)

    def test_repli_si_fiche_inaccessible(self):
        prompt, _ = self._prompt({"channel": "tache-7"}, None)
        self.assertIn("use mcp to read #tache-7", prompt)

    def test_canal_general_inchange(self):
        prompt, appels = self._prompt({"channel": "general"}, self.FICHE)
        self.assertEqual(appels, [])
        self.assertIn("use mcp to read #general", prompt)

    def test_invite_explicite_prioritaire(self):
        prompt, appels = self._prompt({"channel": "tache-7", "prompt": "Fais la ronde"}, self.FICHE)
        self.assertEqual((prompt, appels), ("Fais la ronde", []))


if __name__ == "__main__":
    unittest.main()
