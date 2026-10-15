#!/usr/bin/env python3
"""Backfill des livrables structures (SOCLE-SHOP S5 v2, PR assoc-livrables, 14 oct. 2026).

Applique a TOUTES les taches deja « fait » la meme logique que la completion d'une tache
(`revisions.associer_livrables_tache`) : depuis la `preuve` en texte libre, enregistre une fiche de livrable
structuree reliee a {projet, tache} et, si le mapping piece est net, rattache un dessin a la piece.

Securite d'usage :
- `--dry-run` est le DEFAUT : rien n'est ecrit nulle part. Le dossier data passe en argument n'est jamais
  touche en dry-run (jobs.json et pieces.db sont seulement lus ; une COPIE jetable sert au calcul).
- `--ecrire` ecrit pour de vrai (revisions.json cree/complete, pieces.db modifie). A lancer par Charles,
  jamais automatiquement : c'est une migration de donnees reelles.
- Idempotent : relancer ne duplique pas (dedup du RevisionStore ; une piece deja dotee d'un fichier est laissee).

Exemples :
    python3 outils-socle/backfill_livrables.py data                      # dry-run, tous les projets
    python3 outils-socle/backfill_livrables.py data --projet quad        # dry-run, projet quad
    python3 outils-socle/backfill_livrables.py data --projet quad --ecrire
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import revisions as _revisions_mod            # noqa: E402
from revisions import RevisionStore           # noqa: E402
from pieces import PieceStore                 # noqa: E402


def _taches_faites(data_dir: Path, projet: str) -> list[dict]:
    """Lit jobs.json en SEULE lecture (aucune ecriture, pas de JobStore) et rend les taches « fait »."""
    brut = json.loads((data_dir / "jobs.json").read_text("utf-8"))
    taches = [t for t in brut if isinstance(t, dict) and t.get("projet_id") and t.get("etat") == "fait"]
    if projet:
        taches = [t for t in taches if t.get("projet_id") == projet]
    return sorted(taches, key=lambda t: t.get("id", 0))


def _stores(data_dir: Path, racine: str, ecrire: bool):
    """Rend (store_revisions, store_pieces, dossier_jetable|None).
    En dry-run, les stores pointent sur une COPIE jetable : le data_dir reel n'est jamais ecrit."""
    if ecrire:
        rev = RevisionStore(str(data_dir / "revisions.json"), racine)
        pieces = PieceStore(str(data_dir / "pieces.db")) if (data_dir / "pieces.db").exists() else None
        return rev, pieces, None
    tmp = Path(tempfile.mkdtemp(prefix="backfill-dry-"))
    src_rev = data_dir / "revisions.json"
    dst_rev = tmp / "revisions.json"
    if src_rev.exists():
        shutil.copy2(src_rev, dst_rev)
    rev = RevisionStore(str(dst_rev), racine)
    pieces = None
    if (data_dir / "pieces.db").exists():
        shutil.copy2(data_dir / "pieces.db", tmp / "pieces.db")
        pieces = PieceStore(str(tmp / "pieces.db"))
    return rev, pieces, tmp


def backfill(data_dir: Path, racine: str, projet: str, ecrire: bool) -> dict:
    taches = _taches_faites(data_dir, projet)
    rev, pieces, jetable = _stores(data_dir, racine, ecrire)
    try:
        resultats = [_revisions_mod.associer_livrables_tache(t, rev, pieces, qui="backfill") for t in taches]
    finally:
        if jetable is not None:
            shutil.rmtree(jetable, ignore_errors=True)
    return {"taches": taches, "resultats": resultats}


def _rapport(sortie: dict, ecrire: bool) -> None:
    taches, resultats = sortie["taches"], sortie["resultats"]
    n_present = n_introuvable = n_sans = n_piece = 0
    mode = "ECRITURE" if ecrire else "DRY-RUN (aucune ecriture)"
    print(f"=== Backfill livrables — {mode} — {len(taches)} tache(s) « fait » ===\n")
    for t, cr in zip(taches, resultats):
        livrables = cr.get("livrables", [])
        if not livrables:
            n_sans += 1
        print(f"[tache {t.get('id')}] {t.get('etape')} / {t.get('responsable')} : {t.get('titre')}")
        if not livrables and not cr.get("erreurs"):
            print("    (aucun chemin de fichier dans la preuve — rien a enregistrer)")
        for l in livrables:
            if l["statut"] == "present":
                n_present += 1
            else:
                n_introuvable += 1
            v = f" {l['version_doc']}" if l.get("version_doc") else ""
            c = f" commit {l['commit']}" if l.get("commit") else ""
            print(f"    - {l['statut']:11s} {l['chemin']}{v}{c} (v{l['version']})")
        for e in cr.get("erreurs", []):
            print(f"    ! refus : {e}")
        p = cr.get("piece")
        if p:
            n_piece += 1
            print(f"    -> piece {p.get('numero')} : {p.get('action')} ({p.get('origine')})"
                  + (f" fichier {p.get('fichier')}" if p.get("fichier") else ""))
    print(f"\nResume : {n_present} livrable(s) present(s), {n_introuvable} introuvable(s), "
          f"{n_sans} tache(s) sans chemin, {n_piece} piece(s) rattachee(s).")
    if not ecrire:
        print("Dry-run : relancer avec --ecrire (par Charles) pour appliquer sur le data reel.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill des livrables structures depuis la preuve des taches faites.")
    ap.add_argument("data_dir", help="dossier data (contient jobs.json, pieces.db, revisions.json)")
    ap.add_argument("--racine", default=str(Path.home() / "atelier"),
                    help="racine des livrables (defaut ~/atelier)")
    ap.add_argument("--projet", default="", help="limiter a un projet (ex. quad)")
    ap.add_argument("--ecrire", action="store_true",
                    help="ecrire pour de vrai (defaut : dry-run). A lancer par Charles sur le data reel.")
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir).expanduser()
    if not (data_dir / "jobs.json").exists():
        print(f"jobs.json introuvable sous {data_dir}", file=sys.stderr)
        return 2
    sortie = backfill(data_dir, str(Path(args.racine).expanduser()), args.projet, args.ecrire)
    _rapport(sortie, args.ecrire)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
