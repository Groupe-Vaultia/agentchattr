#!/usr/bin/env bash
# vaultia-watchdog.sh — surveille la salle et relance ce qui tombe (ponts, agents CLI, serveur).
# Objectif : plus de pauses/pannes a gerer a la main.
# 19 oct. 2026 (claude-2, claude-1 msg 5600) : cli() remplace par scripts/gardien_instances.py. L'ancien cli() ne regardait que
# l'instance 1 et son pkill tuait les relais de TOUTES les instances de la famille (qwencode-3 et -4 sans relais depuis 17 h 10).
# Le gardien juge chaque instance (ac-<a><n> / agentchattr-<a>-<n>), ne tue qu'un PID, relance avec la commande d'origine du
# lanceur, et se contente de signaler un relais mort dont le TUI vit (le relancer fermerait le TUI).
GARDE="claude:3 codex:2 qwencode:4 grok:1"   # doit suivre les lanceurs de vaultia-start.sh
cd "$(dirname "$0")" || exit 1
NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"
export PATH="${NODE_BIN}:$HOME/.local/bin:$PATH"
PY=".venv/bin/python"
LOG="data/watchdog.log"
tok(){ grep -oiE "session token: *[0-9a-f]+" data/server.log | tail -1 | grep -o "[0-9a-f]\{16,\}"; }
note(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$LOG"; }
dereg(){ local a="$1"; local t; t="$(tok)"; for n in "$a" "$a-1" "$a-2" "$a-3"; do curl -s -X POST "127.0.0.1:8300/api/deregister/$n" -H "X-Session-Token: $t" >/dev/null 2>&1; done; }

pont(){ # $1 = nom d'agent API
  local a="$1"
  if ! pgrep -f "wrapper_api.py $a" >/dev/null 2>&1; then
    dereg "$a"; : > "data/$a.log"
    (setsid nohup env PATH="$PATH" "$PY" wrapper_api.py "$a" > "data/$a.log" 2>&1 &)
    note "pont relance : $a"
  fi
}
cli(){ # une passe sur toutes les instances CLI ; options de secours si aucun lanceur de la famille n'a de commande connue
  "$PY" scripts/gardien_instances.py $GARDE \
    --defaut "claude=--dangerously-skip-permissions" \
    --defaut "codex=--dangerously-bypass-approvals-and-sandbox --config=check_for_update_on_startup=false" \
    --defaut "qwencode=--approval-mode=yolo" \
    --defaut "grok=" >> "$LOG" 2>&1
}

note "gardien demarre"
while true; do
  if ! curl -s -o /dev/null --max-time 5 127.0.0.1:8300/ ; then
    note "SERVEUR injoignable -> vaultia-start.sh"
    ./vaultia-start.sh >> "$LOG" 2>&1
    sleep 25; continue
  fi
  pont gemini   # cursor et qwenlocal retires le 4 oct. 2026
  cli
  sleep 30
done
