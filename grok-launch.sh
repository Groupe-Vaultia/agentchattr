#!/usr/bin/env bash
# Lanceur Grok pour agentchattr : declare les serveurs MCP recus dans GROK_MCP_CONTENT -- celui de la
# salle (jeton par-lancement) et les serveurs propres a grok, comme le coffre de memoire commune
# (data/extra-mcp/grok.json) -- puis demarre le TUI grok. 22 sept. 2026 ; tous les serveurs, 26 sept.
export PATH="$HOME/.grok/bin:$PATH"
if [ -n "$GROK_MCP_CONTENT" ]; then
  printf '%s' "$GROK_MCP_CONTENT" | python3 -c '
import json, subprocess, sys
d = json.load(sys.stdin)
for nom, s in (d.get("mcp") or {}).items():
    subprocess.run(["grok", "mcp", "remove", nom], capture_output=True)
    if s.get("url"):
        cmd = ["grok", "mcp", "add", nom, s["url"], "-t", "http"]
        auth = (s.get("headers") or {}).get("Authorization")
        if auth:
            cmd += ["-H", "Authorization: " + auth]
    elif s.get("command"):
        cmd = ["grok", "mcp", "add", nom]
        for k, v in (s.get("env") or {}).items():
            cmd += ["-e", k + "=" + v]
        cmd += ["--", s["command"], *(s.get("args") or [])]
    else:
        continue
    subprocess.run(cmd, capture_output=True)
' 2>/dev/null
fi
exec grok --always-approve "$@"
