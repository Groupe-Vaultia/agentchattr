#!/usr/bin/env python3
"""Gardien multi-instance des agents CLI : une passe par appel, une décision par instance.

v1.0.1 (2026-10-19, claude-2, claude-1 msg 5602) : `--relancer base:n`, relance manuelle d'une seule instance (relais, TUI et
lanceur), refusée si un worktree connu de l'instance a des modifications non commitées, ou si aucun n'est connu, sauf `--force`.
v1.0 (2026-10-19, claude-2, claude-1 #tache-22 msg 5600) : l'ancien `cli()` de vaultia-watchdog.sh ne regardait que l'instance 1
(`agentchattr-qwencode`) ; quand elle manquait, `pkill -f "… wrapper\\.py qwencode"` tuait les relais des 4 instances, qui ont la
même ligne de commande, puis n'en relançait qu'un (data/watchdog.log:6149, 19 oct. 17 h 10 : qwencode-3 et -4 sans relais).

    python3 scripts/gardien_instances.py claude:3 codex:2 qwencode:4 grok:1           # appelé par vaultia-watchdog.sh
    python3 scripts/gardien_instances.py --essai claude:3 codex:2 qwencode:4 grok:1   # imprime le plan, ne fait rien
    python3 scripts/gardien_instances.py --relancer qwencode:3 [--essai] [--force]    # relance manuelle d'une instance

Instance <base> n° n : lanceur `ac-<base>` (n = 1) ou `ac-<base><n>`, TUI `agentchattr-<base>` ou `agentchattr-<base>-1` (n = 1),
`agentchattr-<base>-<n>` sinon ; à défaut de nom, le TUI de la même famille créé dans les 60 s qui suivent le lanceur (un relais
relancé peut recevoir un autre numéro du serveur). Décision :
  - TUI et relais vivants : rien ;
  - TUI vivant, relais mort : **signalé seulement**. Relancer le relais tuerait le TUI (wrapper_unix.py:302-306 ferme la session
    de même nom) et son contexte ; la relance est une décision humaine ;
  - TUI absent : si le lanceur a moins de 120 s, rien (démarrage en cours) ; sinon, tuer **le seul** relais de cette instance
    (PID trouvé sous le volet de son lanceur, verifier_relais.relais_sous), fermer ce lanceur, le recréer avec **sa** commande de
    lancement (tmux `pane_start_command`), sinon celle d'un lanceur frère de la même famille, sinon `--defaut <base>=<options>`.
    La relance n'a lieu que si une seconde lecture, 8 s plus tard, donne la même décision (le relais redémarre lui-même son TUI
    en 3 s, wrapper_unix.py:333-336).
Relance manuelle (`--relancer qwencode:3`) : tuer le relais sous `ac-qwencode3`, fermer son TUI puis son lanceur, recréer le
lanceur avec sa commande d'origine. Worktrees connus de l'instance : le dossier courant de son TUI s'il est dans git, et les
worktrees (projetcad-repo, agentchattr) dont le nom ou la branche porte `qwencode3` ou `qwencode-3`. Un fichier modifié ou non
suivi (hors `.pyc` et `__pycache__`) bloque la relance ; aucun worktree connu aussi ; `--force` passe outre. Codes : 0 fait,
3 refusé, 2 instance ou commande introuvable.
Jamais de `pkill` ni de motif : un PID, une session. Le journal ne porte que des noms et des PID : les commandes de lancement
peuvent contenir une clé d'API et ne sont jamais imprimées.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "v1.0.1"
RACINE = Path(__file__).resolve().parents[1]
DEMARRAGE = 120          # s : un lanceur plus jeune n'est pas jugé (son TUI se crée)
APPARIEMENT = 60         # s : TUI créé au plus tard 60 s après son lanceur
CONFIRMATION = 8         # s : seconde lecture avant toute relance

if "verifier_relais" in sys.modules:                      # même recherche de relais que le détecteur (msg 5600)
    VR = sys.modules["verifier_relais"]
else:
    _spec = importlib.util.spec_from_file_location("verifier_relais", Path(__file__).with_name("verifier_relais.py"))
    VR = importlib.util.module_from_spec(_spec)
    sys.modules["verifier_relais"] = VR
    _spec.loader.exec_module(VR)


@dataclass
class Session:
    nom: str
    cree: float                # epoch de création
    pid_volet: int
    commande: str = field(default="", repr=False)   # pane_start_command : peut porter une clé, jamais imprimée
    chemin: str = ""                                 # pane_current_path : dossier courant du volet


@dataclass
class Decision:
    instance: str              # « qwencode-3 »
    lanceur: str
    tui: str | None
    relais: int | None
    etat: str                  # ok, relais mort (TUI vivant), démarrage, relance, sans commande
    actions: list[tuple] = field(default_factory=list, repr=False)


# --- lectures --------------------------------------------------------------------------------------------------------------

def lire_sessions() -> list[Session]:
    r = subprocess.run(["tmux", "list-panes", "-a", "-F",
                        "#{session_name}\t#{session_created}\t#{pane_index}\t#{pane_pid}\t#{pane_current_path}\t#{pane_start_command}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    vus: dict[str, Session] = {}
    for l in r.stdout.splitlines():
        nom, cree, idx, pid, chemin, cmd = (l.split("\t", 5) + [""] * 6)[:6]
        if nom not in vus or idx == "0":
            vus[nom] = Session(nom, float(cree), int(pid), cmd, chemin)
    return list(vus.values())


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def lister_worktrees(depots: list[Path]) -> list[tuple[str, str]]:
    """(chemin, branche) de chaque worktree des dépôts donnés."""
    out = []
    for d in depots:
        chemin = ""
        for l in _git("-C", str(d), "worktree", "list", "--porcelain").stdout.splitlines():
            if l.startswith("worktree "):
                chemin = l[9:]
                out.append((chemin, ""))
            elif l.startswith("branch refs/heads/") and out:
                out[-1] = (chemin, l[18:])
    return out


def est_depot(chemin: str) -> bool:
    return bool(chemin) and _git("-C", chemin, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def non_commites(chemin: str) -> int:
    """Fichiers modifiés ou non suivis, hors .pyc et __pycache__ (des .pyc sont suivis par git dans projetcad)."""
    lignes = _git("-C", chemin, "status", "--porcelain").stdout.splitlines()
    return sum(1 for l in lignes if not re.search(r"(__pycache__/|\.pyc$)", l))


# --- décision (pure) -------------------------------------------------------------------------------------------------------

def noms(base: str, n: int, nb: int = 2) -> tuple[str, list[str], str]:
    """(lanceur, noms de TUI acceptés, nom d'instance) ; une famille d'une seule instance garde son nom nu (grok)."""
    if n == 1:
        return f"ac-{base}", [f"agentchattr-{base}", f"agentchattr-{base}-1"], base if nb == 1 else f"{base}-1"
    return f"ac-{base}{n}", [f"agentchattr-{base}-{n}"], f"{base}-{n}"


def famille(nom_tui: str, base: str) -> bool:
    return nom_tui == f"agentchattr-{base}" or bool(re.fullmatch(rf"agentchattr-{re.escape(base)}-\d+", nom_tui))


def commande_defaut(base: str, options: str) -> str:
    return f'env PATH="{os.environ.get("PATH", "")}" .venv/bin/python wrapper.py {base} {options}; read'


def decider(sessions: list[Session], processus: list[tuple[int, int, bool]], attendu: list[tuple[str, int]],
            defauts: dict[str, str], maintenant: float) -> list[Decision]:
    par_nom = {s.nom: s for s in sessions}
    pris: set[str] = set()
    out: list[Decision] = []
    paires: dict[str, str | None] = {}
    # 1. appariement par nom, puis par heure de création
    for base, nb in attendu:
        for n in range(1, nb + 1):
            lanceur, acceptes, _ = noms(base, n)
            paires[lanceur] = next((t for t in acceptes if t in par_nom and t not in pris), None)
            if paires[lanceur]:
                pris.add(paires[lanceur])
    for base, nb in attendu:
        for n in range(1, nb + 1):
            lanceur = noms(base, n)[0]
            ac = par_nom.get(lanceur)
            if paires[lanceur] or ac is None:
                continue
            libres = [s for s in sessions if famille(s.nom, base) and s.nom not in pris and 0 <= s.cree - ac.cree <= APPARIEMENT]
            if libres:
                t = min(libres, key=lambda s: s.cree - ac.cree)
                paires[lanceur] = t.nom
                pris.add(t.nom)
    # 2. décision par instance
    for base, nb in attendu:
        freres = [par_nom[noms(base, k)[0]].commande for k in range(1, nb + 1)
                  if noms(base, k)[0] in par_nom and par_nom[noms(base, k)[0]].commande]
        for n in range(1, nb + 1):
            lanceur, _, instance = noms(base, n, nb)
            ac, tui = par_nom.get(lanceur), paires[lanceur]
            relais = VR.relais_sous(ac.pid_volet, processus) if ac else None
            d = Decision(instance, lanceur, tui, relais, "ok")
            if tui:
                d.etat = "ok" if relais else "relais mort (TUI vivant)"
            elif ac and maintenant - ac.cree < DEMARRAGE:
                d.etat = "démarrage"
            else:
                cmd = (ac.commande if ac and ac.commande else "") or (freres[0] if freres else "") or \
                      (commande_defaut(base, defauts[base]) if base in defauts else "")
                if not cmd:
                    d.etat = "sans commande"
                else:
                    d.etat = "relance"
                    if relais:
                        d.actions.append(("tuer", relais))
                    if ac:
                        d.actions.append(("fermer", lanceur))
                    d.actions.append(("lancer", lanceur, cmd))
            out.append(d)
    return out


def confirmer(premiere: list[Decision], seconde: list[Decision]) -> list[Decision]:
    """Une relance n'est gardée que si la seconde lecture la redemande pour le même relais."""
    deux = {d.lanceur: d for d in seconde}
    out = []
    for d in premiere:
        s = deux.get(d.lanceur)
        if d.etat == "relance" and not (s and s.etat == "relance" and s.relais == d.relais):
            out.append(Decision(d.instance, d.lanceur, d.tui, d.relais, "relance annulée (seconde lecture)"))
        else:
            out.append(s if (s and d.etat == "relance") else d)
    return out


# --- exécution (injectable) ------------------------------------------------------------------------------------------------

def executer(decisions: list[Decision], run=subprocess.run, tuer=os.kill, dormir=time.sleep) -> None:
    for d in decisions:
        for a in d.actions:
            if a[0] == "tuer":
                try:
                    tuer(a[1], signal.SIGTERM)
                except ProcessLookupError:
                    pass
                dormir(2)                                     # comme l'ancien cli() : laisser le relais partir
            elif a[0] == "fermer":
                run(["tmux", "kill-session", "-t", f"={a[1]}"], capture_output=True)
            elif a[0] == "lancer":
                run(["tmux", "new-session", "-d", "-s", a[1], "-c", str(RACINE), a[2]], capture_output=True)


def journal(decisions: list[Decision], essai: bool) -> list[str]:
    """Une ligne par instance qui n'est pas « ok » ; noms et PID seulement."""
    horo = time.strftime("%m-%d %H:%M:%S")
    out = []
    for d in decisions:
        if d.etat == "ok":
            continue
        quoi = " ; ".join(f"tuer PID {a[1]}" if a[0] == "tuer" else f"fermer {a[1]}" if a[0] == "fermer" else f"relancer {a[1]}"
                          for a in d.actions)
        out.append(f"[{horo}] gardien{' (essai)' if essai else ''} : {d.instance} ({d.lanceur} / {d.tui or 'pas de TUI'}) : {d.etat}"
                   + (f" -> {quoi}" if quoi else "")
                   + (" ; relance du relais = décision humaine (elle fermerait le TUI)" if d.etat.startswith("relais mort") else ""))
    return out


def worktrees_connus(base: str, n: int, nb: int, tui: Session | None, worktrees: list[tuple[str, str]], depot=est_depot) -> list[str]:
    jetons = {f"{base}{n}", f"{base}-{n}"} | ({base} if nb == 1 else set())
    out = [tui.chemin] if tui and tui.chemin and depot(tui.chemin) else []
    for chemin, branche in worktrees:
        nom, br = Path(chemin).name.lower(), branche.lower()
        if any(re.search(rf"(^|[-_/]){re.escape(j)}($|[-_/])", nom) or br.startswith(j + "/") for j in jetons):
            out.append(chemin)
    return list(dict.fromkeys(out))


def plan_relance(base: str, n: int, sessions: list[Session], processus: list[tuple[int, int, bool]], defauts: dict[str, str],
                 worktrees: list[tuple[str, str]], force: bool, depot=est_depot, sales=non_commites) -> tuple[int, Decision, str]:
    """(code, décision, motif de refus) pour `--relancer base:n`."""
    lanceurs = [s for s in sessions if re.fullmatch(rf"ac-{re.escape(base)}\d*", s.nom)]
    nb = max([n] + [int(s.nom[len(f"ac-{base}"):] or 1) for s in lanceurs])
    d = next(x for x in decider(sessions, processus, [(base, nb)], {}, float("inf")) if x.lanceur == noms(base, n, nb)[0])
    par_nom = {s.nom: s for s in sessions}
    ac, tui = par_nom.get(d.lanceur), par_nom.get(d.tui) if d.tui else None
    d.etat, d.actions = "relance manuelle", []
    if ac is None and tui is None:
        return 2, d, f"ni {d.lanceur} ni TUI de {d.instance} dans tmux"
    connus = worktrees_connus(base, n, nb, tui, worktrees, depot)
    sales_ = [(c, k) for c in connus for k in [sales(c)] if k]
    if not force and sales_:
        return 3, d, "modifications non commitées : " + ", ".join(f"{c} ({k})" for c, k in sales_) + " ; commit WIP, ou --force"
    if not force and not connus:
        return 3, d, "aucun worktree connu pour cette instance : vérifier à la main, puis --force"
    freres = [s.commande for s in lanceurs if s.commande]
    cmd = (ac.commande if ac and ac.commande else "") or (freres[0] if freres else "") or \
          (commande_defaut(base, defauts[base]) if base in defauts else "")
    if not cmd:
        return 2, d, "aucune commande de lancement connue (ni lanceur, ni frère, ni --defaut)"
    if d.relais:
        d.actions.append(("tuer", d.relais))                  # d'abord le relais : sinon il relance le TUI fermé (3 s)
    if tui:
        d.actions.append(("fermer", tui.nom))
    if ac:
        d.actions.append(("fermer", ac.nom))
    d.actions.append(("lancer", d.lanceur, cmd))
    return 0, d, ""


def main(argv: list[str] | None = None, lire=lire_sessions, processus=None, dormir=time.sleep, run=subprocess.run, tuer=os.kill,
         worktrees=None, depot=est_depot, sales=non_commites) -> int:
    ap = argparse.ArgumentParser(description="Gardien multi-instance (" + VERSION + ")")
    ap.add_argument("instances", nargs="*", help="base:nombre, ex. qwencode:4")
    ap.add_argument("--defaut", action="append", default=[], help="base=options, commande de secours sans lanceur connu")
    ap.add_argument("--essai", action="store_true", help="imprime le plan sans rien faire")
    ap.add_argument("--relancer", metavar="BASE:N", help="relance manuelle d'une seule instance, ex. qwencode:3")
    ap.add_argument("--force", action="store_true", help="avec --relancer : passer outre les modifications non commitées")
    a = ap.parse_args(argv)
    defauts = dict(x.split("=", 1) for x in a.defaut)
    lire_ps = processus or VR.lire_processus
    if a.relancer:
        base, n = a.relancer.split(":")
        liste = worktrees if worktrees is not None else lister_worktrees([RACINE, RACINE.parent / "projetcad-repo"])
        code, d, motif = plan_relance(base, int(n), lire(), lire_ps(), defauts, liste, a.force, depot, sales)
        horo = time.strftime("%m-%d %H:%M:%S")
        if code:
            print(f"[{horo}] gardien : relance manuelle de {d.instance} refusée : {motif}")
            return code
        for l in journal([d], a.essai):
            print(l)
        if not a.essai:
            executer([d], run=run, tuer=tuer, dormir=dormir)
        return 0
    if not a.instances:
        ap.error("instances attendues (base:nombre), ou --relancer base:n")
    attendu = [(b, int(n)) for b, n in (x.split(":") for x in a.instances)]
    plan = decider(lire(), lire_ps(), attendu, defauts, time.time())
    if any(d.etat == "relance" for d in plan) and not a.essai:
        dormir(CONFIRMATION)
        plan = confirmer(plan, decider(lire(), lire_ps(), attendu, defauts, time.time()))
    for l in journal(plan, a.essai):
        print(l)
    if not a.essai:
        executer(plan, run=run, tuer=tuer, dormir=dormir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
