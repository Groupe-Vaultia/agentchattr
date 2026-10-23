"""agentchattr — FastAPI web UI + agent auto-trigger."""

import asyncio
import hmac
import json
import re as _re
import sys
import threading
import time
import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from store import MessageStore
from rules import RuleStore
from summaries import SummaryStore
from jobs import JobStore
import jobs as _jobs_mod
from executions import ExecutionStore
import historique as _historique
from revisions import RevisionStore
import revisions as _revisions_mod
import sobriete as _sobriete
from jalons import JalonStore
from pieces import PieceStore, Erreur as _ErreurPiece
import jalons as _jalons_mod
from ronde import ronde as _ronde, taches_muettes
import progression as _progression
from schedules import ScheduleStore, parse_schedule_spec
from router import Router
from agents import AgentTrigger
from registry import RuntimeRegistry
from session_store import SessionStore, validate_session_template
from session_engine import SessionEngine

log = logging.getLogger(__name__)

app = FastAPI(title="agentchattr")

# --- globals (set by configure()) ---
store: MessageStore | None = None
rules: RuleStore | None = None
summaries: SummaryStore | None = None
jobs: JobStore | None = None
executions: ExecutionStore | None = None  # SOCLE-SHOP S3
revisions: RevisionStore | None = None  # SOCLE-SHOP S5
sobriete: _sobriete.Compteur | None = None  # salle sobre lots 2-3 : lectures base contre fil
jalons: JalonStore | None = None  # SOCLE-SHOP v1.1 P1
pieces: PieceStore | None = None  # PIECES.md N1
_copie_pieces = [""]
schedules: ScheduleStore | None = None
router: Router | None = None
agents: AgentTrigger | None = None
registry: RuntimeRegistry | None = None
session_store: SessionStore | None = None
session_engine: SessionEngine | None = None
notifs = None  # Atelier v3 : notifications poussées (notifications.Notifications)
config: dict = {}
ws_clients: set[WebSocket] = set()

# --- Security: session token (set by configure()) ---
session_token: str = ""
# Vaultia (19 oct. 2026, lot « jeton hors URL », claude-1 msg 4867) : la page reçoit aussi le jeton dans un cookie
# HttpOnly. EventSource et WebSocket ne posent pas d'en-tête : le navigateur n'a plus à mettre le jeton dans l'URL.
# Le ?token= reste accepté (agents, scripts). Le nom porte le port : deux salles sur une même machine ne partagent
# pas leurs cookies (un cookie ignore le port).
cookie_session: str = "agentchattr_session_8300"
origines_permises: set[str] = set()


def nom_cookie_session(port) -> str:
    return f"agentchattr_session_{int(port)}"


def poser_cookie_session(reponse: Response) -> Response:
    """Pose le cookie de session sur une page servie avec le jeton (/, /atelier)."""
    reponse.set_cookie(cookie_session, session_token, httponly=True, secure=True, samesite="strict", path="/")
    return reponse


def jeton_valide(entetes, query, cookies) -> bool:
    """Vrai si l'un des jetons présentés (en-tête, ?token=, cookie de session) est le jeton de session."""
    if not session_token:
        return False
    return any(hmac.compare_digest(str(j).encode(), session_token.encode())
               for j in (entetes.get("x-session-token"), query.get("token"), cookies.get(cookie_session)) if j)

# Room settings (persisted to data/settings.json)
room_settings: dict = {
    "title": "Vaultia",
    # Shown beside the title, so several servers can be told apart without
    # renaming the product itself. "" hides it.
    "subtitle": "",
    "username": "user",
    "font": "sans",
    "channels": ["general"],
    "history_limit": "all",
    "contrast": "normal",
    "custom_roles": [],
}

# Channel validation
_CHANNEL_NAME_RE = _re.compile(r'^[a-z0-9][a-z0-9\-]{0,19}$')

# Agent hats (persisted to data/hats.json)
agent_hats: dict[str, str] = {}  # { agent_name: svg_string }


def _hats_path() -> Path:
    data_dir = config.get("server", {}).get("data_dir", "./data")
    return Path(data_dir) / "hats.json"


def _load_hats():
    global agent_hats
    p = _hats_path()
    if p.exists():
        try:
            agent_hats = json.loads(p.read_text("utf-8"))
        except Exception:
            agent_hats = {}


def _save_hats():
    p = _hats_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(agent_hats), "utf-8")


def _sanitize_svg(svg: str) -> str:
    """Strip dangerous content from SVG string."""
    svg = _re.sub(r'<script[^>]*>.*?</script>', '', svg, flags=_re.DOTALL | _re.IGNORECASE)
    svg = _re.sub(r'\bon\w+\s*=', '', svg, flags=_re.IGNORECASE)
    svg = _re.sub(r'javascript\s*:', '', svg, flags=_re.IGNORECASE)
    return svg


def set_agent_hat(agent: str, svg: str) -> str | None:
    """Validate, sanitize, and store a hat SVG. Returns error string or None."""
    svg = svg.strip()
    if not svg.lower().startswith("<svg"):
        return "Hat must be an SVG element (starts with <svg)."
    if len(svg) > 5120:
        return "Hat SVG too large (max 5KB)."
    svg = _sanitize_svg(svg)
    agent_hats[agent.lower()] = svg
    _save_hats()
    if _event_loop:
        asyncio.run_coroutine_threadsafe(broadcast_hats(), _event_loop)
    return None


def clear_agent_hat(agent: str):
    """Remove an agent's hat."""
    key = agent.lower()
    if key in agent_hats:
        del agent_hats[key]
        _save_hats()
        if _event_loop:
            asyncio.run_coroutine_threadsafe(broadcast_hats(), _event_loop)


def _settings_path() -> Path:
    data_dir = config.get("server", {}).get("data_dir", "./data")
    return Path(data_dir) / "settings.json"


ROOM_SUBTITLE_MAX = 40


def normalize_room_subtitle(value):
    """Clean a room subtitle, or return None if it is not usable.

    Collapses any internal whitespace so a pasted newline cannot break the
    header across two lines, and caps the length so a long name cannot crowd
    out the rest of the header.
    """
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:ROOM_SUBTITLE_MAX]


def apply_room_subtitle(new: dict):
    """Apply a subtitle from a settings payload, if present and usable."""
    if "subtitle" not in new:
        return
    cleaned = normalize_room_subtitle(new["subtitle"])
    if cleaned is not None:
        room_settings["subtitle"] = cleaned


def _load_settings():
    global room_settings
    p = _settings_path()
    if p.exists():
        try:
            saved = json.loads(p.read_text("utf-8"))
            room_settings.update(saved)
        except Exception:
            pass
    # settings.json is hand-editable, so the file bypasses every check the
    # live update path applies. Re-normalise on load rather than trust it.
    room_settings["subtitle"] = normalize_room_subtitle(room_settings.get("subtitle")) or ""
    # Ensure "general" always exists and is first
    if "channels" not in room_settings or not room_settings["channels"]:
        room_settings["channels"] = ["general"]
    elif "general" not in room_settings["channels"]:
        room_settings["channels"].insert(0, "general")
    # Anti-tournage-a-vide : battements de ronde recurrente sans progres toleres avant la mise en veille.
    room_settings.setdefault("anti_spin_ticks", 3)


def _save_settings():
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(room_settings, indent=2), "utf-8")


def _extract_agent_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-agent-token", "").strip()


def _resolve_authenticated_agent(request: Request) -> dict | None:
    if not registry:
        return None
    token = _extract_agent_token(request)
    if not token:
        return None
    return registry.resolve_token(token)


# --- Security middleware ---
# Paths that don't require the session token (public assets).
_PUBLIC_PREFIXES = ("/", "/static/")


def _install_security_middleware(token: str, cfg: dict, cible: FastAPI | None = None):
    """Add token validation and origin checking middleware to the app (`cible` : une autre app, pour les tests)."""
    import app as _self
    _self.session_token = token
    port = cfg.get("server", {}).get("port", 8300)
    _self.cookie_session = nom_cookie_session(port)
    allowed_origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }
    # Origines de confiance propres a cette machine (ex. le tunnel Tailscale prive de la personne,
    # pour la salle au telephone) : lues de config.local.toml [server] allowed_origins, hors de git
    # car le depot est public. Correspondance exacte seulement ; le token de session reste exige apres.
    _valeurs = cfg.get("server", {}).get("allowed_origins", []) or []
    if isinstance(_valeurs, str):  # une seule origine écrite sans crochets : pas une suite de caractères
        _valeurs = [_valeurs]
    for _origine in _valeurs:
        if isinstance(_origine, str) and _origine.strip():
            allowed_origins.add(_origine.strip().rstrip("/"))
    _self.origines_permises = allowed_origins

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path

            # Static assets, index page, and uploaded images are public.
            # The index page injects the token client-side via same-origin script.
            # Uploads use random filenames and have path-traversal protection.
            if path in ("/", "/atelier") or path.startswith(("/static/", "/uploads/", "/api/roles")):
                return await call_next(request)

            # Agent registration/heartbeat: loopback only (no remote agent minting).
            if path.startswith(("/api/register", "/api/deregister/", "/api/heartbeat/")):
                client_ip = request.client.host if request.client else ""
                if client_ip not in ("127.0.0.1", "::1", "localhost"):
                    return JSONResponse(
                        {"error": f"forbidden: agent registration is restricted to local loopback. Source {client_ip} is not allowed."},
                        status_code=403,
                    )
                return await call_next(request)

            # --- Origin check (blocks cross-origin / DNS-rebinding attacks) ---
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins:
                return JSONResponse(
                    {"error": "forbidden: origin not allowed"},
                    status_code=403,
                )

            # --- Token check ---
            # Allow registered agents to authenticate via Bearer token
            # for /api/messages and /api/send (no browser session needed).
            auth_header = request.headers.get("authorization", "")
            fiche_tache = request.method == "GET" and _re.fullmatch(r"/api/v2/taches/\d+/fiche", path) is not None
            # Memoire de projet en lecture (20 oct. 2026) : les wrappers la lisaient sans jeton -> 403 avale.
            memoire = request.method == "GET" and _re.fullmatch(r"/api/projects/(channel/)?[^/]+/memory", path) is not None
            if auth_header.lower().startswith("bearer ") and (path in ("/api/messages", "/api/send")
                                                              or path.startswith("/api/rules/") or fiche_tache
                                                              or memoire):
                bearer = auth_header[7:].strip()
                if _self.registry and _self.registry.resolve_token(bearer):
                    return await call_next(request)

            if not jeton_valide(request.headers, request.query_params, request.cookies):
                return JSONResponse(
                    {"error": "forbidden: invalid or missing session token"},
                    status_code=403,
                )

            return await call_next(request)

    (cible or app).add_middleware(SecurityMiddleware)


def configure(cfg: dict, session_token: str = ""):
    global sobriete
    global store, rules, summaries, jobs, executions, revisions, jalons, pieces, schedules, router, agents, registry, session_store, session_engine, config, notifs
    config = cfg
    # --- Security: store the session token and install middleware ---
    _install_security_middleware(session_token, cfg)

    data_dir = cfg.get("server", {}).get("data_dir", "./data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    log_path = Path(data_dir) / "agentchattr_log.jsonl"
    legacy_log_path = Path(data_dir) / "room_log.jsonl"
    if not log_path.exists() and legacy_log_path.exists():
        # Backward compatibility for existing installs.
        log_path = legacy_log_path

    store = MessageStore(str(log_path))
    # Initialize store upload dir from config
    raw_upload_dir = cfg.get("images", {}).get("upload_dir", "./uploads")
    store.upload_dir = Path(raw_upload_dir)
    
    # Rules store — migrates from legacy decisions.json automatically
    rules_path = Path(data_dir) / "rules.json"
    legacy_decisions = Path(data_dir) / "decisions.json"
    if not rules_path.exists() and legacy_decisions.exists():
        legacy_decisions.rename(rules_path)
    rules = RuleStore(str(rules_path))
    rules.on_change(_on_rule_change)

    summaries = SummaryStore(str(Path(data_dir) / "summaries.json"))

    # Migrate legacy activities.json → jobs.json
    jobs_path = Path(data_dir) / "jobs.json"
    legacy_activities = Path(data_dir) / "activities.json"
    if not jobs_path.exists() and legacy_activities.exists():
        legacy_activities.rename(jobs_path)

    jobs = JobStore(str(jobs_path))
    jobs.on_change(_on_job_change)
    # Atelier v3 : notifications poussées. Les tâches qui attendent déjà Charles au démarrage ne sont pas renotifiées.
    from notifications import Notifications
    notifs = Notifications(data_dir)
    _attente_notifiee.clear()
    _attente_notifiee.update(t["id"] for t in jobs.list_all() if t.get("type") == "tache" and t.get("etat") == "attend_charles")
    executions = ExecutionStore(str(Path(data_dir) / "executions.json"))
    # Les livrables vivent dans les worktrees de l'atelier ; un chemin hors de cette racine est refuse.
    racine = cfg.get("socle", {}).get("racine_livrables", str(Path.home() / "atelier"))
    revisions = RevisionStore(str(Path(data_dir) / "revisions.json"), racine)
    sobriete = _sobriete.Compteur(Path(data_dir) / "sobriete.json")
    jalons = JalonStore(str(Path(data_dir) / "jalons.json"))
    # PIECES.md N1 : la base des pieces vit sur la tour, dans data/ (exclu du depot public).
    pieces = PieceStore(str(Path(data_dir) / "pieces.db"))
    _copie_pieces[0] = cfg.get("socle", {}).get("copie_pieces", "")
    _demarrer_sauvegardes(Path(data_dir), _copie_pieces[0])

    schedules = ScheduleStore(str(Path(data_dir) / "schedules.json"))
    schedules.on_change(_on_schedule_change)

    max_hops = cfg.get("routing", {}).get("max_agent_hops", 4)
    anti_spin_ticks = cfg.get("routing", {}).get("anti_spin_ticks", 3)

    # Registry: single source of truth for all live agent state
    registry = RuntimeRegistry(data_dir=data_dir)
    registry.seed(cfg.get("agents", {}))
    registry.on_change(_on_registry_change)

    # Router starts with base agent names (backward compat for direct MCP users),
    # registry.on_change updates it dynamically when instances register/deregister
    agent_names = list(cfg.get("agents", {}).keys())
    router = Router(
        agent_names=agent_names,
        default_mention=cfg.get("routing", {}).get("default", "none"),
        max_hops=max_hops,
        online_checker=lambda: set(registry.get_active_names()) if registry else set(),
        anti_spin_ticks=anti_spin_ticks,
    )
    agents = AgentTrigger(registry, data_dir=data_dir)

    # Sessions
    ROOT = Path(__file__).parent
    session_store = SessionStore(
        str(Path(data_dir) / "session_runs.json"),
        templates_dir=str(ROOT / "session_templates"),
    )
    session_engine = SessionEngine(session_store, store, agents, registry)
    session_store.on_change(_on_session_change)

    # Bridge: when ANY message is added to store (including via MCP),
    # broadcast to all WebSocket clients
    store.on_message(_on_store_message)

    _load_settings()
    _load_hats()

    # Apply saved loop guard setting
    if "max_agent_hops" in room_settings:
        router.max_hops = room_settings["max_agent_hops"]
    # Apply saved anti-spin setting (exactement comme max_agent_hops)
    if "anti_spin_ticks" in room_settings:
        router.anti_spin_ticks = room_settings["anti_spin_ticks"]

    # Background thread: check for wrapper recovery flag files
    _data_dir = Path(data_dir)

    _known_online: set[str] = set()  # agents we've seen join — track for leave messages
    _posted_leave: set[str] = set()  # agents we've already posted a leave for — debounce

    _known_active = set()

    def _background_checks():
        import time as _time
        import mcp_bridge

        while True:
            _time.sleep(3)
            # Recovery flags
            try:
                for flag in _data_dir.glob("*_recovered"):
                    agent_name = flag.read_text("utf-8").strip()
                    flag.unlink()
                    store.add(
                        "system",
                        f"Agent routing for {agent_name} interrupted — auto-recovered. "
                        "If agents aren't responding, try sending your message again."
                    )
            except Exception:
                pass

            # Pending instances (slot 2+) wait for human naming or agent claim.
            # No auto-confirm — identity must be explicitly resolved.

            # Presence expiry — post leave messages (but do NOT deregister).
            # Deregistration only happens via /api/deregister (wrapper shutdown)
            # OR the 60s crash timeout below.
            # Short timeout (10s) prevents slot theft when MCP tool calls are intermittent.
            try:
                now = _time.time()
                with mcp_bridge._presence_lock:
                    currently_online = {
                        name for name, ts in mcp_bridge._presence.items()
                        if now - ts < mcp_bridge.PRESENCE_TIMEOUT
                    }
                    currently_active = set()
                    for name, active in mcp_bridge._activity.items():
                        if active:
                            if now - mcp_bridge._activity_ts.get(name, 0) < mcp_bridge.ACTIVITY_TIMEOUT:
                                currently_active.add(name)
                            else:
                                mcp_bridge._activity[name] = False  # auto-expire

                # Crash timeout : le battement est envoye toutes les 5 s ; sous charge, 2-3
                # battements lents/en timeout depassaient 15 s et marquaient a tort un agent
                # OCCUPE (FreeCAD, gros calcul) comme "parti" — surtout le chef. 60 s = 12
                # battements de marge : un agent occupe ne clignote plus, un vrai mort est
                # detecte en 1 min.
                _CRASH_TIMEOUT = 60
                registered = set(registry.get_all_names())
                for name in registered:
                    with mcp_bridge._presence_lock:
                        last_seen = mcp_bridge._presence.get(name, 0)
                    if last_seen > 0 and now - last_seen > _CRASH_TIMEOUT:
                        log.info(f"Crash timeout: deregistering {name} (no heartbeat for {_CRASH_TIMEOUT}s)")
                        # Sleep / crash path: keep the token reclaimable so the
                        # wrapper transparently recovers its identity on wake.
                        # (A deliberate /api/deregister below stays non-reclaimable.)
                        result = registry.deregister(name, reclaimable=True)
                        if result:
                            mcp_bridge.purge_identity(name)
                            registry.clean_renames_for(name)
                            renamed = result.get("_renamed_back")
                            if renamed:
                                mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
                                store.rename_sender(renamed["old"], renamed["new"])
                                _migrate_agent_last_channel(renamed["old"], renamed["new"])
                                if _event_loop:
                                    rename_event = json.dumps({
                                        "type": "agent_renamed",
                                        "old_name": renamed["old"],
                                        "new_name": renamed["new"],
                                    })
                                    asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
                            store.add(name, f"{name} disconnected (timeout)", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))
                            _posted_leave.add(name)

                # Re-fetch registered names (may have changed from crash timeout above)
                registered = set(registry.get_all_names())

                # Detect registered instances going offline (leave message only)
                timed_out = registered - currently_online
                for name in timed_out:
                    inst = registry.get_instance(name)
                    if not inst:
                        continue
                    # Skip names that were just renamed (not actually offline)
                    with mcp_bridge._presence_lock:
                        was_renamed = name in mcp_bridge._renamed_from
                        if was_renamed:
                            mcp_bridge._renamed_from.discard(name)
                    if was_renamed:
                        continue
                    # Post leave message ONCE per offline transition (debounced)
                    if name not in _posted_leave:
                        _posted_leave.add(name)
                        store.add(name, f"{name} disconnected", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))

                # Clear leave debounce for agents that came back online
                _posted_leave.difference_update(currently_online)

                # Detect other agents (non-registered) going offline
                went_offline = (_known_online - currently_online) - timed_out
                for name in went_offline:
                    # Skip leave messages for names that were just renamed
                    with mcp_bridge._presence_lock:
                        was_renamed = name in mcp_bridge._renamed_from
                        if was_renamed:
                            mcp_bridge._renamed_from.discard(name)
                    if was_renamed:
                        continue
                    if not registry.is_registered(name) and name not in _posted_leave:
                        _posted_leave.add(name)
                        store.add(name, f"{name} disconnected", msg_type="leave", channel=_agent_last_channel.get(name, _last_active_channel))

                if _known_online != currently_online and _event_loop:
                    asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)

                # Clear stale activity for agents that went offline
                with mcp_bridge._presence_lock:
                    stale_active = [n for n in mcp_bridge._activity
                                    if mcp_bridge._activity.get(n) and n not in currently_online]
                    for n in stale_active:
                        mcp_bridge._activity[n] = False
                    if stale_active:
                        currently_active -= set(stale_active)

                # Broadcast status on any change (online set or activity set)
                if currently_active != _known_active or _known_online != currently_online:
                    _known_active.clear()
                    _known_active.update(currently_active)
                    if _event_loop:
                        asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)
                _known_online.clear()
                _known_online.update(currently_online)
            except Exception:
                pass

    threading.Thread(target=_background_checks, daemon=True).start()

    # --- Schedule runner: fires due scheduled prompts every 30s ---
    def _schedule_runner():
        import time as _time
        while True:
            _time.sleep(30)
            try:
                if not schedules:
                    continue
                due = schedules.run_due()
                for s in due:
                    prompt = s.get("prompt", "")
                    targets = s.get("targets", [])
                    channel = s.get("channel", "general")
                    if not prompt or not targets:
                        schedules.mark_run(s["id"])
                        continue
                    # Anti-tournage-a-vide : un battement de ronde (planification recurrente qui
                    # relance claude) ne fouette plus la ronde apres anti_spin_ticks battements
                    # consecutifs SANS progres reel (note_progress). On previent Charles une fois,
                    # puis on cesse de relancer claude jusqu'au prochain progres.
                    if router and not s.get("one_shot") and _vise_claude(targets):
                        compte, franchi = router.note_heartbeat(channel)
                        if compte >= router.anti_spin_ticks:
                            if franchi:
                                uname = room_settings.get("username", "user")
                                store.add(
                                    "system",
                                    f"Ronde en veille : aucun progrès depuis {router.anti_spin_ticks} "
                                    f"battements. @{uname} relance quand tu veux.",
                                    msg_type="system",
                                    channel=channel,
                                )
                            schedules.mark_run(s["id"])
                            continue
                    sender = s.get("created_by", "user")
                    mention_str = " ".join(f"@{t}" for t in targets)
                    full_text = f"{mention_str} {prompt}" if mention_str else prompt
                    # store.add triggers _handle_new_message via callback,
                    # which routes @mentions to agents — no manual trigger needed.
                    store.add(
                        sender,
                        full_text,
                        channel=channel,
                    )
                    if s.get("one_shot"):
                        schedules.delete(s["id"])
                    else:
                        schedules.mark_run(s["id"])
            except Exception:
                log.exception("schedule runner error")

    threading.Thread(target=_schedule_runner, daemon=True).start()


# --- Store → WebSocket bridge ---

_event_loop = None  # set by run.py after starting the event loop
_last_active_channel: str = "general"  # last channel any message was sent in
# Per-agent last channel: where each sender was most recently active. Used to
# route leave/disconnect messages to the channel that agent was talking in,
# instead of the global last-active channel (which is usually #general and made
# leave spam land in the wrong place).
_agent_last_channel: dict[str, str] = {}


def _migrate_agent_last_channel(old_name: str, new_name: str):
    """Re-key _agent_last_channel across an agent rename.

    Without this, a disconnect for the post-rename name misses the map and
    falls back to the global last-active channel — putting the leave message
    back in the wrong channel. Call this beside every migrate_identity /
    rename_sender path (slot-1 rename, renamed-back, websocket rename_agent,
    /api/label)."""
    if old_name == new_name:
        return
    ch = _agent_last_channel.pop(old_name, None)
    if ch is not None:
        _agent_last_channel[new_name] = ch


def set_event_loop(loop):
    global _event_loop
    _event_loop = loop


def _on_store_message(msg: dict):
    """Called from any thread when a message is added to the store."""
    if _event_loop is None:
        return
    try:
        # If called from the event loop thread (e.g. WebSocket handler),
        # schedule directly as a task
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(_handle_new_message(msg))
            return
    except RuntimeError:
        pass  # No running loop — we're in a different thread (MCP)
    asyncio.run_coroutine_threadsafe(_handle_new_message(msg), _event_loop)


def _on_rule_change(action: str, rule: dict):
    """Called from any thread when a rule changes."""
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_rule(action, rule))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_rule(action, rule), _event_loop)


# Atelier v3 : tâches pour lesquelles Charles a déjà été prévenu qu'elles l'attendent (une seule fois par attente).
_attente_notifiee: set[int] = set()


def _notifier_attente(tache: dict) -> None:
    """Prévient Charles quand une tâche PASSE à « attend_charles » ; oublie l'attente quand elle en sort."""
    if not isinstance(tache, dict) or tache.get("type") != "tache" or tache.get("id") is None:
        return
    if tache.get("etat") != "attend_charles":
        _attente_notifiee.discard(tache["id"])
        return
    if tache["id"] in _attente_notifiee:
        return
    _attente_notifiee.add(tache["id"])
    if notifs is not None:
        projet = tache.get("projet_id") or ""
        notifs.envoyer_en_fond("Une décision t'attend", f"{tache.get('titre') or 'Tâche ' + str(tache['id'])}",
                               url=f"/atelier#/p/{projet}/taches/{tache['id']}", etiquette=f"tache-{tache['id']}")


def _on_job_change(action: str, data: dict):
    """Called from any thread when a job changes."""
    try:
        _notifier_attente(data)
    except Exception:
        log.exception("notification d'attente")
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_job(action, data))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_job(action, data), _event_loop)


def _on_schedule_change(action: str, schedule: dict):
    """Called from any thread when a schedule changes."""
    if _event_loop is None:
        return
    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_schedule(action, schedule))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_schedule(action, schedule), _event_loop)


def _on_session_change(action: str, session: dict):
    """Called from any thread when a session changes."""
    if _event_loop is None:
        return
    # Enrich with computed fields so the frontend gets phase_name, current_agent, etc.
    if session_engine:
        session = session_engine._enrich(dict(session))

    # Add completion/interruption banners to chat timeline
    if action == "complete" and store:
        output_id = session.get("output_message_id")
        # Tag the output message so it renders highlighted on reload
        if output_id:
            msg = store.get_by_id(output_id)
            if msg:
                meta = msg.get("metadata") or {}
                meta["session_output"] = True
                store.update_message(output_id, {"metadata": meta})
        store.add(
            sender="system",
            text=f"Session complete: {session.get('template_name', '?')}",
            msg_type="session_end",
            channel=session.get("channel", "general"),
            metadata={"session_id": session.get("id"), "output_message_id": output_id},
        )
    elif action == "interrupt" and store:
        reason = session.get("interrupt_reason", "interrupted")
        store.add(
            sender="system",
            text=f"Session ended: {session.get('template_name', '?')} ({reason})",
            msg_type="session_end",
            channel=session.get("channel", "general"),
            metadata={"session_id": session.get("id"), "reason": reason},
        )

    try:
        loop = asyncio.get_running_loop()
        if loop is _event_loop:
            asyncio.ensure_future(broadcast_session(action, session))
            return
    except RuntimeError:
        pass
    asyncio.run_coroutine_threadsafe(broadcast_session(action, session), _event_loop)


_draft_ref_re = _re.compile(r'\[([a-f0-9]{8})\]')

def _resolve_draft_lineage(text: str, channel: str) -> tuple[str, int]:
    """Check if a session draft block is a revision of an existing draft.

    Looks at the agent's own message text for a [draft_id] reference, and also
    scans recent channel messages for "revise session draft [XXXX]" requests.
    Returns (draft_id, revision). New drafts get a fresh id and revision=1.
    """
    # Check the message text itself for a draft_id reference
    ref_match = _draft_ref_re.search(text)
    ref_id = ref_match.group(1) if ref_match else None

    if not ref_id:
        # Also check recent messages for a "revise session draft [XXXX]" request
        recent = store.get_recent(count=20, channel=channel)
        for m in reversed(recent):
            m_text = m.get("text", "")
            if "revise session draft" in m_text.lower():
                ref_match = _draft_ref_re.search(m_text)
                if ref_match:
                    ref_id = ref_match.group(1)
                    break

    if ref_id:
        # Find the highest revision for this draft_id in existing messages
        max_rev = 0
        recent = store.get_recent(count=100, channel=channel)
        for m in recent:
            meta = m.get("metadata") or {}
            if meta.get("draft_id") == ref_id:
                max_rev = max(max_rev, meta.get("revision", 1))
        if max_rev > 0:
            return ref_id, max_rev + 1

    return str(uuid.uuid4())[:8], 1


def _remplacer_decisions(nouvelle: dict) -> list[dict]:
    """Vaultia : la dernière carte d'un agent fait foi.

    Une nouvelle carte de décision ferme les cartes encore ouvertes du MÊME agent dans le MÊME
    canal (« Remplacée », avec le numéro de la nouvelle) : Charles n'a qu'une carte à trancher,
    pas quatre dont seule la dernière compte. Les cartes des autres agents ou des autres canaux,
    et celles déjà tranchées, ne bougent pas. Renvoie les cartes fermées (à diffuser).
    """
    if nouvelle.get("type") != "decision" or store is None:
        return []
    auteur = nouvelle.get("sender")
    canal = nouvelle.get("channel", "general")
    fermees = []
    with store._lock:
        for m in store._messages:
            if m["id"] >= nouvelle["id"] or m.get("type") != "decision":
                continue
            if m.get("sender") != auteur or m.get("channel", "general") != canal:
                continue
            meta = m.get("metadata") or {}
            if meta.get("resolved"):
                continue
            meta.update(resolved=True, chosen="Remplacée", remplacee_par=nouvelle["id"])
            m["metadata"] = meta
            fermees.append(dict(m))
        if fermees:
            store._rewrite()
    return fermees


async def _handle_new_message(msg: dict):
    """Broadcast message to web clients + check for @mention triggers."""
    # For broadcast slash commands, suppress the raw message — only the expanded
    # version should appear. Delete from store if it was persisted (MCP path),
    # and skip broadcasting the raw text.
    text = msg.get("text", "")
    msg_type = msg.get("type", "chat")
    sender = msg.get("sender", "")
    channel = msg.get("channel", "general")

    if msg_type == "decision":
        for ancienne in _remplacer_decisions(msg):
            await _broadcast(json.dumps({"type": "message_update", "message": ancienne}))
        # Atelier v3 : une carte de décision d'un agent attend Charles → notification sur son cell.
        if notifs is not None and sender not in ("system", room_settings.get("username", "user")):
            premiere = next((l.strip(" #*|") for l in text.splitlines() if l.strip(" #*|-")), "")
            cible = (f"/atelier#/p/{msg['projet_id']}/taches/{msg['tache_id']}"
                     if msg.get("projet_id") and msg.get("tache_id") else "/atelier#/")
            notifs.envoyer_en_fond(f"{sender} te demande de choisir", premiere[:200] or "Une carte de décision t'attend.",
                                   url=cible, etiquette=f"decision-{channel}")

    # Track last active channel for leave/join messages (skip system messages)
    global _last_active_channel
    if msg_type not in ("system", "leave", "join"):
        _last_active_channel = channel
        # Remember where this specific sender was last active so their
        # disconnect message follows them to the right channel.
        if sender and sender != "system":
            _agent_last_channel[sender] = channel
    # Strip @mentions to find the slash command (e.g. "@claude @codex /hatmaking")
    stripped = _re.sub(r"@[\w-]+\s*", "", text).strip().lower()
    _broadcast_cmds = ("/hatmaking", "/artchallenge", "/roastreview", "/poetry")
    cmd_word = stripped.split()[0] if stripped else ""
    is_broadcast_cmd = cmd_word in _broadcast_cmds
    known_agents = set(registry.get_all_names()) if registry else set()
    known_agents.update(config.get("agents", {}).keys())
    _session_draft_re = _re.compile(r'```session\s*\n(.*?)\n```', _re.DOTALL)
    draft_match = _session_draft_re.search(text)
    is_agent_session_draft = bool(draft_match and sender in known_agents)
    is_hidden_session_request = msg_type == "session_request"

    is_agent_continue = (stripped == "/continue" and sender in known_agents)
    suppress_broadcast = (
        is_broadcast_cmd
        or is_hidden_session_request
        or is_agent_session_draft
        or is_agent_continue
    )

    if not suppress_broadcast:
        await broadcast(msg)

    # If the raw slash command was persisted (MCP path), silently remove it.
    # It was never broadcast to WebSocket clients, so no delete event needed.
    if suppress_broadcast and msg.get("id"):
        store.delete([msg["id"]])

    # System messages never trigger routing - prevents infinite callback loops
    if sender == "system":
        return

    # Check for slash commands — use stripped text (sans @mentions)
    if stripped == "/continue":
        if sender in known_agents:
            store.add("system", f"Loop guard: only humans can /continue. {sender} tried to self-resume.", channel=channel)
            return
        router.continue_routing(channel)
        store.add("system", f"Routing resumed by {sender}.", channel=channel)
        await broadcast_status()
        return

    if stripped == "/roastreview":
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        store.add(sender, f"{mentions} Time for a roast review! Inspect each other's work and constructively roast it.", channel=channel)
        return

    if stripped.startswith("/artchallenge"):
        parts = stripped.split(None, 1)
        theme = parts[1] if len(parts) > 1 else "anything you like"
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        store.add(
            sender,
            f"{mentions} Art challenge! Create an SVG artwork with the theme: **{theme}**. "
            "Write your SVG code to a .svg file, then attach it using chat_send(image_path=...). "
            "Make it creative, keep it under 5KB. Let's see what you've got!",
            channel=channel,
        )
        return

    if stripped == "/hatmaking":
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        all_instances = registry.get_all() if registry else {}
        agents_cfg = config.get("agents", {})
        color_parts = ", ".join(
            f"{a}={all_instances[a]['color']}" if a in all_instances
            else f"{a}={agents_cfg.get(a, {}).get('color', '#888')}"
            for a in agent_names
        )
        store.add(
            sender,
            f"{mentions} Hat making time! Design a new hat for your avatar using SVG. "
            "Use viewBox=\"0 0 32 16\" so it fits on top of a 32px avatar circle. "
            f"Background is dark (#0f0f17). Avatar colors: {color_parts}. Design for good contrast! "
            "Call chat_set_hat(sender=your_name, svg='<svg ...>...</svg>') to wear it. "
            "Be creative — top hats, party hats, crowns, propeller beanies, whatever you want!",
            channel=channel,
        )
        return

    if stripped.startswith("/poetry"):
        parts = stripped.split(None, 1)
        form = parts[1] if len(parts) > 1 else "haiku"
        if form not in ("haiku", "limerick", "sonnet"):
            form = "haiku"
        agent_names = registry.get_all_names() if registry else list(config.get("agents", {}).keys())
        mentions = " ".join(f"@{a}" for a in agent_names)
        prompts = {
            "haiku": "Write a haiku about the current state of this codebase.",
            "limerick": "Write a limerick about the current state of this codebase.",
            "sonnet": "Write a sonnet about the current state of this codebase.",
        }
        store.add(sender, f"{mentions} {prompts[form]}", channel=channel)
        return

    # Detect session draft blocks from agents only.
    # The session request prompt contains an example ```session block,
    # so treating every non-system sender as a draft source creates a false
    # invalid-draft card the moment the user asks for a custom session.
    _session_draft_re = _re.compile(r'```session\s*\n(.*?)\n```', _re.DOTALL)
    draft_match = _session_draft_re.search(text)
    known_agents = set(registry.get_all_names()) if registry else set()
    known_agents.update(config.get("agents", {}).keys())
    if draft_match and sender in known_agents:
        # Check if this is a revision of an existing draft
        draft_id, revision = _resolve_draft_lineage(text, channel)

        try:
            draft_json = json.loads(draft_match.group(1))
            errors = validate_session_template(draft_json)
            if errors:
                store.add(
                    "system",
                    f"Session draft from {sender} has errors:\n" + "\n".join(f"- {e}" for e in errors),
                    msg_type="session_draft",
                    channel=channel,
                    metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                              "template": draft_json, "errors": errors, "valid": False},
                )
            else:
                draft_json.setdefault("id", f"draft-{draft_id}")
                store.add(
                    "system",
                    f"Session draft from {sender}: **{draft_json.get('name', '?')}**",
                    msg_type="session_draft",
                    channel=channel,
                    metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                              "template": draft_json, "errors": [], "valid": True},
                )
        except json.JSONDecodeError:
            store.add(
                "system",
                f"Session draft from {sender} contains invalid JSON.",
                msg_type="session_draft",
                channel=channel,
                metadata={"draft_id": draft_id, "revision": revision, "proposed_by": sender,
                           "errors": ["Invalid JSON in session block"], "valid": False},
            )

    raw_targets = router.get_targets(sender, text, channel)
    # Resolve base family names to actual registered instances
    # e.g. 'claude' → 'claude-prime' when slot-1 was renamed
    targets = []
    for t in raw_targets:
        if registry:
            targets.extend(registry.resolve_to_instances(t))
        else:
            targets.append(t)
    targets = list(dict.fromkeys(targets))  # dedupe, preserve order

    if router.is_paused(channel):
        # Only emit the loop guard notice once per pause
        if not router.is_guard_emitted(channel):
            router.set_guard_emitted(channel)
            groupe = router.derniere_paire(channel)
            entre = f" between {', '.join(groupe[:-1])} and {groupe[-1]}" if len(groupe) >= 2 else ""
            store.add(
                "system",
                f"Loop guard: {router.max_hops} consecutive agent-to-agent hops{entre} "
                "(same group of agents or @all, no one else, no human). Type /continue to resume.",
                channel=channel
            )
            await _reveiller_chef_garde(channel, sender, msg.get("id"))
        return

    # Build a readable message string for the wake prompt
    chat_msg = f"{sender}: {text}" if text else ""
    custom_prompt = text if is_hidden_session_request else ""

    # Session turn guard: if a session is active on this channel and the sender
    # is an agent, only allow triggering the agent whose turn it is.
    # Human @mentions are always allowed (the session engine handles pausing).
    sender_is_agent = sender in known_agents
    allowed_agent = session_engine.get_allowed_agent(channel) if session_engine and sender_is_agent else None

    # SOCLE-SHOP S1 : un projet en veille ou termine ne declenche aucun agent ; le message reste visible.
    projet_id = msg.get("projet_id")
    if projet_id and targets:
        info = _projets.memoire_projet(projet_id)
        if info is None or info.get("statut") != "actif":
            if store is not None:
                etat = "inconnu" if info is None else info.get("statut")
                store.add("system", f"Projet « {projet_id} » {etat} : aucun agent déclenché.",
                          msg_type="system", channel=channel)
            return

    import mcp_bridge
    for target in targets:
        # Skip pending instances — they haven't been named/claimed yet
        if registry:
            inst = registry.get_instance(target)
            if inst and inst.get("state") == "pending":
                continue
        # Session guard: suppress out-of-turn agent triggers
        if allowed_agent and target != allowed_agent:
            continue
        if not mcp_bridge.is_online(target):
            store.add("system", f"{target} appears offline — message queued.", msg_type="system", channel=channel)
        if agents.is_available(target):
            await agents.trigger(target, message=chat_msg, channel=channel, prompt=custom_prompt,
                                 projet_id=msg.get("projet_id"))
            _ouvrir_execution(target, msg.get("tache_id"), text)


# --- broadcasting ---

# Atelier v3 : flux en direct (SSE) pour l'atelier. Le WebSocket /ws renvoie tout l'historique à chaque connexion
# (~4 Mo) ; l'atelier n'a besoin que de savoir qu'un message, une carte, un état d'agent ou une tâche a bougé.
_flux_abonnes: set[asyncio.Queue] = set()
_FLUX_TYPES = ("message", "message_update", "status", "job")


def _diffuser_flux(raw_json: str, type_: str = "") -> None:
    if not _flux_abonnes:
        return
    if not type_:
        try:
            type_ = json.loads(raw_json).get("type", "")
        except (ValueError, AttributeError):
            return
    if type_ not in _FLUX_TYPES:
        return
    for q in list(_flux_abonnes):
        try:
            q.put_nowait(raw_json)
        except asyncio.QueueFull:
            pass  # abonné trop lent : il se remet à jour à son rafraîchissement suivant


async def _broadcast(raw_json: str):
    """Send a pre-serialized JSON string to all WebSocket clients."""
    _diffuser_flux(raw_json)
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(raw_json)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast(msg: dict):
    data = json.dumps({"type": "message", "data": msg})
    _diffuser_flux(data, "message")
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_status():
    status = agents.get_status()
    status["paused"] = any(router.is_paused(ch) for ch in room_settings.get("channels", ["general"]))
    data = json.dumps({"type": "status", "data": status})
    _diffuser_flux(data, "status")
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_typing(agent_name: str, is_typing: bool):
    data = json.dumps({"type": "typing", "agent": agent_name, "active": is_typing})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_clear(channel: str | None = None):
    payload = {"type": "clear"}
    if channel:
        payload["channel"] = channel
    data = json.dumps(payload)
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_todo_update(msg_id: int, status: str | None):
    data = json.dumps({"type": "todo_update", "data": {"id": msg_id, "status": status}})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_settings():
    data = json.dumps({"type": "settings", "data": room_settings})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_rule(action: str, rule: dict):
    data = json.dumps({"type": "rule", "action": action, "data": rule})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_job(action: str, data: dict):
    payload = json.dumps({"type": "job", "action": action, "data": data})
    _diffuser_flux(payload, "job")
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_schedule(action: str, schedule: dict):
    payload = json.dumps({"type": "schedule", "action": action, "data": schedule})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_session(action: str, session: dict):
    payload = json.dumps({"type": "session", "action": action, "data": session})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(payload)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_hats():
    data = json.dumps({"type": "hats", "data": agent_hats})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


async def broadcast_agents():
    """Send updated agent config (from registry) to all WebSocket clients."""
    agent_cfg = registry.get_agent_config() if registry else {}
    data = json.dumps({"type": "agents", "data": agent_cfg})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


def _on_registry_change():
    """Called from registry (any thread) when instances register/deregister/claim/rename."""
    # Update router with current agent names (base names + registered instances)
    if router and registry:
        base_names = list(registry.get_bases().keys())
        # Only include active instances in routing (pending ones are inert)
        instance_names = registry.get_active_names()
        all_names = list(set(base_names + instance_names))
        router.update_agents(all_names)
    # Broadcast to WebSocket clients
    if _event_loop:
        asyncio.run_coroutine_threadsafe(broadcast_agents(), _event_loop)
        asyncio.run_coroutine_threadsafe(broadcast_status(), _event_loop)


# --- WebSocket ---

def _ws_autorise(websocket) -> bool:
    """Jeton en ?token= ou dans le cookie de session ; une origine étrangère est refusée (le cookie part tout seul)."""
    origine = websocket.headers.get("origin")
    if origine and origine not in origines_permises:
        return False
    return jeton_valide({}, websocket.query_params, websocket.cookies)


def _ws_session_humaine(websocket) -> bool:
    """Le navigateur présente le cookie de session et une origine autorisée.

    Un client qui n'a que le jeton en ?token= (agents et scripts) peut utiliser /ws, mais pas /continue.
    Le champ sender d'un événement WebSocket ne prouve jamais l'identité du client.
    """
    origine = websocket.headers.get("origin")
    return origine in origines_permises and jeton_valide({}, {}, websocket.cookies)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # --- Security: validate session token on WebSocket connect ---
    if not _ws_autorise(websocket):
        # Must accept before closing so the browser receives the close frame.
        # Code 4003 triggers an auto-reload in the client to pick up the new token.
        await websocket.accept()
        await websocket.close(code=4003, reason="forbidden: invalid session token")
        return

    session_humaine = _ws_session_humaine(websocket)
    await websocket.accept()
    ws_clients.add(websocket)

    # Send settings
    await websocket.send_text(json.dumps({"type": "settings", "data": room_settings}))

    # Send registered instances (used for pills/mentions)
    agent_cfg = registry.get_agent_config() if registry else {}
    await websocket.send_text(json.dumps({"type": "agents", "data": agent_cfg}))

    # Send base agent colors (used for message coloring, no pills)
    base_colors = {}
    for name, cfg in config.get("agents", {}).items():
        base_colors[name] = {"color": cfg.get("color", "#888"), "label": cfg.get("label", name)}
    await websocket.send_text(json.dumps({"type": "base_colors", "data": base_colors}))

    # Send todos {msg_id: status}
    await websocket.send_text(json.dumps({"type": "todos", "data": store.get_todos()}))

    # Send rules
    await websocket.send_text(json.dumps({"type": "rules", "data": rules.list_all()}))

    # Send hats
    await websocket.send_text(json.dumps({"type": "hats", "data": agent_hats}))

    # Send jobs
    await websocket.send_text(json.dumps({"type": "jobs", "data": jobs.list_all()}))

    # Send schedules
    await websocket.send_text(json.dumps({"type": "schedules", "data": schedules.list_all()}))

    # Send pending instances (so late-connecting browsers still see the naming lightbox)
    if registry:
        for inst in registry.get_all().values():
            if inst.get("state") == "pending":
                await websocket.send_text(json.dumps({
                    "type": "pending_instance",
                    "name": inst["name"],
                    "base": inst.get("base", ""),
                    "label": inst.get("label", inst["name"]),
                    "color": inst.get("color", "#888"),
                }))

    # Send history (per channel based on history_limit)
    limit_val = room_settings.get("history_limit", "all")
    count = 10000 if limit_val == "all" else int(limit_val)
    
    history = []
    for ch in room_settings["channels"]:
        history.extend(store.get_recent(count, channel=ch))
    
    # Sort history by timestamp to interleave messages from different channels correctly
    history.sort(key=lambda m: m.get("timestamp", 0))
    
    # Saved messages have their own boundary; presence updates can arrive at
    # any time and must never make old history look like new chat.
    for offset in range(0, len(history), 100):
        await websocket.send_text(json.dumps({
            "type": "history", "messages": history[offset:offset + 100],
        }))
        await asyncio.sleep(0)
    await websocket.send_text(json.dumps({"type": "history_complete"}))

    # Send status
    await broadcast_status()

    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)

            if event.get("type") == "message":
                text = event.get("text", "").strip()
                attachments = event.get("attachments", [])
                sender = event.get("sender") or room_settings.get("username", "user")
                channel = event.get("channel", "general")

                if not text and not attachments:
                    continue

                # Command handling
                if text.startswith("/"):
                    cmd_parts = text.split()
                    cmd = cmd_parts[0].lower()
                    if cmd == "/clear":
                        store.clear(channel=channel)
                        await broadcast_clear(channel=channel)
                        continue
                    if cmd == "/continue":
                        # L'identité vient de la connexion, jamais du sender fourni par l'événement.
                        if not session_humaine:
                            store.add("system", "Loop guard: only humans can /continue.",
                                      msg_type="system", channel=channel)
                            continue
                        router.continue_routing(channel)
                        store.add("system", f"Routing resumed by {room_settings.get('username', 'user')}.",
                                  msg_type="system", channel=channel)
                        await broadcast_status()
                        continue
                    # Broadcast slash commands — expand without storing the raw command.
                    # _handle_new_message will store the expanded version.
                    if cmd in ("/hatmaking", "/artchallenge", "/roastreview", "/poetry"):
                        await _handle_new_message({"sender": sender, "text": text, "channel": channel})
                        continue

                # Store message — the on_message callback handles broadcast + triggers
                reply_to = event.get("reply_to")
                if reply_to is not None:
                    reply_to = int(reply_to)

                # SOCLE-SHOP S1/S4 : projet ou tache inconnus = refus, jamais remplaces par d'autres
                projet_id, tache_id, err = _etiquettes(event.get("projet_id"), event.get("tache_id"), channel)
                if err:
                    store.add("system", f"{err} : message non envoyé.", msg_type="system", channel=channel)
                    continue
                store.add(sender, text, attachments=attachments, reply_to=reply_to,
                          channel=channel, projet_id=projet_id, tache_id=tache_id)

            elif event.get("type") == "delete":
                ids = event.get("ids", [])
                if ids:
                    deleted = store.delete([int(i) for i in ids])
                    if deleted:
                        data = json.dumps({"type": "delete", "ids": deleted})
                        dead = set()
                        for client in list(ws_clients):
                            try:
                                await client.send_text(data)
                            except Exception:
                                dead.add(client)
                        ws_clients.difference_update(dead)
                continue

            elif event.get("type") == "todo_add":
                msg_id = event.get("id")
                if msg_id is not None:
                    store.add_todo(int(msg_id))
                    await broadcast_todo_update(int(msg_id), "todo")
                continue

            elif event.get("type") == "todo_toggle":
                msg_id = event.get("id")
                if msg_id is not None:
                    mid = int(msg_id)
                    status = store.get_todo_status(mid)
                    if status == "todo":
                        store.complete_todo(mid)
                        await broadcast_todo_update(mid, "done")
                    elif status == "done":
                        store.reopen_todo(mid)
                        await broadcast_todo_update(mid, "todo")
                continue

            elif event.get("type") == "todo_remove":
                msg_id = event.get("id")
                if msg_id is not None:
                    store.remove_todo(int(msg_id))
                    await broadcast_todo_update(int(msg_id), None)
                continue

            elif event.get("type") in ("decision_propose", "rule_propose"):
                text = event.get("text") or event.get("decision", "")
                text = text.strip()
                author = event.get("author") or event.get("owner") or room_settings.get("username", "user")
                reason = event.get("reason", "")
                is_human = author.lower() == room_settings.get("username", "user").lower()
                if text:
                    rule = rules.propose(text, author, reason)
                    if rule:
                        if is_human:
                            # Human-created rules go straight to draft, no card
                            rules.make_draft(rule["id"])
                        else:
                            # Agent proposals get a card in the timeline
                            channel = event.get("channel", "general")
                            msg = store.add(
                                author, f"Rule proposal: {text}",
                                msg_type="rule_proposal",
                                channel=channel,
                                metadata={"rule_id": rule["id"], "text": text, "status": "pending"},
                            )
                            # store.add() fires _on_store_message → broadcast already.
                            # Do NOT call broadcast(msg) again here.
                continue

            elif event.get("type") in ("decision_approve", "rule_activate"):
                rid = event.get("id")
                if rid is not None:
                    if not rules.activate(int(rid)):
                        await websocket.send_text(json.dumps({
                            "type": "rule_error", "error": "Rule no longer exists. Refresh the page.",
                        }))
                continue

            elif event.get("type") in ("decision_unapprove", "rule_deactivate"):
                rid = event.get("id")
                if rid is not None:
                    rules.deactivate(int(rid))
                continue

            elif event.get("type") == "rule_make_draft":
                rid = event.get("id")
                if rid is not None:
                    rules.make_draft(int(rid))
                continue

            elif event.get("type") in ("decision_edit", "rule_edit"):
                rid = event.get("id")
                if rid is not None:
                    rules.edit(
                        int(rid),
                        text=event.get("text") or event.get("decision"),
                        reason=event.get("reason"),
                    )
                continue

            elif event.get("type") in ("decision_delete", "rule_delete"):
                rid = event.get("id")
                if rid is not None:
                    rules.delete(int(rid))
                continue

            elif event.get("type") == "rule_remind":
                rules.set_remind()
                remind_data = json.dumps({"type": "rules_remind", "data": {}})
                for client in list(ws_clients):
                    try:
                        await client.send_text(remind_data)
                    except Exception:
                        pass
                continue

            elif event.get("type") == "update_settings":
                new = event.get("data", {})
                if "title" in new and isinstance(new["title"], str):
                    room_settings["title"] = new["title"].strip() or "Vaultia"
                apply_room_subtitle(new)
                if "username" in new and isinstance(new["username"], str):
                    room_settings["username"] = new["username"].strip() or "user"
                if "font" in new and new["font"] in ("mono", "serif", "sans"):
                    room_settings["font"] = new["font"]
                if "max_agent_hops" in new:
                    try:
                        hops = int(new["max_agent_hops"])
                        hops = max(1, min(hops, 50))
                        room_settings["max_agent_hops"] = hops
                        router.max_hops = hops
                    except (ValueError, TypeError):
                        pass
                if "anti_spin_ticks" in new:
                    try:
                        ticks = int(new["anti_spin_ticks"])
                        ticks = max(1, min(ticks, 20))
                        room_settings["anti_spin_ticks"] = ticks
                        router.anti_spin_ticks = ticks
                    except (ValueError, TypeError):
                        pass
                if "contrast" in new and new["contrast"] in ("normal", "high"):
                    room_settings["contrast"] = new["contrast"]
                if "rules_refresh_interval" in new:
                    try:
                        ri = int(new["rules_refresh_interval"])
                        room_settings["rules_refresh_interval"] = max(0, min(ri, 100))
                    except (ValueError, TypeError):
                        pass
                if "history_limit" in new:
                    val = str(new["history_limit"]).strip().lower()
                    if val == "all":
                        room_settings["history_limit"] = "all"
                    else:
                        try:
                            val_int = int(val)
                            room_settings["history_limit"] = max(1, min(val_int, 10000))
                        except (ValueError, TypeError):
                            pass
                if "custom_roles" in new and isinstance(new["custom_roles"], list):
                    room_settings["custom_roles"] = [
                        str(r).strip()[:20] for r in new["custom_roles"]
                        if isinstance(r, str) and r.strip()
                    ][:20]
                _save_settings()
                await broadcast_settings()

            elif event.get("type") == "rename_agent":
                agent_name = (event.get("name") or "").strip()
                new_label = (event.get("label") or "").strip()
                if agent_name and new_label and registry:
                    # Derive a sanitized sender ID from the label
                    import re as _re
                    new_id = _re.sub(r'[^a-z0-9-]', '', new_label.lower().replace(' ', '-')).strip('-')
                    if not new_id:
                        new_id = agent_name  # fallback: keep old name, just change label
                    if new_id == agent_name:
                        # Same ID — label-only change
                        registry.set_label(agent_name, new_label)
                    else:
                        result = registry.rename(agent_name, new_id, new_label)
                        if isinstance(result, str):
                            # Rename failed (collision etc.) — fall back to label-only
                            registry.set_label(agent_name, new_label)
                        else:
                            # Migrate presence + cursors to new name
                            import mcp_bridge
                            mcp_bridge.migrate_identity(agent_name, new_id)
                            # Update sender on all historical messages
                            store.rename_sender(agent_name, new_id)
                            _migrate_agent_last_channel(agent_name, new_id)
                            # Notify clients so they can update sender in DOM
                            rename_event = json.dumps({
                                "type": "agent_renamed",
                                "old_name": agent_name,
                                "new_name": new_id,
                            })
                            await _broadcast(rename_event)
                continue

            elif event.get("type") == "name_pending":
                # Human names a pending instance (from lightbox)
                agent_name = (event.get("name") or "").strip()
                new_label = (event.get("label") or "").strip()
                if agent_name and registry:
                    if not new_label:
                        # Accept default name
                        registry.confirm_pending(agent_name)
                    else:
                        import re as _re
                        new_id = _re.sub(r'[^a-z0-9-]', '', new_label.lower().replace(' ', '-')).strip('-')
                        if not new_id:
                            new_id = agent_name
                        if new_id == agent_name:
                            # Same ID — just update label and confirm
                            registry.set_label(agent_name, new_label)
                            registry.confirm_pending(agent_name)
                        else:
                            result = registry.rename(agent_name, new_id, new_label)
                            if isinstance(result, str):
                                # Rename failed — just confirm with label
                                registry.set_label(agent_name, new_label)
                                registry.confirm_pending(agent_name)
                            else:
                                # Rename succeeded — confirm new name
                                registry.confirm_pending(new_id)
                                import mcp_bridge
                                mcp_bridge.migrate_identity(agent_name, new_id)
                                # Update sender on all historical messages
                                store.rename_sender(agent_name, new_id)
                                _migrate_agent_last_channel(agent_name, new_id)
                                rename_event = json.dumps({
                                    "type": "agent_renamed",
                                    "old_name": agent_name,
                                    "new_name": new_id,
                                })
                                await _broadcast(rename_event)
                continue

            elif event.get("type") == "channel_create":
                name = (event.get("name") or "").strip().lower()
                if not name or not _CHANNEL_NAME_RE.match(name):
                    continue
                if name in room_settings["channels"]:
                    continue
                room_settings["channels"].append(name)
                _save_settings()
                await broadcast_settings()

            elif event.get("type") == "channel_rename":
                old_name = (event.get("old_name") or "").strip().lower()
                new_name = (event.get("new_name") or "").strip().lower()
                if old_name == "general":
                    continue
                if not new_name or not _CHANNEL_NAME_RE.match(new_name):
                    continue
                if old_name not in room_settings["channels"]:
                    continue
                if new_name in room_settings["channels"]:
                    continue
                idx = room_settings["channels"].index(old_name)
                room_settings["channels"][idx] = new_name
                store.rename_channel(old_name, new_name)
                import mcp_bridge
                mcp_bridge.migrate_cursors_rename(old_name, new_name)
                _save_settings()
                await broadcast_settings()
                # Tell clients to migrate DOM elements
                rename_event = json.dumps({
                    "type": "channel_renamed",
                    "old_name": old_name,
                    "new_name": new_name,
                })
                for c in list(ws_clients):
                    try:
                        await c.send_text(rename_event)
                    except Exception:
                        pass

            elif event.get("type") == "channel_delete":
                name = (event.get("name") or "").strip().lower()
                if name == "general":
                    continue
                if name not in room_settings["channels"]:
                    continue
                room_settings["channels"].remove(name)
                store.delete_channel(name)
                import mcp_bridge
                mcp_bridge.migrate_cursors_delete(name)
                _save_settings()
                await broadcast_settings()

    except WebSocketDisconnect:
        ws_clients.discard(websocket)
    except Exception:
        ws_clients.discard(websocket)
        log.exception("WebSocket error")


# --- REST endpoints ---

ALLOWED_UPLOAD_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.heic', '.heif', '.pdf', '.txt', '.md', '.csv', '.json', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.rtf', '.odt', '.dxf', '.step', '.stp', '.stl', '.3mf', '.fcstd'}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB default


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    upload_dir = Path(config.get("images", {}).get("upload_dir", "./uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix or ".png"
    if ext.lower() not in ALLOWED_UPLOAD_EXTS:
        return JSONResponse({"error": f"unsupported file type: {ext}"}, status_code=400)

    content = await file.read()
    max_bytes = config.get("images", {}).get("max_size_mb", 10) * 1024 * 1024
    if len(content) > max_bytes:
        return JSONResponse({"error": f"file too large (max {max_bytes // 1024 // 1024} MB)"}, status_code=400)

    filename = f"{uuid.uuid4().hex[:8]}{ext}"
    filepath = upload_dir / filename
    filepath.write_bytes(content)

    return JSONResponse({
        "name": file.filename,
        "url": f"/uploads/{filename}",
    })


# --- Export / Import ---

@app.get("/api/export")
async def export_history():
    """Download a zip archive of project history."""
    import archive as _archive
    import time as _time
    try:
        zip_bytes = _archive.build_export(
            store, jobs, rules, summaries,
            app_version=config.get("server", {}).get("version", ""),
        )
    except Exception as exc:
        return JSONResponse({"error": f"export failed: {exc}"}, status_code=500)
    filename = f"agentchattr-export-{_time.strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/import")
async def import_history(file: UploadFile = File(...)):
    """Upload a zip archive and merge it into current stores."""
    import archive as _archive
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return JSONResponse({"error": "unsupported file type: expected .zip"}, status_code=400)
    content = await file.read()
    if len(content) > _archive.MAX_IMPORT_SIZE:
        return JSONResponse(
            {"error": f"file too large (max {_archive.MAX_IMPORT_SIZE // 1024 // 1024}MB)"},
            status_code=400,
        )
    channel_list = list(room_settings.get("channels", ["general"]))
    max_ch = room_settings.get("max_channels", 8)
    report = _archive.import_archive(
        content, store, jobs, rules, summaries,
        channel_list, max_channels=max_ch,
    )
    if not report.get("ok"):
        error = report.get("error", "import failed")
        status = 409 if "already running" in error else 400
        return JSONResponse({"error": error}, status_code=status)
    # Update channel list if new channels were created
    if report["channels"]["created"]:
        room_settings["channels"] = channel_list
        _save_settings()
        await broadcast_settings()
    # Tell all connected clients to reload (picks up imported messages)
    data = json.dumps({"type": "reload"})
    dead = set()
    for client in list(ws_clients):
        try:
            await client.send_text(data)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)
    return JSONResponse(report)


def _etiquettes(projet_id, tache_id, channel: str = "") -> tuple[str | None, int | None, str]:
    """SOCLE-SHOP S4 : valide l'etiquette projet/tache d'un message. Une tache doit exister et appartenir au
    projet ; sans projet_id, il est repris de la tache. Rend (projet_id, tache_id, erreur).
    v1.0 : un message sans etiquette prend celle de son canal : `tache-<id>` donne la tache, un canal range sous
    un projet donne le projet. Une etiquette explicite garde la priorite."""
    projet_id = str(projet_id or "").strip() or None
    if not projet_id and tache_id in (None, "", 0) and channel:
        tache_id = _jobs_mod.tache_du_canal(channel)
        tache = jobs.get(tache_id) if (jobs and tache_id) else None
        if not tache or not tache.get("projet_id"):  # canal ordinaire, ou nomme tache-N sans tache : jamais de refus
            return (_projets.projet_du_canal(channel) or None), None, ""
    if projet_id and not _projets.existe(projet_id):
        return None, None, f"projet inconnu : {projet_id}"
    if tache_id in (None, "", 0):
        return projet_id, None, ""
    try:
        tache_id = int(tache_id)
    except (TypeError, ValueError):
        return None, None, "tache_id entier attendu"
    tache = jobs.get(tache_id) if jobs else None
    if not tache or not tache.get("projet_id"):
        return None, None, f"tache inconnue : {tache_id}"
    if projet_id and tache["projet_id"] != projet_id:
        return None, None, f"la tache {tache_id} n'appartient pas au projet {projet_id}"
    return tache["projet_id"], tache_id, ""


def _agent_du_jeton(request: Request) -> str:
    """Nom de l'agent si la requete porte un jeton Bearer d'agent enregistre, sinon ''."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or registry is None:
        return ""
    inst = registry.resolve_token(auth[7:].strip())
    return inst["name"] if inst else ""


@app.get("/api/messages")
async def get_messages(request: Request, since_id: int = 0, limit: int = 50, channel: str = "",
                       complet: bool = False):
    ch = channel if channel else None
    # Salle sobre : un AGENT (jeton Bearer) qui lit un canal de tache ne recoit que les messages des humains, ceux
    # qui le mentionnent et les siens (ces agents ne gardent rien entre deux reveils); l'etat est dans la fiche.
    # L'interface (jeton de session) et le chef ([routing] chef) voient tout, comme avant.
    agent = _agent_du_jeton(request)
    chef = str(config.get("routing", {}).get("chef", "")).strip().lower() if config else ""
    sobre = bool(agent) and _sobriete.est_canal_tache(ch) and agent.lower() != chef
    if sobre and not complet:
        tous = store.get_since(since_id, channel=ch) if since_id else store.get_recent(limit * 5, channel=ch)
        inst = registry.get_instance(agent) if registry else None
        msgs, masques = _sobriete.filtrer_pour(tous, agent, _humains(), base=(inst or {}).get("base", ""),
                                               garder_siens=True)
        if sobriete is not None:
            sobriete.masquer(agent, masques)
        return msgs[-limit:]
    msgs = store.get_since(since_id, channel=ch) if since_id else store.get_recent(limit, channel=ch)
    if sobre and complet and sobriete is not None:
        sobriete.ajouter(agent, lecture_complete=1)
    return msgs


@app.get("/api/v2/taches/{tache_id}/fiche")
async def fiche_tache(tache_id: int, request: Request, pour: str = "", reveil: bool = False):
    """Fiche de travail d'une tache (taille bornee). Un agent (jeton Bearer) la lit pour lui-meme : `pour` est
    alors son nom, quel que soit le parametre. `reveil=1` : injectee par le wrapper au declenchement."""
    tache = jobs.get(tache_id) if jobs else None
    if not tache or not tache.get("projet_id"):
        return JSONResponse({"error": "tache inconnue"}, status_code=404)
    agent = _agent_du_jeton(request)
    qui = agent or pour
    livrables = []
    if revisions is not None:
        livrables = [l for l in revisions.livrables(tache["projet_id"]) if str(l.get("tache_id", "")) == str(tache_id)]
    if agent and sobriete is not None:
        sobriete.ajouter(agent, **({"fiche_au_reveil": 1} if reveil else {"tache_lire": 1}))
    return JSONResponse(_jobs_mod.fiche(tache, pour=qui, livrables=livrables))


@app.get("/api/v2/sobriete")
async def rapport_sobriete():
    """Par agent : lectures de la base (fiche) contre lectures du fil, et ce que le filtre a evite."""
    if sobriete is None:
        return JSONResponse({"error": "compteur indisponible"}, status_code=503)
    rapport = sobriete.rapport()
    # Taille de chaque memoire de projet face a la borne d'injection : jamais le texte lui-meme (R3, R4).
    borne = _sobriete.memoire_max(config)
    try:
        projets = _projets.lister()["v2"]["projets"]
    except Exception:
        projets = {}
    rapport["memoires"] = {"borne": borne, "projets": sorted(
        ({"id": pid, "nom": p.get("nom", ""), "statut": p.get("statut", ""),
          "caracteres": len(p.get("memoire") or ""), "tronquee": len(p.get("memoire") or "") > borne}
         for pid, p in projets.items()), key=lambda m: -m["caracteres"])}
    return JSONResponse(rapport)


@app.post("/api/send")
async def api_send(request: Request):
    """REST endpoint for API agents to send messages without WebSocket.

    Authenticated via Bearer registration token. Sender is resolved from
    the token — the agent cannot impersonate another identity.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return JSONResponse({"error": "missing Authorization: Bearer <token>"}, status_code=401)
    token = auth[7:].strip()
    inst = registry.resolve_token(token) if registry else None
    if not inst:
        return JSONResponse({"error": "invalid or expired token"}, status_code=403)

    sender = inst["name"]
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    channel = body.get("channel", "general")
    projet_id, tache_id, err = _etiquettes(body.get("projet_id"), body.get("tache_id"), channel)
    if err:
        return JSONResponse({"error": err}, status_code=422)

    msg = store.add(sender, text, channel=channel, projet_id=projet_id, tache_id=tache_id)
    return JSONResponse(msg)


@app.get("/api/status")
async def get_status():
    status = agents.get_status()
    status["paused"] = any(router.is_paused(ch) for ch in room_settings.get("channels", ["general"]))
    return status


@app.get("/api/settings")
async def get_settings():
    return room_settings


@app.delete("/api/hat/{agent_name}")
async def delete_hat(agent_name: str):
    """Remove an agent's hat (called by the trash-can UI)."""
    clear_agent_hat(agent_name)
    return JSONResponse({"ok": True})


# --- Jobs API ---

@app.get("/api/schedules")
async def get_schedules():
    return schedules.list_all()


@app.post("/api/schedules")
async def create_schedule(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    targets = body.get("targets", [])
    channel = body.get("channel", "general")
    spec = body.get("spec", "")
    one_shot = bool(body.get("one_shot", False))
    send_at_date = body.get("send_at_date", "")  # "YYYY-MM-DD" for one-shot
    created_by = body.get("created_by", "user")
    if not prompt or not targets or not spec:
        return JSONResponse({"error": "prompt, targets, and spec are required"}, status_code=400)
    # A relative send ("in 2h 30m") is resolved by the client, which posts the
    # resulting moment directly; there is no recurrence to parse out of it.
    # A send_at names a single moment, so it only means anything for a one-shot.
    # A recurring request ignores it, exactly as it did before the field
    # existed; that keeps an unparseable spec falling through to the 400 below
    # instead of being stored as an unasked-for daily repeat.
    explicit_send_at = None
    if one_shot and body.get("send_at") is not None:
        try:
            explicit_send_at = float(body["send_at"])
        except (TypeError, ValueError, OverflowError):
            return JSONResponse(
                {"error": "send_at must be an epoch timestamp"}, status_code=400
            )
    interval_sec, daily_at = parse_schedule_spec(spec)
    if interval_sec is None and explicit_send_at is None:
        return JSONResponse({"error": f"Invalid schedule spec: {spec}"}, status_code=400)
    # For one-shot, compute exact send_at timestamp from date + daily_at time
    send_at = explicit_send_at
    if send_at is None and one_shot and daily_at and send_at_date:
        import datetime as _dt
        try:
            dt = _dt.datetime.strptime(f"{send_at_date} {daily_at}", "%Y-%m-%d %H:%M")
            send_at = dt.timestamp()
        except ValueError:
            pass
    try:
        s = schedules.create(
            prompt=prompt, targets=targets, channel=channel,
            interval_seconds=interval_sec, daily_at=daily_at,
            one_shot=one_shot, send_at=send_at,
            created_by=created_by,
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(s)


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    removed = schedules.delete(schedule_id)
    if not removed:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@app.patch("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    result = schedules.toggle(schedule_id)
    if not result:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(result)


@app.get("/api/jobs")
async def get_jobs(channel: str = "", status: str = ""):
    """List jobs, optionally filtered."""
    ch = channel if channel else None
    st = status if status else None
    return jobs.list_all(channel=ch, status=st)


@app.post("/api/messages/{msg_id}/demote")
async def demote_proposal(msg_id: int):
    """Demote a proposal-style message back to a regular chat message."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    msg_type = msg.get("type")
    if msg_type not in {"job_proposal", "session_draft"}:
        return JSONResponse({"error": "not a proposal"}, status_code=400)
    meta = msg.get("metadata", {})
    updated_fields = {"type": "chat", "metadata": {}}

    if msg_type == "job_proposal":
        body_text = meta.get("body", "")
        title = meta.get("title", "")
        plain_text = f"**{title}**\n\n{body_text}" if title else body_text or msg.get("text", "")
        updated_fields["text"] = plain_text
    else:
        tmpl = meta.get("template")
        errors = meta.get("errors", []) or []
        proposed_by = meta.get("proposed_by") or msg.get("sender", "system")
        parts = []

        if isinstance(tmpl, dict):
            name = str(tmpl.get("name", "")).strip()
            desc = str(tmpl.get("description", "")).strip()
            if name:
                parts.append(f"**{name}**")
            if desc:
                parts.append(desc)
            phases = tmpl.get("phases") or []
            if phases:
                lines = []
                for i, ph in enumerate(phases, 1):
                    ph_name = ph.get("name", f"Round {i}")
                    participants = ", ".join(ph.get("participants", []))
                    line = f"{i}. {ph_name}"
                    if participants:
                        line += f" -- {participants}"
                    prompt = (ph.get("prompt") or "").strip()
                    if prompt:
                        line += f"\n   {prompt}"
                    lines.append(line)
                parts.append("\n".join(lines))
        else:
            label = str(msg.get("text", "")).strip() or "Session draft"
            parts.append(label)
            if errors:
                parts.append("\n".join(f"- {e}" for e in errors))

        updated_fields["sender"] = proposed_by
        updated_fields["text"] = "\n\n".join(p for p in parts if p).strip()

    updated = store.update_message(msg_id, updated_fields)
    if updated:
        # Broadcast the updated message to all clients
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


def _etiquette_reponse(projet_id, tache_id, channel: str) -> tuple[str | None, int | None]:
    """Etiquette de la reponse de Charles a une carte de decision : celle de la carte, qui l'emporte sur le canal.
    Une carte qui n'a que son projet prend la tache de son canal `tache-<id>`, seulement si cette tache est du meme
    projet (revue codex-1 msg 4934, cas fixes par claude-1 msg 4935). Une etiquette invalide (tache ou projet
    disparu) donne une reponse sans etiquette : elle part quand meme."""
    projet, tache, err = _etiquettes(projet_id, tache_id, channel)
    if err:
        return None, None
    if projet and tache is None and jobs is not None:
        du_canal = jobs.get(_jobs_mod.tache_du_canal(channel) or 0)
        if du_canal and du_canal.get("projet_id") == projet:
            tache = du_canal["id"]
    return projet, tache


def _liberer_tache_attente(tache_id) -> None:
    """Vaultia (19 oct. 2026) : une tâche « attend_charles » dont la dernière carte ouverte vient d'être tranchée
    repasse « en_cours ». Sinon l'atelier affichait « t'attend » sans rien à trancher (t22, quatre jours)."""
    if jobs is None or not tache_id:
        return
    try:
        tid = int(tache_id)
        tache = jobs.get(tid)
        if not tache or tache.get("etat") != "attend_charles":
            return
        if any(m.get("type") == "decision" and not (m.get("metadata") or {}).get("resolved")
               for m in store.filtrer(None, tid, -1, 0)):
            return
        _, err = jobs.update_tache(tid, {"etat": "en_cours"})
        if err:
            log.warning("tache %s : retour en_cours refuse (%s)", tid, err)
            return
        _note_round_progress(_jobs_mod.canal_tache(tid))
    except Exception:
        log.exception("tache %s : liberation apres decision", tache_id)


@app.post("/api/messages/{msg_id}/resolve_decision")
async def resolve_decision(msg_id: int, request: Request):
    """Resolve an inline decision card by recording the chosen option."""
    body = await request.json()
    # Vaultia : « Répondu autrement » ferme la carte SANS choix de la liste et SANS publier de
    # message (Charles a répondu en texte). Sinon « @agent Répondu autrement » relançait l'agent.
    autrement = bool(body.get("autrement"))
    # Vaultia : « Autre réponse… » — Charles écrit sa propre réponse au lieu d'un choix proposé ;
    # elle part à l'agent comme un choix (« @agent sa réponse »), hors de la liste.
    texte = str(body.get("texte") or "").strip()[:2000]
    autre = bool(texte) and not autrement
    chosen = "Répondu autrement" if autrement else (texte or body.get("choice", ""))
    if not chosen:
        return JSONResponse({"error": "choice is required"}, status_code=400)
    # Atomic check + resolve under lock to prevent double-click race
    error = None
    channel = "general"
    sender = ""
    tache_id = None
    projet_id = None
    with store._lock:
        msg = None
        for m in store._messages:
            if m["id"] == msg_id:
                msg = m
                break
        if not msg:
            error = ("message not found", 404)
        elif msg.get("type") != "decision":
            error = ("not a decision message", 400)
        else:
            meta = msg.get("metadata") or {}
            if meta.get("resolved"):
                error = ("already resolved", 400)
            else:
                valid_choices = meta.get("choices", [])
                if not autrement and not autre and valid_choices and chosen not in valid_choices:
                    error = (f"invalid choice. Valid: {valid_choices}", 400)
                else:
                    meta["resolved"] = True
                    meta["chosen"] = chosen
                    if autrement:
                        meta["autrement"] = True
                    if autre:
                        meta["autre"] = True
                    msg["metadata"] = meta
                    channel = msg.get("channel", "general")
                    sender = msg.get("sender", "")
                    tache_id = msg.get("tache_id")
                    projet_id = msg.get("projet_id")
                    store._rewrite()
    if error:
        return JSONResponse({"error": error[0]}, status_code=error[1])
    # Post the chosen answer as a regular chat message tagged @sender (pas pour « Répondu autrement »)
    if not autrement:
        username = room_settings.get("username", "user")
        reply_text = f"@{sender} {chosen}" if sender else chosen
        # La reponse porte l'etiquette de la carte (sinon celle de son canal) : elle reste dans la conversation de la
        # tache et dans le flux de l'atelier (tache-22 : msgs 4872 et 4874 etaient sans tache).
        rep_projet, rep_tache = _etiquette_reponse(projet_id, tache_id, channel)
        try:
            store.add(username, reply_text, reply_to=msg_id, channel=channel, projet_id=rep_projet, tache_id=rep_tache)
        except Exception:
            import traceback; traceback.print_exc()
    _liberer_tache_attente(tache_id)
    # Broadcast updated decision card so the UI swaps buttons to resolved state
    updated = store.get_by_id(msg_id)
    if updated:
        await _broadcast(json.dumps({"type": "message_update", "message": updated}))
    return {"ok": True, "chosen": chosen}


@app.post("/api/messages/{msg_id}/resolve_rule_proposal")
async def resolve_rule_proposal(msg_id: int, request: Request):
    """Activate or dismiss a rule proposal."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    if msg.get("type") != "rule_proposal":
        return JSONResponse({"error": "not a rule proposal"}, status_code=400)
    body = await request.json()
    action = body.get("action", "")
    meta = dict(msg.get("metadata") or {})
    rule_id = meta.get("rule_id")

    if action == "activate" and rule_id is not None:
        if not rules.activate(int(rule_id)):
            return JSONResponse({"error": "Rule no longer exists."}, status_code=409)
        meta["status"] = "activated"
    elif action == "draft" and rule_id is not None:
        if not rules.make_draft(int(rule_id)):
            return JSONResponse({"error": "Rule no longer exists."}, status_code=409)
        meta["status"] = "drafted"
    elif action == "dismiss" and rule_id is not None:
        rules.delete(int(rule_id))
        meta["status"] = "dismissed"
    else:
        return JSONResponse({"error": "invalid action"}, status_code=400)

    updated = store.update_message(msg_id, {"metadata": meta})
    if updated:
        # Broadcast the updated message so all clients re-render the card
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


@app.post("/api/messages/{msg_id}/demote_rule_proposal")
async def demote_rule_proposal(msg_id: int):
    """Demote a rule_proposal message back to a regular chat message and delete the rule."""
    msg = store.get_by_id(msg_id)
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    if msg.get("type") != "rule_proposal":
        return JSONResponse({"error": "not a rule proposal"}, status_code=400)
    meta = msg.get("metadata", {})
    rule_id = meta.get("rule_id")
    if rule_id is not None:
        rules.delete(int(rule_id))
    text = meta.get("text", msg.get("text", ""))
    updated = store.update_message(msg_id, {
        "type": "chat",
        "text": text,
        "metadata": {},
    })
    if updated:
        payload = json.dumps({"type": "edit", "message": updated})
        dead = set()
        for client in list(ws_clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        ws_clients.difference_update(dead)
    return updated or {"ok": True}


@app.post("/api/trigger-agent")
async def trigger_agent_silent(request: Request):
    """Silently trigger an agent with a message (no chat message posted)."""
    body = await request.json()
    agent_name = body.get("agent", "").strip()
    message = body.get("message", "").strip()
    channel = body.get("channel", "general")
    source_msg_id = body.get("source_msg_id")
    if not agent_name or not message:
        return JSONResponse({"error": "agent and message required"}, status_code=400)

    custom_prompt = body.get("prompt", "").strip()
    if not custom_prompt:
        if source_msg_id is not None:
            custom_prompt = (
                f"use mcp to read #{channel} - you're mentioned, take appropriate action and respond "
                f"- conversion request: use chat history to find message #{source_msg_id} "
                f"and use chat_propose_job to propose it as a job with title<=80 chars and body<=500 chars."
            )
        else:
            custom_prompt = (
                f"use mcp to read #{channel} - you're mentioned, take appropriate action and respond "
                f"- conversion request: use chat_propose_job to propose a job from the referenced message."
            )
    # Resolve to instances if multi-instance
    targets = [agent_name]
    if registry:
        resolved = registry.resolve_to_instances(agent_name)
        if resolved:
            targets = resolved
    for target in targets:
        if agents.is_available(target):
            await agents.trigger(target, message=message, channel=channel, prompt=custom_prompt)
    return {"ok": True, "triggered": targets}


@app.post("/api/jobs")
async def create_job(request: Request):
    """Create a new job."""
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "title required"}, status_code=400)
    job_type = body.get("type", "job")
    channel = body.get("channel", "general")
    created_by = body.get("created_by", "user")
    anchor_msg_id = body.get("anchor_msg_id")
    assignee = body.get("assignee", "")
    job_body = body.get("body", "")
    result = jobs.create(
        title=title, job_type=job_type, channel=channel,
        created_by=created_by, anchor_msg_id=anchor_msg_id,
        assignee=assignee, body=job_body,
    )
    # Mark the proposal message as accepted so it persists across refresh
    if anchor_msg_id:
        anchor_msg = store.get_by_id(anchor_msg_id)
        if anchor_msg and anchor_msg.get("type") == "job_proposal":
            meta = dict(anchor_msg.get("metadata", {}))
            meta["status"] = "accepted"
            updated_msg = store.update_message(anchor_msg_id, {"metadata": meta})
            if updated_msg:
                payload = json.dumps({"type": "edit", "message": updated_msg})
                dead = set()
                for client in list(ws_clients):
                    try:
                        await client.send_text(payload)
                    except Exception:
                        dead.add(client)
                ws_clients.difference_update(dead)
    # Post breadcrumb in main timeline with job_id for clickable link
    store.add(created_by, f"Job created: {title}", msg_type="job_created",
              channel=channel, metadata={"job_id": result["id"]})
    return result


@app.patch("/api/jobs/{job_id}")
async def update_job(job_id: int, request: Request):
    """Update a job's status, title, or assignee."""
    body = await request.json()
    result = None
    if "status" in body:
        result = jobs.update_status(job_id, body["status"])
    if "title" in body:
        result = jobs.update_title(job_id, body["title"])
    if "assignee" in body:
        result = jobs.update_assignee(job_id, body["assignee"])
    if result is None:
        return JSONResponse({"error": "not found or invalid"}, status_code=404)
    return result


@app.post("/api/jobs/reorder")
async def reorder_jobs(request: Request):
    """Reorder jobs within a status group (globally, not per-channel)."""
    body = await request.json()
    status = body.get("status", "open")
    ordered_ids = body.get("ordered_ids", [])
    if not isinstance(ordered_ids, list) or len(ordered_ids) == 0:
        return JSONResponse({"error": "ordered_ids required"}, status_code=400)
    updated = jobs.reorder(status=status, ordered_ids=ordered_ids)
    return {"ok": True, "updated": len(updated)}


@app.get("/api/jobs/{job_id}/messages")
async def get_job_messages(job_id: int):
    """Get all messages in a job."""
    msgs = jobs.get_messages(job_id)
    if msgs is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return msgs


@app.post("/api/jobs/{job_id}/messages")
async def post_job_message(job_id: int, request: Request):
    """Post a message to a job."""
    body = await request.json()
    text = body.get("text", "").strip()
    sender = body.get("sender", "user")
    attachments = body.get("attachments", [])
    if not text and not attachments:
        return JSONResponse({"error": "text or attachments required"}, status_code=400)
    msg_type = body.get("type", "chat")
    msg = jobs.add_message(job_id, sender, text,
                           attachments=attachments, msg_type=msg_type)
    if msg is None:
        return JSONResponse({"error": "job not found"}, status_code=404)

    # Route @mentions in job messages to agents (with job_id context)
    job = jobs.get(job_id)
    if job:
        channel = job.get("channel", "general")
        raw_targets = router.get_targets(sender, text, channel)
        targets = []
        for t in raw_targets:
            if registry:
                targets.extend(registry.resolve_to_instances(t))
            else:
                targets.append(t)
        targets = list(dict.fromkeys(targets))

        import mcp_bridge
        chat_msg = f"{sender}: {text}" if text else ""
        for target in targets:
            if registry:
                inst = registry.get_instance(target)
                if inst and inst.get("state") == "pending":
                    continue
            if agents.is_available(target):
                await agents.trigger(target, message=chat_msg, channel=channel,
                                     job_id=job_id)

    return msg


@app.delete("/api/jobs/{job_id}/messages/{msg_id}")
async def delete_job_message(job_id: int, msg_id: int):
    """Soft-delete a message in a job thread."""
    result = jobs.delete_message(job_id, msg_id)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True, **result}


@app.post("/api/jobs/{job_id}/messages/{msg_index}/resolve")
async def resolve_job_message(job_id: int, msg_index: int, request: Request):
    """Resolve a suggestion message (accept/dismiss)."""
    body = await request.json()
    resolution = body.get("resolution", "dismissed")
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    msgs = job.get("messages", [])
    if msg_index < 0 or msg_index >= len(msgs):
        return JSONResponse({"error": "invalid message index"}, status_code=400)
    msg = msgs[msg_index]
    msg["resolved"] = resolution
    jobs._save()

    # If accepted, trigger the suggesting agent with context
    if resolution == "accepted" and msg.get("sender"):
        agent_name = msg["sender"]
        channel = job.get("channel", "general")
        if agents.is_available(agent_name):
            await agents.trigger(agent_name,
                                 message=f"Your suggestion was accepted: {msg.get('text', '')}",
                                 channel=channel, job_id=job_id)

    return {"ok": True, "resolution": resolution}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int, request: Request):
    """Delete or archive a job. ?permanent=true for real delete."""
    permanent = request.query_params.get("permanent", "").lower() == "true"
    if permanent:
        result = jobs.delete(job_id)
    else:
        result = jobs.update_status(job_id, "archived")
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return result


@app.get("/api/roles")
async def get_roles():
    """Get all agent roles."""
    import mcp_bridge
    return mcp_bridge.get_all_roles()


@app.post("/api/roles/{agent_name}")
async def set_agent_role(agent_name: str, request: Request):
    """Set or clear an agent's role."""
    import mcp_bridge
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    role = body.get("role", "").strip()
    mcp_bridge.set_role(agent_name, role)
    await broadcast_status()
    return JSONResponse({"ok": True, "role": role})


# --- Effort de raisonnement par agent (Vaultia) ---

_EFFORTS_VALIDES = {"", "rapide", "standard", "profond"}


@app.get("/api/efforts")
async def get_efforts():
    import mcp_bridge
    return mcp_bridge.get_all_efforts()


@app.post("/api/efforts/{agent_name}")
async def set_agent_effort(agent_name: str, request: Request):
    """Fixe l'effort de raisonnement d'un agent.

    Pour un agent API (Qwen local, etc.), il s'applique au message suivant. Pour un
    agent CLI (Claude, Codex), il est retenu et pris au prochain lancement de l'agent.
    """
    import mcp_bridge
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    effort = str(body.get("effort", "")).strip().lower()
    if effort not in _EFFORTS_VALIDES:
        return JSONResponse({"error": "effort invalide (rapide, standard, profond, ou vide)"}, status_code=400)
    mcp_bridge.set_effort(agent_name, effort)
    await broadcast_status()
    return JSONResponse({"ok": True, "effort": effort})


# --- Modele choisi par agent (Vaultia) ---

@app.get("/api/models_choice")
async def get_models_choice():
    import mcp_bridge
    return mcp_bridge.get_all_models()


@app.post("/api/models_choice/{agent_name}")
async def set_agent_model(agent_name: str, request: Request):
    """Epingle un modele pour un agent (vide = Auto/defaut). Agent API/CLI-print : au message
    suivant. Agent CLI en terminal (claude/codex) : au prochain lancement."""
    import mcp_bridge
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    model = str(body.get("model", "")).strip()
    mcp_bridge.set_model(agent_name, model)
    await broadcast_status()
    return JSONResponse({"ok": True, "model": model})


# --- Statistiques de consommation (Vaultia) ---

@app.get("/api/stats")
async def get_stats():
    """Consommation estimee par agent, calculee a la demande depuis les messages produits.
    Les CLI (claude/codex/cursor/gemini) ne rapportent pas leurs jetons : l'estimation vient
    du texte publie (~4 caracteres par jeton). Honnete sur son approximation."""
    msgs = store.get_recent(count=100000)
    par_agent: dict[str, dict] = {}
    agents_connus = set(registry.get_agent_config().keys()) if registry else set()
    for m in msgs:
        exp = m.get("sender", "")
        if not exp or exp == "system":
            continue
        texte = m.get("text", "") or ""
        e = par_agent.setdefault(exp, {"messages": 0, "caracteres": 0, "jetons_estimes": 0, "est_agent": exp in agents_connus})
        e["messages"] += 1
        e["caracteres"] += len(texte)
        e["jetons_estimes"] += max(1, len(texte) // 4)
    return JSONResponse({"par_agent": par_agent, "note": "Estimation ~4 caracteres/jeton d'apres le texte publie ; les CLI ne rapportent pas leurs jetons."})


# --- Projets avec memoire propre (Vaultia) ---

import projects as _projets


@app.get("/api/projects")
async def get_projects():
    return JSONResponse(_projets.lister())


@app.post("/api/projects")
async def create_project(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    nom = str(body.get("name", "")).strip()
    if not nom:
        return JSONResponse({"error": "nom requis"}, status_code=400)
    _projets.creer(nom, str(body.get("memory", "")))
    return JSONResponse({"ok": True, **_projets.lister()})


@app.post("/api/projects/{name}/memory")
async def set_project_memory(name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not _projets.definir_memoire(name, str(body.get("memory", ""))):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True})


@app.get("/api/projects/{projet_id}/memory")
async def get_project_memory(projet_id: str):
    """SOCLE-SHOP S1 : la memoire d'UN projet, pour le declenchement qui porte ce projet_id.
    Inconnu = 404, sans repli sur un autre projet."""
    info = _projets.memoire_projet(projet_id)
    if info is None:
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse(info)


@app.get("/api/projects/channel/{channel}/memory")
async def get_channel_project_memory(channel: str):
    """Declenchement sans projet_id : seul un canal d'avant la Shop, rattache a un projet, porte une
    memoire. Sinon : aucune (pas de projet par defaut)."""
    pid = _projets.projet_du_canal(channel)
    info = _projets.memoire_projet(pid) if pid else None
    return JSONResponse(info or {"projet_id": "", "nom": "", "statut": "", "memoire": ""})


@app.post("/api/projects/{name}/status")
async def set_project_status(name: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    statut = str(body.get("status", "")).strip()
    if statut not in _projets.STATUTS:
        return JSONResponse({"error": f"statut parmi {', '.join(_projets.STATUTS)}"}, status_code=400)
    if not _projets.definir_statut(name, statut):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


@app.post("/api/projects/{name}/activate")
async def activate_project(name: str):
    if not _projets.activer(name):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


@app.delete("/api/projects/{name}")
async def delete_project(name: str):
    _projets.supprimer(name)
    return JSONResponse({"ok": True, **_projets.lister()})


@app.post("/api/projects/assign")
async def assign_channel(request: Request):
    """Range une conversation (canal) dans un projet, ou l'en retire (project vide)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    canal = str(body.get("channel", "")).strip()
    projet = str(body.get("project", "")).strip()
    if not canal:
        return JSONResponse({"error": "canal requis"}, status_code=400)
    if not _projets.assigner_canal(canal, projet):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


# SOCLE-SHOP S1 : routes v2, identifiant strict (jamais le nom). Un nom egal a l'ID d'un autre projet
# ne peut donc pas viser le mauvais projet (revue codex msg 2100). Les routes v1 ci-dessus restent par nom.
@app.post("/api/v2/projects/{projet_id}/memory")
async def set_project_memory_v2(projet_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not _projets.definir_memoire(projet_id, str(body.get("memory", "")), par_id=True):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/v2/projects/{projet_id}/status")
async def set_project_status_v2(projet_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    statut = str(body.get("status", "")).strip()
    if statut not in _projets.STATUTS:
        return JSONResponse({"error": f"statut parmi {', '.join(_projets.STATUTS)}"}, status_code=400)
    if not _projets.definir_statut(projet_id, statut, par_id=True):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


@app.delete("/api/v2/projects/{projet_id}")
async def delete_project_v2(projet_id: str):
    if not _projets.supprimer(projet_id, par_id=True):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


@app.post("/api/v2/projects/assign")
async def assign_channel_v2(request: Request):
    """Comme /api/projects/assign, mais `projet_id` est un identifiant strict (vide = detacher)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    canal = str(body.get("channel", "")).strip()
    projet_id = str(body.get("projet_id", "")).strip()
    if not canal:
        return JSONResponse({"error": "canal requis"}, status_code=400)
    if not _projets.assigner_canal(canal, projet_id, par_id=True):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"ok": True, **_projets.lister()})


# SOCLE-SHOP S4 : filtres « Ce projet » / « Ce sujet » sur la conversation unique.
@app.get("/api/v2/messages")
async def filtrer_messages(projet_id: str = "", tache_id: int = 0, since_id: int = -1, limit: int = 100):
    if not projet_id and not tache_id:
        return JSONResponse({"error": "projet_id ou tache_id requis"}, status_code=400)
    if projet_id and not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"messages": store.filtrer(projet_id or None, tache_id or None, since_id,
                                                   max(1, min(limit, 500)))})


# Atelier v3 : flux en direct. Le jeton passe en ?token= (EventSource ne pose pas d'en-tête) ; un battement toutes
# les 20 s garde la connexion ouverte à travers les relais (Tailscale) et détecte un client parti.
@app.get("/api/v2/flux")
async def flux_atelier(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _flux_abonnes.add(q)

    async def evenements():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    donnee = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {donnee}\n\n"
                except asyncio.TimeoutError:
                    yield ": battement\n\n"
        finally:
            _flux_abonnes.discard(q)

    return StreamingResponse(evenements(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# Atelier v3 : notifications poussées. La clé publique VAPID sert à l'abonnement du navigateur ; l'abonnement
# (adresse du service de push + clés du navigateur) reste dans data/push_abonnements.json.
@app.get("/api/v2/push/cle")
async def push_cle():
    if notifs is None:
        return JSONResponse({"error": "notifications indisponibles"}, status_code=503)
    return JSONResponse({"cle": notifs.cle_publique()})


@app.post("/api/v2/push/abonner")
async def push_abonner(request: Request):
    if notifs is None:
        return JSONResponse({"error": "notifications indisponibles"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    err = notifs.abonner(body)
    return JSONResponse({"error": err}, status_code=400) if err else JSONResponse({"ok": True})


@app.post("/api/v2/push/desabonner")
async def push_desabonner(request: Request):
    if notifs is None:
        return JSONResponse({"error": "notifications indisponibles"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    notifs.desabonner(str((body or {}).get("endpoint") or ""))
    return JSONResponse({"ok": True})


@app.post("/api/v2/push/essai")
async def push_essai():
    if notifs is None:
        return JSONResponse({"error": "notifications indisponibles"}, status_code=503)
    n = await asyncio.to_thread(notifs.envoyer, "Notifications de l'atelier", "C'est branché : tu seras prévenu quand une décision t'attend.",
                                "/atelier#/", "essai", 0)
    return JSONResponse({"envoyees": n, "appareils": len(notifs.abonnements())})


# Atelier v3 : Charles écrit dans la conversation d'une tâche sans quitter l'atelier. Même circuit que la
# salle (store.add → diffusion + réveil des @agent), sans la connexion WebSocket qui renvoie tout l'historique.
# L'expéditeur est toujours l'utilisateur de la salle : il n'est jamais lu du corps (pas d'usurpation d'agent).
@app.post("/api/v2/messages")
async def ecrire_message(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "objet attendu"}, status_code=400)
    channel = str(body.get("channel") or "").strip()
    if not channel or channel not in room_settings.get("channels", []):
        return JSONResponse({"error": "canal inconnu"}, status_code=404)
    text = str(body.get("text") or "").strip()[:20000]
    # Pièces jointes : seulement des fichiers déjà déposés par /api/upload (jamais une URL externe).
    pieces_jointes = []
    for a in body.get("attachments") or []:
        if isinstance(a, dict) and str(a.get("url", "")).startswith("/uploads/") and ".." not in str(a.get("url")):
            pieces_jointes.append({"name": str(a.get("name") or "")[:200], "url": str(a["url"])[:500]})
    if not text and not pieces_jointes:
        return JSONResponse({"error": "texte ou pièce jointe requis"}, status_code=400)
    reply_to = body.get("reply_to")
    try:
        reply_to = int(reply_to) if reply_to not in (None, "") else None
    except (TypeError, ValueError):
        return JSONResponse({"error": "reply_to entier attendu"}, status_code=400)
    projet_id, tache_id, err = _etiquettes(body.get("projet_id"), body.get("tache_id"), channel)
    if err:
        return JSONResponse({"error": err}, status_code=422)
    msg = store.add(room_settings.get("username", "user"), text, attachments=pieces_jointes, reply_to=reply_to,
                    channel=channel, projet_id=projet_id, tache_id=tache_id)
    return JSONResponse(msg)


# Historique d'un projet (module de grok, lecture seule). Les id deviennent du texte, comme le veut son contrat.
@app.get("/api/v2/projects/{projet_id}/historique")
async def projet_historique(projet_id: str, limite: int = 200):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    msgs = [{**m, "id": str(m["id"])} for m in store.filtrer(projet_id, None, -1, 0)]
    execs = [{**e, "id": str(e["id"])} for e in executions.lister(projet_id)]
    revs = revisions.revisions(projet_id) if revisions else []
    jals = _jalons_mod.pour_historique(jalons.lister(projet_id)) if jalons else []
    lignes = _historique.historique(projet_id, messages=msgs, executions=execs, revisions=revs, jalons=jals,
                                    limite=max(1, min(limite, 1000)))
    return JSONResponse([[jour, entrees] for jour, entrees in _historique.par_jour(lignes)])


# SOCLE-SHOP S5 : livrables et revisions figees. Seul Charles (« user ») approuve une revision.
@app.get("/api/v2/projects/{projet_id}/revisions")
async def projet_revisions(projet_id: str):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"livrables": revisions.livrables(projet_id), "revisions": revisions.revisions(projet_id)})


@app.post("/api/v2/projects/{projet_id}/livrables")
async def projet_ajouter_livrable(projet_id: str, request: Request):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    tache_id = body.get("tache_id")
    if tache_id not in (None, ""):
        _, _, err = _etiquettes(projet_id, tache_id)
        if err:
            return JSONResponse({"error": err}, status_code=422)
    try:
        l = revisions.ajouter_livrable(projet_id, str(tache_id or ""), str(body.get("chemin", "")))
    except FileNotFoundError:
        return JSONResponse({"error": "fichier absent"}, status_code=404)
    except ValueError as err:
        return JSONResponse({"error": str(err)}, status_code=400)
    # Progres reel : un livrable produit fait avancer la ronde (canal de la tache, sinon orchestration).
    _note_round_progress(_jobs_mod.canal_tache(tache_id) if tache_id not in (None, "") else _canal_orchestration())
    return JSONResponse(l)


@app.post("/api/v2/projects/{projet_id}/revisions")
async def projet_approuver(projet_id: str, request: Request):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if str(body.get("approuvee_par", "")) != "user":
        return JSONResponse({"error": "seul Charles approuve une revision"}, status_code=403)
    try:
        r = revisions.approuver(projet_id, "user")
    except FileNotFoundError as err:
        return JSONResponse({"error": f"livrable disparu : {err}"}, status_code=409)
    except ValueError as err:
        return JSONResponse({"error": str(err)}, status_code=409)
    # Progres reel : une revision figee (revue rendue) fait avancer la ronde du projet.
    _note_round_progress(_canal_orchestration())
    return JSONResponse(r)


@app.get("/api/v2/projects/{projet_id}/revisions/{numero}/verifier")
async def projet_verifier(projet_id: str, numero: str):
    try:
        return JSONResponse({"livrables": revisions.verifier(projet_id, numero)})
    except KeyError:
        return JSONResponse({"error": "revision inconnue"}, status_code=404)


# Visualiseur de livrables (14 oct. 2026, Charles msg du 13 oct.) : servir le CONTENU d'un livrable
# pour le LIRE dans l'atelier (une preuve n'etait qu'une ligne de texte, sans acces au document).
# Borne a racine_livrables par le MEME garde-fou que S5 (RevisionStore.resoudre : chemin absolu,
# « .. » ou lien qui sort de la racine = refuse). Protege par le token de session comme toute route.
_LIVR_TEXTE = {".md", ".markdown", ".txt", ".csv", ".json"}
_LIVR_IMAGE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
# Types connus servis en telechargement (jamais rendus inline) ; un type inconnu tombe sur octet-stream.
_LIVR_TELECHARGER = {".pdf": "application/pdf", ".step": "application/step", ".stp": "application/step",
                     ".stl": "model/stl", ".dxf": "image/vnd.dxf", ".fcstd": "application/octet-stream",
                     ".3mf": "model/3mf", ".iges": "model/iges", ".igs": "model/iges",
                     ".obj": "model/obj", ".glb": "model/gltf-binary"}
_LIVR_MAX_TEXTE = 2 * 1024 * 1024  # 2 Mio : au-dela, on ne rend pas le texte inline (message clair).


@app.get("/api/v2/livrable")
async def livrable_contenu(chemin: str = ""):
    """Contenu d'un livrable sous racine_livrables, pour le visualiseur de l'atelier.
    - .md/.markdown/.txt/.csv/.json -> JSON {chemin, type:"texte", ext, contenu} (rendu inline cote client) ;
      au-dela de 2 Mio -> JSON {type:"trop_volumineux"} avec un message, sans servir le texte.
    - .png/.jpg/.jpeg/.gif/.webp/.svg -> FileResponse image, inline, sans droit d'executer (CSP).
    - tout autre type (PDF, STEP/STL/DXF/FCStd, binaire) -> FileResponse en telechargement, jamais rendu.
    Un futur type CAO (apercu 3D, « Ouvrir dans FreeCAD ») se branche cote client sur l'extension/type."""
    if revisions is None:
        return JSONResponse({"error": "store des livrables indisponible"}, status_code=503)
    try:
        f = revisions.resoudre(chemin)
    except ValueError as err:
        return JSONResponse({"error": f"chemin refuse : {err}"}, status_code=403)
    if not f.is_file():
        return JSONResponse({"error": f"livrable introuvable : {chemin}"}, status_code=404)
    ext = f.suffix.lower()
    # 1) Texte lisible inline (markdown, texte, csv, json) : echappe et rendu cote client, jamais en HTML brut.
    if ext in _LIVR_TEXTE:
        taille = f.stat().st_size
        if taille > _LIVR_MAX_TEXTE:
            return JSONResponse({"chemin": chemin, "type": "trop_volumineux", "octets": taille,
                                 "message": f"Fichier de {taille // 1024} Kio — trop gros pour l'aperçu "
                                            f"(limite {_LIVR_MAX_TEXTE // (1024 * 1024)} Mio). "
                                            f"Télécharge-le pour le lire."})
        contenu = f.read_text("utf-8", errors="replace")
        return JSONResponse({"chemin": chemin, "type": "texte", "ext": ext[1:], "contenu": contenu})
    # 2) Image : servie inline. Un SVG peut porter du script : on le sert sans droit d'executer quoi que ce soit.
    if ext in _LIVR_IMAGE:
        entetes = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                   "X-Content-Type-Options": "nosniff"}
        return FileResponse(f, media_type=_LIVR_IMAGE[ext], headers=entetes,
                            content_disposition_type="inline", filename=f.name)
    # 3) Tout le reste : telechargement, jamais rendu ici (type inconnu = octet-stream).
    media = _LIVR_TELECHARGER.get(ext, "application/octet-stream")
    return FileResponse(f, media_type=media, headers={"X-Content-Type-Options": "nosniff"},
                        content_disposition_type="attachment", filename=f.name)


# SOCLE-SHOP S6 : ce que la ronde planifiee du gestionnaire doit traiter, pour les projets actifs.
@app.get("/api/v2/ronde")
async def get_ronde():
    v2 = _projets.lister()["v2"]["projets"]
    taches = [t for pid in v2 for t in jobs.taches(pid)]
    sortie = _ronde(v2, taches, executions.lister(), jalons.lister() if jalons else [], _methodes_etapes())
    sortie["alertes"] = _alertes_sauvegarde(bool(_copie_pieces[0])) if pieces is not None else []
    sortie["agents_inactifs"] = _agents_inactifs()
    actifs = {pid for pid, p in v2.items() if p.get("statut", "actif") == "actif"}
    sortie["taches_muettes"] = taches_muettes(
        [t for t in taches if t.get("projet_id") in actifs],
        _derniers_messages_canaux(),
        time.time(),
    )
    sortie["rien_a_faire"] = (sortie["rien_a_faire"] and not sortie["alertes"]
                              and not sortie["agents_inactifs"] and not sortie["taches_muettes"])
    return JSONResponse(sortie)


def _humains() -> set[str]:
    """Les noms sous lesquels Charles ecrit dans la salle."""
    return {"user", str(room_settings.get("username") or "user")}


def _derniers_messages_canaux() -> dict[str, float]:
    """`tache-<id>` -> epoch du dernier message d'agent de la tache. Un message de Charles ou du systeme, ou le rappel
    qu'un agent s'adresse a lui-meme, n'est pas un signe de vie (tache-22 : t21 se disait muette depuis 2 h, alors
    qu'aucun agent n'avait ecrit depuis 83 h)."""
    if store is None:
        return {}
    return _progression.derniers_messages_agents(store.get_since(-1), _humains())


_DEMARRAGE = time.time()


def _agents_inactifs() -> list[dict]:
    """Agents en ligne (presence fraiche) sans activite depuis 20 min (ronde v3)."""
    import mcp_bridge
    from ronde import agents_inactifs
    maintenant = time.time()
    with mcp_bridge._presence_lock:
        en_ligne = {n for n, ts in mcp_bridge._presence.items() if maintenant - ts < mcp_bridge.PRESENCE_TIMEOUT}
        activite = dict(mcp_bridge._activity_ts)
    return agents_inactifs(en_ligne, activite, maintenant, _DEMARRAGE)


# SOCLE-SHOP v1.1 P3 : la methode de chaque etape vient de docs/PILOTE.md (une section `## <etape>` par etape).
_PILOTE_MD = Path(__file__).parent / "docs" / "PILOTE.md"


def _methodes_etapes() -> dict:
    try:
        texte = _PILOTE_MD.read_text("utf-8")
    except OSError:
        return {}
    out, courante, lignes = {}, None, []
    preambule = []
    for ligne in texte.splitlines() + ["## "]:
        if ligne.startswith("## "):
            if courante is None:
                preambule = lignes[:]              # tout ce qui precede la 1re etape
            elif courante in _jobs_mod.ETAPES:
                out[courante] = "\n".join(lignes).strip()
            courante, lignes = ligne[3:].strip(), []
        else:
            lignes.append(ligne)
    # Les regles universelles (prambule, a partir de "Regles pour toutes les etapes") sont
    # prefixees a CHAQUE etape : sinon elles n'atteignent jamais l'agent, qui ne recoit que la
    # section de son etape, et la doctrine reste decorative.
    pre = "\n".join(preambule).strip()
    i = pre.find("Règles pour toutes les étapes")
    if i >= 0:
        pre = pre[i:].strip()
        for k in list(out):
            out[k] = pre + "\n\n" + out[k]
    return out


@app.get("/api/v2/methodes")
async def get_methodes():
    """La methode de chaque etape (docs/PILOTE.md), pour l'atelier : {etape: texte}."""
    return JSONResponse(_methodes_etapes())


# SOCLE-SHOP v1.1 P1 : jalons J1/J2. claude les prepare ; seul Charles decide (corps `par: "user"`).
@app.get("/api/v2/projects/{projet_id}/jalons")
async def list_jalons(projet_id: str):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"jalons": jalons.lister(projet_id)})


@app.post("/api/v2/projects/{projet_id}/jalons")
async def create_jalon(projet_id: str, request: Request):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "objet attendu"}, status_code=400)
    jalon, err = jalons.preparer(projet_id, body)
    if err:
        return JSONResponse({"error": err}, status_code=409 if err.startswith("en attente") else 400)
    # Progres reel : un jalon prepare fait avancer la ronde du projet.
    _note_round_progress(_canal_orchestration())
    if notifs is not None:
        notifs.envoyer_en_fond(f"Jalon {jalon.get('jalon', '')} : décide de la suite",
                               (_projets.lister()["v2"]["projets"].get(projet_id) or {}).get("nom", projet_id),
                               url="/atelier#/", etiquette=f"jalon-{jalon.get('id', '')}")
    return JSONResponse(jalon)


_EFFET_DECISION = {"hold": "veille", "kill": "arrete"}


@app.post("/api/v2/jalons/{jalon_id}/decision")
async def decide_jalon(jalon_id: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "objet attendu"}, status_code=400)
    if body.get("par") != "user":
        return JSONResponse({"error": "seul Charles decide un jalon"}, status_code=403)
    jalon, err = jalons.decider(jalon_id, str(body.get("decision", "")), str(body.get("note", "")),
                                str(body.get("recycle_etape", "")))
    if err:
        code = 404 if err == "inconnu" else 409 if err.startswith("deja") else 400
        return JSONResponse({"error": err}, status_code=code)
    statut = _EFFET_DECISION.get(jalon["decision"])
    if statut:
        _projets.definir_statut(jalon["projet_id"], statut, par_id=True)
    if jalon["decision"] == "kill":  # PIECES.md N2 : un kill arrete aussi les sous-projets
        for sous in _projets.descendants(jalon["projet_id"]):
            _projets.definir_statut(sous, "arrete", par_id=True)
    # `par: "user"` n'est qu'une convention (revue codex, msg 2277) : la decision est donc toujours annoncee dans le
    # canal, ou Charles voit tout de suite une decision qu'il n'aurait pas prise.
    canal = _CANAL_PILOTE if _CANAL_PILOTE in room_settings["channels"] else "general"
    vers = f" vers {jalon['recycle_etape']}" if jalon["recycle_etape"] else ""
    store.add("system", f"Jalon {jalon['jalon']} du projet {jalon['projet_id']} : décision « {jalon['decision']}{vers} » "
              "enregistrée au nom de Charles depuis l'atelier.", channel=canal, projet_id=jalon["projet_id"])
    # Progres reel : un jalon franchi (decide par Charles) fait avancer la ronde du projet.
    _note_round_progress(canal)
    return JSONResponse(jalon)


# SOCLE-SHOP v1.1 P2 : fiche projet (champs du skill pilote-rd).
@app.patch("/api/v2/projects/{projet_id}/fiche")
async def patch_fiche(projet_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    projet, err = _projets.definir_fiche(projet_id, body)
    if err:
        return JSONResponse({"error": "projet inconnu" if err == "inconnu" else err},
                            status_code=404 if err == "inconnu" else 400)
    return JSONResponse(projet)


# SOCLE-SHOP v1.1 P4 : lancement guide. Le bouton « Lancer le projet » de l'atelier est un geste de Charles : le
# message de cadrage part donc a son nom, etiquete du projet, et declenche claude par sa mention.
_CANAL_PILOTE = "developpement-de-pro"


@app.post("/api/v2/projects")
async def lancer_projet(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "objet attendu"}, status_code=400)
    nom = str(body.get("nom", "")).strip()
    objectif = str(body.get("objectif", "")).strip()
    if not nom:
        return JSONResponse({"error": "nom requis"}, status_code=400)
    # Photos et documents d'idee : deja deposes par POST /api/upload, qui rend {name, url}.
    pieces = body.get("pieces_jointes") or []
    if not isinstance(pieces, list) or not all(
            isinstance(p, dict) and _re.fullmatch(r"/uploads/[0-9a-f]{8}\.[A-Za-z0-9]{1,8}", str(p.get("url", "")))
            for p in pieces):
        return JSONResponse({"error": "pieces_jointes : [{name, url}] rendus par /api/upload"}, status_code=400)
    pieces = [{"name": str(p.get("name", ""))[:200], "url": p["url"]} for p in pieces]
    if _projets.lister()["projets"].get(nom):
        return JSONResponse({"error": "un projet porte deja ce nom"}, status_code=409)
    pid = _projets.creer(nom, objectif)
    _projets.definir_fiche(pid, {"objectif": objectif})
    canal = _CANAL_PILOTE if _CANAL_PILOTE in room_settings["channels"] else "general"
    store.add("user", f"@claude Lancement guidé du projet « {nom} » ({pid}). Objectif : {objectif or '(à préciser)'}\n"
              "Applique pilote-rd : au plus 3 questions qui changent le projet (fiche.questions), le reste en "
              f"hypothèses écrites, niveau, risques et critères (PATCH /api/v2/projects/{pid}/fiche), puis les tâches "
              "des étapes 1 à 3 avec leur méthode (docs/PILOTE.md).", channel=canal, projet_id=pid, attachments=pieces)
    return JSONResponse({"projet_id": pid, "channel": canal, **_projets.lister()})


# SOCLE-SHOP S2 : taches de projet (un job avec projet_id, etape, responsable, equipe, preuve).
@app.get("/api/v2/taches")
async def list_taches(projet_id: str):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    taches = jobs.taches(projet_id)
    # Tableau de l'atelier en direct (tache-22, msg 4926) : la derniere progression de chaque tache et les agents
    # dont l'execution est active. Les deux viennent de ce que le serveur sait deja : aucun terminal n'est sonde.
    acts = _progression.activites(store.get_since(-1), _humains()) if store is not None else {}
    actifs = _progression.au_travail(executions.lister(projet_id=projet_id)) if executions is not None else {}
    for t in taches:
        t["activite"] = acts.get(t["id"])
        t["au_travail"] = actifs.get(t["id"], [])
    return JSONResponse({"taches": taches, "etape": _jobs_mod.etape_du_projet(taches),
                         "etapes": list(_jobs_mod.ETAPES), "humains": sorted(_humains())})


@app.post("/api/v2/taches")
async def create_tache(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    projet_id = str(body.get("projet_id", "")).strip()
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    titre = str(body.get("titre", "")).strip()
    if not titre:
        return JSONResponse({"error": "titre requis"}, status_code=400)
    tache, err = jobs.create_tache(
        projet_id, titre, str(body.get("etape", "")), str(body.get("responsable", "")),
        created_by=str(body.get("created_by", "user")), channel=str(body.get("channel", "general")),
        equipe=body.get("equipe") or [], critere=str(body.get("critere", "")),
        **{c: str(body.get(c, "")) for c in ("incertitude", "hypothese", "methode")})
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return JSONResponse(tache)


@app.post("/api/v2/taches/{tache_id}/conversation")
async def tache_conversation(tache_id: int):
    """SOCLE-SHOP v1.0 : ouvre (ou retrouve) le canal `tache-<id>` de la salle, range sous le projet de la tache.
    Les messages et les @agent de ce canal portent la tache : ils vont dans l'historique et ouvrent les executions."""
    tache = jobs.get(tache_id) if jobs else None
    if not tache or not tache.get("projet_id"):
        return JSONResponse({"error": "tache inconnue"}, status_code=404)
    canal = _jobs_mod.canal_tache(tache_id)
    if canal not in room_settings["channels"]:
        room_settings["channels"].append(canal)
        _save_settings()
        await broadcast_settings()
    _projets.assigner_canal(canal, tache["projet_id"], par_id=True)
    return JSONResponse({"channel": canal, "projet_id": tache["projet_id"], "tache_id": tache_id})


def _enregistrer_livrables_tache(tache: dict) -> dict | None:
    """SOCLE-SHOP S5 v2 : a la completion d'une tache, double sa `preuve` d'une (ou de) fiche(s) de livrable
    structuree(s) (RevisionStore), reliee(s) a {projet, tache, piece}. Addition isolee : ne bloque JAMAIS la
    transition de tache (elle logue l'erreur et continue)."""
    if revisions is None:
        return None
    try:
        return _revisions_mod.associer_livrables_tache(tache, revisions, pieces, qui="socle")
    except Exception:
        log.exception("S5 : enregistrement des livrables de la tache %s", tache.get("id"))
        return None


@app.patch("/api/v2/taches/{tache_id}")
async def update_tache(tache_id: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "objet attendu"}, status_code=400)
    tache, err = appliquer_maj_tache(tache_id, body)
    if err:
        return JSONResponse({"error": err}, status_code=404 if err == "tache inconnue" else 400)
    return JSONResponse(tache)


def appliquer_maj_tache(tache_id: int, champs: dict, par_agent: bool = False) -> tuple[dict | None, str]:
    """Mise a jour d'une tache et ses effets (livrables a `fait`, progres de la ronde sur changement d'etat).
    Chemin unique pour la route PATCH et l'outil MCP `tache_maj` (salle sobre lot 1).
    par_agent=True (outil MCP, revue du 20 oct.) : le progres n'est compte que si l'etat CHANGE vraiment, et il ne
    leve jamais une pause du loop guard. Sinon un agent pourrait, en redeclarant son etat, relancer une boucle
    que seul le /continue de Charles doit relancer."""
    if jobs is None:
        return None, "taches indisponibles"
    avant = jobs.get(tache_id) or {}
    tache, err = jobs.update_tache(tache_id, champs)
    if err:
        return None, err
    if tache.get("etat") == "fait":
        _enregistrer_livrables_tache(tache)
    # Progres reel : une transition d'etat de tache fait avancer la ronde.
    if par_agent:
        if "etat" in champs and avant.get("etat") != tache.get("etat"):
            _note_round_progress(_jobs_mod.canal_tache(tache_id), reprendre=False)
    elif "etat" in champs:
        _note_round_progress(_jobs_mod.canal_tache(tache_id))
    return tache, ""


# SOCLE-SHOP S3 : executions et evenements (panneau « En direct »).
@app.get("/api/v2/executions")
async def list_executions(projet_id: str = "", tache_id: int | None = None):
    if projet_id and not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse({"executions": executions.lister(projet_id or None, tache_id)})


# SOCLE-SHOP S3 v0.9 : le serveur tient les executions lui-meme, sans changer les wrappers. Un @agent dans un message
# etiquete d'une tache ouvre une execution ; le battement « actif » du wrapper vaut signe de vie ; le retour au repos
# la termine avec l'issue neutre « terminee » (le tour est fini, le resultat n'est pas juge).
_SIGNE_MIN_S = 30


def _execution_ouverte(agent: str) -> dict | None:
    if executions is None:
        return None
    return next((e for e in executions.lister() if e["agent"] == agent and not e.get("fin")), None)


def _ouvrir_execution(agent: str, tache_id, consigne: str) -> None:
    """Sans effet si la tache est inconnue, son projet pas actif ou l'essai pas pret : le message part quand meme."""
    if executions is None or jobs is None or not tache_id:
        return
    try:
        tache = jobs.get(int(tache_id))
        if not tache or not tache.get("projet_id") or not _jobs_mod.essai_pret(tache):
            return
        info = _projets.memoire_projet(tache["projet_id"])
        if info is None or info["statut"] != "actif":
            return
        ouverte = _execution_ouverte(agent)
        if ouverte and ouverte["tache_id"] == tache["id"]:
            executions.signe(ouverte["id"])
            return
        if ouverte:
            executions.terminer(ouverte["id"], "terminee")
        role = next((m.get("role", "") for m in tache.get("equipe") or [] if m.get("agent") == agent), "")
        executions.demarrer(tache["id"], tache["projet_id"], agent, role or "producteur", consigne, info["memoire"])
    except Exception:
        log.exception("S3 : ouverture d'execution pour %s", agent)


def _battement_execution(agent: str, actif: bool, etait_actif: bool) -> None:
    ouverte = _execution_ouverte(agent)
    if ouverte is None:
        return
    if actif and time.time() - ouverte["dernier_signe"] >= _SIGNE_MIN_S:
        executions.signe(ouverte["id"])
    elif etait_actif and not actif:
        executions.terminer(ouverte["id"], "terminee")


# --- Garde-fou conscient du progres (SOCLE-SHOP) ---
# Le loop guard par canal (router) met un canal en pause apres max_agent_hops relais agent->agent
# sans message humain. Il ne distingue pas le sur-place du progres reel : une ronde qui avance se
# faisait couper. On branche donc un signal de progres sur chaque ecriture d'avancement du socle Shop
# (transition d'etat de tache, execution terminee, revue/revision postee, jalon franchi), qui remet
# le canal concerne a zero comme un message humain.

async def _reveiller_chef_garde(channel: str, sender: str, msg_id) -> None:
    """Le loop guard coupe un canal sans prevenir personne : les @mentions entre agents y tombent
    en silence et l'atelier s'arrete (19 oct. 2026, #tache-21 : 2 h 45 sans suite). On reveille donc
    le chef ([routing] chef), une fois par pause. La consigne ne porte que le canal, l'auteur et le
    numero du message bloque, jamais son texte (R3 : un message peut contenir un secret) ; le chef
    lit le canal lui-meme. /continue reste reserve aux humains."""
    chef = str(config.get("routing", {}).get("chef", "")).strip()
    if not chef or not agents or not agents.is_available(chef):
        return
    consigne = (f"Loop guard dans #{channel} : les @mentions entre agents y sont coupees jusqu'au "
                f"/continue de Charles. Message bloque : n° {msg_id}, de {sender}. Lis #{channel} "
                "par since_id, decide de la suite des lots ouverts de ce canal (orchestration "
                "seulement) et previens Charles en une ligne.")
    await agents.trigger(chef, message=f"system: {consigne}", channel=channel, prompt=consigne)


def _vise_claude(targets) -> bool:
    """Un battement de ronde relance claude : vrai si une cible est claude (ou une de ses instances
    claude-*), ou une mention large (@all / @both)."""
    for t in targets or []:
        n = str(t).strip().lstrip("@").lower()
        if n in ("all", "both", "everyone"):
            return True
        if n == "claude" or n.startswith("claude-"):
            return True
    return False


def _canal_orchestration() -> str:
    """Canal ou la ronde de projet est orchestree et annoncee (pilote si present, sinon general).
    Sert de canal par defaut pour un progres de niveau projet (sans tache)."""
    return _CANAL_PILOTE if _CANAL_PILOTE in room_settings.get("channels", []) else "general"


def _note_round_progress(channel: str, reprendre: bool = True) -> None:
    """Un progres reel enregistre cote serveur. Remet le loop guard ET le compteur anti-tournage-a-vide
    du canal a zero, sans router de message. Sans routeur (demarrage partiel) ou sans canal : sans effet.
    reprendre=False : ne leve jamais une pause du loop guard (progres declare par un agent)."""
    if not router or not channel:
        return
    router.note_progress(channel, reprendre=reprendre)
    log.info("garde-fou : progrès réel sur « %s » — compteurs remis à zéro", channel)


@app.post("/api/v2/executions")
async def start_execution(request: Request):
    """Demarre une execution sur une tache. Refus : tache inconnue, projet pas actif (veille, arrete, termine),
    ou essai sans incertitude / hypothese / methode / critere ecrits avant (RS&DE)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    try:
        tache_id = int(body.get("tache_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "tache_id requis"}, status_code=400)
    tache = jobs.get(tache_id)
    if not tache or not tache.get("projet_id"):
        return JSONResponse({"error": "tache inconnue"}, status_code=404)
    info = _projets.memoire_projet(tache["projet_id"])
    if info is None:
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    if info["statut"] != "actif":
        return JSONResponse({"error": f"projet {info['statut']} : aucune execution"}, status_code=409)
    if not _jobs_mod.essai_pret(tache):
        return JSONResponse({"error": "essai : incertitude, hypothese, methode et critere d'abord"},
                            status_code=409)
    agent = str(body.get("agent", "")).strip()
    if not agent:
        return JSONResponse({"error": "agent requis"}, status_code=400)
    e = executions.demarrer(tache_id, tache["projet_id"], agent, str(body.get("role", "producteur")),
                            str(body.get("consigne", "")), info["memoire"])
    return JSONResponse(e)


@app.post("/api/v2/executions/{exec_id}/signe")
async def execution_signe(exec_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    e = executions.signe(exec_id, str(body.get("outil", "")), str(body.get("resume", "")))
    if e is None:
        return JSONResponse({"error": "execution inconnue"}, status_code=404)
    return JSONResponse(e)


@app.post("/api/v2/executions/{exec_id}/fin")
async def execution_fin(exec_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    try:
        e = executions.terminer(exec_id, str(body.get("issue", "")))
    except ValueError as err:
        return JSONResponse({"error": str(err)}, status_code=400)
    if e is None:
        return JSONResponse({"error": "execution inconnue"}, status_code=404)
    # Progres reel : une execution terminee fait avancer la ronde, sur le canal de sa tache.
    if e.get("tache_id"):
        _note_round_progress(_jobs_mod.canal_tache(e["tache_id"]))
    return JSONResponse(e)


@app.get("/api/v2/executions/{exec_id}/evenements")
async def execution_evenements(exec_id: str):
    ev = executions.evenements(exec_id)
    if ev is None:
        return JSONResponse({"error": "execution inconnue"}, status_code=404)
    return JSONResponse({"evenements": ev})


# --- Ajouter une IA par lien (agent API OpenAI-compatible) (Vaultia) ---

import re as _re_vaultia


@app.post("/api/agents/add")
async def add_api_agent(request: Request):
    """Ajoute une IA connectee par un lien (point OpenAI-compatible) et la met en ligne.

    Corps : {name, label?, base_url, model?, api_key?, color?, effort?, system_prompt?,
    context_messages?}. Ecrit l'agent dans config.local.toml, l'enseigne au registre en
    direct, puis lance son wrapper API. Ne touche jamais claude/codex/gemini.
    """
    import mcp_bridge
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    name = str(body.get("name", "")).strip().lower()
    base_url = str(body.get("base_url", "")).strip()
    if not _re_vaultia.fullmatch(r"[a-z0-9][a-z0-9_-]{1,30}", name):
        return JSONResponse({"error": "nom invalide : lettres, chiffres, - et _ (2 a 31 caracteres)"}, status_code=400)
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        return JSONResponse({"error": "le lien doit commencer par http:// ou https://"}, status_code=400)
    if registry and name in registry.get_bases():
        return JSONResponse({"error": f"une IA nommee '{name}' existe deja"}, status_code=409)

    cfg = {
        "type": "api",
        "base_url": base_url,
        "model": str(body.get("model", "")).strip(),
        "label": str(body.get("label", "")).strip() or name.capitalize(),
        "color": str(body.get("color", "")).strip() or "#6b7280",
    }
    if body.get("api_key_env"):
        cfg["api_key_env"] = str(body["api_key_env"]).strip()
    if body.get("system_prompt"):
        cfg["system_prompt"] = str(body["system_prompt"]).strip()
    if body.get("context_messages"):
        try:
            cfg["context_messages"] = int(body["context_messages"])
        except (TypeError, ValueError):
            pass

    # 1. Ecrire dans config.local.toml (jamais config.toml : la trinite y est protegee).
    from pathlib import Path as _P
    local = _P(__file__).parent / "config.local.toml"
    bloc = [f"\n[agents.{name}]"]
    for cle in ("type", "base_url", "model", "label", "color", "api_key_env", "system_prompt"):
        if cfg.get(cle):
            valeur = str(cfg[cle]).replace("\\", "\\\\").replace('"', '\\"')
            bloc.append(f'{cle} = "{valeur}"')
    if cfg.get("context_messages"):
        bloc.append(f'context_messages = {cfg["context_messages"]}')
    try:
        with local.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(bloc) + "\n")
    except OSError as exc:
        return JSONResponse({"error": f"ecriture de config.local.toml impossible : {exc}"}, status_code=500)

    # 2. Enseigner l'agent au registre en direct (couleur/label sans redemarrage).
    if registry:
        registry.seed({name: cfg})
    if body.get("effort"):
        mcp_bridge.set_effort(name, str(body["effort"]).strip().lower())

    # 3. Lancer le wrapper API (il s'enregistre et bat le pouls tout seul).
    import subprocess, sys as _sys
    root = _P(__file__).parent
    python = root / ".venv" / "bin" / "python"
    try:
        subprocess.Popen(
            [str(python if python.exists() else _sys.executable), "wrapper_api.py", name],
            cwd=str(root),
            stdout=open(root / "data" / f"{name}.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"agent ecrit mais lancement du wrapper impossible : {exc}"}, status_code=500)

    await broadcast_agents()
    await broadcast_status()
    return JSONResponse({"ok": True, "name": name, "label": cfg["label"], "color": cfg["color"]})


# --- Rules API ---

@app.get("/api/rules")
async def get_rules():
    """Get all rules (all states)."""
    return JSONResponse(rules.list_all())


@app.get("/api/rules/active")
async def get_active_rules():
    """Get compact active rules for agent injection."""
    data = rules.active_list()
    data["refresh_interval"] = room_settings.get("rules_refresh_interval", 10)
    return JSONResponse(data)


@app.post("/api/rules/remind")
async def remind_agents():
    """Set remind flag — agents get rules on next trigger."""
    rules.set_remind()
    remind_data = json.dumps({"type": "rules_remind", "data": {}})
    for client in list(ws_clients):
        try:
            await client.send_text(remind_data)
        except Exception:
            pass
    return JSONResponse({"ok": True})


@app.post("/api/rules/agent_sync/{agent_name}")
async def report_rule_sync(agent_name: str, request: Request):
    """Wrapper reports that an agent has seen rules at a given epoch."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    epoch = body.get("epoch", 0)
    rules.report_agent_sync(agent_name, epoch)
    # Clear remind flag once any agent has seen the updated rules
    rules.clear_remind()
    return JSONResponse({"ok": True})


@app.get("/api/rules/freshness")
async def get_rules_freshness():
    """Get per-agent sync status."""
    return JSONResponse(rules.agent_freshness())


@app.post("/api/register")
async def register_agent(request: Request):
    """Wrapper calls this to register a new agent instance."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    base = body.get("base", "")
    label = body.get("label")
    if not base:
        return JSONResponse({"error": "base is required"}, status_code=400)
    result = registry.register(base, label)
    if result is None:
        return JSONResponse({"error": f"unknown base: {base}"}, status_code=400)
    # Touch presence so the instance doesn't immediately time out
    import mcp_bridge
    with mcp_bridge._presence_lock:
        mcp_bridge._presence[result["name"]] = __import__("time").time()
    # If slot 1 was renamed (e.g. "claude" → "claude-1"), migrate state
    renamed = result.pop("_renamed_slot1", None)
    if renamed:
        mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
        store.rename_sender(renamed["old"], renamed["new"])
        _migrate_agent_last_channel(renamed["old"], renamed["new"])
        if _event_loop:
            rename_event = json.dumps({
                "type": "agent_renamed",
                "old_name": renamed["old"],
                "new_name": renamed["new"],
            })
            asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
    # Broadcast pending_instance event so UI can show naming lightbox
    if result.get("state") == "pending" and _event_loop:
        pending_event = json.dumps({
            "type": "pending_instance",
            "name": result["name"],
            "base": base,
            "label": result.get("label", result["name"]),
            "color": result.get("color", "#888"),
        })
        asyncio.run_coroutine_threadsafe(_broadcast(pending_event), _event_loop)
    return JSONResponse(result)


@app.post("/api/deregister/{name}")
async def deregister_agent(name: str, request: Request):
    """Wrapper calls this on shutdown to remove its instance."""
    auth_inst = _resolve_authenticated_agent(request)
    presented_token = _extract_agent_token(request)
    if presented_token and not auth_inst:
        return JSONResponse({"error": "stale_session"}, status_code=409)
    if auth_inst:
        name = auth_inst["name"]
    elif registry and registry.is_agent_family(name):
        return JSONResponse({"error": "authenticated agent session required"}, status_code=403)

    result = registry.deregister(name)
    if result is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    # Clean up runtime state (presence, activity, cursors, rename chains)
    import mcp_bridge
    mcp_bridge.purge_identity(name)
    registry.clean_renames_for(name)
    # If the remaining instance was renamed back (e.g. "claude-1" → "claude"), migrate state
    renamed = result.pop("_renamed_back", None)
    if renamed:
        mcp_bridge.migrate_identity(renamed["old"], renamed["new"])
        store.rename_sender(renamed["old"], renamed["new"])
        _migrate_agent_last_channel(renamed["old"], renamed["new"])
        if _event_loop:
            rename_event = json.dumps({
                "type": "agent_renamed",
                "old_name": renamed["old"],
                "new_name": renamed["new"],
            })
            asyncio.run_coroutine_threadsafe(_broadcast(rename_event), _event_loop)
    return JSONResponse({"ok": True})


@app.post("/api/label/{name}")
async def rename_agent_label(name: str, request: Request):
    """Rename an agent (human-initiated from UI). Changes identity + label."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    label = body.get("label", "").strip()
    if not label:
        return JSONResponse({"error": "label is required"}, status_code=400)

    import re as _re
    new_id = _re.sub(r'[^a-z0-9-]', '', label.lower().replace(' ', '-')).strip('-')
    if not new_id:
        new_id = name

    if new_id == name:
        # Same ID — label-only change
        if registry.set_label(name, label):
            return JSONResponse({"ok": True})
        return JSONResponse({"error": "not found"}, status_code=404)

    result = registry.rename(name, new_id, label)
    if isinstance(result, str):
        # Rename failed — try label-only as fallback
        if registry.set_label(name, label):
            return JSONResponse({"ok": True, "warning": result})
        return JSONResponse({"error": result}, status_code=400)

    import mcp_bridge
    mcp_bridge.migrate_identity(name, new_id)
    # Update sender on all historical messages
    store.rename_sender(name, new_id)
    _migrate_agent_last_channel(name, new_id)
    return JSONResponse({"ok": True, "new_name": new_id})


@app.post("/api/heartbeat/{agent_name}")
async def heartbeat(agent_name: str, request: Request):
    """Wrapper calls this to keep presence alive and report activity.

    Returns the canonical name from the registry so the wrapper can
    detect renames (e.g. claim renamed 'claude-2' to 'claude-music').
    """
    import mcp_bridge
    auth_inst = _resolve_authenticated_agent(request)
    presented_token = _extract_agent_token(request)
    if presented_token and not auth_inst:
        return JSONResponse({"error": "stale_session"}, status_code=409)
    if registry and registry.is_agent_family(agent_name) and not auth_inst:
        return JSONResponse({"error": "authenticated agent session required"}, status_code=403)

    current_name = auth_inst["name"] if auth_inst else agent_name
    with mcp_bridge._presence_lock:
        mcp_bridge._presence[current_name] = __import__("time").time()
    # Optional activity report from wrapper's terminal monitor
    _activity_changed = False
    try:
        body = await request.json()
        if "active" in body:
            active_val = bool(body["active"])
            was_active = mcp_bridge._activity.get(current_name, False)
            mcp_bridge.set_active(current_name, active_val)
            _activity_changed = was_active != active_val
            _battement_execution(current_name, active_val, was_active)  # SOCLE-SHOP S3 v0.9
    except Exception:
        pass  # No body = plain heartbeat
    # Immediately broadcast on activity state change (don't wait for background checker)
    if _activity_changed:
        await broadcast_status()
    # Return canonical name so wrapper can track renames
    resp = {"ok": True, "name": current_name}
    if registry:
        # Follow rename chain (e.g. claude-2 was renamed to claude-music)
        canonical = registry.resolve_name(current_name)
        inst = registry.get_instance(canonical)
        # If rename chain didn't help, try family-based lookup
        # (handles case where _renames was cleared by server restart but
        # the instance was claimed/renamed via MCP)
        if not inst:
            base = current_name.split("-")[0] if "-" in current_name else current_name
            family_inst = registry.get_family_instance(base)
            if family_inst:
                inst = family_inst
                canonical = inst["name"]
        if inst:
            resp["name"] = inst["name"]
            resp["pending"] = inst.get("state") == "pending"
            # Also update presence under the canonical name
            if canonical != current_name:
                now = __import__("time").time()
                with mcp_bridge._presence_lock:
                    mcp_bridge._presence[canonical] = now
    return resp


# --- Open agent session in terminal ---

@app.get("/api/platform")
async def get_platform():
    """Return the server's platform so the web UI can match path formats."""
    import sys
    return JSONResponse({"platform": sys.platform})


@app.post("/api/open-path")
async def open_path(body: dict):
    """Open a file or directory in the native file manager.

    Cross-platform: Explorer on Windows, Finder on macOS, xdg-open on Linux.

    Security note: This endpoint is intended for local-only use (127.0.0.1).
    Do not expose this server on a public network without additional access controls.
    """
    import subprocess
    import sys

    path = body.get("path", "")
    if not path:
        return JSONResponse({"error": "no path"}, status_code=400)

    p = Path(path)
    try:
        if sys.platform == "win32":
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            elif p.is_dir():
                subprocess.Popen(["explorer", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
        elif sys.platform == "darwin":
            if p.is_file():
                subprocess.Popen(["open", "-R", str(p)])
            elif p.is_dir():
                subprocess.Popen(["open", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
        else:
            # Linux — xdg-open opens the containing folder for files
            if p.is_file():
                subprocess.Popen(["xdg-open", str(p.parent)])
            elif p.is_dir():
                subprocess.Popen(["xdg-open", str(p)])
            else:
                return JSONResponse({"error": "path not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({"ok": True})


# Serve uploaded images
# --- Sessions API ---

@app.get("/api/sessions/templates")
async def get_session_templates():
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    return JSONResponse(session_store.get_templates())


@app.get("/api/sessions/active")
async def get_active_session(channel: str = "general"):
    if not session_engine:
        return JSONResponse(None)
    session = session_engine.get_active(channel)
    return JSONResponse(session)


@app.get("/api/sessions/active-all")
async def get_all_active_sessions():
    if not session_engine:
        return JSONResponse([])
    return JSONResponse(session_engine.list_active())


@app.post("/api/sessions/start")
async def start_session(request: Request):
    if not session_engine or not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    body = await request.json()
    template_id = body.get("template_id", "")
    draft_message_id = body.get("draft_message_id")
    channel = body.get("channel", "general")
    cast = body.get("cast", {})
    goal = body.get("goal", "")
    started_by = body.get("started_by", "user")

    # If running from a draft, load the inline template from message metadata
    tmpl = None
    if draft_message_id:
        draft_msg = store.get_by_id(int(draft_message_id))
        if not draft_msg:
            return JSONResponse({"error": "draft message not found"}, status_code=404)
        meta = draft_msg.get("metadata", {})
        if not meta.get("valid"):
            return JSONResponse({"error": "draft is not valid"}, status_code=400)
        tmpl = meta.get("template")
        if not tmpl:
            return JSONResponse({"error": "draft has no template"}, status_code=400)
        # Register as a temporary template
        template_id = tmpl.get("id", f"draft-{draft_message_id}")
        tmpl["id"] = template_id
        tmpl["is_custom"] = True
        session_store._templates[template_id] = tmpl

    # Validate template exists
    if not tmpl:
        tmpl = session_store.get_template(template_id)
    if not tmpl:
        return JSONResponse({"error": f"unknown template: {template_id}"}, status_code=400)

    # Auto-fill cast from available agents if not fully provided
    if not cast:
        online = registry.get_active_names() if registry else []
        roles = tmpl.get("roles", [])
        cast = _auto_cast(roles, online, started_by)
        if not cast:
            return JSONResponse(
                {"error": "not enough agents online to fill all roles"},
                status_code=400,
            )

    session = session_engine.start_session(template_id, channel, cast, started_by, goal)
    if not session:
        return JSONResponse({"error": "could not start session (one may already be active)"}, status_code=409)

    # Add start banner to chat (only after confirmed success)
    store.add(
        sender="system",
        text=f"Session started: {tmpl.get('name', template_id)}",
        msg_type="session_start",
        channel=channel,
        metadata={"template_id": template_id, "goal": goal, "session_id": session["id"]},
    )
    session_engine.emit_current_phase_banner(session)

    return JSONResponse(session)


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: int):
    if not session_engine:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    session = session_engine.end_session(session_id)
    if not session:
        return JSONResponse({"error": "session not found or already ended"}, status_code=404)

    # Banner is added by _on_session_change("interrupt", ...) callback
    return JSONResponse(session)


@app.post("/api/sessions/request-draft")
async def request_session_draft(request: Request):
    """Ask an agent to design a session template. Called by the 'Design a session' UI."""
    body = await request.json()
    agent_name = body.get("agent", "").strip()
    description = body.get("description", "").strip()
    channel = body.get("channel", "general")
    sender = body.get("sender", "user")
    if not agent_name or not description:
        return JSONResponse({"error": "agent and description required"}, status_code=400)

    mention_str = f"@{agent_name}"
    store.add(
        "system",
        f"Requested session draft from {mention_str}. Wait for a proposal.",
        channel=channel,
    )
    store.add(
        sender,
        f"{mention_str} Design a session workflow for: **{description}**\n\n"
        "Respond with a single chat message containing a fenced JSON code block with this exact structure:\n"
        "```session\n"
        '{"name": "...", "description": "...", "roles": ["role1", "role2", ...], '
        '"phases": [{"name": "...", "participants": ["role1"], "prompt": "...", "is_output": false}, ...]}\n'
        "```\n"
        "Rules: max 6 roles, max 6 phases, max 4 participants per phase, max 200 chars per prompt. "
        "Mark exactly one phase as `is_output: true` (the final deliverable). "
        f"Keep it focused and sequential. Use the chat_send tool to post your response in the #{channel} channel. "
        "Do NOT respond only in your terminal.",
        channel=channel,
        msg_type="session_request",
        metadata={"session_request": True, "mentions": [f"@{agent_name}"], "request": description},
    )
    return JSONResponse({"ok": True})


@app.post("/api/sessions/save-draft")
async def save_draft(request: Request):
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    body = await request.json()
    msg_id = body.get("message_id")
    if not msg_id:
        return JSONResponse({"error": "message_id required"}, status_code=400)
    msg = store.get_by_id(int(msg_id))
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)
    meta = msg.get("metadata", {})
    if not meta.get("valid"):
        return JSONResponse({"error": "draft is not valid"}, status_code=400)
    tmpl = meta.get("template")
    if not tmpl:
        return JSONResponse({"error": "no template in draft"}, status_code=400)

    tmpl.setdefault("id", f"custom-{msg_id}")
    session_store.save_custom_template(tmpl)
    return JSONResponse({"ok": True, "template_id": tmpl["id"]})


@app.delete("/api/sessions/templates/{template_id}")
async def delete_session_template(template_id: str):
    if not session_store:
        return JSONResponse({"error": "sessions not configured"}, status_code=500)
    deleted = session_store.delete_custom_template(template_id)
    if not deleted:
        return JSONResponse({"error": "template not found or not custom"}, status_code=404)
    return JSONResponse({"ok": True, "template_id": template_id})


def _auto_cast(roles: list[str], online_agents: list[str], started_by: str) -> dict:
    """Auto-assign roles to available agents. Returns empty dict if not enough agents."""
    cast = {}
    available = list(online_agents)

    for role in roles:
        if not available:
            # Reuse agents if we run out (one agent, multiple roles)
            available = list(online_agents)
        if not available:
            return {}
        agent = available.pop(0)
        cast[role] = agent

    return cast


# --- Version check (GitHub release notifier) ---

_version_cache: dict = {"data": None, "fetched_at": 0.0}
_VERSION_CACHE_TTL = 1800  # 30 minutes


def _read_local_version() -> str:
    """Read version from VERSION file in project root."""
    vfile = Path(__file__).parent / "VERSION"
    try:
        return vfile.read_text().strip()
    except Exception:
        return ""


def _detect_install_kind() -> str:
    """Detect how this copy was installed: official_git, fork, or unknown."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).parent,
        )
        url = result.stdout.strip().lower()
        if "bcurts/agentchattr" in url:
            return "official_git"
        elif url:
            return "fork"
    except Exception:
        pass
    return "unknown"


def _fetch_latest_release() -> dict | None:
    """Fetch latest release from GitHub API, with 30-min cache."""
    import time
    import urllib.request

    now = time.time()
    if _version_cache["data"] and (now - _version_cache["fetched_at"]) < _VERSION_CACHE_TTL:
        return _version_cache["data"]

    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/bcurts/agentchattr/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "agentchattr"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            result = {
                "tag": data.get("tag_name", ""),
                "url": data.get("html_url", ""),
            }
            _version_cache["data"] = result
            _version_cache["fetched_at"] = now
            return result
    except Exception:
        return _version_cache.get("data")


def _compare_versions(current: str, latest_tag: str) -> str:
    """Compare version strings. Returns 'behind', 'current', or 'unknown'."""
    # Strip leading 'v' from tag
    latest = latest_tag.lstrip("v")
    if not current or not latest:
        return "unknown"
    try:
        from packaging.version import Version
        if Version(current) < Version(latest):
            return "behind"
        return "current"
    except Exception:
        return "unknown"


@app.get("/api/version_check")
async def version_check():
    """Check for newer releases on GitHub."""
    current = _read_local_version()
    loop = asyncio.get_event_loop()
    release = await loop.run_in_executor(None, _fetch_latest_release)

    if not release or not release.get("tag"):
        return JSONResponse({"current": current, "latest": "", "state": "unknown", "url": ""})

    latest_tag = release["tag"]
    install_kind = _detect_install_kind()
    comparison = _compare_versions(current, latest_tag)

    if comparison == "behind":
        if install_kind == "official_git":
            state = "update_available"
        elif install_kind == "fork":
            state = "upstream_update"
        else:
            state = "unknown"
    elif comparison == "current":
        state = "current"
    else:
        state = "unknown"

    return JSONResponse({
        "current": current,
        "latest": latest_tag,
        "state": state,
        "url": release.get("url", ""),
    })


# Vaultia : un fichier televerse n'est jamais une page de la salle. `nosniff` empeche le navigateur de
# deviner du HTML dans un .txt/.csv ; un SVG ouvert DIRECTEMENT pouvait executer du script avec les
# droits de la salle (et lire le jeton injecte dans « / ») -> CSP sandbox sans script. Les miniatures
# ne sont pas touchees : un SVG affiche dans un <img> n'execute jamais de script.
UPLOAD_HEADERS = {"X-Content-Type-Options": "nosniff"}
UPLOAD_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


@app.get("/uploads/{filename}")
async def serve_upload(filename: str):
    upload_dir = Path(config.get("images", {}).get("upload_dir", "./uploads"))
    filepath = (upload_dir / filename).resolve()
    if not filepath.is_relative_to(upload_dir.resolve()):
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if filepath.exists():
        headers = dict(UPLOAD_HEADERS)
        if filepath.suffix.lower() == ".svg":
            headers["Content-Security-Policy"] = UPLOAD_SVG_CSP
        return FileResponse(filepath, headers=headers)
    return JSONResponse({"error": "not found"}, status_code=404)


# --- PIECES.md v0.6 (lot N1) : pieces, offres, nomenclature, mouvements, sauvegarde ---

# Etat de la derniere sauvegarde, lu par la ronde (revue codex msg 2409 : un echec doit se voir, pas seulement au journal).
_etat_sauvegarde: dict = {"local": "", "copie": "", "erreur": ""}


def _alertes_sauvegarde(copie_configuree: bool) -> list[str]:
    jour = time.strftime("%Y-%m-%d")
    hier = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    a = []
    if _etat_sauvegarde["local"] not in (jour, hier):
        a.append(f"sauvegarde des pieces : derniere locale {_etat_sauvegarde['local'] or 'aucune'} ({_etat_sauvegarde['erreur'] or 'pas encore faite'})")
    if copie_configuree and _etat_sauvegarde["copie"] not in (jour, hier):
        a.append(f"copie des pieces hors tour : derniere {_etat_sauvegarde['copie'] or 'aucune'} ({_etat_sauvegarde['erreur'] or 'pas encore faite'})")
    return a


def _demarrer_sauvegardes(data_dir: Path, copie: str):
    """Une sauvegarde par jour dans data/sauvegardes (30 jours), puis copie par scp vers `copie`
    ([socle] copie_pieces = "x1:vaultia-sauvegardes/"). Chaque heure, on reessaie ce qui n'a pas reussi aujourd'hui
    (laptop eteint = copie au prochain essai) ; l'etat va dans la ronde (`alertes`)."""
    import subprocess

    def boucle():
        import time as _t
        while True:
            jour = _t.strftime("%Y-%m-%d")
            if pieces is not None:
                try:
                    if _etat_sauvegarde["local"] != jour:
                        f = pieces.sauvegarder(str(data_dir / "sauvegardes"))
                        _etat_sauvegarde.update(local=jour, fichier=str(f), erreur="")
                    if copie and _etat_sauvegarde["copie"] != jour:
                        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                                            _etat_sauvegarde["fichier"], copie], capture_output=True, text=True, timeout=120)
                        if r.returncode:
                            _etat_sauvegarde["erreur"] = f"copie : {r.stderr.strip()[:160] or 'echec'}"
                            log.warning("copie des pieces vers %s : echec, nouvel essai dans 1 h", copie)
                        else:
                            _etat_sauvegarde.update(copie=jour, erreur="")
                except Exception as exc:
                    _etat_sauvegarde["erreur"] = str(exc)[:160]
                    log.exception("sauvegarde des pieces")
            _t.sleep(3600)

    threading.Thread(target=boucle, daemon=True).start()


async def _corps(request: Request) -> dict | JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    return body if isinstance(body, dict) else JSONResponse({"error": "objet attendu"}, status_code=400)


_AUTEURS = ("user", "claude", "codex", "gemini", "grok", "qwencode")


def _auteur(body: dict) -> str:
    """`par` obligatoire, parmi les membres de l'equipe. C'est une declaration, pas une preuve d'identite (meme
    convention que les jalons, revue codex msg 2409) : l'historique dit « declare par »."""
    qui = str(body.pop("par", "")).strip()
    if qui not in _AUTEURS:
        raise _ErreurPiece(f"par obligatoire, parmi {', '.join(_AUTEURS)}")
    return qui


def _piece_route(fn):
    """Traduit une erreur de regle (pieces.Erreur) en reponse 400/404/409."""
    import functools

    @functools.wraps(fn)
    async def enveloppe(*a, **k):
        try:
            return await fn(*a, **k)
        except _ErreurPiece as e:
            return JSONResponse({"error": str(e)}, status_code=e.code)
    return enveloppe


@app.get("/api/v2/pieces")
@_piece_route
async def list_pieces(projet_id: str = "", statut: str = "", q: str = ""):
    return JSONResponse({"pieces": pieces.lister(projet_id, statut, q)})


@app.post("/api/v2/pieces")
@_piece_route
async def create_piece(request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    qui = _auteur(body)
    if body.get("projet_id") and not _projets.existe(str(body["projet_id"])):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse(pieces.creer(body, qui))


def _tache_faite(tache_id: int) -> bool:
    t = jobs.get(tache_id) if jobs else None
    return bool(t and t.get("etat") == "fait")


@app.get("/api/v2/pieces/{piece_id}")
@_piece_route
async def get_piece(piece_id: int):
    return JSONResponse({**pieces.get(piece_id), "offres": pieces.offres(piece_id),
                         "historique": pieces.historique(piece_id), "revisions": pieces.revisions(piece_id),
                         "utilisee_dans": pieces.utilisee_dans(piece_id),
                         "stock": pieces.stock(piece_id)})


# Lot A1 (Charles msg 2557) : plans et modeles d'une piece, lus sur la tour (fichiers_pieces.py).
@app.get("/api/v2/pieces/{piece_id}/fichiers")
@_piece_route
async def piece_fichiers(piece_id: int):
    import fichiers_pieces
    p = pieces.get(piece_id)
    return JSONResponse({"numero": p["numero"], "fichiers": fichiers_pieces.lister(p["numero"])})


@app.get("/api/v2/pieces/{piece_id}/fichiers/{revision}/{nom}")
@_piece_route
async def piece_fichier(piece_id: int, revision: str, nom: str):
    import fichiers_pieces
    f = fichiers_pieces.chemin(pieces.get(piece_id)["numero"], revision, nom)
    if f is None:
        return JSONResponse({"error": "fichier inconnu"}, status_code=404)
    # Un SVG peut porter du script : on le sert sans droit d'executer quoi que ce soit.
    entetes = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
               "X-Content-Type-Options": "nosniff"}
    return FileResponse(f, media_type=fichiers_pieces.TYPES[f.suffix.lower()], headers=entetes,
                        content_disposition_type="inline" if f.suffix.lower() in (".svg", ".pdf", ".png", ".glb") else "attachment",
                        filename=f.name)


@app.patch("/api/v2/pieces/{piece_id}")
@_piece_route
async def patch_piece(piece_id: int, request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    qui = _auteur(body)
    if body.get("projet_id") and not _projets.existe(str(body["projet_id"])):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse(pieces.modifier(piece_id, body, qui, tache_faite=_tache_faite))


@app.get("/api/v2/pieces/{piece_id}/nomenclature")
@_piece_route
async def get_nomenclature(piece_id: int):
    return JSONResponse(pieces.arbre(piece_id))


@app.post("/api/v2/nomenclature")
@_piece_route
async def post_nomenclature(request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    return JSONResponse(pieces.lier(int(body.get("parent_id", 0)), int(body.get("enfant_id", 0)), body.get("quantite"),
                                    str(body.get("unite", "u")), str(body.get("note", ""))))


@app.delete("/api/v2/nomenclature/{parent_id}/{enfant_id}")
@_piece_route
async def delete_nomenclature(parent_id: int, enfant_id: int):
    if not pieces.delier(parent_id, enfant_id):
        return JSONResponse({"error": "lien inconnu"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/v2/pieces/{piece_id}/offres")
@_piece_route
async def post_offre(piece_id: int, request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    return JSONResponse(pieces.ajouter_offre(piece_id, body, _auteur(body)))


@app.post("/api/v2/offres/{offre_id}/retrait")
@_piece_route
async def post_retrait_offre(offre_id: int, request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    return JSONResponse(pieces.retirer_offre(offre_id, body.get("motif", ""), _auteur(body)))


@app.post("/api/v2/pieces/{piece_id}/mouvements")
@_piece_route
async def post_mouvement(piece_id: int, request: Request):
    body = await _corps(request)
    if isinstance(body, JSONResponse):
        return body
    return JSONResponse(pieces.mouvement(piece_id, body.get("quantite"), str(body.get("quoi", "")),
                                         _auteur(body), str(body.get("preuve", ""))))


@app.get("/api/v2/projects/{projet_id}/achats")
@_piece_route
async def get_achats(projet_id: str):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    return JSONResponse(pieces.achats(projet_id))


@app.get("/api/v2/projects/{projet_id}/cout")
@_piece_route
async def get_cout(projet_id: str):
    if not _projets.existe(projet_id):
        return JSONResponse({"error": "projet inconnu"}, status_code=404)
    a = pieces.achats(projet_id)
    return JSONResponse({"totaux": a["totaux"], "sans_prix": len(a["sans_offre"]),
                         "a_convertir": sum(1 for l in a["lignes"] if l["a_convertir"])})
