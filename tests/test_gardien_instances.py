"""Gardien multi-instance (scripts/gardien_instances.py), sans tmux, sans kill réel.

v1.0 (2026-10-19, claude-2) : l'ancien cli() de vaultia-watchdog.sh tuait par pkill les relais de toutes les instances d'une
famille quand l'instance 1 manquait (claude-1 #tache-22 msg 5600).
"""

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gardien_instances", ROOT / "scripts" / "gardien_instances.py")
G = importlib.util.module_from_spec(SPEC)
sys.modules["gardien_instances"] = G
SPEC.loader.exec_module(G)

MAINTENANT = 1_800_000_000.0
T0 = MAINTENANT - 3600
SECRET = "sk-cle-secrete-de-test"
CMD = {b: f'env PATH="/x" .venv/bin/python wrapper.py {b} --openai-api-key {SECRET}; read' for b in ("qwencode", "grok")}
ATTENDU = [("qwencode", 4), ("grok", 1)]


def salle(sans=(), crees=None):
    """Salle de ce soir : qwencode-3 et -4 ont un TUI mais plus de relais. `sans` retire des sessions."""
    crees = crees or {}
    s = [G.Session("ac-qwencode", T0, 100, CMD["qwencode"]), G.Session("agentchattr-qwencode", T0, 110),
         G.Session("ac-qwencode2", T0, 200, CMD["qwencode"]), G.Session("agentchattr-qwencode-2", T0, 210),
         G.Session("ac-qwencode3", T0, 300, CMD["qwencode"]), G.Session("agentchattr-qwencode-3", T0, 310),
         G.Session("ac-qwencode4", T0, 400, CMD["qwencode"]), G.Session("agentchattr-qwencode-4", T0, 410),
         G.Session("ac-grok", T0, 500, CMD["grok"]), G.Session("agentchattr-grok", T0, 510)]
    for x in s:
        x.cree = crees.get(x.nom, x.cree)
    return [x for x in s if x.nom not in sans]


PROCESSUS = [(101, 100, True), (201, 200, True), (501, 500, True), (300, 1, False), (400, 1, False)]


class _Faux:
    def __init__(self):
        self.run, self.tues = [], []

    def lancer(self, cmd, **kw):
        self.run.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    def tuer(self, pid, sig):
        self.tues.append(pid)


def par_instance(decisions):
    return {d.instance: d for d in decisions}


class TestDecision(unittest.TestCase):
    def test_ce_soir_relais_mort_tui_vivant_signale_seulement(self):
        d = par_instance(G.decider(salle(), PROCESSUS, ATTENDU, {}, MAINTENANT))
        self.assertEqual({k: v.etat for k, v in d.items()}, {"qwencode-1": "ok", "qwencode-2": "ok",
                         "qwencode-3": "relais mort (TUI vivant)", "qwencode-4": "relais mort (TUI vivant)", "grok": "ok"})
        self.assertTrue(all(not v.actions for v in d.values()))
        f = _Faux()
        G.executer(list(d.values()), run=f.lancer, tuer=f.tuer, dormir=lambda s: None)
        self.assertEqual((f.run, f.tues), ([], []))                           # ni kill, ni tmux : le TUI vivant est gardé

    def test_tui_mort_une_seule_instance_touchee(self):
        d = par_instance(G.decider(salle(sans={"agentchattr-qwencode-2"}), PROCESSUS, ATTENDU, {}, MAINTENANT))
        self.assertEqual(d["qwencode-2"].etat, "relance")
        self.assertEqual(d["qwencode-2"].actions, [("tuer", 201), ("fermer", "ac-qwencode2"), ("lancer", "ac-qwencode2", CMD["qwencode"])])
        f = _Faux()
        G.executer(list(d.values()), run=f.lancer, tuer=f.tuer, dormir=lambda s: None)
        self.assertEqual(f.tues, [201])                                       # pas 101 : l'ancien pkill tuait toute la famille
        self.assertEqual(f.run, [["tmux", "kill-session", "-t", "=ac-qwencode2"],
                                 ["tmux", "new-session", "-d", "-s", "ac-qwencode2", "-c", str(G.RACINE), CMD["qwencode"]]])

    def test_lanceur_absent_commande_du_frere(self):
        d = par_instance(G.decider(salle(sans={"ac-qwencode2", "agentchattr-qwencode-2"}), PROCESSUS, ATTENDU, {}, MAINTENANT))
        self.assertEqual(d["qwencode-2"].actions, [("lancer", "ac-qwencode2", CMD["qwencode"])])

    def test_commande_de_secours(self):
        s = salle(sans={"ac-grok", "agentchattr-grok"})
        self.assertEqual(par_instance(G.decider(s, PROCESSUS, ATTENDU, {}, MAINTENANT))["grok"].etat, "sans commande")
        d = par_instance(G.decider(s, PROCESSUS, ATTENDU, {"grok": ""}, MAINTENANT))["grok"]
        self.assertEqual(d.actions, [("lancer", "ac-grok", G.commande_defaut("grok", ""))])

    def test_instance_1_nom_numerote(self):
        s = salle(sans={"agentchattr-qwencode"}) + [G.Session("agentchattr-qwencode-1", T0, 120)]
        self.assertEqual(par_instance(G.decider(s, PROCESSUS, ATTENDU, {}, MAINTENANT))["qwencode-1"].etat, "ok")

    def test_appariement_par_heure_apres_relance(self):
        """Relancé, le relais de ac-qwencode2 a reçu qwencode-5 du serveur : pas de relance en boucle."""
        base = salle(sans={"agentchattr-qwencode-2"}, crees={"ac-qwencode2": MAINTENANT - 300})
        d = par_instance(G.decider(base + [G.Session("agentchattr-qwencode-5", MAINTENANT - 295, 250)], PROCESSUS, ATTENDU, {}, MAINTENANT))
        self.assertEqual((d["qwencode-2"].etat, d["qwencode-2"].tui), ("ok", "agentchattr-qwencode-5"))
        d = par_instance(G.decider(base + [G.Session("agentchattr-qwencode-5", MAINTENANT - 200, 250)], PROCESSUS, ATTENDU, {}, MAINTENANT))
        self.assertEqual(d["qwencode-2"].etat, "relance")                     # 100 s après le lanceur : pas le sien

    def test_lanceur_jeune_pas_juge(self):
        s = salle(sans={"agentchattr-qwencode-2"}, crees={"ac-qwencode2": MAINTENANT - 30})
        d = par_instance(G.decider(s, PROCESSUS, ATTENDU, {}, MAINTENANT))["qwencode-2"]
        self.assertEqual((d.etat, d.actions), ("démarrage", []))


class TestPasse(unittest.TestCase):
    def _main(self, lectures, essai=False):
        f, pauses, sortie = _Faux(), [], io.StringIO()
        it = iter(lectures)
        args = (["--essai"] if essai else []) + ["qwencode:4", "grok:1"]
        with contextlib.redirect_stdout(sortie), unittest.mock.patch.object(G.time, "time", return_value=MAINTENANT):
            code = G.main(args, lire=lambda: next(it), processus=lambda: PROCESSUS, dormir=pauses.append, run=f.lancer, tuer=f.tuer)
        return code, f, pauses, sortie.getvalue()

    def test_seconde_lecture_annule(self):
        """Le TUI de qwencode-2 manquait à la première lecture et revient à la seconde (redémarrage du relais en 3 s)."""
        code, f, pauses, out = self._main([salle(sans={"agentchattr-qwencode-2"}), salle()])
        self.assertEqual((code, f.run, f.tues), (0, [], []))
        self.assertIn(G.CONFIRMATION, pauses)
        self.assertIn("qwencode-2 (ac-qwencode2 / pas de TUI) : relance annulée (seconde lecture)", out)

    def test_seconde_lecture_confirme(self):
        code, f, pauses, out = self._main([salle(sans={"agentchattr-qwencode-2"})] * 2)
        self.assertEqual(f.tues, [201])
        self.assertIn("relance -> tuer PID 201 ; fermer ac-qwencode2 ; relancer ac-qwencode2", out)

    def test_essai_ne_fait_rien_et_journal_sans_secret(self):
        code, f, pauses, out = self._main([salle(sans={"agentchattr-qwencode-2"})], essai=True)
        self.assertEqual((f.run, f.tues, pauses), ([], [], []))
        for interdit in (SECRET, "--openai-api-key", "wrapper.py", "env PATH"):
            self.assertNotIn(interdit, out)
        self.assertIn("relais mort (TUI vivant) ; relance du relais = décision humaine", out)


class TestGardienBash(unittest.TestCase):
    def test_plus_de_pkill_et_appel_du_gardien(self):
        texte = (ROOT / "vaultia-watchdog.sh").read_text("utf-8")
        code = [l for l in texte.splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse([l for l in code if "pkill" in l])
        self.assertIn('GARDE="claude:3 codex:2 qwencode:4 grok:1"', texte)
        self.assertIn('"$PY" scripts/gardien_instances.py $GARDE', texte)
        self.assertEqual(subprocess.run(["bash", "-n", str(ROOT / "vaultia-watchdog.sh")]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
