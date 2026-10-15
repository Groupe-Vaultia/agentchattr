"""S5 v2 : a la completion d'une tache, sa `preuve` est doublee d'une fiche de livrable structuree.

PR assoc-livrables (14 oct. 2026, claude). Couvre :
  (a) tache -> `fait` avec une preuve citant un .md present => livrable {projet, tache, chemin, empreinte} dans revisions ;
  (b) fichier cite absent => fiche `introuvable`, aucun plantage ;
  (c) idempotence (2e passage `fait` ne duplique pas) ;
  (d) rattachement a la piece quand une piece porte ce tache_id et un dessin ;
  (e) securite de chemin (refus « .. » et absolu hors racine) ;
  plus l'extraction depuis des preuves reelles du projet quad, et l'exposition par GET .../revisions.
"""

import copy
import hashlib
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
import projects
import revisions as _revisions_mod
from revisions import RevisionStore
from pieces import PieceStore


class ParsingPreuveTests(unittest.TestCase):
    """L'extraction depuis le texte libre, sur des preuves reelles du projet quad."""

    def test_extrait_chemin_commit_version(self):
        p = "wt-grok-cao docs/quad/normes.md v1.2, commit d97bec3 (grok/tache-13) ; GO codex msg 2536 (#tache-13)."
        self.assertEqual(_revisions_mod.extraire_chemins(p), ["docs/quad/normes.md"])
        self.assertEqual(_revisions_mod.extraire_commit(p), "d97bec3")
        self.assertEqual(_revisions_mod.extraire_version(p), "v1.2")

    def test_chemin_absolu_avec_tilde(self):
        p = "~/atelier/projets/quad/concepts.md v1.2 : concept B retenu (430/500), matrice.py 35/32 ; GO codex msg 2595."
        self.assertEqual(_revisions_mod.extraire_chemins(p), ["~/atelier/projets/quad/concepts.md"])
        self.assertEqual(_revisions_mod.extraire_version(p), "v1.2")
        self.assertEqual(_revisions_mod.extraire_commit(p), "")  # pas de hash 7+ ici

    def test_commit_nu_entre_parentheses(self):
        p = "GO codex msg 2733 sur CALC-004 v1.6 (426b2e9, cad-gemini), pytest 52 passed"
        self.assertEqual(_revisions_mod.extraire_chemins(p), [])           # aucun fichier cite
        self.assertEqual(_revisions_mod.extraire_commit(p), "426b2e9")

    def test_preuve_api_sans_fichier(self):
        p = "Problème ... — PATCH /api/v2/projects/quad/fiche 200."
        self.assertEqual(_revisions_mod.extraire_livrables(p), [])

    def test_numero_piece(self):
        p = "API : 89 fiches, VLT-10019 et VLT-10051 rejetee (msg 2636, 2639)"
        self.assertEqual(_revisions_mod.extraire_numeros_piece(p), {"VLT-10019", "VLT-10051"})


class StoreLivrableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.racine = root / "atelier"
        (self.racine / "docs").mkdir(parents=True)
        (self.racine / "cao").mkdir()
        self.rev = RevisionStore(str(root / "revisions.json"), str(self.racine))
        self.pieces = PieceStore(str(root / "pieces.db"))

    def _ecrire(self, rel, octets=b"contenu"):
        f = self.racine / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(octets)
        return hashlib.sha256(octets).hexdigest()

    def test_a_present_md_devient_fiche_structuree(self):
        emp = self._ecrire("docs/rapport.md", b"# rapport")
        tache = {"id": 42, "projet_id": "quad", "titre": "Rapport",
                 "preuve": "docs/rapport.md v1.0, commit abc1234"}
        cr = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertEqual(cr["erreurs"], [])
        livrables = self.rev.livrables("quad")
        self.assertEqual(len(livrables), 1)
        l = livrables[0]
        self.assertEqual(l["chemin"], "docs/rapport.md")
        self.assertEqual(l["empreinte"], emp)
        self.assertEqual(l["projet_id"], "quad")
        self.assertEqual(l["tache_id"], "42")
        self.assertEqual(l["statut"], "present")
        self.assertEqual(l["commit"], "abc1234")
        self.assertEqual(l["version_doc"], "v1.0")

    def test_b_fichier_absent_donne_introuvable_sans_crash(self):
        tache = {"id": 7, "projet_id": "quad", "titre": "Normes",
                 "preuve": "docs/quad/normes.md v1.2, commit d97bec3"}
        cr = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertEqual(cr["erreurs"], [])
        l = self.rev.livrables("quad")[0]
        self.assertEqual(l["statut"], "introuvable")
        self.assertEqual(l["empreinte"], "")
        self.assertEqual(l["commit"], "d97bec3")
        self.assertEqual(l["chemin"], "docs/quad/normes.md")

    def test_c_idempotence(self):
        self._ecrire("docs/rapport.md")
        tache = {"id": 42, "projet_id": "quad", "preuve": "docs/rapport.md, commit abc1234"}
        _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        livrables = self.rev.livrables("quad")
        self.assertEqual(len(livrables), 1)
        self.assertEqual(livrables[0]["version"], 1)   # pas de version 2 pour un contenu identique
        # Un passage introuvable, deux fois, ne duplique pas non plus.
        t2 = {"id": 8, "projet_id": "quad", "preuve": "docs/absent.md"}
        _revisions_mod.associer_livrables_tache(t2, self.rev, self.pieces)
        _revisions_mod.associer_livrables_tache(t2, self.rev, self.pieces)
        self.assertEqual(len([x for x in self.rev.livrables("quad") if x["chemin"] == "docs/absent.md"]), 1)

    def test_d_rattachement_piece_par_tache_id(self):
        emp = self._ecrire("cao/bras.step", b"ISO-10303-21;")
        piece = self.pieces.creer({"nom": "Bras oscillant", "projet_id": "quad", "tache_id": 20,
                                   "origine": "concevoir", "type": "piece"}, "claude")
        self.assertEqual(piece["fichier"], "")
        tache = {"id": 20, "projet_id": "quad", "titre": "Bras oscillant arriere",
                 "preuve": "cao/bras.step v1.2, commit 8c22c65, 15 tests OK"}
        cr = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertIsNotNone(cr["piece"])
        self.assertEqual(cr["piece"]["action"], "rattachee")
        self.assertEqual(cr["piece"]["origine"], "tache_id")
        maj = self.pieces.get(piece["id"])
        self.assertEqual(maj["fichier"], "cao/bras.step")
        self.assertEqual(maj["empreinte"], emp)
        revs = self.pieces.revisions(piece["id"])
        self.assertEqual(revs[0]["fichier"], "cao/bras.step")
        # 2e passage : la piece est deja rattachee, on ne la retouche pas.
        cr2 = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertEqual(cr2["piece"]["action"], "deja_rattachee")

    def test_d_document_non_cao_ne_touche_pas_de_piece(self):
        self._ecrire("docs/rapport.md")
        self.pieces.creer({"nom": "Bras", "projet_id": "quad", "tache_id": 20,
                           "origine": "concevoir", "type": "piece"}, "claude")
        tache = {"id": 20, "projet_id": "quad", "preuve": "docs/rapport.md"}
        cr = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertIsNone(cr["piece"])   # un .md n'est pas un dessin

    def test_e_securite_chemin_refuse_hors_racine(self):
        with self.assertRaises(ValueError):
            self.rev.enregistrer_livrable("quad", 1, "../evil.md")
        with self.assertRaises(ValueError):
            self.rev.enregistrer_livrable("quad", 1, "/etc/evil.md")
        # Via la preuve : le refus est signale dans le compte-rendu, pas une exception.
        tache = {"id": 9, "projet_id": "quad", "preuve": "voir ../evil.md pour la suite"}
        cr = _revisions_mod.associer_livrables_tache(tache, self.rev, self.pieces)
        self.assertEqual(cr["livrables"], [])
        self.assertTrue(cr["erreurs"])
        self.assertEqual(self.rev.livrables("quad"), [])


class HookCompletionTests(unittest.TestCase):
    """De bout en bout : PATCH .../taches/{id} -> `fait` branche l'enregistrement et GET .../revisions l'expose."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.deliverables = self.root / "deliverables"
        self.deliverables.mkdir()

        self._app_state = app.__dict__.copy()
        self._room_settings = copy.deepcopy(app.room_settings)
        self._middleware = list(app.app.user_middleware)
        self._projects_state = (projects._state, projects._FILE)
        self.addCleanup(self._restore_globals)

        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({
                "server": {"data_dir": str(self.data)},
                "agents": {}, "routing": {}, "images": {},
                "socle": {"racine_livrables": str(self.deliverables)},
            }, session_token="test-livrables-session")

        projects.configurer(self.root / "projects.json")
        self.pid = projects.creer("Quad synthetique")
        self.client = TestClient(app.app, headers={"x-session-token": "test-livrables-session"})
        self.addCleanup(self.client.close)

    def _restore_globals(self):
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

    def _creer_tache(self):
        r = self.client.post("/api/v2/taches", json={
            "projet_id": self.pid, "titre": "Normes VHR", "etape": "etat_art",
            "responsable": "grok", "equipe": [{"agent": "grok", "role": "producteur"}]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def test_patch_fait_cree_une_fiche_exposee_par_revisions(self):
        (self.deliverables / "docs" / "quad").mkdir(parents=True)
        (self.deliverables / "docs" / "quad" / "normes.md").write_text("# normes", encoding="utf-8")
        tid = self._creer_tache()
        patch = self.client.patch(f"/api/v2/taches/{tid}", json={
            "etat": "fait", "preuve": "docs/quad/normes.md v1.2, commit d97bec3 (grok/tache-13)"})
        self.assertEqual(patch.status_code, 200, patch.text)

        revs = self.client.get(f"/api/v2/projects/{self.pid}/revisions")
        self.assertEqual(revs.status_code, 200, revs.text)
        livrables = revs.json()["livrables"]
        self.assertEqual(len(livrables), 1)
        l = livrables[0]
        self.assertEqual(l["chemin"], "docs/quad/normes.md")
        self.assertEqual(l["statut"], "present")
        self.assertEqual(l["commit"], "d97bec3")
        self.assertEqual(l["version_doc"], "v1.2")
        self.assertEqual(str(l["tache_id"]), str(tid))
        self.assertEqual(l["empreinte"], hashlib.sha256(b"# normes").hexdigest())

    def test_patch_fait_fichier_absent_nexpose_pas_de_crash(self):
        tid = self._creer_tache()
        patch = self.client.patch(f"/api/v2/taches/{tid}", json={
            "etat": "fait", "preuve": "cad-gemini/docs/etat-art.md, commit 7750b15"})
        self.assertEqual(patch.status_code, 200, patch.text)   # la tache passe quand meme
        livrables = self.client.get(f"/api/v2/projects/{self.pid}/revisions").json()["livrables"]
        self.assertEqual(livrables[0]["statut"], "introuvable")


if __name__ == "__main__":
    unittest.main()
