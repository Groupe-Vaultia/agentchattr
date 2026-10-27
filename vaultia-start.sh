#!/usr/bin/env bash
# vaultia-start.sh — demarre TOUTE la salle Vaultia proprement : serveur + 11 agents (claude x3, codex x2, qwencode x4, grok, pont gemini).
# 27 oct. 2026 : en-tete corrige (disait « 5 agents » depuis le 21 sept. ; bilan du 27 oct.).
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
rm -f data/provider-config/*.json              # configs d'instances mortes (jetons perimes) ; chaque agent regenere la sienne

echo "== serveur =="
rm -f data/server.log; (umask 077; : > data/server.log)   # le journal affiche le jeton de session : prive
(setsid nohup "$PY" run.py > data/server.log 2>&1 &)
for i in $(seq 1 20); do curl -s -o /dev/null 127.0.0.1:8300/ && break; sleep 0.5; done

echo "== ponts API (Gemini) =="
for a in gemini; do : > "data/$a.log"; (setsid nohup env PATH="$PATH" "$PY" wrapper_api.py "$a" > "data/$a.log" 2>&1 &); done

echo "== agents CLI (Claude, Codex) en tmux =="
tmux new-session -d -s ac-claude -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py claude --dangerously-skip-permissions; read"
tmux new-session -d -s ac-claude2 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py claude --dangerously-skip-permissions; read"
tmux new-session -d -s ac-claude3 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py claude --dangerously-skip-permissions; read"
tmux new-session -d -s ac-codex  -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py codex --dangerously-bypass-approvals-and-sandbox --config=check_for_update_on_startup=false; read"
tmux new-session -d -s ac-codex2 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py codex --dangerously-bypass-approvals-and-sandbox --config=check_for_update_on_startup=false; read"
# 18 oct. 2026 : bolt (Nemotron) retire ; ses 2 instances deviennent qwencode-3 et -4, sur le routeur Qwen :8085 (cartes A + B).
Q8085_FLAGS="--approval-mode=yolo --auth-type openai --openai-base-url http://172.30.0.1:8085/v1 --openai-api-key local -m qwen-cartes-ab"   # nom absent de ~/.qwen/settings.json : sinon Qwen Code reprend son baseUrl :8080
# 19 oct. 2026 : qwencode-1/-2 passent aussi en Q4 sur :8085 (Charles msg tache-26) ; qwen-local :8080 (Q6, 2 cartes) ne charge plus.
tmux new-session -d -s ac-qwencode -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $Q8085_FLAGS; read"
tmux new-session -d -s ac-qwencode2 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $Q8085_FLAGS; read"
tmux new-session -d -s ac-qwencode3 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $Q8085_FLAGS; read"
tmux new-session -d -s ac-qwencode4 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $Q8085_FLAGS; read"
tmux new-session -d -s ac-grok -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py grok; read"

sleep 12
TOK=$(grep -oiE "session token: *[0-9a-f]+" data/server.log | tail -1 | grep -o "[0-9a-f]\{16,\}")
echo "== etat =="
curl -s 127.0.0.1:8300/api/status -H "X-Session-Token: $TOK" | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:v.get('available') for k,v in d.items() if k!='paused'})" 2>/dev/null

echo "== roles =="
sleep 8
sr(){ curl -s -X POST "127.0.0.1:8300/api/roles/$1" -H "X-Session-Token: $TOK" -H "Content-Type: application/json" -d "{\"role\":\"$2\"}" >/dev/null; echo "  $1 -> $2"; }
sr claude-1 chef
sr claude-2 producteur
sr claude-3 producteur
sr codex-1 verificateur
sr codex-2 verificateur
sr grok producteur
sr gemini producteur
sr qwencode-1 producteur
sr qwencode-2 producteur
sr qwencode-3 producteur
sr qwencode-4 producteur
echo "Salle prete : http://127.0.0.1:8300/"
