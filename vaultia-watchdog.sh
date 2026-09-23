#!/usr/bin/env bash
# vaultia-watchdog.sh — surveille la salle et relance ce qui tombe (ponts, agents CLI, serveur).
# Objectif : plus de pauses/pannes a gerer a la main.
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
cli(){ # $1 = nom ; $2.. = flags
  local a="$1"; shift
  # la session TUI reelle (agentchattr-<a>) meurt quand le CLI meurt ; c'est le vrai signal
  if ! tmux has-session -t "agentchattr-$a" 2>/dev/null; then
    tmux kill-session -t "ac-$a" 2>/dev/null; dereg "$a"
    tmux new-session -d -s "ac-$a" -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py $a $*; read"
    note "agent CLI relance : $a"
  fi
}

note "gardien demarre"
while true; do
  if ! curl -s -o /dev/null --max-time 5 127.0.0.1:8300/ ; then
    note "SERVEUR injoignable -> vaultia-start.sh"
    ./vaultia-start.sh >> "$LOG" 2>&1
    sleep 25; continue
  fi
  pont qwenlocal; pont cursor; pont gemini
  cli claude --dangerously-skip-permissions
  cli codex --dangerously-bypass-approvals-and-sandbox
  cli qwencode
  sleep 30
done
