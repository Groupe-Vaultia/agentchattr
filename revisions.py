"""Livrables et revisions figees par empreintes (SOCLE-SHOP.md S5). 12 octobre 2026.

v1 (12 oct. 2026, claude ; lot reassigne de gemini, dont le lanceur a plante, msg 2118) : contrat de FICHES-LOTS.md v0.1.
- Un livrable est un fichier sous `racine`, identifie par (projet_id, chemin), avec son sha256 et une version.
- « Approuver » relit les octets presents A CET INSTANT, enregistre une nouvelle version si le fichier a change, puis
  fige ces empreintes dans la revision P01, P02… Une revision figee n'est jamais modifiee (critere de codex, msg 2107).
- Un chemin absolu, ou qui sort de la racine une fois resolu (« .. », lien symbolique), est refuse.

v2 (14 oct. 2026, claude, PR assoc-livrables) : a la completion d'une tache, sa `preuve` en texte libre est DOUBLEE
d'une fiche de livrable structuree, reliee a {projet, tache, piece}. Nouveaux champs d'un livrable :
`statut` (« present » ou « introuvable » — un fichier cite mais absent laisse un trou VISIBLE, pas silencieux),
`commit`, `version_doc` (la version citee « v1.2 », a ne pas confondre avec `version`, le compteur interne), `qui`.
Le parsing de la preuve est une passerelle de depannage ; a terme les agents enregistrent un livrable directement.
"""

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path


def _sha256(fichier: Path) -> str:
    h = hashlib.sha256()
    with open(fichier, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# ---- Extraction d'un livrable depuis une `preuve` en texte libre (passerelle de depannage) ----------------------
# Extensions reconnues comme un livrable qu'on suit (documents + CAO). `.py` et autres outils sont volontairement exclus.
EXTENSIONS_LIVRABLE = ("md", "markdown", "txt", "rst", "csv", "json", "yaml", "yml",
                       "png", "jpg", "jpeg", "svg", "pdf",
                       "step", "stp", "stl", "fcstd", "dxf", "dwg", "iges", "igs", "3mf")
# Un dessin / modele CAO rattachable a une piece.
EXTENSIONS_DESSIN = (".fcstd", ".step", ".stp", ".stl", ".dxf", ".dwg", ".iges", ".igs", ".3mf", ".pdf")

# Un chemin = au moins un dossier puis un fichier a extension connue. Facultativement precede de `~/` ou `/`.
# Le regard arriere evite de couper un chemin au milieu d'un mot.
_RE_CHEMIN = re.compile(
    r"(?<![\w/.~])(~?/?(?:[\w.\-]+/)+[\w.\-]+\.(?:" + "|".join(EXTENSIONS_LIVRABLE) + r"))",
    re.IGNORECASE)
_RE_COMMIT_EXPLICITE = re.compile(r"\bcommit\s+([0-9a-f]{7,40})\b", re.IGNORECASE)
_RE_COMMIT_CROCHET = re.compile(r"\[([0-9a-f]{7,40})\]", re.IGNORECASE)
# Un hash « nu » (dans une parenthese, ex. « (426b2e9, cad-gemini) ») : 7 a 40 hex contenant au moins un chiffre
# (pour ne pas confondre avec un mot anglais purement alphabetique comme « defaced »).
_RE_COMMIT_NU = re.compile(r"(?<![\w/])(?=[0-9a-f]{7,40}(?![\w]))[0-9a-f]*\d[0-9a-f]*", re.IGNORECASE)
_RE_VERSION = re.compile(r"\bv(\d+(?:\.\d+)+)\b", re.IGNORECASE)  # v1.2, v1.6 ; exige au moins un point
_RE_VLT = re.compile(r"\bVLT-(\d{4,6})\b", re.IGNORECASE)


def extraire_chemins(preuve: str) -> list[str]:
    """Tous les chemins de fichier cites, dans l'ordre, sans doublon."""
    vus, out = set(), []
    for m in _RE_CHEMIN.finditer(preuve or ""):
        c = m.group(1)
        if c not in vus:
            vus.add(c)
            out.append(c)
    return out


def extraire_commit(preuve: str) -> str:
    """Le premier commit cite : « commit <hash> », « [hash] », puis un hash nu. '' si aucun."""
    for rx in (_RE_COMMIT_EXPLICITE, _RE_COMMIT_CROCHET):
        m = rx.search(preuve or "")
        if m:
            return m.group(1).lower()
    m = _RE_COMMIT_NU.search(preuve or "")
    return m.group(0).lower() if m else ""


def extraire_version(preuve: str) -> str:
    """La premiere version citee « v1.2 » (telle quelle, avec le v), '' si aucune."""
    m = _RE_VERSION.search(preuve or "")
    return f"v{m.group(1)}" if m else ""


def extraire_numeros_piece(texte: str) -> set[str]:
    """Les numeros de piece « VLT-xxxxx » cites."""
    return {f"VLT-{m}" for m in _RE_VLT.findall(texte or "")}


def extraire_livrables(preuve: str) -> list[dict]:
    """Depuis une preuve : une fiche {chemin, commit, version_doc} par chemin cite.
    Le commit et la version du texte sont rattaches a tous les chemins de la meme preuve (voir la note v2 :
    le texte libre ne dit pas quel commit va avec quel fichier ; c'est pourquoi les agents devront, a terme,
    enregistrer un livrable structure directement)."""
    commit = extraire_commit(preuve)
    version = extraire_version(preuve)
    return [{"chemin": c, "commit": commit, "version_doc": version} for c in extraire_chemins(preuve)]


class RevisionStore:
    def __init__(self, path: str, racine: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._racine = Path(racine).resolve()
        self._lock = threading.Lock()
        self._etat = {"livrables": [], "revisions": []}
        if self._path.exists():
            raw = json.loads(self._path.read_text("utf-8"))  # illisible = ValueError, jamais d'effacement
            if not isinstance(raw, dict) or not isinstance(raw.get("livrables"), list) \
                    or not isinstance(raw.get("revisions"), list):
                raise ValueError(f"{self._path} : forme inattendue")
            self._etat = raw

    def _sauver(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._etat, ensure_ascii=False), "utf-8")
        os.replace(tmp, self._path)

    def _fichier(self, chemin: str) -> Path:
        if not chemin or Path(chemin).is_absolute():
            raise ValueError(f"chemin relatif a la racine attendu : {chemin!r}")
        f = (self._racine / chemin).resolve()
        if not f.is_relative_to(self._racine):
            raise ValueError(f"chemin hors de la racine : {chemin!r}")
        return f

    def _derniere(self, projet_id: str, chemin: str) -> dict | None:
        versions = [l for l in self._etat["livrables"] if l["projet_id"] == projet_id and l["chemin"] == chemin]
        return max(versions, key=lambda l: l["version"]) if versions else None

    def _enregistrer(self, projet_id: str, tache_id: str, chemin: str, empreinte: str, t: float,
                     *, statut: str = "present", commit: str = "", version_doc: str = "", qui: str = "") -> dict:
        """Sous _lock. Idempotent : memes empreinte, statut et commit que la derniere version = l'existant ;
        sinon version + 1. Un fichier absent se note `statut='introuvable'` avec une empreinte vide."""
        der = self._derniere(projet_id, chemin)
        if der and der.get("empreinte", "") == empreinte \
                and der.get("statut", "present") == statut and der.get("commit", "") == commit:
            return der
        l = {"id": f"{projet_id}:{chemin}:v{(der['version'] + 1) if der else 1}", "projet_id": projet_id,
             "tache_id": str(tache_id) if tache_id is not None else (der or {}).get("tache_id", ""),
             "chemin": chemin, "empreinte": empreinte, "version": (der["version"] + 1) if der else 1, "heure": t,
             "statut": statut, "commit": commit, "version_doc": version_doc, "qui": qui}
        self._etat["livrables"].append(l)
        return l

    def ajouter_livrable(self, projet_id: str, tache_id: str, chemin: str) -> dict:
        f = self._fichier(chemin)
        if not f.is_file():
            raise FileNotFoundError(chemin)
        empreinte = _sha256(f)
        with self._lock:
            l = self._enregistrer(projet_id, tache_id, chemin, empreinte, time.time())
            self._sauver()
            return dict(l)

    def _vers_relatif(self, chemin: str) -> str:
        """Normalise un chemin cite en texte libre vers un chemin relatif a la racine.
        Un `~` ou un chemin absolu SOUS la racine devient relatif ; hors racine, c'est refuse (securite)."""
        brut = os.path.expanduser(str(chemin).strip())
        if not brut:
            raise ValueError("chemin vide")
        p = Path(brut)
        if p.is_absolute():
            resolu = p.resolve()
            if not resolu.is_relative_to(self._racine):
                raise ValueError(f"chemin hors de la racine : {chemin!r}")
            return str(resolu.relative_to(self._racine))
        return brut

    def enregistrer_livrable(self, projet_id: str, tache_id, chemin: str,
                             *, commit: str = "", version_doc: str = "", qui: str = "") -> dict:
        """Enregistre une fiche de livrable depuis une preuve (v2). Tolere un fichier absent : la fiche est
        alors `introuvable` (le trou reste visible). Idempotent. Rend la fiche. Leve ValueError sur un chemin
        hors racine / « .. » / lien symbolique (garde-fou identique au reste du module)."""
        chemin_rel = self._vers_relatif(chemin)   # ValueError si absolu hors racine
        f = self._fichier(chemin_rel)              # ValueError si .. / lien symbolique / absolu
        present = f.is_file()
        empreinte = _sha256(f) if present else ""
        statut = "present" if present else "introuvable"
        with self._lock:
            l = self._enregistrer(projet_id, tache_id, chemin_rel, empreinte, time.time(),
                                  statut=statut, commit=str(commit or ""), version_doc=str(version_doc or ""),
                                  qui=str(qui or ""))
            self._sauver()
            return dict(l)

    def livrables(self, projet_id: str) -> list[dict]:
        with self._lock:
            chemins = sorted({l["chemin"] for l in self._etat["livrables"] if l["projet_id"] == projet_id})
            return [dict(self._derniere(projet_id, c)) for c in chemins]

    def approuver(self, projet_id: str, approuvee_par: str) -> dict:
        with self._lock:
            chemins = sorted({l["chemin"] for l in self._etat["livrables"] if l["projet_id"] == projet_id})
            if not chemins:
                raise ValueError(f"aucun livrable pour {projet_id}")
            t = time.time()
            figes = []
            for c in chemins:
                f = self._fichier(c)
                if not f.is_file():
                    raise FileNotFoundError(c)  # on ne fige pas un livrable disparu
                l = self._enregistrer(projet_id, None, c, _sha256(f), t)
                figes.append({"chemin": c, "empreinte": l["empreinte"], "version": l["version"]})
            n = sum(1 for r in self._etat["revisions"] if r["projet_id"] == projet_id) + 1
            r = {"projet_id": projet_id, "numero": f"P{n:02d}", "livrables": figes,
                 "approuvee_par": approuvee_par, "heure": t}
            self._etat["revisions"].append(r)
            self._sauver()
            return json.loads(json.dumps(r))

    def revisions(self, projet_id: str) -> list[dict]:
        with self._lock:
            return [json.loads(json.dumps(r)) for r in self._etat["revisions"] if r["projet_id"] == projet_id]

    def verifier(self, projet_id: str, numero: str) -> list[dict]:
        with self._lock:
            r = next((r for r in self._etat["revisions"]
                      if r["projet_id"] == projet_id and r["numero"] == numero), None)
            if r is None:
                raise KeyError(numero)
            out = []
            for l in r["livrables"]:
                f = self._fichier(l["chemin"])
                actuelle = _sha256(f) if f.is_file() else None
                out.append({"chemin": l["chemin"], "empreinte_figee": l["empreinte"],
                            "empreinte_actuelle": actuelle, "intact": actuelle == l["empreinte"]})
            return out


# ---- Rattachement a la completion d'une tache (v2) -----------------------------------------------------------
# Ces fonctions n'importent ni app.py ni pieces.py : le store des pieces est passe en argument (duck-typing),
# pour garder ce module sans dependance vers le reste du socle. Elles ne levent jamais : elles rendent un
# compte-rendu, pour que la transition de tache reussisse meme si l'enregistrement du livrable echoue.

def _rattacher_piece(tache: dict, preuve: str, fiches: list[dict], store_pieces, qui: str) -> dict | None:
    """Rattache un dessin a une piece SI le mapping est net (une seule piece candidate) et qu'un dessin present
    existe. Sinon rend None et ne touche a aucune piece. Idempotent (une piece deja dotee d'un fichier n'est pas
    retouchee)."""
    dessins = [f for f in fiches if f.get("statut") == "present"
               and Path(f["chemin"]).suffix.lower() in EXTENSIONS_DESSIN]
    if not dessins:
        return None
    projet_id = tache.get("projet_id") or ""
    toutes = store_pieces.lister(projet_id)
    origine = "tache_id"
    candidates = [p for p in toutes if p.get("tache_id") == tache.get("id")]
    if not candidates:
        numeros = extraire_numeros_piece(preuve) | extraire_numeros_piece(str(tache.get("titre") or ""))
        if len(numeros) == 1:
            num = next(iter(numeros))
            candidates = [p for p in toutes if str(p.get("numero")) == num]
            origine = "numero"
    if len(candidates) != 1:
        return None  # mapping pas net : on ne touche pas la piece
    piece = candidates[0]
    if str(piece.get("fichier") or "").strip():
        return {"piece_id": piece["id"], "numero": piece.get("numero"), "origine": origine,
                "action": "deja_rattachee", "fichier": piece.get("fichier")}
    dessin = dessins[0]
    maj = store_pieces.modifier(piece["id"], {"fichier": dessin["chemin"], "empreinte": dessin["empreinte"]}, qui)
    return {"piece_id": piece["id"], "numero": maj.get("numero"), "origine": origine, "action": "rattachee",
            "fichier": dessin["chemin"], "revision": maj.get("revision")}


def associer_livrables_tache(tache: dict, store_revisions, store_pieces=None, *, qui: str = "socle") -> dict:
    """A la completion d'une tache (etat « fait »), DOUBLE sa `preuve` d'une ou plusieurs fiches de livrable
    structurees (RevisionStore), reliees a {projet, tache}. Rattache un dessin a la piece si le mapping est net.
    Ne leve jamais ; rend un compte-rendu {tache_id, projet_id, livrables[], piece, erreurs[]}."""
    cr = {"tache_id": tache.get("id"), "projet_id": tache.get("projet_id"),
          "livrables": [], "piece": None, "erreurs": []}
    projet_id = tache.get("projet_id")
    preuve = str(tache.get("preuve") or "")
    if not projet_id or store_revisions is None:
        return cr
    fiches = []
    for spec in extraire_livrables(preuve):
        try:
            l = store_revisions.enregistrer_livrable(
                projet_id, tache.get("id"), spec["chemin"],
                commit=spec["commit"], version_doc=spec["version_doc"], qui=qui)
            fiches.append(l)
            cr["livrables"].append({"chemin": l["chemin"], "statut": l["statut"], "version": l["version"],
                                    "commit": l["commit"], "version_doc": l["version_doc"]})
        except ValueError as err:   # chemin hors racine / .. / lien symbolique : refuse, signale, continue
            cr["erreurs"].append({"chemin": spec["chemin"], "erreur": str(err)})
    if store_pieces is not None and fiches:
        try:
            cr["piece"] = _rattacher_piece(tache, preuve, fiches, store_pieces, qui)
        except Exception as err:    # une piece figee, une regle refusee : on ne bloque pas la tache
            cr["erreurs"].append({"piece": str(err)})
    return cr
