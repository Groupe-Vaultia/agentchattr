"""Salle sobre, lot 1 : la tache est la memoire de travail, pas le fil.

v1.0 (2026-10-20, claude) : outils MCP tache_lire, tache_maj, livrable_deposer, decision_noter; fiche bornee;
journal de decisions en ajout seul. Donnees synthetiques seulement.
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

import jobs as jobs_mod
import mcp_bridge
from jobs import JobStore
from revisions import RevisionStore


class SalleSobreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.jobs = JobStore(str(self.root / "jobs.json"))
        self.racine = self.root / "atelier"
        self.racine.mkdir()
        self.revs = RevisionStore(str(self.root / "revisions.json"), str(self.racine))
        self.tache, err = self.jobs.create_tache(
            "alpha", "Collier tubulaire", "conception", "qwen",
            created_by="user", equipe=[{"agent": "qwen", "role": "producteur"},
                                       {"agent": "codex", "role": "verificateur"}],
            critere="paroi >= 1,2 mm")
        self.assertEqual(err, "")
        self.tid = self.tache["id"]
        self.appels = []

        def maj(tid, champs):
            self.appels.append((tid, dict(champs)))
            return self.jobs.update_tache(tid, champs)

        for p in (
            mock.patch.object(mcp_bridge, "jobs", self.jobs),
            mock.patch.object(mcp_bridge, "revisions", self.revs),
            mock.patch.object(mcp_bridge, "maj_tache", maj),
            mock.patch.object(mcp_bridge, "_resolve_tool_identity",
                              side_effect=lambda sender, *_a, **_k: (sender, None)),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _fiche(self, sender="qwen"):
        return json.loads(mcp_bridge.tache_lire(sender=sender, tache_id=self.tid))

    # --- tache_lire -------------------------------------------------------------------------------------------

    def test_fiche_donne_l_etat_et_le_role(self):
        f = self._fiche("codex-2")
        self.assertEqual(f["titre"], "Collier tubulaire")
        self.assertEqual(f["etat"], "a_faire")
        self.assertEqual(f["critere"], "paroi >= 1,2 mm")
        self.assertEqual(f["ton_role"], "verificateur")  # nom d'instance -> nom de base
        self.assertEqual(f["canal"], f"tache-{self.tid}")

    def test_fiche_hors_equipe(self):
        self.assertEqual(self._fiche("grok")["ton_role"], "hors equipe")

    def test_tache_inconnue(self):
        self.assertIn("inconnue", mcp_bridge.tache_lire(sender="qwen", tache_id=999))

    def test_job_sans_projet_refuse(self):
        job = self.jobs.create("Ancien job", "job", "general", "user")
        self.assertIn("inconnue", mcp_bridge.tache_lire(sender="qwen", tache_id=job["id"]))

    def test_taille_de_la_fiche_ne_depend_pas_de_l_historique(self):
        """Le coeur du lot : 200 messages et 40 decisions plus tard, la fiche reste bornee."""
        for i in range(200):
            self.jobs.add_message(self.tid, "codex", f"message {i} " + "x" * 400)
        for i in range(40):
            self.jobs.noter_decision(self.tid, f"decision {i} " + "y" * 300, "claude-1")
        self.jobs.update_tache(self.tid, {"preuve": "z" * 5000})
        brut = mcp_bridge.tache_lire(sender="qwen", tache_id=self.tid)
        f = json.loads(brut)
        self.assertEqual(len(f["decisions"]), jobs_mod.DECISIONS_FICHE)
        self.assertEqual(f["decisions"][-1]["texte"].split()[1], "39")  # les plus recentes
        self.assertEqual(f["decisions_masquees"], 40 - jobs_mod.DECISIONS_FICHE)
        self.assertLessEqual(len(f["preuve"]), jobs_mod.MAX_PREUVE_FICHE + 4)
        self.assertNotIn("message", brut)  # aucun message du fil dans la fiche
        self.assertLess(len(brut), 6000)

    # --- tache_maj --------------------------------------------------------------------------------------------

    def test_maj_passe_par_le_chemin_de_l_api(self):
        r = json.loads(mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid, etat="en_cours",
                                            prochaine_action="Generer le script build123d"))
        self.assertTrue(r["ok"])
        self.assertEqual(r["modifies"], ["etat", "prochaine_action"])
        self.assertEqual(self.appels, [(self.tid, {"etat": "en_cours",
                                                   "prochaine_action": "Generer le script build123d"})])
        self.assertEqual(self._fiche()["prochaine_action"], "Generer le script build123d")

    def test_maj_vide_refusee(self):
        self.assertIn("aucun champ", mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid))
        self.assertEqual(self.appels, [])

    def test_fait_sans_preuve_refuse(self):
        r = mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid, etat="fait")
        self.assertIn("preuve", r)
        self.assertEqual(self.jobs.get(self.tid)["etat"], "a_faire")

    def test_tiret_vide_un_champ(self):
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid, derniere_erreur="pytest: 2 echecs")
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid, derniere_erreur="-")
        self.assertEqual(self._fiche()["derniere_erreur"], "")

    def test_champs_courts_tronques(self):
        mcp_bridge.tache_maj(sender="qwen", tache_id=self.tid, prochaine_action="a" * 2000)
        self.assertEqual(len(self.jobs.get(self.tid)["prochaine_action"]), jobs_mod.MAX_COURT)

    # --- livrable_deposer ---------------------------------------------------------------------------------------

    def test_livrable_par_chemin_avec_empreinte(self):
        (self.racine / "piece.py").write_text("print('collier')\n", encoding="utf-8")
        r = json.loads(mcp_bridge.livrable_deposer(sender="qwen", tache_id=self.tid, chemin="piece.py"))
        self.assertEqual((r["chemin"], r["version"], r["statut"]), ("piece.py", 1, "present"))
        self.assertEqual(len(r["empreinte"]), 12)
        (self.racine / "piece.py").write_text("print('collier v2')\n", encoding="utf-8")
        r2 = json.loads(mcp_bridge.livrable_deposer(sender="qwen", tache_id=self.tid, chemin="piece.py"))
        self.assertEqual(r2["version"], 2)
        liv = self._fiche()["livrables"]
        self.assertEqual([(l["chemin"], l["version"]) for l in liv], [("piece.py", 2)])

    def test_livrable_hors_racine_refuse(self):
        r = mcp_bridge.livrable_deposer(sender="qwen", tache_id=self.tid, chemin="/etc/passwd")
        self.assertTrue(r.startswith("Error"))

    def test_livrables_d_une_autre_tache_absents_de_la_fiche(self):
        autre, _ = self.jobs.create_tache("alpha", "Autre", "conception", "qwen", created_by="user",
                                          equipe=[{"agent": "qwen", "role": "producteur"}])
        (self.racine / "autre.py").write_text("x\n", encoding="utf-8")
        mcp_bridge.livrable_deposer(sender="qwen", tache_id=autre["id"], chemin="autre.py")
        self.assertEqual(self._fiche()["livrables"], [])

    # --- decision_noter -----------------------------------------------------------------------------------------

    def test_decision_en_ajout_seul(self):
        mcp_bridge.decision_noter(sender="claude-1", tache_id=self.tid, texte="PETG, pas PLA : chaleur")
        mcp_bridge.decision_noter(sender="claude-1", tache_id=self.tid, texte="Jeu diametral 0,3 mm")
        f = self._fiche()
        self.assertEqual([d["texte"] for d in f["decisions"]],
                         ["PETG, pas PLA : chaleur", "Jeu diametral 0,3 mm"])
        self.assertEqual(f["decisions"][0]["par"], "claude-1")

    def test_decisions_non_modifiables_par_update(self):
        _, err = self.jobs.update_tache(self.tid, {"decisions": []})
        self.assertIn("champs inconnus", err)

    def test_decision_trop_longue_refusee(self):
        r = mcp_bridge.decision_noter(sender="claude-1", tache_id=self.tid, texte="w" * 900)
        self.assertIn("trop longue", r)

    def test_journal_borne(self):
        for i in range(jobs_mod.MAX_DECISIONS + 10):
            self.jobs.noter_decision(self.tid, f"d{i}", "claude-1")
        self.assertEqual(len(self.jobs.get(self.tid)["decisions"]), jobs_mod.MAX_DECISIONS)

    # --- enregistrement -----------------------------------------------------------------------------------------

    def test_outils_exposes_au_serveur_mcp(self):
        noms = {f.__name__ for f in mcp_bridge._ALL_TOOLS}
        self.assertTrue({"tache_lire", "tache_maj", "livrable_deposer", "decision_noter"} <= noms)


class RoutePatchTests(unittest.TestCase):
    """La route PATCH et l'outil MCP partagent appliquer_maj_tache : les effets restent identiques."""

    def test_patch_utilise_appliquer_maj_tache(self):
        import inspect
        import app
        self.assertIn("appliquer_maj_tache(tache_id, body)", inspect.getsource(app.update_tache))
        src = inspect.getsource(app.appliquer_maj_tache)
        self.assertIn("_enregistrer_livrables_tache", src)
        self.assertIn("_note_round_progress", src)


if __name__ == "__main__":
    unittest.main()
