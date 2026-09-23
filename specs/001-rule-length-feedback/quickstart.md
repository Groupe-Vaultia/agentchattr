# Quickstart: valider le refus des règles trop longues

Prérequis : worktree `wt-claude`, branche `poc/spec-kit`, venv du clone principal.

```bash
PY=~/atelier/agentchattr/.venv/bin/python

# 1. Tests de la fonctionnalité (doivent passer)
$PY -m unittest tests.test_rule_length_feedback -v

# 2. Non-régression : mêmes 5 échecs préexistants, pas un de plus
$PY -m unittest discover -s tests 2>&1 | grep -E "^(Ran|OK|FAILED|FAIL:|ERROR:)"

# 3. Plus aucun « 160 » en dur dans les consignes
grep -n "max 160" mcp_bridge.py   # attendu : aucune ligne
```

Résultats attendus : voir [contracts/chat_rules-propose.md](contracts/chat_rules-propose.md).
