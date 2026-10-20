#!/usr/bin/env python3
"""usage_qwen.py — bilan des requêtes des 4 Qwen par agent, depuis ~/.qwen/usage/token-usage-*.jsonl. v1.0 (2026-10-20,
claude-2, claude-1 #tache-22 msgs 5691 et 5699).

Lecture seule ; ne lit ni prompt ni réponse : seulement les compteurs de chaque requête (entrée, sortie, cache, réflexion, durée)
et le nom des fichiers de conversation (~/.qwen/projects/<cwd>/chats/<sessionId>.jsonl) pour rattacher une session à son agent
(cwd : atelier = qwencode-1, qwencode-2, cad-bolt = qwencode-3, cad-bolt-2 = qwencode-4).

    python3 scripts/usage_qwen.py "2026-10-19T17:00:00-04:00"
"""
import json, sys, statistics
from pathlib import Path
from datetime import datetime, timezone
DEPUIS = datetime.fromisoformat(sys.argv[1]).astimezone(timezone.utc) if len(sys.argv) > 1 else datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)
AGENTS = {"-home-charles-antoine-atelier": "qwencode-1", "-home-charles-antoine-atelier-qwencode-2": "qwencode-2",
          "-home-charles-antoine-atelier-cad-bolt": "qwencode-3", "-home-charles-antoine-atelier-cad-bolt-2": "qwencode-4"}
session_agent = {}
for proj, agent in AGENTS.items():
    for f in (Path.home() / ".qwen" / "projects" / proj / "chats").glob("*.jsonl"):
        session_agent[f.stem] = agent
par = {}
lignes = [l for f in sorted((Path.home() / ".qwen" / "usage").glob("token-usage-*.jsonl")) for l in f.read_text().splitlines() if l.strip()]
for l in lignes:
    d = json.loads(l)
    t = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
    if t < DEPUIS or d.get("authType") != "openai":
        continue
    a = session_agent.get(d["sessionId"], "autre")
    par.setdefault(a, []).append(d)
print(f"depuis {DEPUIS.astimezone():%Y-%m-%d %H:%M}")
print("agent | req | sortie (jetons) | dont réflexion | entrée moy. | entrée en cache | durée API moy. (s) | ≥ 60 k d'entrée sans cache | sortie méd. / p90")
for a, ds in sorted(par.items()):
    sortie = sum(d["outputTokens"] for d in ds); pens = sum(d.get("thoughtsTokens", 0) for d in ds)
    entree = sum(d["inputTokens"] for d in ds); cache = sum(d.get("cachedTokens", 0) for d in ds)
    gros = sum(1 for d in ds if d["inputTokens"] >= 60000 and d.get("cachedTokens", 0) == 0)
    outs = sorted(d["outputTokens"] for d in ds)
    print(f"{a} | {len(ds)} | {sortie} | {pens} ({100*pens/max(sortie,1):.1f} %) | {entree/len(ds):.0f} | {100*cache/max(entree,1):.1f} % | "
          f"{statistics.mean(d['apiDurationMs'] for d in ds)/1000:.1f} | {gros} | {outs[len(outs)//2]} / {outs[int(len(outs)*0.9)]}")
