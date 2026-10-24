"""Vitesse des cartes Qwen (scripts/vitesse_cartes_qwen.py), sur des lignes de journal fabriquées.

v1.0 (2026-10-20, claude-2) : période sans requête, sans ligne MTP, et un partage de carte (claude-3 msg 5704, claude-1 msg 5705).
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vitesse_cartes_qwen", ROOT / "scripts" / "vitesse_cartes_qwen.py")
V = importlib.util.module_from_spec(SPEC)
sys.modules["vitesse_cartes_qwen"] = V
SPEC.loader.exec_module(V)


def requete(fente, tache, t0, p_s, p_n, e_s, e_n, draft=None):
    """Lignes journalctl -o short-unix d'une requête : lancement, prompt, génération, (MTP), fin."""
    t1 = t0 + p_s + e_s
    l = [f"{t0:.3f} hote x: I slot launch_slot_: id  {fente} | task {tache} | processing task, is_child = 0",
         f"{t1:.3f} hote x: I slot print_timing: id  {fente} | task {tache} | prompt eval time =  {p_s * 1000:.2f} ms / {p_n} tokens (x)",
         f"{t1:.3f} hote x: I slot print_timing: id  {fente} | task {tache} |        eval time =  {e_s * 1000:.2f} ms / {e_n} tokens (x)"]
    if draft is not None:
        l.append(f"{t1:.3f} hote x: I slot print_timing: id  {fente} | task {tache} | draft acceptance = {draft} (1 accepted / 1 generated)")
    l.append(f"{t1:.3f} hote x: I slot      release: id  {fente} | task {tache} | stop processing: n_tokens = 1, truncated = 0")
    return l


class TestVitesse(unittest.TestCase):
    def test_periode_vide(self):
        self.assertIsNone(V.bilan(V.taches([])))
        self.assertEqual(V.imprimer("a", None, "2026-10-21 00:00"), ["carte A : aucune requête terminée depuis 2026-10-21 00:00"])
        self.assertIsNone(V.bilan(V.taches(["-- No entries --"])))

    def test_sans_mtp(self):
        b = V.bilan(V.taches(requete(0, 1, 1000.0, 2.0, 1000, 10.0, 220)))
        self.assertIsNone(b["mtp"])
        self.assertIn("acceptation MTP médiane —", V.imprimer("b", b, "x")[-1])

    def test_seule_et_partagee(self):
        lignes = requete(0, 1, 1000.0, 1.0, 6000, 10.0, 220, draft=0.9)            # seule : 22 jetons/s
        lignes += requete(0, 2, 2000.0, 1.0, 100, 20.0, 220, draft=0.8)            # les deux fentes travaillent ensemble
        lignes += requete(1, 3, 2000.0, 1.0, 100, 20.0, 220, draft=0.85)           # : 11 jetons/s chacune
        b = V.bilan(V.taches(lignes))
        self.assertEqual(b["n"], 3)
        self.assertEqual(b["seule"], [22.0])
        self.assertEqual(sorted(b["partagee"]), [11.0, 11.0])
        self.assertAlmostEqual(b["mtp"], 0.85)
        self.assertEqual(b["p_seule"], [6000.0])


if __name__ == "__main__":
    unittest.main()
