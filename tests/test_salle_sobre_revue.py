"""Salle sobre : un test par constat de la revue independante du 20 oct. 2026 (PR #66 et #67).

v1.0 (2026-10-20, claude) : chaque test reproduit le scenario du relecteur et verifie la correction.
Donnees synthetiques seulement.
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
import jobs as jobs_mod
import mcp_bridge
import projects
import sobriete
import wrapper
from jobs import JobStore
from store import MessageStore

IDENTITE = mock.patch.object(mcp_bridge, "_resolve_tool_identity", side_effect=lambda s, *_a, **_k: (s, None))


class _AppReelle(unittest.TestCase):
    """App configuree pour de vrai (routeur, jobs, middleware), etat global restaure a la fin."""

    CONFIG_AGENTS = {"claude": {}, "codex": {}, "qwen": {}, "gemini": {}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._app_state = app.__dict__.copy()
        self._room = copy.deepcopy(app.room_settings)
        self._mw = list(app.app.user_middleware)
        self._proj = (projects._state, projects._FILE)
        self._bridge = {k: getattr(mcp_bridge, k) for k in ("jobs", "maj_tache", "config", "room_settings",
                                                             "store", "registry", "sobriete", "revisions")}
        self.addCleanup(self._restore)
        app.app.middleware_stack = None
        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({"server": {"data_dir": str(self.root / "data")}, "agents": self.CONFIG_AGENTS,
                           "routing": {"max_agent_hops": 1, "chef": "claude-1"}, "images": {},
                           "socle": {"racine_livrables": str(self.root)}}, session_token="sess")
        projects.configurer(self.root / "projects.json")
        self.pid = projects.creer("P")
        self.tache, err = app.jobs.create_tache(
            self.pid, "T", "conception", "qwen", created_by="user",
            equipe=[{"agent": "qwen", "role": "producteur"}, {"agent": "codex", "role": "verificateur"}])
        self.assertEqual(err, "")
        self.canal = f"tache-{self.tache['id']}"
        mcp_bridge.jobs = app.jobs
        mcp_bridge.maj_tache = app.appliquer_maj_tache
        mcp_bridge.config = app.config
        mcp_bridge.room_settings = app.room_settings
        mcp_bridge.store = app.store
        mcp_bridge.registry = None
        mcp_bridge.sobriete = app.sobriete
        mcp_bridge.revisions = app.revisions
        IDENTITE.start()
        self.addCleanup(IDENTITE.stop)
        # Curseurs de lecture : globaux au module, ils ne doivent pas fuir d'un test a l'autre.
        for p in (mock.patch.object(mcp_bridge, "_cursors", {}), mock.patch.object(mcp_bridge, "_save_cursors")):
            p.start()
            self.addCleanup(p.stop)

    def _restore(self):
        for k, v in self._bridge.items():
            setattr(mcp_bridge, k, v)
        for key in list(app.__dict__):
            if key not in self._app_state:
                delattr(app, key)
        for key, value in self._app_state.items():
            setattr(app, key, value)
        app.room_settings.clear()
        app.room_settings.update(self._room)
        app.app.user_middleware = self._mw
        app.app.middleware_stack = None
        projects._state, projects._FILE = self._proj

    def _mettre_en_pause(self):
        r = app.router
        r.get_targets("codex", "@qwen a toi", self.canal)
        r.get_targets("qwen", "@codex non a toi", self.canal)
        self.assertTrue(r.is_paused(self.canal))


class BloquantGardeFouTests(_AppReelle):
    """Bloquant : un agent ne doit jamais lever une pause du loop guard par tache_maj."""

    def test_meme_etat_ne_leve_pas_la_pause(self):
        self._mettre_en_pause()
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="a_faire")
        self.assertTrue(app.router.is_paused(self.canal))

    def test_vraie_transition_par_agent_ne_leve_pas_la_pause(self):
        self._mettre_en_pause()
        r = json.loads(mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="en_cours"))
        self.assertEqual(r["etat"], "en_cours")
        self.assertTrue(app.router.is_paused(self.canal))

    def test_vraie_transition_hors_pause_compte_comme_progres(self):
        app.router.note_heartbeat(self.canal)
        self.assertEqual(app.router.heartbeats_since_progress(self.canal), 1)
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="en_cours")
        self.assertEqual(app.router.heartbeats_since_progress(self.canal), 0)

    def test_redeclarer_le_meme_etat_n_est_pas_un_progres(self):
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="en_cours")
        app.router.note_heartbeat(self.canal)
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="en_cours")
        self.assertEqual(app.router.heartbeats_since_progress(self.canal), 1)

    def test_patch_de_l_interface_inchange(self):
        """La route PATCH (Charles) garde son comportement : elle releve la pause comme avant."""
        self._mettre_en_pause()
        c = TestClient(app.app, headers={"x-session-token": "sess"})
        self.addCleanup(c.close)
        self.assertEqual(c.patch(f"/api/v2/taches/{self.tache['id']}", json={"etat": "en_cours"}).status_code, 200)
        self.assertFalse(app.router.is_paused(self.canal))


class DroitsTests(_AppReelle):
    """Important : seuls l'equipe et le chef ecrivent; seul le responsable (ou le chef) passe a fait."""

    def test_hors_equipe_refuse(self):
        tid = self.tache["id"]
        for appel in (lambda: mcp_bridge.tache_maj(sender="gemini", tache_id=tid, etat="en_cours"),
                      lambda: mcp_bridge.decision_noter(sender="gemini", tache_id=tid, texte="x"),
                      lambda: mcp_bridge.livrable_deposer(sender="gemini", tache_id=tid, chemin="a.py")):
            self.assertIn("pas dans l'equipe", appel())
        self.assertEqual(app.jobs.get(tid)["etat"], "a_faire")

    def test_fait_reserve_au_responsable(self):
        r = mcp_bridge.tache_maj(sender="codex", tache_id=self.tache["id"], etat="fait", preuve="pytest 3 passed")
        self.assertIn("seul le responsable", r)
        r = json.loads(mcp_bridge.tache_maj(sender="qwen", tache_id=self.tache["id"], etat="fait",
                                            preuve="pytest 3 passed"))
        self.assertEqual(r["etat"], "fait")

    def test_verificateur_peut_ecrire_hors_fait(self):
        r = json.loads(mcp_bridge.tache_maj(sender="codex-2", tache_id=self.tache["id"],
                                            derniere_erreur="paroi 0,8 mm"))
        self.assertTrue(r["ok"])

    def test_chef_peut_tout(self):
        r = json.loads(mcp_bridge.tache_maj(sender="claude-1", tache_id=self.tache["id"], etat="fait",
                                            preuve="go de Charles"))
        self.assertEqual(r["etat"], "fait")


class LectureTests(_AppReelle):
    def _ajout(self, sender, text, canal=None):
        return app.store.add(sender, text, channel=canal or self.canal)

    def test_complet_recupere_les_masques_deja_depasses(self):
        self._ajout("codex", "revue de grok, longue")
        self._ajout("codex", "@qwen a toi")
        mcp_bridge.chat_read(sender="qwen", channel=self.canal)
        brut = mcp_bridge.chat_read(sender="qwen", channel=self.canal, complet=True)
        self.assertIn("revue de grok, longue", brut)

    def test_chef_exempte_du_filtre(self):
        self._ajout("codex", "@qwen corrige la paroi")  # message bloque entre deux AUTRES agents
        brut = mcp_bridge.chat_read(sender="claude-1", channel=self.canal)
        self.assertIn("@qwen corrige la paroi", brut)
        self.assertNotIn("masque", brut)

    def test_rappel_auto_adresse_garde(self):
        self._ajout("qwen", "@qwen Point d'etape : relancer le banc")
        brut = mcp_bridge.chat_read(sender="qwen", channel=self.canal)
        self.assertIn("Point d'etape", brut)

    def test_instance_renommee_reconnue_par_son_nom_de_base(self):
        self._ajout("user", "debut")
        self._ajout("codex", "@claude regarde le carter")
        reg = mock.Mock()
        reg.get_instance.side_effect = lambda n: {"name": n, "base": "claude"} if n == "claude-music" else None
        reg.is_registered.return_value = False
        with mock.patch.object(mcp_bridge, "registry", reg):
            brut = mcp_bridge.chat_read(sender="claude-music", channel=self.canal)
        self.assertIn("@claude regarde le carter", brut)

    def test_lecture_tous_canaux_filtree_message_par_message(self):
        self._ajout("grok", "travail de grok")
        self._ajout("grok", "annonce generale", canal="general")
        brut = mcp_bridge.chat_read(sender="qwen")
        self.assertIn("annonce generale", brut)
        self.assertNotIn("travail de grok", brut)
        self.assertIn("masque", brut)

    def test_premiere_lecture_filtree_regarde_plus_loin_que_la_limite(self):
        self._ajout("codex", "@qwen consigne ancienne")
        for i in range(8):
            self._ajout("grok", f"bruit {i}")
        brut = mcp_bridge.chat_read(sender="qwen", channel=self.canal, limit=3)
        self.assertIn("consigne ancienne", brut)


class ApiMessagesTests(_AppReelle):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(app.registry, "resolve_token",
                              side_effect=lambda t: {"gemini": {"name": "gemini"}, "chef": {"name": "claude-1"}}.get(t))
        p.start()
        self.addCleanup(p.stop)
        self.agent = TestClient(app.app, headers={"authorization": "Bearer gemini"})
        self.chef = TestClient(app.app, headers={"authorization": "Bearer chef"})
        self.addCleanup(self.agent.close)
        self.addCleanup(self.chef.close)

    def test_garde_ses_propres_messages_et_regarde_avant_la_limite(self):
        app.store.add("codex", "@gemini fais le DFM", channel=self.canal)
        app.store.add("gemini", "DFM fait : 2 avertissements", channel=self.canal)
        for i in range(10):
            app.store.add("grok", f"bruit {i}", channel=self.canal)
        textes = [m["text"] for m in self.agent.get(f"/api/messages?channel={self.canal}&limit=5").json()]
        self.assertEqual(textes, ["@gemini fais le DFM", "DFM fait : 2 avertissements"])

    def test_chef_voit_tout(self):
        app.store.add("codex", "@qwen a toi", channel=self.canal)
        self.assertEqual(len(self.chef.get(f"/api/messages?channel={self.canal}").json()), 1)

    def test_regex_stricte_de_la_fiche(self):
        self.assertEqual(self.agent.get(f"/api/v2/taches/{self.tache['id']}/fiche").status_code, 200)
        self.assertEqual(self.agent.get("/api/v2/taches/abc/fiche").status_code, 403)
        self.assertEqual(self.agent.get("/api/v2/taches/1/x/fiche").status_code, 403)


class MineursTests(unittest.TestCase):
    def test_fiche_bornee_sur_critere_et_livrables(self):
        t = {"id": 3, "titre": "T", "critere": "c" * 2000, "equipe": [], "decisions": []}
        livs = [{"chemin": f"f{i}.py", "version": 1, "empreinte": "a" * 64, "statut": "present", "heure": i}
                for i in range(25)]
        f = jobs_mod.fiche(t, livrables=livs)
        self.assertEqual(len(f["critere"]), jobs_mod.MAX_CRITERE_FICHE)
        self.assertEqual([l["chemin"] for l in f["livrables"]][-1], "f24.py")
        self.assertEqual(len(f["livrables"]), jobs_mod.LIVRABLES_FICHE)
        self.assertEqual(f["livrables_masques"], 15)

    def test_oserror_rendue_proprement(self):
        js = JobStore(str(Path(tempfile.mkdtemp()) / "j.json"))
        t, _ = js.create_tache("p", "T", "conception", "qwen", created_by="user",
                               equipe=[{"agent": "qwen", "role": "producteur"}])
        revs = mock.Mock()
        revs.enregistrer_livrable.side_effect = OSError("File name too long")
        with mock.patch.object(mcp_bridge, "jobs", js), mock.patch.object(mcp_bridge, "revisions", revs), \
                mock.patch.object(mcp_bridge, "config", {}), mock.patch.object(mcp_bridge, "room_settings", {}), \
                IDENTITE:
            r = mcp_bridge.livrable_deposer(sender="qwen", tache_id=t["id"], chemin="x" * 300)
        self.assertEqual(r, "Error: File name too long")

    def test_json_non_objet_ne_bloque_pas_le_demarrage(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "sobriete.json"
            chemin.write_text("[]", encoding="utf-8")
            self.assertEqual(sobriete.Compteur(chemin).rapport()["agents"], {})

    def test_ecritures_groupees(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "sobriete.json"
            c = sobriete.Compteur(chemin, intervalle=3600)
            c.ajouter("qwen", tache_lire=1)                      # premiere ecriture immediate
            c.ajouter("qwen", tache_lire=1)                      # retenue
            self.assertEqual(json.loads(chemin.read_text())["agents"]["qwen"]["tache_lire"], 1)
            c.vider()
            self.assertEqual(json.loads(chemin.read_text())["agents"]["qwen"]["tache_lire"], 2)

    def test_outils_declares_au_proxy(self):
        import mcp_proxy
        for nom in ("tache_lire", "tache_maj", "livrable_deposer", "decision_noter"):
            self.assertEqual(mcp_proxy._SENDER_PARAMS[nom], "sender")


class _Stop(Exception):
    pass


class TriggerPromptPrioritaireTests(unittest.TestCase):
    FICHE = {"tache_id": 7, "titre": "Collier", "prochaine_action": "Relire la paroi"}

    def _prompt(self, trigger_prompt):
        with tempfile.TemporaryDirectory() as d:
            queue = Path(d) / "q.jsonl"
            queue.write_text(json.dumps({"channel": "tache-7"}) + "\n", encoding="utf-8")
            injecte, appels = [], []

            def poll(sec):
                if sec == 1:
                    raise _Stop()

            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_trigger_memory", return_value=("", "")), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=None), \
                    mock.patch.object(wrapper, "_fetch_fiche",
                                      side_effect=lambda *a, **k: appels.append(a) or self.FICHE), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=poll):
                with self.assertRaises(_Stop):
                    wrapper._queue_watcher(lambda: ("bolt-1", queue), injecte.append, server_port=8300,
                                           agent_name="bolt", trigger_prompt=trigger_prompt)
            return injecte[0], appels

    def test_invite_propre_gardee_sans_fiche(self):
        prompt, appels = self._prompt("Lis {cible} avec chat_read puis reponds, {name}.")
        self.assertEqual(prompt, "Lis channel='tache-7' avec chat_read puis reponds, bolt-1.")
        self.assertEqual(appels, [])

    def test_invite_propre_avec_fiche_sur_demande(self):
        prompt, appels = self._prompt("Etat : {fiche}. Reponds dans {cible}.")
        self.assertIn("Relire la paroi", prompt)
        self.assertEqual(len(appels), 1)


if __name__ == "__main__":
    unittest.main()
