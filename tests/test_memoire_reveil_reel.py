"""Memoire de projet et fiche au reveil, de bout en bout : vrai serveur HTTP, vrai middleware, vrai jeton.

v1.1 (2026-10-20, claude) : borne reglable ([sobriete] memoire_max) et tailles des memoires dans /api/v2/sobriete.
v1.0 (2026-10-20, claude) : les tests existants remplacaient urlopen par un faux; ils ne pouvaient pas voir que le
middleware refusait (403) les lectures de memoire faites sans jeton par wrapper.py et wrapper_api.py. Ici, uvicorn
ecoute sur un port libre et les fonctions des wrappers l'appellent comme en production. Donnees synthetiques.
"""

import copy
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import projects
import wrapper


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ReveilReelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls._app_state = app.__dict__.copy()
        cls._room = copy.deepcopy(app.room_settings)
        cls._mw = list(app.app.user_middleware)
        cls._proj = (projects._state, projects._FILE)
        app.app.middleware_stack = None
        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({"server": {"data_dir": str(root / "data")}, "agents": {"codex": {}}, "routing": {},
                           "images": {}, "socle": {"racine_livrables": str(root)}}, session_token="sess-reel")
        projects.configurer(root / "projects.json")
        cls.pid = projects.creer("Quad synthetique", memoire="MEMO_QUAD : bus 48 V, FS >= 1,25")
        cls.tache, _ = app.jobs.create_tache(cls.pid, "Collier", "conception", "codex", created_by="user",
                                             equipe=[{"agent": "codex", "role": "producteur"}],
                                             critere="paroi >= 1,2 mm")
        cls._jeton = mock.patch.object(app.registry, "resolve_token",
                                       side_effect=lambda t: {"name": "codex"} if t == "tok-codex" else None)
        cls._jeton.start()
        cls.port = _port_libre()
        cls.serveur = uvicorn.Server(uvicorn.Config(app.app, host="127.0.0.1", port=cls.port, log_level="error"))
        cls.fil = threading.Thread(target=cls.serveur.run, daemon=True)
        cls.fil.start()
        for _ in range(100):
            if cls.serveur.started:
                break
            time.sleep(0.05)
        assert cls.serveur.started, "le serveur de test n'a pas demarre"

    @classmethod
    def tearDownClass(cls):
        cls.serveur.should_exit = True
        cls.fil.join(timeout=5)
        cls._jeton.stop()
        for key in list(app.__dict__):
            if key not in cls._app_state:
                delattr(app, key)
        for key, value in cls._app_state.items():
            setattr(app, key, value)
        app.room_settings.clear()
        app.room_settings.update(cls._room)
        app.app.user_middleware = cls._mw
        app.app.middleware_stack = None
        projects._state, projects._FILE = cls._proj
        cls.tmp.cleanup()

    def test_sans_jeton_la_memoire_est_refusee(self):
        """Le bogue d'origine : sans jeton, 403, et le wrapper rend une memoire vide."""
        self.assertEqual(wrapper._fetch_trigger_memory(self.port, {self.pid}, "general"), ("", ""))

    def test_avec_le_jeton_de_l_agent_la_memoire_arrive(self):
        memoire, nom = wrapper._fetch_trigger_memory(self.port, {self.pid}, "general", "tok-codex")
        self.assertIn("MEMO_QUAD", memoire)
        self.assertEqual(nom, "Quad synthetique")

    def test_jeton_inconnu_refuse(self):
        self.assertEqual(wrapper._fetch_trigger_memory(self.port, {self.pid}, "general", "tok-faux"), ("", ""))

    def test_fiche_au_reveil_par_le_vrai_serveur(self):
        fiche = wrapper._fetch_fiche(self.port, self.tache["id"], "tok-codex")
        self.assertEqual((fiche["tache_id"], fiche["ton_role"]), (self.tache["id"], "producteur"))
        self.assertIsNone(wrapper._fetch_fiche(self.port, self.tache["id"], ""))

    def test_reveil_complet_injecte_memoire_puis_rappel(self):
        """Deux reveils de suite dans le meme contexte : la memoire entiere au premier, une ligne au second."""
        with tempfile.TemporaryDirectory() as d:
            queue = Path(d) / "q.jsonl"
            injecte = []
            tours = {"n": 0}

            def poll(sec):
                if sec == 1:
                    tours["n"] += 1
                    if tours["n"] == 1:
                        queue.write_text(json.dumps({"channel": "general", "projet_id": self.pid}) + "\n",
                                         encoding="utf-8")
                    else:
                        raise KeyboardInterrupt

            queue.write_text(json.dumps({"channel": "general", "projet_id": self.pid}) + "\n", encoding="utf-8")
            with mock.patch.object(wrapper, "_fetch_role", return_value=""), \
                    mock.patch.object(wrapper, "_fetch_active_rules", return_value=None), \
                    mock.patch.object(wrapper.time, "sleep", side_effect=poll):
                with self.assertRaises(KeyboardInterrupt):
                    wrapper._queue_watcher(lambda: ("codex", queue), injecte.append, server_port=self.port,
                                           agent_name="codex", get_token_fn=lambda: "tok-codex")
        self.assertEqual(len(injecte), 2)
        self.assertIn("MEMO_QUAD", injecte[0])
        self.assertNotIn("MEMO_QUAD", injecte[1])
        self.assertIn("memoire inchangee", injecte[1])


    def test_rapport_montre_la_taille_des_memoires_sans_leur_texte(self):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/v2/sobriete",
                                     headers={"x-session-token": "sess-reel"})
        with urllib.request.urlopen(req, timeout=3) as r:
            rapport = json.loads(r.read())
        m = rapport["memoires"]
        self.assertEqual(m["borne"], 3000)
        quad = next(x for x in m["projets"] if x["id"] == self.pid)
        self.assertEqual((quad["caracteres"], quad["tronquee"]), (len("MEMO_QUAD : bus 48 V, FS >= 1,25"), False))
        self.assertNotIn("MEMO_QUAD", json.dumps(rapport))


class BorneMemoireTests(unittest.TestCase):
    def test_borne_reglable_et_encadree(self):
        import sobriete
        self.assertEqual(sobriete.memoire_max({}), 3000)
        self.assertEqual(sobriete.memoire_max({"sobriete": {"memoire_max": 8000}}), 8000)
        self.assertEqual(sobriete.memoire_max({"sobriete": {"memoire_max": 10}}), 500)
        self.assertEqual(sobriete.memoire_max({"sobriete": {"memoire_max": 10**9}}), 50000)
        self.assertEqual(sobriete.memoire_max({"sobriete": {"memoire_max": "abc"}}), 3000)

    def test_troncature_dit_ce_qu_elle_coupe(self):
        import sobriete
        t = sobriete.borner_memoire("m" * 4200, 3000)
        self.assertTrue(t.startswith("m" * 3000))
        self.assertIn("tronquee a 3000 caracteres sur 4200", t)
        self.assertEqual(sobriete.borner_memoire("court", 3000), "court")


if __name__ == "__main__":
    unittest.main()
