#!/usr/bin/env python3
"""vitesse_cartes_qwen.py — vitesse de génération et de prompt de chaque carte Qwen (A :8081, B :8082), selon que l'autre fente de la
même carte travaille ou non. v1.0 (2026-10-20, claude-2, claude-1 #tache-22 msgs 5691 et 5699).

Lecture seule de `journalctl --user -u qwen-q4-a|b` (lignes print_timing, launch_slot_, release) ; aucun contenu de requête.
« seule » : l'autre fente est libre pendant plus de 90 % de la génération (ou du prompt) ; « partagée » : occupée plus de 90 %.

    python3 scripts/vitesse_cartes_qwen.py "2026-10-19 17:00"
"""
import re, subprocess, sys, statistics
DEPUIS = sys.argv[1] if len(sys.argv) > 1 else "2026-10-19 17:00"
R_L = re.compile(r"launch_slot_: id\s+(\d+) \| task (\d+)")
R_P = re.compile(r"id\s+(\d+) \| task (\d+) \| prompt eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
R_E = re.compile(r"id\s+(\d+) \| task (\d+) \|\s+eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
R_R = re.compile(r"release: id\s+(\d+) \| task (\d+)")
R_D = re.compile(r"id\s+(\d+) \| task (\d+) \| draft acceptance = ([\d.]+)")
res = {}
for carte in "ab":
    taches = {}
    for l in subprocess.run(["journalctl", "--user", "-u", f"qwen-q4-{carte}", "--since", DEPUIS, "--no-pager", "-o", "short-unix"],
                            capture_output=True, text=True).stdout.splitlines():
        try:
            t = float(l.split()[0])
        except (ValueError, IndexError):
            continue
        for rx, cle in ((R_L, "debut"), (R_P, "p"), (R_E, "e"), (R_R, "fin"), (R_D, "draft")):
            m = rx.search(l)
            if m:
                d = taches.setdefault(m.group(2), {"fente": int(m.group(1))})
                if cle in ("debut", "fin"):
                    d[cle] = t
                elif cle == "draft":
                    d["draft"] = float(m.group(3))
                else:
                    d[cle] = (float(m.group(3)) / 1000, int(m.group(4)))
                break
    ts = [d for d in taches.values() if {"debut", "fin", "p", "e"} <= d.keys()]
    for d in ts:                               # fenêtre de génération ≈ [fin − durée de génération, fin]
        d["g0"], d["g1"] = d["fin"] - d["e"][0], d["fin"]
    def occupe_autre(d, a, b):
        return sum(max(0.0, min(b, o["fin"]) - max(a, o["debut"])) for o in ts if o["fente"] != d["fente"] and o["fin"] > a and o["debut"] < b)
    seule, partagee, p_seule, p_part = [], [], [], []
    for d in ts:
        if d["e"][1] >= 50 and d["e"][0] > 0:
            frac = occupe_autre(d, d["g0"], d["g1"]) / d["e"][0]
            (seule if frac < 0.1 else partagee if frac > 0.9 else []).append(d["e"][1] / d["e"][0])
        if d["p"][1] >= 5000:
            p0, p1 = d["debut"], d["debut"] + d["p"][0]
            frac = occupe_autre(d, p0, p1) / max(d["p"][0], 1e-6)
            (p_seule if frac < 0.1 else p_part if frac > 0.9 else []).append(d["p"][1] / d["p"][0])
    tp, te = sum(d["p"][0] for d in ts), sum(d["e"][0] for d in ts)
    ntp, nte = sum(d["p"][1] for d in ts), sum(d["e"][1] for d in ts)
    duree = max(d["fin"] for d in ts) - min(d["debut"] for d in ts)
    q = lambda v: f"{statistics.median(v):.1f} (n {len(v)})" if v else "—"
    print(f"carte {carte.upper()} : {len(ts)} requêtes sur {duree/3600:.1f} h ; temps de prompt {tp/3600:.2f} h ({ntp} jetons), "
          f"temps de génération {te/3600:.2f} h ({nte} jetons) ; part du prompt {100*tp/(tp+te):.0f} %")
    print(f"   génération, jetons/s par requête (médiane) : seule {q(seule)} ; partagée {q(partagee)}")
    print(f"   prompt ≥ 5 k jetons, jetons/s : seule {q(p_seule)} ; partagée {q(p_part)}")
    print(f"   débit de sortie moyen de la carte sur la période : {nte/duree:.1f} jetons/s ; acceptation MTP médiane "
          f"{statistics.median([d['draft'] for d in ts if 'draft' in d]):.2f}")
