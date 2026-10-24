#!/usr/bin/env python3
"""pertes_cache_qwen.py — attribution des pertes de cache des Qwen (cartes A :8081, B :8082). v1.0 (2026-10-19, claude-2,
claude-1 #tache-22 msg 5648).

Lecture seule de `journalctl --user -u qwen-q4-a|b` (llama-server). Une requête « perd » le cache quand sa fente ne contenait pas
sa conversation : sélection LRU, ou LCP qui jette plus de 10 % du cache de la fente (f_keep < 0,9). Les journaux ne disent pas quel
agent a envoyé la requête (nginx : access_log off) : la conversation est suivie par sa longueur (≈ jetons retraités / (1 − f_sim)),
et chaque perte est rattachée au dernier état plausible de sa conversation :
  - changement de carte : seul précédent plausible sur l'autre carte ;
  - éviction sur la même carte : seul précédent plausible sur la même carte, dans une fente écrasée depuis par une autre conversation ;
  - ambigu : précédents plausibles sur les deux cartes ; indéterminé : aucun ;
  - nouvelle conversation (relance ou /clear) : prompt de moins de 30 k jetons (invite système et outils ≈ 26-28 k).
Avec une carte fixe par Qwen (2 Qwen pour 2 fentes), seules les nouvelles conversations restent inévitables.

    python3 scripts/pertes_cache_qwen.py ["2026-10-19 17:00"] [seuil_jetons] [-v]
"""
import re, subprocess, sys
from datetime import datetime
DEPUIS = sys.argv[1] if len(sys.argv) > 1 else "2026-10-19 17:00"
SEUIL = int(sys.argv[2]) if len(sys.argv) > 2 else 10000          # jetons retraités : en dessous, perte négligeable
CROISS = 20000                                                       # croissance max d'une conversation entre deux tours
FENETRE = 1800                                                       # s : la requête précédente de la même conversation
NEUVE = 30000                                                        # une conversation neuve (invite système + outils) fait ~26-28 k
R_SEL = re.compile(r"get_availabl: id\s+(\d+) \| task -1 \| selected slot by (LRU|LCP similarity)(?:, f_sim_best = ([\d.]+).*f_keep = ([\d.]+))?")
R_LAUNCH = re.compile(r"launch_slot_: id\s+(\d+) \| task (\d+)")
R_PROG = re.compile(r"id\s+(\d+) \| task (\d+) \| prompt processing, n_tokens =\s+(\d+), progress = ([\d.]+)")
R_EVAL = re.compile(r"id\s+(\d+) \| task (\d+) \| prompt eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
taches = []
for carte in ("a", "b"):
    sortie = subprocess.run(["journalctl", "--user", "-u", f"qwen-q4-{carte}", "--since", DEPUIS, "--no-pager", "-o", "short-unix"],
                            capture_output=True, text=True).stdout.splitlines()
    sel, par_tache = {}, {}
    for l in sortie:
        try:
            t = float(l.split()[0])
        except (ValueError, IndexError):
            continue
        if m := R_SEL.search(l):
            sel[m.group(1)] = (m.group(2), float(m.group(3) or 0), float(m.group(4) or 0))
        elif m := R_LAUNCH.search(l):
            mode, sim, keep = sel.pop(m.group(1), ("?", 0, 0))
            d = {"carte": carte.upper(), "fente": int(m.group(1)), "tache": int(m.group(2)), "t": t, "mode": mode, "sim": sim,
                 "keep": keep, "n": 0, "total": 0}
            par_tache[m.group(2)] = d
            taches.append(d)
        elif m := R_PROG.search(l):
            d = par_tache.get(m.group(2))
            if d and float(m.group(4)) > 0:
                d["total_prog"] = int(m.group(3)) / float(m.group(4))
        elif m := R_EVAL.search(l):
            d = par_tache.get(m.group(2))
            if d:
                d["n"], d["ms"] = int(m.group(4)), float(m.group(3))
for d in taches:                                                     # longueur totale du prompt
    if d["mode"] == "LCP similarity" and d["sim"] < 1:
        d["total"] = d["n"] / (1 - d["sim"]) if d["n"] else 0
    else:
        d["total"] = d["n"]
taches.sort(key=lambda d: d["t"])
# perte = la fente ne contenait pas cette conversation : LRU, ou LCP qui jette plus de 10 % du cache de la fente
pertes = [d for d in taches if d["n"] >= SEUIL and (d["mode"] == "LRU" or d["keep"] < 0.9)]
# historique des fentes : une requête est une « suite » si LCP garde ≥ 90 % du cache de sa fente
def suite(d):
    return d["mode"] == "LCP similarity" and d["keep"] >= 0.9
par_fente = {}
for d in taches:
    par_fente.setdefault((d["carte"], d["fente"]), []).append(d)
for seq in par_fente.values():
    for p, q in zip(seq, seq[1:] + [None]):
        p["suivant"] = q                                             # prochaine requête dans la même fente
classes, pris = {}, set()
for d in pertes:
    def candidat(p):
        if p is d or id(p) in pris or not p["total"] or not (0 < d["t"] - p["t"] <= FENETRE):
            return False
        if not (0 <= d["total"] - p["total"] <= CROISS):
            return False
        q = p["suivant"]
        if q is not None and q["t"] < d["t"] and suite(q):
            return False                                             # la conversation de p a continué dans sa fente : p n'est pas un bout
        if p["carte"] == d["carte"]:
            # même carte : p n'est un précédent que si sa fente a été écrasée par une autre conversation avant d
            return q is not None and q is not d and q["t"] < d["t"] and not suite(q)
        return True
    autre = [p for p in taches if p["carte"] != d["carte"] and candidat(p)]
    meme = [p for p in taches if p["carte"] == d["carte"] and candidat(p)]
    if d["total"] < NEUVE:
        c = "nouvelle conversation (relance ou /clear)"
    elif autre and meme:
        c = "ambigu (précédent possible sur les deux cartes)"
    elif autre:
        c = "changement de carte"
        pris.add(id(max(autre, key=lambda p: p["t"])))
    elif meme:
        c = "éviction sur la même carte"
        pris.add(id(max(meme, key=lambda p: p["t"])))
    else:
        c = "indéterminé"
    d["classe"] = c
    classes.setdefault(c, []).append(d)
lru = [d for d in taches if d["mode"] == "LRU"]
petits = [d for d in lru if d["n"] < SEUIL]
print(f"depuis {DEPUIS} : {len(taches)} requêtes ; {len(lru)} LRU (A {sum(d['carte']=='A' for d in lru)}, B {sum(d['carte']=='B' for d in lru)}) ;"
      f" pertes ≥ {SEUIL} jetons retraités : {len(pertes)}")
for c, ds in sorted(classes.items(), key=lambda x: -len(x[1])):
    print(f"  {c} : {len(ds)} (LRU {sum(d['mode']=='LRU' for d in ds)}) ; {sum(d['n'] for d in ds)} jetons retraités ; "
          f"{sum(d.get('ms', 0) for d in ds) / 60000:.0f} min de calcul de prompt")
print(f"  LRU à moins de {SEUIL} jetons retraités (requêtes courtes) : {len(petits)}")
if "-v" in sys.argv:
    for d in pertes:
        print(f"    {datetime.fromtimestamp(d['t']):%H:%M:%S} {d['carte']}{d['fente']} {d['mode'][:3]} sim {d['sim']:.2f} "
              f"keep {d['keep']:.2f} retraité {d['n']} total≈{d['total']:.0f} → {d['classe']}")
