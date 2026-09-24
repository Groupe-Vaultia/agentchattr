#!/usr/bin/env bash
# Lanceur Grok pour agentchattr : branche le MCP de la salle (jeton injecte par-lancement
# dans GROK_MCP_CONTENT), puis demarre le TUI grok. 22 sept. 2026.
export PATH="$HOME/.grok/bin:$PATH"
if [ -n "$GROK_MCP_CONTENT" ]; then
  url=$(printf '%s' "$GROK_MCP_CONTENT" | python3 -c "import json,sys;d=json.load(sys.stdin);s=list(d['mcp'].values())[0];print(s.get('url',''))" 2>/dev/null)
  tok=$(printf '%s' "$GROK_MCP_CONTENT" | python3 -c "import json,sys;d=json.load(sys.stdin);s=list(d['mcp'].values())[0];print(s.get('headers',{}).get('Authorization','').replace('Bearer ',''))" 2>/dev/null)
  if [ -n "$url" ]; then
    grok mcp remove agentchattr >/dev/null 2>&1
    if [ -n "$tok" ]; then grok mcp add agentchattr "$url" -t http -H "Authorization: Bearer $tok" >/dev/null 2>&1
    else grok mcp add agentchattr "$url" -t http >/dev/null 2>&1; fi
  fi
fi
exec grok --always-approve "$@"
