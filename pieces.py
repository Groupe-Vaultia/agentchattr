"""Pieces, offres, nomenclature et mouvements (docs/PIECES.md v0.6, lot N1). 13 octobre 2026.

v1 (13 oct. 2026, claude) : base SQLite sur la tour (`data/pieces.db`, hors du depot public).
- Numero `VLT-` + 5 chiffres, non signifiant, attribue ici a partir de VLT-10001 et jamais reutilise (Charles, msg 2337).
- Revision P01, P02… puis A, B, C… sans I O Q S X Z (skill ingenieur-rd-fusion, ASME Y14.35) ; un changement de
  revision ou de statut s'ecrit dans `historique_pieces`, jamais d'ecrasement silencieux.
- Une offre sans `source` est refusee (pas de chiffre externe sans source).
- Nomenclature parent -> enfant x quantite ; un lien qui ferait un cycle est refuse.
- Sauvegarde par l'API backup de sqlite (sure pendant l'ecriture).
- Chaque revision a sa ligne figee dans `revisions_pieces` (revision, fichier, empreinte) : une revision deja
  enregistree ne se reecrit pas et ne revient pas (revue codex, msg 2349).
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

ORIGINES = ("acheter", "concevoir")
TYPES = ("assemblage", "piece", "visserie", "matiere")
PROCEDES = ("", "laser", "soudure", "cnc", "impression_3d", "achat", "autre")
STATUTS = ("a_concevoir", "concue", "a_commander", "commandee", "recue", "fabriquee", "validee", "rejetee")
UNITES = ("u", "m", "kg")
MOUVEMENTS = ("commande", "reception", "fabrication", "rebut", "consommation")
_REVISION = re.compile(r"^(P(0[1-9]|[1-9][0-9])|[A-HJ-NPRTUVWY]{1,2})$")  # P01-P99, puis A… sans I O Q S X Z
PREMIER_NUMERO = 10001

_SCHEMA = """
CREATE TABLE IF NOT EXISTS compteur (nom TEXT PRIMARY KEY, valeur INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pieces (
  id INTEGER PRIMARY KEY, numero TEXT UNIQUE NOT NULL, revision TEXT NOT NULL, nom TEXT NOT NULL,
  origine TEXT NOT NULL, type TEXT NOT NULL, sous_systeme TEXT DEFAULT '', categorie TEXT DEFAULT '',
  matiere TEXT DEFAULT '', procede TEXT DEFAULT '', statut TEXT NOT NULL, masse_g REAL,
  fichier TEXT DEFAULT '', empreinte TEXT DEFAULT '', projet_id TEXT DEFAULT '', tache_id INTEGER,
  cree REAL NOT NULL, maj REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fournisseurs (
  id INTEGER PRIMARY KEY, nom TEXT UNIQUE NOT NULL, site TEXT DEFAULT '', delai_jours INTEGER, note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS offres (
  id INTEGER PRIMARY KEY, piece_id INTEGER NOT NULL REFERENCES pieces(id), fournisseur_id INTEGER REFERENCES fournisseurs(id),
  reference TEXT DEFAULT '', prix REAL NOT NULL, devise TEXT NOT NULL, quantite_min REAL DEFAULT 1,
  livraison REAL, source TEXT NOT NULL, date REAL NOT NULL, par TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS nomenclature (
  parent_id INTEGER NOT NULL REFERENCES pieces(id), enfant_id INTEGER NOT NULL REFERENCES pieces(id),
  quantite REAL NOT NULL, unite TEXT NOT NULL, note TEXT DEFAULT '', PRIMARY KEY (parent_id, enfant_id));
CREATE TABLE IF NOT EXISTS mouvements (
  id INTEGER PRIMARY KEY, piece_id INTEGER NOT NULL REFERENCES pieces(id), quantite REAL NOT NULL, quoi TEXT NOT NULL,
  qui TEXT NOT NULL, date REAL NOT NULL, preuve TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS revisions_pieces (
  piece_id INTEGER NOT NULL REFERENCES pieces(id), revision TEXT NOT NULL, fichier TEXT DEFAULT '',
  empreinte TEXT DEFAULT '', qui TEXT NOT NULL, date REAL NOT NULL, PRIMARY KEY (piece_id, revision));
CREATE TABLE IF NOT EXISTS historique_pieces (
  id INTEGER PRIMARY KEY, piece_id INTEGER NOT NULL REFERENCES pieces(id), champ TEXT NOT NULL,
  avant TEXT, apres TEXT, qui TEXT NOT NULL, date REAL NOT NULL);
"""

_MODIFIABLES = ("nom", "revision", "sous_systeme", "categorie", "matiere", "procede", "statut", "masse_g", "fichier",
                "empreinte", "projet_id", "tache_id", "type", "origine")


class Erreur(ValueError):
    """Refus d'une regle de la spec ; `code` = 400, 404 ou 409 pour la route."""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def _choix(champ: str, valeur, permis) -> str:
    v = "" if valeur is None else str(valeur)
    if v not in permis:
        raise Erreur(f"{champ} parmi {', '.join(p for p in permis if p) or '(vide)'}")
    return v


class PieceStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self._path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ---------- pieces ----------
    def _ligne(self, piece_id: int) -> dict:
        r = self._db.execute("SELECT * FROM pieces WHERE id = ?", (piece_id,)).fetchone()
        if r is None:
            raise Erreur("piece inconnue", 404)
        return dict(r)

    def get(self, piece_id: int) -> dict:
        with self._lock:
            return self._ligne(piece_id)

    def _valider(self, champs: dict, partiel: bool) -> dict:
        inconnus = set(champs) - set(_MODIFIABLES)
        if inconnus:
            raise Erreur(f"champs inconnus : {', '.join(sorted(inconnus))}")
        out = {}
        for c, v in champs.items():
            if c == "origine":
                out[c] = _choix(c, v, ORIGINES)
            elif c == "type":
                out[c] = _choix(c, v, TYPES)
            elif c == "procede":
                out[c] = _choix(c, v, PROCEDES)
            elif c == "statut":
                out[c] = _choix(c, v, STATUTS)
            elif c == "revision":
                if not _REVISION.match(str(v)):
                    raise Erreur("revision : P01 a P99, puis A, B, C… (sans I, O, Q, S, X, Z)")
                out[c] = str(v)
            elif c == "masse_g":
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
                    raise Erreur("masse_g : nombre positif")
                out[c] = v
            elif c == "tache_id":
                if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
                    raise Erreur("tache_id : entier")
                out[c] = v
            else:
                out[c] = str(v).strip()
        if not partiel and not out.get("nom"):
            raise Erreur("nom requis")
        return out

    def creer(self, champs: dict, qui: str) -> dict:
        c = self._valider(champs, partiel=False)
        c.setdefault("origine", "concevoir")
        c.setdefault("type", "piece")
        c.setdefault("revision", "P01")
        c.setdefault("statut", "a_commander" if c["origine"] == "acheter" else "a_concevoir")
        with self._lock:
            n = self._db.execute("SELECT valeur FROM compteur WHERE nom = 'piece'").fetchone()
            suivant = n["valeur"] + 1 if n else PREMIER_NUMERO
            self._db.execute("INSERT OR REPLACE INTO compteur (nom, valeur) VALUES ('piece', ?)", (suivant,))
            t = time.time()
            c.update(numero=f"VLT-{suivant}", cree=t, maj=t)
            cols = ", ".join(c)
            cur = self._db.execute(f"INSERT INTO pieces ({cols}) VALUES ({', '.join('?' * len(c))})", list(c.values()))
            self._db.execute("INSERT INTO historique_pieces (piece_id, champ, avant, apres, qui, date) "
                             "VALUES (?, 'creation', NULL, ?, ?, ?)", (cur.lastrowid, c["numero"], qui, t))
            self._db.execute("INSERT INTO revisions_pieces (piece_id, revision, fichier, empreinte, qui, date) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (cur.lastrowid, c["revision"], c.get("fichier", ""),
                                                           c.get("empreinte", ""), qui, t))
            self._db.commit()
            return self._ligne(cur.lastrowid)

    def modifier(self, piece_id: int, champs: dict, qui: str, tache_faite=None) -> dict:
        """`tache_faite(tache_id) -> bool` : une piece `validee` exige une tache faite (preuve d'essai)."""
        c = self._valider(champs, partiel=True)
        with self._lock:
            avant = self._ligne(piece_id)
            if c.get("statut") == "validee":
                tid = c.get("tache_id", avant["tache_id"])
                if tid is None or tache_faite is None or not tache_faite(tid):
                    raise Erreur("validee exige une tache faite (preuve d'essai) rattachee a la piece")
            nouvelle_rev = "revision" in c and c["revision"] != avant["revision"]
            if nouvelle_rev:
                if self._db.execute("SELECT 1 FROM revisions_pieces WHERE piece_id = ? AND revision = ?",
                                    (piece_id, c["revision"])).fetchone():
                    raise Erreur(f"la revision {c['revision']} existe deja : une revision figee ne revient pas", 409)
                if "fichier" not in c and avant["fichier"]:
                    raise Erreur("nouvelle revision = nouveau fichier : donne aussi `fichier` (l'ancien reste)")
            elif ("fichier" in c and c["fichier"] != avant["fichier"]) or ("empreinte" in c and c["empreinte"] != avant["empreinte"]):
                if avant["fichier"]:
                    raise Erreur("le fichier d'une revision est fige : change de revision pour changer de fichier", 409)
            t = time.time()
            for k, v in c.items():
                if v != avant[k]:
                    self._db.execute("INSERT INTO historique_pieces (piece_id, champ, avant, apres, qui, date) "
                                     "VALUES (?, ?, ?, ?, ?, ?)", (piece_id, k, None if avant[k] is None else str(avant[k]),
                                                                   None if v is None else str(v), qui, t))
            if nouvelle_rev:
                self._db.execute("INSERT INTO revisions_pieces (piece_id, revision, fichier, empreinte, qui, date) "
                                 "VALUES (?, ?, ?, ?, ?, ?)", (piece_id, c["revision"], c.get("fichier", avant["fichier"]),
                                                               c.get("empreinte", ""), qui, t))
            elif "fichier" in c or "empreinte" in c:  # premier fichier de la revision courante
                self._db.execute("UPDATE revisions_pieces SET fichier = ?, empreinte = ? WHERE piece_id = ? AND revision = ?",
                                 (c.get("fichier", avant["fichier"]), c.get("empreinte", avant["empreinte"]), piece_id,
                                  avant["revision"]))
            if c:
                c["maj"] = t
                self._db.execute(f"UPDATE pieces SET {', '.join(f'{k} = ?' for k in c)} WHERE id = ?",
                                 [*c.values(), piece_id])
                self._db.commit()
            return self._ligne(piece_id)

    def lister(self, projet_id: str = "", statut: str = "", q: str = "") -> list[dict]:
        sql, args = "SELECT * FROM pieces WHERE 1=1", []
        if projet_id:
            sql += " AND projet_id = ?"; args.append(projet_id)
        if statut:
            sql += " AND statut = ?"; args.append(statut)
        if q:
            sql += " AND (numero LIKE ? OR nom LIKE ? OR categorie LIKE ? OR sous_systeme LIKE ?)"
            args += [f"%{q}%"] * 4
        with self._lock:
            return [dict(r) for r in self._db.execute(sql + " ORDER BY numero", args)]

    def revisions(self, piece_id: int) -> list[dict]:
        with self._lock:
            self._ligne(piece_id)
            return [dict(r) for r in self._db.execute(
                "SELECT revision, fichier, empreinte, qui, date FROM revisions_pieces WHERE piece_id = ? ORDER BY date",
                (piece_id,))]

    def historique(self, piece_id: int) -> list[dict]:
        with self._lock:
            self._ligne(piece_id)
            return [dict(r) for r in self._db.execute(
                "SELECT champ, avant, apres, qui, date FROM historique_pieces WHERE piece_id = ? ORDER BY date, id",
                (piece_id,))]

    # ---------- fournisseurs et offres ----------
    def fournisseur(self, nom: str, site: str = "", delai_jours=None, note: str = "") -> dict:
        nom = str(nom).strip()
        if not nom:
            raise Erreur("nom de fournisseur requis")
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO fournisseurs (nom, site, delai_jours, note) VALUES (?, ?, ?, ?)",
                             (nom, site, delai_jours, note))
            self._db.commit()
            return dict(self._db.execute("SELECT * FROM fournisseurs WHERE nom = ?", (nom,)).fetchone())

    def ajouter_offre(self, piece_id: int, champs: dict, qui: str) -> dict:
        source = str(champs.get("source", "")).strip()
        if not source:
            raise Erreur("source obligatoire (URL ou devis) : pas de prix sans source")
        prix = champs.get("prix")
        if isinstance(prix, bool) or not isinstance(prix, (int, float)) or prix < 0:
            raise Erreur("prix : nombre positif")
        devise = str(champs.get("devise", "CAD")).upper()
        if not re.fullmatch(r"[A-Z]{3}", devise):
            raise Erreur("devise : code a 3 lettres (CAD, USD…)")
        livraison = champs.get("livraison")
        if livraison is not None and (isinstance(livraison, bool) or not isinstance(livraison, (int, float)) or livraison < 0):
            raise Erreur("livraison : nombre positif")
        fid = None
        if champs.get("fournisseur"):
            fid = self.fournisseur(str(champs["fournisseur"]))["id"]
        with self._lock:
            self._ligne(piece_id)
            cur = self._db.execute(
                "INSERT INTO offres (piece_id, fournisseur_id, reference, prix, devise, quantite_min, livraison, source, date, par) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (piece_id, fid, str(champs.get("reference", "")), float(prix), devise,
                 float(champs.get("quantite_min") or 1), livraison, source, time.time(), qui))
            self._db.commit()
            return dict(self._db.execute("SELECT * FROM offres WHERE id = ?", (cur.lastrowid,)).fetchone())

    def offres(self, piece_id: int) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(
                "SELECT o.*, f.nom AS fournisseur FROM offres o LEFT JOIN fournisseurs f ON f.id = o.fournisseur_id "
                "WHERE o.piece_id = ? ORDER BY o.prix", (piece_id,))]

    # ---------- nomenclature ----------
    def _enfants(self, parent_id: int) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM nomenclature WHERE parent_id = ?", (parent_id,)).fetchall()

    def _descendants(self, piece_id: int) -> set[int]:
        vus, pile = set(), [piece_id]
        while pile:
            for r in self._enfants(pile.pop()):
                if r["enfant_id"] not in vus:
                    vus.add(r["enfant_id"])
                    pile.append(r["enfant_id"])
        return vus

    def lier(self, parent_id: int, enfant_id: int, quantite, unite: str = "u", note: str = "") -> dict:
        if isinstance(quantite, bool) or not isinstance(quantite, (int, float)) or quantite <= 0:
            raise Erreur("quantite : nombre > 0")
        unite = _choix("unite", unite, UNITES)
        with self._lock:
            parent, _ = self._ligne(parent_id), self._ligne(enfant_id)
            if parent_id == enfant_id or parent_id in self._descendants(enfant_id):
                raise Erreur("ce lien ferait un cycle dans la nomenclature", 409)
            if parent["type"] != "assemblage":
                raise Erreur("seul un assemblage a des enfants")
            self._db.execute("INSERT OR REPLACE INTO nomenclature (parent_id, enfant_id, quantite, unite, note) "
                             "VALUES (?, ?, ?, ?, ?)", (parent_id, enfant_id, float(quantite), unite, note))
            self._db.commit()
            return {"parent_id": parent_id, "enfant_id": enfant_id, "quantite": float(quantite), "unite": unite}

    def delier(self, parent_id: int, enfant_id: int) -> bool:
        with self._lock:
            n = self._db.execute("DELETE FROM nomenclature WHERE parent_id = ? AND enfant_id = ?",
                                 (parent_id, enfant_id)).rowcount
            self._db.commit()
            return n > 0

    def arbre(self, piece_id: int) -> dict:
        """Champs de la piece + `quantite` (par parent), `quantite_cumulee` (depuis la racine), `unite`, `enfants`."""
        with self._lock:
            def noeud(pid: int, qte: float, cumul: float, unite: str) -> dict:
                return {**self._ligne(pid), "quantite": qte, "quantite_cumulee": cumul, "unite": unite,
                        "enfants": [noeud(r["enfant_id"], r["quantite"], cumul * r["quantite"], r["unite"])
                                    for r in self._enfants(pid)]}
            return noeud(piece_id, 1.0, 1.0, "u")

    # ---------- achats et cout ----------
    def _racines(self, projet_id: str) -> list[int]:
        return [r["id"] for r in self._db.execute(
            "SELECT id FROM pieces WHERE projet_id = ? AND id NOT IN (SELECT enfant_id FROM nomenclature)", (projet_id,))]

    def _besoins(self, projet_id: str) -> dict[int, float]:
        """Quantites cumulees des feuilles achetees, sur toutes les racines du projet."""
        besoins: dict[int, float] = {}

        def descendre(pid: int, qte: float):
            enfants = self._enfants(pid)
            p = self._ligne(pid)
            if p["origine"] == "acheter" and not enfants:
                besoins[pid] = besoins.get(pid, 0.0) + qte
            for r in enfants:
                descendre(r["enfant_id"], qte * r["quantite"])

        for racine in self._racines(projet_id):
            descendre(racine, 1.0)
        return besoins

    def achats(self, projet_id: str) -> dict:
        with self._lock:
            lignes, sans_offre, totaux = [], [], {}
            for pid, qte in sorted(self._besoins(projet_id).items()):
                p = self._ligne(pid)
                offres = [dict(r) for r in self._db.execute(
                    "SELECT o.*, f.nom AS fournisseur FROM offres o LEFT JOIN fournisseurs f ON f.id = o.fournisseur_id "
                    "WHERE o.piece_id = ?", (pid,))]
                if not offres:
                    sans_offre.append({"piece_id": pid, "numero": p["numero"], "nom": p["nom"], "quantite": qte})
                    continue
                def total(o):
                    return max(qte, o["quantite_min"]) * o["prix"] + (o["livraison"] or 0)
                # Pas de conversion de devise inventee : on compare en CAD si une offre CAD existe ; sinon dans une
                # seule devise, et la ligne le signale (`a_convertir`) pour que claude source le taux.
                devises = {o["devise"] for o in offres}
                d = "CAD" if "CAD" in devises else sorted(devises)[0]
                meilleure = min((o for o in offres if o["devise"] == d), key=total)
                t = round(total(meilleure), 2)
                totaux[meilleure["devise"]] = round(totaux.get(meilleure["devise"], 0) + t, 2)
                lignes.append({"piece_id": pid, "numero": p["numero"], "nom": p["nom"], "quantite": qte,
                               "offre": meilleure, "total": t, "nb_offres": len(offres),
                               "a_convertir": len(devises) > 1 or d != "CAD",
                               "age_jours": round((time.time() - meilleure["date"]) / 86400, 1)})
            return {"lignes": lignes, "sans_offre": sans_offre, "totaux": totaux}

    # ---------- mouvements ----------
    def mouvement(self, piece_id: int, quantite, quoi: str, qui: str, preuve: str = "") -> dict:
        quoi = _choix("quoi", quoi, MOUVEMENTS)
        if isinstance(quantite, bool) or not isinstance(quantite, (int, float)) or quantite == 0:
            raise Erreur("quantite : nombre non nul (+ recu, - consomme)")
        with self._lock:
            self._ligne(piece_id)
            cur = self._db.execute("INSERT INTO mouvements (piece_id, quantite, quoi, qui, date, preuve) "
                                   "VALUES (?, ?, ?, ?, ?, ?)", (piece_id, float(quantite), quoi, qui, time.time(), preuve))
            self._db.commit()
            return dict(self._db.execute("SELECT * FROM mouvements WHERE id = ?", (cur.lastrowid,)).fetchone())

    def stock(self, piece_id: int) -> float:
        with self._lock:
            self._ligne(piece_id)
            r = self._db.execute("SELECT COALESCE(SUM(quantite), 0) AS s FROM mouvements WHERE piece_id = ? "
                                 "AND quoi IN ('reception', 'fabrication', 'rebut', 'consommation')", (piece_id,)).fetchone()
            return r["s"]

    # ---------- sauvegarde ----------
    def sauvegarder(self, dossier: str, garder_jours: int = 30) -> Path:
        d = Path(dossier)
        d.mkdir(parents=True, exist_ok=True)
        cible = d / f"pieces-{time.strftime('%Y-%m-%d')}.db"
        with self._lock:
            dest = sqlite3.connect(str(cible))
            try:
                self._db.backup(dest)
            finally:
                dest.close()
        limite = time.time() - garder_jours * 86400
        for f in d.glob("pieces-*.db"):
            if f.stat().st_mtime < limite:
                f.unlink()
        return cible
