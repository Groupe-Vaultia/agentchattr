"""Progression en direct sur le tableau de l'atelier (tache-22, msg 4925-4926, 2026-10-19).

Charles : « la tableau de l'atelier n'est pas live que ça... Je ne vois pas vraiment les progressions ». Les cartes
dataient de `updated_at` (t29 : « il y a 14 h » apres 2 fusions et 20 messages) ; /api/v2/taches sert maintenant la
derniere progression et les agents au travail. Les silences de la ronde ne comptent plus Charles (t21 se disait muette
depuis 2 h, aucun agent depuis 83 h). La reponse a une carte de decision porte l'etiquette de la carte (msgs 4872 et
4874 etaient sans tache). Cas communs avec le navigateur : progression_cas.json (aussi lu par test_progression.mjs).
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import progression  # noqa: E402
import projects  # noqa: E402
from executions import ExecutionStore  # noqa: E402
from jobs import JobStore  # noqa: E402
from store import MessageStore  # noqa: E402

CAS = json.loads((Path(__file__).parent / "progression_cas.json").read_text("utf-8"))


class _Requete:
    def __init__(self, corps):
        self._corps = corps

    async def json(self):
        return self._corps


class ReglesCommunesTests(unittest.TestCase):
    """Les memes cas que static/progression.js."""

    def test_est_progression(self):
        for c in CAS["est_progression"]:
            with self.subTest(c["cas"]):
                self.assertIs(progression.est_progression(c["msg"]), c["attendu"])

    def test_tache_du_message(self):
        for c in CAS["tache_du_message"]:
            with self.subTest(c["msg"]):
                self.assertEqual(progression.tache_du_message(c["msg"]), c["attendu"])

    def test_extrait(self):
        for c in CAS["extrait"]:
            with self.subTest(c["cas"]):
                self.assertEqual(progression.extrait(c["texte"]), c["attendu"])

    def test_activites_et_derniers_messages_d_agents(self):
        a = CAS["activites"]
        obtenu = progression.activites(a["messages"], set(a["humains"]))
        self.assertEqual({str(k): v for k, v in obtenu.items()}, a["attendu"])
        self.assertEqual(progression.derniers_messages_agents(a["messages"], set(a["humains"])),
                         a["derniers_messages_agents"])


class AuTravailTests(unittest.TestCase):
    def test_seules_les_executions_actives_comptent(self):
        execs = [{"tache_id": 29, "agent": "claude-2", "etat": "actif"},
                 {"tache_id": 29, "agent": "codex-1", "etat": "actif"},
                 {"tache_id": 29, "agent": "claude-2", "etat": "actif"},
                 {"tache_id": 27, "agent": "claude-3", "etat": "silencieux"},
                 {"tache_id": 28, "agent": "claude-1", "etat": "fini"}]
        self.assertEqual(progression.au_travail(execs), {29: ["claude-2", "codex-1"]})


class _Salle(unittest.TestCase):
    """Un projet, une tache et leurs magasins dans un dossier temporaire ; Charles ecrit sous « charles »."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        avant = projects._FILE
        projects.configurer(root / "projects.json")
        self.addCleanup(lambda: projects.configurer(avant) if avant else None)
        self.pid = projects.creer("Synthetic Alpha")
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.jobs = JobStore(str(root / "jobs.json"))
        self.executions = ExecutionStore(str(root / "executions.json"))
        self.tache, err = self.jobs.create_tache(self.pid, "G8 berceau", "conception", "claude-2", "claude-1",
                                                 equipe=[{"agent": "claude-2", "role": "producteur"}])
        self.assertEqual(err, "")
        self.tid = self.tache["id"]
        self.canal = f"tache-{self.tid}"

        async def _rien(*_):
            return None
        for nom, valeur in (("store", self.store), ("jobs", self.jobs), ("executions", self.executions),
                            ("room_settings", {"username": "charles", "channels": ["general", self.canal]}),
                            ("_broadcast", _rien)):
            patcher = mock.patch.object(app, nom, valeur)
            patcher.start()
            self.addCleanup(patcher.stop)

    def taches(self) -> dict:
        reponse = asyncio.run(app.list_taches(self.pid))
        self.assertEqual(reponse.status_code, 200)
        return json.loads(reponse.body)


class RouteTachesTests(_Salle):
    def test_la_tache_porte_son_dernier_message_et_ses_agents_au_travail(self):
        self.store.add("claude-2", "@claude-1 Livraison : **G8** fusionnée", channel=self.canal, tache_id=self.tid)
        self.store.add("claude-1", "@claude-1 Point d'étape du chef (R14)", channel=self.canal)
        self.executions.demarrer(self.tid, self.pid, "claude-2", "producteur", "lot G8")
        fini = self.executions.demarrer(self.tid, self.pid, "codex-1", "verificateur", "revue")
        self.executions.terminer(fini["id"], "terminee")
        corps = self.taches()
        t = corps["taches"][0]
        self.assertEqual((t["activite"]["par"], t["activite"]["extrait"]), ("claude-2", "Livraison : G8 fusionnée"),
                         "le rappel que le chef s'adresse n'est pas une progression")
        self.assertEqual(t["activite"]["agent"], "claude-2")
        self.assertEqual(t["au_travail"], ["claude-2"], "une execution finie n'est plus au travail")
        self.assertEqual(corps["humains"], ["charles", "user"])

    def test_un_message_de_charles_est_une_activite_pas_un_signe_de_vie(self):
        agent = self.store.add("claude-2", "Fait.", channel=self.canal, tache_id=self.tid)
        self.store.add("charles", "@claude-2 Pousse les PR", channel=self.canal)
        a = self.taches()["taches"][0]["activite"]
        self.assertEqual(a["par"], "charles")
        self.assertEqual((a["agent"], a["agent_ts"]), ("claude-2", agent["timestamp"]))

    def test_le_dual_une_tache_sans_message_ni_execution(self):
        t = self.taches()["taches"][0]
        self.assertIsNone(t["activite"])
        self.assertEqual(t["au_travail"], [])

    def test_les_champs_ajoutes_ne_sont_pas_ecrits_dans_la_tache(self):
        self.store.add("claude-2", "Fait.", channel=self.canal, tache_id=self.tid)
        self.taches()
        self.assertNotIn("activite", self.jobs.get(self.tid))


class SilenceRondeTests(_Salle):
    def test_seuls_les_messages_d_agents_datent_le_silence(self):
        agent = self.store.add("claude-2", "Fait.", channel=self.canal, tache_id=self.tid)
        self.store.add("charles", "@claude-2 tu en es où ?", channel=self.canal)
        self.store.add("system", "Ronde en veille", msg_type="system", channel=self.canal)
        self.store.add("claude-2", "@claude-2 relire demain", channel=self.canal)
        self.assertEqual(app._derniers_messages_canaux(), {self.canal: agent["timestamp"]})

    def test_le_dual_sans_message_d_agent_la_tache_n_a_pas_de_date(self):
        self.store.add("charles", "@claude-2 tu en es où ?", channel=self.canal)
        self.assertEqual(app._derniers_messages_canaux(), {})


class ReponseCarteTests(_Salle):
    """Point E : la reponse de Charles a une carte reste dans la conversation de sa tache."""

    def resoudre(self, carte):
        return asyncio.run(app.resolve_decision(carte["id"], _Requete({"choice": "Oui"})))

    def reponse(self) -> dict:
        return self.store.get_recent(1)[0]

    def test_la_reponse_porte_le_tache_id_et_le_projet_id_de_la_carte(self):
        carte = self.store.add("claude-1", "Je pousse ?", msg_type="decision", channel=self.canal,
                               metadata={"choices": ["Oui", "Non"]}, projet_id=self.pid, tache_id=self.tid)
        self.assertEqual(self.resoudre(carte)["chosen"], "Oui")
        r = self.reponse()
        self.assertEqual((r["sender"], r["text"], r["reply_to"]), ("charles", "@claude-1 Oui", carte["id"]))
        self.assertEqual((r.get("projet_id"), r.get("tache_id")), (self.pid, self.tid))
        self.assertIn(r["id"], [m["id"] for m in self.store.filtrer(None, self.tid, -1, 0)],
                      "la conversation de la fiche (filtre par tache) montre la reponse")

    def test_une_carte_sans_etiquette_prend_celle_de_son_canal(self):
        carte = self.store.add("claude-1", "Je pousse ?", msg_type="decision", channel=self.canal,
                               metadata={"choices": ["Oui", "Non"]})
        self.resoudre(carte)
        self.assertEqual((self.reponse().get("projet_id"), self.reponse().get("tache_id")), (self.pid, self.tid))

    def test_le_dual_une_carte_hors_tache_reste_sans_tache(self):
        carte = self.store.add("claude-1", "Je pousse ?", msg_type="decision", channel="general",
                               metadata={"choices": ["Oui", "Non"]})
        self.resoudre(carte)
        self.assertIsNone(self.reponse().get("tache_id"))

    # Revue codex-1 (msg 4934) et cas fixes par claude-1 (msg 4935) : la carte qui n'a que son projet.
    def carte_dans(self, canal, **etiquette):
        return self.store.add("claude-1", "Je pousse ?", msg_type="decision", channel=canal,
                              metadata={"choices": ["Oui", "Non"]}, **etiquette)

    def etiquette(self) -> tuple:
        r = self.reponse()
        return r.get("projet_id"), r.get("tache_id")

    def autre_tache(self, projet_id):
        t, err = self.jobs.create_tache(projet_id, "Autre", "conception", "claude-2", "claude-1",
                                        equipe=[{"agent": "claude-2", "role": "producteur"}])
        self.assertEqual(err, "")
        return t

    def test_cas_de_codex_1_carte_avec_son_projet_seul_dans_tache_n(self):
        self.assertEqual((self.pid, self.canal), ("synthetic-alpha", "tache-1"))
        self.resoudre(self.carte_dans(self.canal, projet_id=self.pid))
        self.assertEqual(self.etiquette(), (self.pid, self.tid), "tache_id restait None (msg 4934)")

    def test_le_dual_la_tache_du_canal_est_d_un_autre_projet_on_ne_melange_pas(self):
        beta = projects.creer("Synthetic Beta")
        autre = self.autre_tache(beta)
        self.resoudre(self.carte_dans(f"tache-{autre['id']}", projet_id=self.pid))
        self.assertEqual(self.etiquette(), (self.pid, None))

    def test_la_carte_qui_porte_ses_deux_etiquettes_l_emporte_sur_le_canal(self):
        autre = self.autre_tache(self.pid)
        self.resoudre(self.carte_dans(f"tache-{autre['id']}", projet_id=self.pid, tache_id=self.tid))
        self.assertEqual(self.etiquette(), (self.pid, self.tid))

    def test_le_dual_projet_seul_dans_un_canal_tache_sans_tache(self):
        self.resoudre(self.carte_dans("tache-777", projet_id=self.pid))
        self.assertEqual(self.etiquette(), (self.pid, None))

    def test_le_dual_une_tache_disparue_ne_bloque_pas_la_reponse(self):
        carte = self.store.add("claude-1", "Je pousse ?", msg_type="decision", channel="general",
                               metadata={"choices": ["Oui", "Non"]}, projet_id=self.pid, tache_id=9999)
        self.assertEqual(self.resoudre(carte)["chosen"], "Oui")
        r = self.reponse()
        self.assertEqual((r["text"], r.get("tache_id")), ("@claude-1 Oui", None))


if __name__ == "__main__":
    unittest.main()
