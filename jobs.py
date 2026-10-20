"""Job store — bounded work conversations with threaded messages.

v2 (12 oct. 2026, socle de la Shop, SOCLE-SHOP.md S2) : un job peut etre une **tache** d'un projet :
`projet_id`, `etape` (pilote-rd 1-8), `etat`, un seul `responsable`, une `equipe` avec roles, `critere`, `preuve`,
et pour les essais les champs RS&DE. Un job sans `projet_id` reste un job « sans projet » (anciens jobs).

v3 (13 oct. 2026, claude, SOCLE-SHOP v1.0) : la conversation d'une tache est le canal `tache-<id>`.

v4 (20 oct. 2026, claude, salle sobre lot 1) : la tache devient la memoire de travail, pas le fil. Champs
`prochaine_action` et `derniere_erreur` (texte court, ecrasable); journal `decisions` en ajout seul (`noter_decision`,
jamais par `update_tache`); `fiche()` rend l'etat d'une tache en taille bornee, quel que soit le nombre de messages.
"""

import json
import re
import time
import threading
import uuid
from pathlib import Path


ETAPES = ("probleme", "etat_art", "concepts", "design_initial", "conception", "prototype", "essais",
          "industrialisation", "lancement")
ETATS = ("a_faire", "en_cours", "attend_charles", "bloque", "fait")
ROLES = ("producteur", "verificateur", "relecteur", "proposant")
CHAMPS_ESSAI = ("incertitude", "hypothese", "methode", "critere")  # avant la 1re execution (RS&DE)
_CANAL_TACHE = re.compile(r"^tache-([1-9][0-9]{0,13})$")


def canal_tache(tache_id: int) -> str:
    """Le canal de la salle ou l'on discute d'une tache (20 caracteres au plus, regle des canaux)."""
    return f"tache-{int(tache_id)}"


def tache_du_canal(canal: str) -> int | None:
    m = _CANAL_TACHE.match(str(canal or ""))
    return int(m.group(1)) if m else None


CHAMPS_TACHE = ("titre", "etape", "etat", "responsable", "equipe", "critere", "preuve",
                "incertitude", "hypothese", "methode", "resultat", "conclusion",
                "prochaine_action", "derniere_erreur")
# Bornes de la fiche (salle sobre) : la fiche garde une taille fixe, quel que soit l'historique.
MAX_COURT = 500          # prochaine_action, derniere_erreur, texte d'une decision
MAX_PREUVE_FICHE = 600   # la preuve complete reste dans la tache; la fiche n'en montre que le debut
MAX_DECISIONS = 50       # journal conserve
DECISIONS_FICHE = 8      # decisions montrees dans la fiche (les plus recentes)


def _equipe_valide(equipe) -> list[dict] | None:
    """[{agent, role}] sans doublon d'agent ; None si invalide."""
    if not isinstance(equipe, list):
        return None
    vus, out = set(), []
    for m in equipe:
        if not isinstance(m, dict):
            return None
        agent, role = str(m.get("agent", "")).strip(), str(m.get("role", "")).strip()
        if not agent or role not in ROLES or agent in vus:
            return None
        vus.add(agent)
        out.append({"agent": agent, "role": role})
    return out


def essai_pret(tache: dict) -> bool:
    """Une tache d'essai ne s'execute qu'une fois incertitude, hypothese, methode et critere ecrits."""
    if tache.get("etape") != "essais":
        return True
    return all(str(tache.get(c, "")).strip() for c in CHAMPS_ESSAI)


def etape_du_projet(taches: list[dict]) -> str:
    """Premiere etape (ordre pilote-rd) qui contient une tache pas encore faite ; '' si aucune."""
    ouvertes = {t.get("etape") for t in taches if t.get("etat") != "fait"}
    for e in ETAPES:
        if e in ouvertes:
            return e
    return ""


def _role_de(tache: dict, agent: str) -> str:
    """Role de `agent` dans l'equipe de la tache. Accepte le nom d'instance (claude-1) ou le nom de base (claude)."""
    agent = str(agent or "").strip().lower()
    base = re.sub(r"-\d+$", "", agent)
    for m in tache.get("equipe") or []:
        nom = str(m.get("agent", "")).strip().lower()
        if nom in (agent, base) or re.sub(r"-\d+$", "", nom) == agent:
            return str(m.get("role", ""))
    return ""


def fiche(tache: dict, pour: str = "", livrables: list[dict] | None = None) -> dict:
    """Etat de travail d'une tache, en taille bornee (salle sobre). C'est ce qu'un agent lit au lieu du fil :
    la taille ne depend pas du nombre de messages echanges. `livrables` : fiches RevisionStore de CETTE tache."""
    preuve = str(tache.get("preuve") or "")
    decisions = list(tache.get("decisions") or [])[-DECISIONS_FICHE:]
    f = {
        "tache_id": tache.get("id"),
        "titre": tache.get("titre") or tache.get("title", ""),
        "projet_id": tache.get("projet_id", ""),
        "etape": tache.get("etape", ""),
        "etat": tache.get("etat", ""),
        "responsable": tache.get("responsable", ""),
        "critere": tache.get("critere", ""),
        "prochaine_action": tache.get("prochaine_action", ""),
        "derniere_erreur": tache.get("derniere_erreur", ""),
        "preuve": preuve[:MAX_PREUVE_FICHE] + (" […]" if len(preuve) > MAX_PREUVE_FICHE else ""),
        "decisions": [{"texte": d.get("texte", ""), "par": d.get("par", "")} for d in decisions],
        "livrables": [{"chemin": l.get("chemin", ""), "version": l.get("version"),
                       "empreinte": str(l.get("empreinte", ""))[:12], "statut": l.get("statut", "")}
                      for l in (livrables or [])],
        "canal": canal_tache(tache["id"]) if tache.get("id") else "",
    }
    if pour:
        f["ton_role"] = _role_de(tache, pour) or "hors equipe"
    nb_decisions = len(tache.get("decisions") or [])
    if nb_decisions > DECISIONS_FICHE:
        f["decisions_masquees"] = nb_decisions - DECISIONS_FICHE
    return f


class JobStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: list[dict] = []
        self._next_id = 1
        self._lock = threading.Lock()
        self._callbacks: list = []  # (action, job) on any change
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            if isinstance(raw, list):
                self._jobs = raw
                if self._jobs:
                    self._next_id = max(a["id"] for a in self._jobs) + 1
                    if self._ensure_sort_orders_locked():
                        self._save()
        except (json.JSONDecodeError, KeyError) as err:
            # S2 (revue codex) : un fichier illisible n'est jamais vide en silence, sinon la prochaine
            # sauvegarde l'ecraserait. La salle refuse de demarrer et le fichier reste intact.
            raise ValueError(f"{self._path} illisible : {err}") from err

    def _save(self):
        self._path.write_text(
            json.dumps(self._jobs, indent=2, ensure_ascii=False) + "\n",
            "utf-8",
        )

    def _next_sort_order_locked(self, status: str) -> int:
        max_order = 0
        for a in self._jobs:
            if a.get("status") != status:
                continue
            try:
                max_order = max(max_order, int(a.get("sort_order", 0)))
            except (TypeError, ValueError):
                continue
        return max_order + 1

    def _ensure_sort_orders_locked(self):
        max_by_group: dict[str, int] = {}
        changed = False
        for a in self._jobs:
            key = a.get("status", "open")
            try:
                cur = int(a.get("sort_order", 0))
            except (TypeError, ValueError):
                cur = 0
            if cur > 0:
                max_by_group[key] = max(max_by_group.get(key, 0), cur)

        for a in self._jobs:
            key = a.get("status", "open")
            try:
                cur = int(a.get("sort_order", 0))
            except (TypeError, ValueError):
                cur = 0
            if cur <= 0:
                next_order = max_by_group.get(key, 0) + 1
                a["sort_order"] = next_order
                max_by_group[key] = next_order
                changed = True
        return changed

    def on_change(self, callback):
        """Register a callback(action, job) on any change.
        action: 'create', 'update', 'message', 'message_delete'."""
        self._callbacks.append(callback)

    def _fire(self, action: str, job: dict):
        for cb in self._callbacks:
            try:
                cb(action, job)
            except Exception:
                pass

    def list_all(self, channel: str | None = None,
                 status: str | None = None) -> list[dict]:
        """List jobs, optionally filtered by channel and/or status."""
        with self._lock:
            changed = self._ensure_sort_orders_locked()
            if changed:
                self._save()
            result = list(self._jobs)
        if channel:
            result = [a for a in result if a.get("channel") == channel]
        if status:
            result = [a for a in result if a.get("status") == status]
        return result

    def get(self, job_id: int) -> dict | None:
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    return dict(a)
            return None

    def create(self, title: str, job_type: str, channel: str,
               created_by: str, anchor_msg_id: int | None = None,
               assignee: str | None = None,
               body: str | None = None,
               uid: str | None = None,
               status: str | None = None,
               created_at: float | None = None,
               updated_at: float | None = None) -> dict:
        """Create a new job. Returns the job dict."""
        with self._lock:
            st = status or "done"
            now = time.time()
            a = {
                "id": self._next_id,
                "uid": uid or str(uuid.uuid4()),
                "type": job_type,
                "title": title.strip()[:120],
                "body": (body or "").strip()[:1000],
                "status": st,
                "channel": channel,
                "created_by": created_by,
                "assignee": assignee or "",
                "anchor_msg_id": anchor_msg_id,
                "messages": [],
                "created_at": created_at or now,
                "updated_at": updated_at or now,
                "sort_order": self._next_sort_order_locked(st),
            }
            self._next_id += 1
            self._jobs.append(a)
            self._save()
        self._fire("create", a)
        return a

    # --- S2 : taches de projet -------------------------------------------------------------------------------

    def taches(self, projet_id: str) -> list[dict]:
        with self._lock:
            return [dict(a) for a in self._jobs if a.get("projet_id") == projet_id]

    def create_tache(self, projet_id: str, titre: str, etape: str, responsable: str,
                     created_by: str, channel: str = "general", equipe=None,
                     critere: str = "", **essai) -> tuple[dict | None, str]:
        """Cree une tache de projet. Rend (tache, '') ou (None, erreur). L'existence du projet est verifiee par
        l'appelant (app.py), pour garder ce module sans dependance."""
        if not projet_id:
            return None, "projet_id requis"
        if etape not in ETAPES:
            return None, f"etape parmi {', '.join(ETAPES)}"
        if not str(responsable).strip():
            return None, "un responsable"
        eq = _equipe_valide(equipe or [])
        if eq is None:
            return None, f"equipe : [{{agent, role}}], role parmi {', '.join(ROLES)}, sans doublon"
        if str(responsable).strip() not in {m["agent"] for m in eq}:
            return None, "le responsable doit faire partie de l'equipe"
        a = self.create(title=titre, job_type="tache", channel=channel, created_by=created_by,
                        assignee=str(responsable).strip(), status="open")
        champs = {"projet_id": projet_id, "titre": a["title"], "etape": etape, "etat": "a_faire",
                  "responsable": str(responsable).strip(), "equipe": eq, "critere": str(critere),
                  "preuve": ""}
        for c in ("incertitude", "hypothese", "methode"):
            champs[c] = str(essai.get(c, ""))
        with self._lock:
            for j in self._jobs:
                if j["id"] == a["id"]:
                    j.update(champs)
                    self._save()
                    a = dict(j)
                    break
        self._fire("update", a)
        return a, ""

    def update_tache(self, job_id: int, champs: dict) -> tuple[dict | None, str]:
        """Met a jour les champs d'une tache. `fait` exige une preuve (R6). Rend (tache, '') ou (None, erreur)."""
        inconnus = set(champs) - set(CHAMPS_TACHE)
        if inconnus:
            return None, f"champs inconnus : {', '.join(sorted(inconnus))}"
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id and a.get("projet_id"):
                    break
            else:
                return None, "tache inconnue"
            nouveau = dict(a)
            for k, v in champs.items():
                nouveau[k] = v
            for k in ("prochaine_action", "derniere_erreur"):
                if k in champs:
                    nouveau[k] = str(champs[k] or "").strip()[:MAX_COURT]
            if nouveau.get("etape") not in ETAPES:
                return None, f"etape parmi {', '.join(ETAPES)}"
            if nouveau.get("etat") not in ETATS:
                return None, f"etat parmi {', '.join(ETATS)}"
            if not str(nouveau.get("responsable", "")).strip():
                return None, "un responsable"
            if "equipe" in champs:
                eq = _equipe_valide(champs["equipe"])
                if eq is None:
                    return None, f"equipe : [{{agent, role}}], role parmi {', '.join(ROLES)}, sans doublon"
                nouveau["equipe"] = eq
            if str(nouveau["responsable"]).strip() not in {m.get("agent") for m in nouveau.get("equipe") or []}:
                return None, "le responsable doit faire partie de l'equipe"
            if nouveau["etat"] == "fait" and not str(nouveau.get("preuve", "")).strip():
                return None, "fait exige une preuve (commande et sortie, sortie d'outil ou fichier:ligne)"
            nouveau["title"] = str(nouveau.get("titre", a["title"])).strip()[:120]
            nouveau["titre"] = nouveau["title"]
            nouveau["assignee"] = str(nouveau["responsable"]).strip()
            nouveau["status"] = "done" if nouveau["etat"] == "fait" else "open"
            nouveau["updated_at"] = time.time()
            a.clear()
            a.update(nouveau)
            self._save()
            result = dict(a)
        self._fire("update", result)
        return result, ""

    def noter_decision(self, job_id: int, texte: str, par: str) -> tuple[dict | None, str]:
        """Ajoute une decision au journal de la tache (ajout seul, jamais reecrit). Rend (decision, '') ou
        (None, erreur). Le journal garde les MAX_DECISIONS plus recentes."""
        texte = str(texte or "").strip()
        if not texte:
            return None, "texte requis"
        if len(texte) > MAX_COURT:
            return None, f"decision trop longue ({len(texte)} > {MAX_COURT} caracteres) : le detail va dans le depot"
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id and a.get("projet_id"):
                    break
            else:
                return None, "tache inconnue"
            d = {"texte": texte, "par": str(par or "").strip(), "heure": time.time()}
            a["decisions"] = (list(a.get("decisions") or []) + [d])[-MAX_DECISIONS:]
            a["updated_at"] = time.time()
            self._save()
            result = dict(a)
        self._fire("update", result)
        return dict(d), ""

    def update_status(self, job_id: int, status: str) -> dict | None:
        """Update job status. Valid: open, done, archived."""
        if status not in ("open", "done", "archived"):
            return None
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    old_status = a.get("status")
                    next_order = None
                    if old_status != status:
                        # Compute destination order before moving this job so
                        # the job doesn't count itself in the target lane.
                        next_order = self._next_sort_order_locked(status)
                    a["status"] = status
                    a["updated_at"] = time.time()
                    if next_order is not None:
                        a["sort_order"] = next_order
                    self._save()
                    result = dict(a)
                    break
            else:
                return None
        self._fire("update", result)
        return result

    def update_title(self, job_id: int, title: str) -> dict | None:
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    a["title"] = title.strip()[:120]
                    a["updated_at"] = time.time()
                    self._save()
                    result = dict(a)
                    break
            else:
                return None
        self._fire("update", result)
        return result

    def update_assignee(self, job_id: int, assignee: str) -> dict | None:
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    a["assignee"] = assignee.strip()
                    a["updated_at"] = time.time()
                    self._save()
                    result = dict(a)
                    break
            else:
                return None
        self._fire("update", result)
        return result

    def add_message(self, job_id: int, sender: str, text: str,
                    attachments: list | None = None,
                    msg_type: str = "chat",
                    uid: str | None = None,
                    timestamp: float | None = None,
                    time_str: str | None = None) -> dict | None:
        """Add a message to a job's conversation. Returns the message."""
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    msg_id = len(a["messages"])
                    ts = timestamp if timestamp is not None else time.time()
                    msg = {
                        "id": msg_id,
                        "uid": uid or str(uuid.uuid4()),
                        "sender": sender,
                        "text": text.strip(),
                        "time": time_str or time.strftime("%H:%M:%S"),
                        "timestamp": ts,
                        "attachments": attachments or [],
                    }
                    if msg_type != "chat":
                        msg["type"] = msg_type
                    a["messages"].append(msg)
                    a["updated_at"] = time.time()
                    self._save()
                    result_msg = dict(msg)
                    result_msg["job_id"] = job_id
                    break
            else:
                return None
        self._fire("message", {"job_id": job_id, "message": result_msg})
        return result_msg

    def get_messages(self, job_id: int) -> list[dict] | None:
        """Get all messages for a job."""
        with self._lock:
            for a in self._jobs:
                if a["id"] == job_id:
                    return list(a["messages"])
            return None

    def delete_message(self, job_id: int, msg_id: int) -> dict | None:
        """Soft-delete a message from a job conversation by message id."""
        with self._lock:
            for a in self._jobs:
                if a["id"] != job_id:
                    continue
                msgs = a.get("messages", [])
                hit = None
                for i, m in enumerate(msgs):
                    try:
                        mid = int(m.get("id", -1))
                    except (TypeError, ValueError):
                        mid = -1
                    if mid == msg_id:
                        hit = (i, m)
                        break
                if hit is None:
                    return None
                _, msg = hit
                if msg.get("deleted"):
                    return {"job_id": job_id, "message_id": msg_id}
                msg["deleted"] = True
                msg["text"] = ""
                msg["attachments"] = []
                msg["updated_at"] = time.time()
                a["updated_at"] = time.time()
                self._save()
                payload = {"job_id": job_id, "message_id": msg_id}
                break
            else:
                return None
        self._fire("message_delete", payload)
        return payload

    def delete(self, job_id: int) -> dict | None:
        """Permanently delete a job."""
        with self._lock:
            for i, a in enumerate(self._jobs):
                if a["id"] == job_id:
                    removed = self._jobs.pop(i)
                    self._save()
                    result = dict(removed)
                    break
            else:
                return None
        self._fire("delete", result)
        return result

    def reorder(self, status: str, ordered_ids: list[int]) -> list[dict]:
        """Reorder jobs within a status group by explicit id order (top to bottom)."""
        if status not in ("open", "done", "archived"):
            return []
        with self._lock:
            self._ensure_sort_orders_locked()
            group = [
                a for a in self._jobs
                if a.get("status") == status
            ]
            if not group:
                return []

            by_id = {int(a["id"]): a for a in group}
            ordered: list[int] = []
            seen = set()
            for raw in ordered_ids:
                try:
                    aid = int(raw)
                except (TypeError, ValueError):
                    continue
                if aid in by_id and aid not in seen:
                    ordered.append(aid)
                    seen.add(aid)

            if not ordered:
                return []

            existing_sorted = sorted(
                group,
                key=lambda x: (int(x.get("sort_order", 0) or 0), float(x.get("updated_at", 0) or 0)),
                reverse=True,
            )
            for a in existing_sorted:
                aid = int(a["id"])
                if aid not in seen:
                    ordered.append(aid)

            changed: list[dict] = []
            n = len(ordered)
            for idx, aid in enumerate(ordered):
                item = by_id.get(aid)
                if not item:
                    continue
                new_order = n - idx
                old_order = int(item.get("sort_order", 0) or 0)
                if old_order != new_order:
                    item["sort_order"] = new_order
                    changed.append(dict(item))

            if changed:
                self._save()

        for item in changed:
            self._fire("update", item)
        return changed
