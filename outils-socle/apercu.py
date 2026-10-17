#!/usr/bin/env python3
"""apercu.py — voir un changement de la salle AVANT sa mise en service, sans toucher la salle en service.

v1.0 (2026-10-16, claude) : première version (piste 4 acceptée par Charles).
v1.1 (2026-10-16, claude) : revue codex-2 (msg 4328). Le journal du bac à sable contient le jeton de session que run.py
affiche au démarrage : il est créé en 0600, vidé à chaque lancement, dans un dossier en 0700. La copie des données
exclut les secrets et ce qui agit hors de la tour : jeton de la salle, jetons des agents (registry.json), configuration
des fournisseurs, clé VAPID et abonnements aux notifications (sinon le bac à sable notifierait le vrai cell).

Deux modes :

  bac-a-sable   Copie les données de la salle (data/, sans journaux ni sauvegardes) dans un dossier jetable et
                lance le serveur d'un worktree sur un autre port. Aucun agent n'y est branché : on peut tout
                essayer (écrire, décider, approuver) sans réveiller personne ni toucher les vraies données.
                C'est le bon mode dès qu'un changement touche le serveur (app.py, routes…).

  relais        Sert atelier.html/.css/.js d'un worktree et relaie tout le reste vers la salle en service.
                Pour un changement d'affichage seulement : les données sont les vraies, et une action
                (Discuter, décision, Approuver) compte POUR DE VRAI.

Les deux modes peuvent écouter sur l'adresse Tailscale de la tour (--ecoute 100.x.y.z:PORT) pour un essai au cell.
Seules les origines de l'aperçu lui-même sont traduites vers celle de la salle ; toute autre origine reste refusée
par le contrôle d'origine du serveur, et le jeton de session reste exigé.

Exemples :
  .venv/bin/python outils-socle/apercu.py bac-a-sable --worktree ~/atelier/wt-claude-atelier --ecoute 100.x.y.z:8321
  .venv/bin/python outils-socle/apercu.py relais --worktree ~/atelier/wt-claude-atelier --ecoute 127.0.0.1:8310
  .venv/bin/python outils-socle/apercu.py arreter
"""
import argparse
import http.server
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SALLE = Path(__file__).resolve().parents[1]           # le dépôt (clone principal ou worktree) qui porte l'outil
CACHE = Path.home() / ".cache" / "agentchattr-apercu"  # hors du dépôt : la copie des données n'est jamais commitée
EXCLUS = ("*.log", "sauvegardes", "*_queue.jsonl", "*.sauv-*",
          # secrets et effets hors de la tour : jamais copiés dans le bac à sable
          "session_token", "registry.json", "provider-config", "extra-mcp", ".config.local.toml*",
          "vapid.json", "push_abonnements.json")


def _dossier_prive(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)


def _attendre(url: str, delai: float = 60) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def _pid_ecrit(nom: str, pid: int) -> None:
    _dossier_prive(CACHE)
    (CACHE / f"{nom}.pid").write_text(str(pid))


def bac_a_sable(a) -> int:
    worktree = Path(a.worktree).expanduser().resolve()
    if not (worktree / "run.py").exists():
        print(f"ERREUR : {worktree} n'est pas un dépôt agentchattr (run.py absent).", file=sys.stderr)
        return 1
    source = Path(a.donnees).expanduser().resolve()
    _dossier_prive(CACHE)
    copie = CACHE / "data"
    if copie.exists():
        shutil.rmtree(copie)
    shutil.copytree(source, copie, ignore=shutil.ignore_patterns(*EXCLUS))
    os.chmod(copie, 0o700)
    port = int(a.port)
    # run.py affiche le jeton de session du bac à sable : journal privé (0600), vidé à chaque lancement.
    chemin_journal = CACHE / "bac-a-sable.log"
    journal = os.fdopen(os.open(chemin_journal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb")
    os.chmod(chemin_journal, 0o600)
    # Ports MCP distincts de la salle (8200/8201) : aucun agent ne s'y branche.
    proc = subprocess.Popen(
        [a.python, "run.py", "--data-dir", str(copie), "--port", str(port),
         "--mcp-http-port", str(port - 100), "--mcp-sse-port", str(port - 99)],
        cwd=worktree, stdout=journal, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    _pid_ecrit("bac-a-sable", proc.pid)
    if not _attendre(f"http://127.0.0.1:{port}/"):
        print(f"ERREUR : le bac à sable ne répond pas sur {port} (voir {CACHE / 'bac-a-sable.log'}).", file=sys.stderr)
        return 1
    print(f"Bac à sable : http://127.0.0.1:{port}/atelier  (données copiées dans {copie}, aucun agent branché)")
    if a.ecoute:
        return relais_vers(f"http://127.0.0.1:{port}", a.ecoute, statique=None, jeton=None)
    return 0


def relais(a) -> int:
    worktree = Path(a.worktree).expanduser().resolve()
    jeton = Path(a.jeton).expanduser().read_text().strip()
    return relais_vers(a.amont, a.ecoute, statique=worktree / "static", jeton=jeton)


def relais_vers(amont: str, ecoute: str, statique: Path | None, jeton: str | None) -> int:
    hote, _, port = ecoute.rpartition(":")
    origine_amont = amont.rstrip("/")
    propres = {f"http://{ecoute}"}
    try:  # le nom Tailscale (MagicDNS) de la machine, s'il existe
        nom = socket.getfqdn(hote)
        if nom and nom != hote:
            propres.add(f"http://{nom.rstrip('.')}:{port}")
    except Exception:
        pass
    locaux = {"/static/atelier.css": "text/css", "/static/atelier.js": "text/javascript"}

    class Relais(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # réponse délimitée par la fermeture : le flux en direct (SSE) passe tel quel

        def log_message(self, *args):
            pass

        def _local(self, ctype: str, data: bytes):
            self.send_response(200)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _relayer(self):
            n = int(self.headers.get("Content-Length") or 0)
            corps = self.rfile.read(n) if n else None
            req = urllib.request.Request(origine_amont + self.path, data=corps, method=self.command)
            for k, v in self.headers.items():
                if k.lower() in ("host", "content-length", "connection", "accept-encoding"):
                    continue
                req.add_header(k, origine_amont if (k.lower() == "origin" and v in propres) else v)
            try:
                r = urllib.request.urlopen(req, timeout=None)
            except urllib.error.HTTPError as e:
                r = e
            self.send_response(r.status if hasattr(r, "status") else r.code)
            for k, v in r.headers.items():
                if k.lower() not in ("transfer-encoding", "connection", "content-encoding"):
                    self.send_header(k, v)
            self.end_headers()
            try:
                while True:
                    morceau = r.read1(65536) if hasattr(r, "read1") else r.read(65536)
                    if not morceau:
                        break
                    self.wfile.write(morceau)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            chemin = self.path.split("?")[0]
            if statique is not None and chemin in ("/atelier", "/atelier/"):
                html = (statique / "atelier.html").read_text(encoding="utf-8")
                html = html.replace("</head>", f'<script>window.__SESSION_TOKEN__="{jeton}";</script>\n</head>')
                return self._local("text/html", html.encode())
            if statique is not None and chemin in locaux:
                return self._local(locaux[chemin], (statique / chemin.rsplit("/", 1)[1]).read_bytes())
            return self._relayer()

        do_POST = do_PUT = do_PATCH = do_DELETE = _relayer

    serveur = http.server.ThreadingHTTPServer((hote, int(port)), Relais)
    serveur.daemon_threads = True
    _pid_ecrit("relais", os.getpid())
    print(f"Relais : http://{ecoute}/atelier → {origine_amont}" + (f" (affichage servi depuis {statique})" if statique else ""))
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def arreter(_a) -> int:
    for nom in ("relais", "bac-a-sable"):
        f = CACHE / f"{nom}.pid"
        if not f.exists():
            continue
        try:
            pid = int(f.read_text())
            # Le bac à sable est lancé dans sa propre session : on arrête tout son groupe (serveur + fils MCP).
            os.killpg(pid, signal.SIGTERM) if nom == "bac-a-sable" else os.kill(pid, signal.SIGTERM)
            print(f"{nom} arrêté (pid {pid}).")
        except (ProcessLookupError, ValueError):
            print(f"{nom} : déjà arrêté.")
        f.unlink(missing_ok=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = p.add_subparsers(dest="mode", required=True)
    b = sp.add_parser("bac-a-sable", help="copie des données + serveur du worktree, aucun agent")
    b.add_argument("--worktree", default=str(SALLE))
    b.add_argument("--donnees", default=str(Path.home() / "atelier" / "agentchattr" / "data"))
    b.add_argument("--port", default="8320")
    b.add_argument("--python", default=sys.executable)
    b.add_argument("--ecoute", default="", help="adresse:port d'un relais (ex. l'adresse Tailscale) devant le bac à sable")
    r = sp.add_parser("relais", help="affichage du worktree, données de la salle en service")
    r.add_argument("--worktree", default=str(SALLE))
    r.add_argument("--amont", default="http://127.0.0.1:8300")
    r.add_argument("--jeton", default=str(Path.home() / "atelier" / "agentchattr" / "data" / "session_token"))
    r.add_argument("--ecoute", default="127.0.0.1:8310")
    sp.add_parser("arreter", help="arrête le bac à sable et le relais lancés par cet outil")
    a = p.parse_args()
    return {"bac-a-sable": bac_a_sable, "relais": relais, "arreter": arreter}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main())
