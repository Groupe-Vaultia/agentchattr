#!/usr/bin/env python3
"""vitesse_cartes_qwen.py — vitesse de génération et de prompt de chaque carte Qwen (A :8081, B :8082), selon que l'autre fente de la
même carte travaille ou non. v1.0.1 (2026-10-20, claude-2, claude-3 msg 5704, claude-1 msg 5705) : période sans requête
terminée ou sans ligne MTP gérée (plus de `max()` vide) ; fonctions testables. v1.0 (2026-10-20, claude-2, claude-1 #tache-22 msgs 5691 et
5699).

Lecture seule de `journalctl --user -u qwen-q4-a|b` (lignes print_timing, launch_slot_, release) ; aucun contenu de requête.
« seule » : l'autre fente est libre pendant plus de 90 % de la génération (ou du prompt) ; « partagée » : occupée plus de 90 %.

    python3 scripts/vitesse_cartes_qwen.py "2026-10-19 17:00"
"""
import re, subprocess, sys, statistics
R_L = re.compile(r"launch_slot_: id\s+(\d+) \| task (\d+)")
R_P = re.compile(r"id\s+(\d+) \| task (\d+) \| prompt eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
R_E = re.compile(r"id\s+(\d+) \| task (\d+) \|\s+eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
R_R = re.compile(r"release: id\s+(\d+) \| task (\d+)")
R_D = re.compile(r"id\s+(\d+) \| task (\d+) \| draft acceptance = ([\d.]+)")


def lire_journal(carte: str, depuis: str) -> list[str]:
    return subprocess.run(["journalctl", "--user", "-u", f"qwen-q4-{carte}", "--since", depuis, "--no-pager", "-o", "short-unix"],
                          capture_output=True, text=True).stdout.splitlines()


def taches(lignes: list[str]) -> list[dict]:
    """Requêtes terminées : début, fin, (s, jetons) de prompt et de génération, acceptation MTP."""
    par_tache = {}
    for l in lignes:
        try:
            t = float(l.split()[0])
        except (ValueError, IndexError):
            continue
        for rx, cle in ((R_L, "debut"), (R_P, "p"), (R_E, "e"), (R_R, "fin"), (R_D, "draft")):
            m = rx.search(l)
            if m:
                d = par_tache.setdefault(m.group(2), {"fente": int(m.group(1))})
                if cle in ("debut", "fin"):
                    d[cle] = t
                elif cle == "draft":
                    d["draft"] = float(m.group(3))
                else:
                    d[cle] = (float(m.group(3)) / 1000, int(m.group(4)))
                break
    ts = [d for d in par_tache.values() if {"debut", "fin", "p", "e"} <= d.keys()]
    for d in ts:                               # fenêtre de génération ≈ [fin − durée de génération, fin]
        d["g0"], d["g1"] = d["fin"] - d["e"][0], d["fin"]
    return ts


def bilan(ts: list[dict]) -> dict | None:
    """None s'il n'y a aucune requête terminée sur la période."""
    if not ts:
        return None
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
    drafts = [d["draft"] for d in ts if "draft" in d]
    return {"n": len(ts), "duree": max(d["fin"] for d in ts) - min(d["debut"] for d in ts),
            "tp": sum(d["p"][0] for d in ts), "te": sum(d["e"][0] for d in ts),
            "ntp": sum(d["p"][1] for d in ts), "nte": sum(d["e"][1] for d in ts),
            "seule": seule, "partagee": partagee, "p_seule": p_seule, "p_part": p_part,
            "mtp": statistics.median(drafts) if drafts else None}


def imprimer(carte: str, b: dict | None, depuis: str) -> list[str]:
    if b is None:
        return [f"carte {carte.upper()} : aucune requête terminée depuis {depuis}"]
    q = lambda v: f"{statistics.median(v):.1f} (n {len(v)})" if v else "—"
    debit = f"{b['nte'] / b['duree']:.1f} jetons/s" if b["duree"] > 0 else "—"
    part = f"{100 * b['tp'] / (b['tp'] + b['te']):.0f} %" if b["tp"] + b["te"] > 0 else "—"
    return [f"carte {carte.upper()} : {b['n']} requêtes sur {b['duree']/3600:.1f} h ; temps de prompt {b['tp']/3600:.2f} h ({b['ntp']} jetons), "
            f"temps de génération {b['te']/3600:.2f} h ({b['nte']} jetons) ; part du prompt {part}",
            f"   génération, jetons/s par requête (médiane) : seule {q(b['seule'])} ; partagée {q(b['partagee'])}",
            f"   prompt ≥ 5 k jetons, jetons/s : seule {q(b['p_seule'])} ; partagée {q(b['p_part'])}",
            f"   débit de sortie moyen de la carte sur la période : {debit} ; acceptation MTP médiane "
            + (f"{b['mtp']:.2f}" if b["mtp"] is not None else "—")]


if __name__ == "__main__":
    depuis = sys.argv[1] if len(sys.argv) > 1 else "2026-10-19 17:00"
    for carte in "ab":
        print("\n".join(imprimer(carte, bilan(taches(lire_journal(carte, depuis))), depuis)))
