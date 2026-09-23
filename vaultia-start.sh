#!/usr/bin/env bash
# vaultia-start.sh — demarre TOUTE la salle Vaultia proprement : serveur + 5 agents.
# Evite le piege recurrent (serveur relance sans ses ponts -> agents "en ligne" mais muets).
cd "$(dirname "$0")" || exit 1
NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"
export PATH="${NODE_BIN}:$HOME/.local/bin:$PATH"
PY=".venv/bin/python"

echo "== arret de l'existant =="
for s in $(tmux ls 2>/dev/null | cut -d: -f1 | grep -iE '^ac-|^agentchattr-'); do tmux kill-session -t "$s" 2>/dev/null; done
python3 - <<'PYKILL'
import glob,os,signal
for d in glob.glob('/proc/[0-9]*'):
    try: c=open(d+'/cmdline','rb').read().decode(errors='replace').replace(chr(0),' ')
    except OSError: continue
    cw=os.readlink(d+'/cwd') if os.path.exists(d+'/cwd') else ''
    if ('run.py' in c and 'agentchattr' in cw) or 'wrapper_api.py' in c or 'wrapper.py claude' in c or 'wrapper.py codex' in c:
        try: os.kill(int(d.split('/')[-1]), signal.SIGKILL)
        except OSError: pass
PYKILL
sleep 2; fuser -k 8300/tcp 2>/dev/null; sleep 2
rm -f data/registry.json data/renames.json   # repart de noms propres

echo "== serveur =="
: > data/server.log
(setsid nohup "$PY" run.py > data/server.log 2>&1 &)
for i in $(seq 1 20); do curl -s -o /dev/null 127.0.0.1:8300/ && break; sleep 0.5; done

echo "== ponts API (Qwen local, Cursor, Gemini) =="
for a in qwenlocal cursor gemini; do : > "data/$a.log"; (setsid nohup env PATH="$PATH" "$PY" wrapper_api.py "$a" > "data/$a.log" 2>&1 &); done

echo "== agents CLI (Claude, Codex) en tmux =="
tmux new-session -d -s ac-claude -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py claude --dangerously-skip-permissions; read"
tmux new-session -d -s ac-codex  -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py codex --dangerously-bypass-approvals-and-sandbox; read"

sleep 12
TOK=$(grep -oiE "session token: *[0-9a-f]+" data/server.log | tail -1 | grep -o "[0-9a-f]\{16,\}")
echo "== etat =="
curl -s 127.0.0.1:8300/api/status -H "X-Session-Token: $TOK" | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:v.get('available') for k,v in d.items() if k!='paused'})" 2>/dev/null
echo "Salle prete : http://127.0.0.1:8300/"
