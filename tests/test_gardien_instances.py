"""Gardien multi-instance (scripts/gardien_instances.py), sans tmux, sans kill réel.

v1.0.2 (2026-10-19, claude-2) : `pane_start_command` déshabillé, vérifié sur un vrai tmux jetable (NO-GO claude-3 msg 5605).
v1.0.1 (2026-10-19, claude-2) : relance manuelle `--relancer base:n` (claude-1 msg 5602).
v1.0 (2026-10-19, claude-2) : l'ancien cli() de vaultia-watchdog.sh tuait par pkill les relais de toutes les instances d'une
famille quand l'instance 1 manquait (claude-1 #tache-22 msg 5600).
"""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
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


class TestRelanceManuelle(unittest.TestCase):
    WT = [("/a/cad-bolt", "cad-bolt/travail"), ("/a/wt-qwencode3-freins", "qwen/t21-freins"), ("/a/wt-qwencode-t21b", "qwen/t21-jante"),
          ("/a/wt-x", "qwencode3/lot"), ("/a/wt-qwencode2-transmission", "qwencode2/t21-transmission")]

    def _plan(self, base, n, sessions=None, sales=None, force=False, worktrees=None, depot=lambda c: c == "/a/cad-bolt"):
        s = sessions or salle()
        for x in s:
            if x.nom == "agentchattr-qwencode-3":
                x.chemin = "/a/cad-bolt"
        return G.plan_relance(base, n, s, PROCESSUS, {}, self.WT if worktrees is None else worktrees, force,
                              depot=depot, sales=sales or (lambda c: 0))

    def test_worktrees_connus(self):
        tui = G.Session("agentchattr-qwencode-3", T0, 310, "", "/a/cad-bolt")
        self.assertEqual(G.worktrees_connus("qwencode", 3, 4, tui, self.WT, depot=lambda c: True),
                         ["/a/cad-bolt", "/a/wt-qwencode3-freins", "/a/wt-x"])     # pas wt-qwencode-t21b (sans numéro)

    def test_relance_qwencode3_ce_soir(self):
        code, d, motif = self._plan("qwencode", 3)
        self.assertEqual((code, motif), (0, ""))
        self.assertEqual(d.actions, [("fermer", "agentchattr-qwencode-3"), ("fermer", "ac-qwencode3"),
                                     ("lancer", "ac-qwencode3", CMD["qwencode"])])  # relais déjà mort : rien à tuer

    def test_relais_tue_avant_le_tui(self):
        code, d, _ = self._plan("qwencode", 2, worktrees=[("/a/wt-qwencode2-transmission", "")])
        self.assertEqual([a[:2] for a in d.actions], [("tuer", 201), ("fermer", "agentchattr-qwencode-2"), ("fermer", "ac-qwencode2"),
                                                      ("lancer", "ac-qwencode2")])
        f = _Faux()
        G.executer([d], run=f.lancer, tuer=f.tuer, dormir=lambda s: None)
        self.assertEqual(f.tues, [201])
        self.assertEqual([c[:4] for c in f.run], [["tmux", "kill-session", "-t", "=agentchattr-qwencode-2"],
                                                   ["tmux", "kill-session", "-t", "=ac-qwencode2"], ["tmux", "new-session", "-d", "-s"]])

    def test_refus_si_non_commite_sauf_force(self):
        sales = lambda c: 1 if c == "/a/wt-qwencode3-freins" else 0
        code, d, motif = self._plan("qwencode", 3, sales=sales)
        self.assertEqual((code, d.actions), (3, []))
        self.assertIn("/a/wt-qwencode3-freins (1)", motif)
        self.assertEqual(self._plan("qwencode", 3, sales=sales, force=True)[0], 0)

    def test_refus_si_aucun_worktree_connu_sauf_force(self):
        code, _, motif = self._plan("qwencode", 4, worktrees=[], depot=lambda c: False)
        self.assertEqual(code, 3)
        self.assertIn("aucun worktree connu", motif)
        self.assertEqual(self._plan("qwencode", 4, worktrees=[], depot=lambda c: False, force=True)[0], 0)

    def test_instance_inconnue(self):
        self.assertEqual(self._plan("qwencode", 7)[0], 2)

    def test_non_commites_ignore_les_pyc(self):
        with tempfile.TemporaryDirectory() as d:
            git = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, check=True)
            git("init", "-q")
            Path(d, "__pycache__").mkdir()
            Path(d, "__pycache__", "x.cpython-314.pyc").write_bytes(b"a")
            Path(d, "fiche.md").write_text("a", "utf-8")
            git("add", ".")
            git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
            Path(d, "__pycache__", "x.cpython-314.pyc").write_bytes(b"b")
            self.assertEqual(G.non_commites(d), 0)
            Path(d, "fiche.md").write_text("b", "utf-8")
            Path(d, "nouveau.md").write_text("c", "utf-8")
            self.assertEqual(G.non_commites(d), 2)

    def test_main_relancer(self):
        f, sortie = _Faux(), io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = G.main(["--relancer", "qwencode:3", "--essai"], lire=salle, processus=lambda: PROCESSUS, run=f.lancer, tuer=f.tuer,
                          worktrees=[("/a/wt-qwencode3-freins", "")], depot=lambda c: False, sales=lambda c: 0)
        self.assertEqual((code, f.run, f.tues), (0, [], []))
        self.assertIn("relance manuelle -> fermer agentchattr-qwencode-3 ; fermer ac-qwencode3 ; relancer ac-qwencode3", sortie.getvalue())
        self.assertNotIn(SECRET, sortie.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as s2:
            code = G.main(["--relancer", "qwencode:3"], lire=salle, processus=lambda: PROCESSUS, run=f.lancer, tuer=f.tuer,
                          worktrees=[("/a/wt-qwencode3-freins", "")], depot=lambda c: False, sales=lambda c: 2)
        self.assertEqual((code, f.run), (3, []))
        self.assertIn("refusée : modifications non commitées : /a/wt-qwencode3-freins (2)", s2.getvalue())


class TestCommandeTmux(unittest.TestCase):
    """Vrai tmux sur un socket jetable (-S, sans TMUX hérité) : rien du serveur réel n'est touché."""
    ORIGINE = 'env PATH="$PATH" FOO="a b" X=\\$HOME sleep 120; read # wrapper.py essai'

    def setUp(self):
        if not shutil.which("tmux"):
            self.skipTest("tmux absent")
        self.dossier = tempfile.mkdtemp(prefix="tmx.", dir="/tmp")
        self.tmux = ("tmux", "-S", os.path.join(self.dossier, "s"))
        self.env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
        self._t("new-session", "-d", "-s", "garde", "sleep 600")             # garde le serveur jetable en vie

    def tearDown(self):
        self._t("kill-server")
        shutil.rmtree(self.dossier, ignore_errors=True)

    def _t(self, *args):
        return subprocess.run([*self.tmux, *args], capture_output=True, text=True, env=self.env)

    def _run(self, cmd, **kw):                                               # executer() parle à ce tmux-ci
        return subprocess.run([*self.tmux, *cmd[1:]], env=self.env, **kw)

    def _vivante(self, nom):
        r = self._t("display-message", "-p", "-t", f"={nom}:", "#{pane_dead}")
        return r.returncode == 0 and r.stdout.strip() == "0"

    def test_brut_mort_ne_deshabille_vivant(self):
        self._t("new-session", "-d", "-s", "ac-x", self.ORIGINE)
        brut = self._t("display-message", "-p", "-t", "=ac-x:", "#{pane_start_command}").stdout.rstrip("\n")
        self.assertTrue(brut.startswith('"') and brut.endswith('"'))           # ce que rend tmux (claude-3 msg 5605)
        self.assertEqual(G.deshabiller(brut), self.ORIGINE)
        lue = next(s for s in G.lire_sessions(self.tmux) if s.nom == "ac-x")
        self.assertEqual(lue.commande, self.ORIGINE)
        self.assertTrue(G.commande_valide(lue.commande))
        # l'ancienne relance (chaîne brute) : session mort-née
        self._t("kill-session", "-t", "=ac-x")
        self._t("new-session", "-d", "-s", "ac-brut", "-c", "/tmp", brut)
        time.sleep(0.3)
        self.assertFalse(self._vivante("ac-brut"))
        # la relance du gardien : vivante
        d = G.Decision("x-1", "ac-x", None, None, "relance", [("lancer", "ac-x", lue.commande)])
        G.executer([d], run=self._run, tuer=lambda *a: None, dormir=lambda s: None)
        time.sleep(0.3)
        self.assertTrue(self._vivante("ac-x"))

    def test_commande_illisible_rien_n_est_tue(self):
        s = salle(sans={"agentchattr-qwencode-2"})
        for x in s:
            if x.nom == "ac-qwencode2":
                x.commande = G.deshabiller('"a" "b"')                         # deux mots : illisible
        f = _Faux()
        d = par_instance(G.decider([x for x in s if x.nom != "ac-qwencode"], PROCESSUS, ATTENDU, {}, MAINTENANT,
                                   valide=G.commande_valide))["qwencode-2"]
        self.assertEqual(d.actions[-1][2], CMD["qwencode"])                  # repli sur un frère lisible
        s2 = [x for x in s if not x.nom.startswith("ac-qwencode") or x.nom == "ac-qwencode2"]
        d = par_instance(G.decider(s2, PROCESSUS, ATTENDU, {}, MAINTENANT))["qwencode-2"]
        self.assertEqual((d.etat, d.actions), ("sans commande", []))
        s3 = salle(sans={"agentchattr-qwencode-2"})
        d = par_instance(G.decider(s3, PROCESSUS, ATTENDU, {}, MAINTENANT, valide=lambda c: False))["qwencode-2"]
        self.assertEqual((d.etat, d.actions), ("commande illisible (rien n'est tué)", []))
        G.executer([d], run=f.lancer, tuer=f.tuer, dormir=lambda s: None)
        self.assertEqual((f.run, f.tues), ([], []))


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
