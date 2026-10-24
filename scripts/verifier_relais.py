#!/usr/bin/env python3
"""Détecteur de relais morts : pour chaque session tmux `agentchattr-<agent>`, le relais `wrapper.py` est-il vivant ?

v1.0 (2026-10-19, claude-2, claude-1 #tache-22 msg 5596) : les `wrapper.py` de qwencode-3 et qwencode-4 étaient morts depuis
17 h 10 alors que leurs Qwen tournaient toujours dans tmux : plus de @mentions injectées, plus de messages possibles.

Lecture seule : ne relance rien, ne tue rien, n'écrit rien. N'imprime que des noms, des PID et des états, jamais un jeton ni la
ligne de commande d'un processus (elle peut porter une clé d'API).

    python3 scripts/verifier_relais.py                 # données de ./data du dépôt
    python3 scripts/verifier_relais.py --data ../agentchattr/data

Par session `agentchattr-<agent>` :
  1. relais : la session `ac-<agent sans tiret>` (lancée par vaultia-start.sh) et le PID du `wrapper.py` sous son volet ;
     « mort » si le volet n'a plus de `wrapper.py` (il attend sur `read`), « sans ac-* » si la session de lancement manque ;
  2. registre (`data/registry.json`) : actif, en attente, récupérable (désinscrit par le crash-timeout, jeton gardé) ou absent ;
     `agentchattr-claude` vaut pour `claude-1` quand la famille a été renumérotée ;
  3. dernier battement : la dernière ligne `POST /api/heartbeat/<agent>` de `data/server.log`. Ces lignes n'ont pas d'heure :
     la sienne est interpolée par sa position entre les lignes horodatées qui l'encadrent (la dernière ligne du journal a l'heure
     de modification du fichier) ; un relais vivant bat toutes les 5 s, donc les lignes arrivent à cadence à peu près régulière.
Code de sortie : 0 si chaque session a un relais vivant, 1 sinon, 2 si tmux ou les données sont illisibles.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

VERSION = "v1.0"
RACINE = Path(__file__).resolve().parents[1]
RE_HEURE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}) \[")
RE_BATTEMENT = re.compile(r'"POST /api/heartbeat/([\w.-]+) HTTP')
CRASH_TIMEOUT = 60      # s, app.py : sans battement depuis 60 s, le serveur désinscrit l'agent


@dataclass
class Ligne:
    session: str
    agent: str
    lanceur: str
    pid: int | None
    relais: str
    registre: str
    battement: str
    verdict: str


# --- lectures (seules fonctions qui touchent au système) --------------------------------------------------------------------

def lire_tmux() -> list[tuple[str, int]]:
    """(session, PID du premier volet) pour chaque session tmux."""
    r = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{pane_index}\t#{pane_pid}"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("tmux illisible")
    vus: dict[str, int] = {}
    for l in r.stdout.splitlines():
        s, idx, pid = l.split("\t")
        if s not in vus or idx == "0":
            vus[s] = int(pid)
    return sorted(vus.items())


def lire_processus() -> list[tuple[int, int, bool]]:
    """(PID, PID parent, est un wrapper.py) ; la ligne de commande est lue ici et n'en sort pas."""
    r = subprocess.run(["ps", "-eo", "pid=,ppid=,comm=,args="], capture_output=True, text=True)
    return [p for p in (analyser_ps(l) for l in r.stdout.splitlines()) if p]


def analyser_ps(ligne: str) -> tuple[int, int, bool] | None:
    """Un relais est un python dont un argument est wrapper.py ; le `bash -c "… wrapper.py …; read"` du volet ne l'est pas."""
    morceaux = ligne.split(None, 3)
    if len(morceaux) < 3:
        return None
    args = morceaux[3].split() if len(morceaux) == 4 else []
    est_relais = morceaux[2].startswith("python") and any(Path(a).name == "wrapper.py" for a in args[1:])
    return int(morceaux[0]), int(morceaux[1]), est_relais


def lire_registre(chemin: Path) -> dict[str, str]:
    """Nom → état ; seuls les noms et les états sortent de cette fonction (registry.json porte les jetons)."""
    data = json.loads(chemin.read_text("utf-8"))
    etats = {n: "récupérable" for n in data.get("reclaimable", {})}
    for n, d in data.get("instances", {}).items():
        etats[n] = "actif" if d.get("state", "active") == "active" else "en attente"
    return etats


# --- calcul (pur, testé sans tmux) ------------------------------------------------------------------------------------------

def relais_sous(pid_volet: int, processus: list[tuple[int, int, bool]]) -> int | None:
    """PID du premier wrapper.py parmi les descendants du volet."""
    enfants: dict[int, list[int]] = {}
    wrappers = set()
    for pid, ppid, w in processus:
        enfants.setdefault(ppid, []).append(pid)
        if w:
            wrappers.add(pid)
    pile = [pid_volet]
    while pile:
        p = pile.pop()
        if p in wrappers:
            return p
        pile.extend(enfants.get(p, []))
    return None


def battements(lignes: list[str], fin: float) -> dict[str, float]:
    """Agent → instant estimé (epoch) de son dernier battement. `fin` = heure de la dernière ligne (modification du fichier)."""
    reperes: list[tuple[int, int]] = []                       # (rang de ligne, seconde du jour)
    dernier: dict[str, int] = {}
    for i, l in enumerate(lignes):
        m = RE_HEURE.match(l)
        if m:
            h, mi, s = (int(x) for x in m.groups())
            reperes.append((i, h * 3600 + mi * 60 + s))
            continue
        b = RE_BATTEMENT.search(l)
        if b:
            dernier[b.group(1)] = i
    # dates absolues, de la fin vers le début : chaque repère est le dernier instant de sa seconde du jour avant le suivant
    absolus: list[tuple[int, float]] = [(len(lignes) - 1, fin)]
    for i, sec in reversed(reperes):
        if i >= absolus[0][0]:
            continue
        suivant = absolus[0][1]
        t = time.localtime(suivant)
        minuit = suivant - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)
        instant = minuit + sec
        absolus.insert(0, (i, instant if instant <= suivant else instant - 86400))
    out = {}
    for agent, k in dernier.items():
        avant = [a for a in absolus if a[0] <= k]
        apres = [a for a in absolus if a[0] >= k]
        if not avant:                                         # avant le premier repère : borne par le premier
            out[agent] = apres[0][1]
            continue
        (i0, t0), (i1, t1) = avant[-1], apres[0]
        out[agent] = t0 if i1 == i0 else t0 + (k - i0) / (i1 - i0) * (t1 - t0)
    return out


def nom_agent(session: str, registre: dict[str, str]) -> str:
    """agentchattr-claude → claude-1 si seul claude-1 existe au registre (famille renumérotée)."""
    nom = session[len("agentchattr-"):]
    if nom not in registre and f"{nom}-1" in registre:
        return f"{nom}-1"
    return nom


def tableau(sessions: list[tuple[str, int]], processus: list[tuple[int, int, bool]], registre: dict[str, str],
            ages: dict[str, float]) -> list[Ligne]:
    """`ages` : agent → âge estimé (s) du dernier battement."""
    volets = dict(sessions)
    out = []
    for s, _ in sessions:
        if not s.startswith("agentchattr-"):
            continue
        nom_session = s[len("agentchattr-"):]
        agent = nom_agent(s, registre)
        lanceur = "ac-" + nom_session.replace("-", "")
        if lanceur not in volets:
            pid, relais = None, "sans ac-*"
        else:
            pid = relais_sous(volets[lanceur], processus)
            relais = "vivant" if pid else "mort"
        etat = registre.get(agent, "absent")
        age = ages.get(agent, ages.get(nom_session))
        battement = "jamais (journal)" if age is None else f"≈ {_duree(age)}"
        if relais != "vivant":
            verdict = "RELAIS MORT" if relais == "mort" else "RELAIS INTROUVABLE"
        elif etat != "actif":
            verdict = f"à surveiller : registre {etat}"
        elif age is None or age > CRASH_TIMEOUT:
            verdict = "à surveiller : battement ancien"
        else:
            verdict = "ok"
        out.append(Ligne(s, agent, lanceur, pid, relais, etat, battement, verdict))
    return out


def _duree(s: float) -> str:
    s = int(s)
    if s < 120:
        return f"{s} s"
    if s < 7200:
        return f"{s // 60} min"
    return f"{s // 3600} h {s % 3600 // 60:02d}"


def imprimer(lignes: list[Ligne]) -> str:
    entetes = ("Session", "Agent", "Lanceur", "PID relais", "Relais", "Registre", "Dernier battement", "Verdict")
    rangs = [(l.session, l.agent, l.lanceur, str(l.pid or "—"), l.relais, l.registre, l.battement, l.verdict) for l in lignes]
    larg = [max(len(x) for x in col) for col in zip(entetes, *rangs)]
    fmt = "  ".join(f"{{:<{n}}}" for n in larg)
    return "\n".join([fmt.format(*entetes), fmt.format(*("-" * n for n in larg)), *(fmt.format(*r) for r in rangs)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Détecteur de relais morts (" + VERSION + "), lecture seule.")
    ap.add_argument("--data", type=Path, default=RACINE / "data", help="dossier data d'agentchattr (registry.json, server.log)")
    a = ap.parse_args(argv)
    try:
        sessions = lire_tmux()
        registre = lire_registre(a.data / "registry.json")
    except (RuntimeError, OSError, ValueError) as e:
        print(f"lecture impossible : {e.__class__.__name__} ({'tmux' if isinstance(e, RuntimeError) else a.data})")
        return 2
    journal = a.data / "server.log"
    instants = {}
    if journal.exists():
        instants = battements(journal.read_text("utf-8", errors="replace").splitlines(), journal.stat().st_mtime)
    maintenant = time.time()
    lignes = tableau(sessions, lire_processus(), registre, {n: max(0.0, maintenant - t) for n, t in instants.items()})
    print(imprimer(lignes))
    morts = [l for l in lignes if l.relais != "vivant"]
    print(f"\n{len(lignes)} sessions agentchattr-* ; {len(morts)} sans relais vivant"
          + (f" : {', '.join(l.agent for l in morts)}" if morts else ""))
    return 1 if morts else 0


if __name__ == "__main__":
    sys.exit(main())
