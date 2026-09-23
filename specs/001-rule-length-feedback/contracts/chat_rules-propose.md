# Contract: `chat_rules(action="propose")`

Entrées inchangées : `action`, `sender`, `rule`, `reason`, `channel`.

| Condition (ordre d'évaluation) | Réponse | Effets |
|---|---|---|
| `rule.strip()` vide | `Error: rule text is required.` | aucun |
| `sender` vide | `Error: sender is required.` | aucun |
| `len(rule.strip()) > MAX_TEXT_CHARS` | `Error: rule text is {n} chars; the limit is {MAX_TEXT_CHARS}. Shorten it by {n - MAX_TEXT_CHARS} and propose again. Nothing was saved.` | aucun |
| `len(reason.strip()) > MAX_REASON_CHARS` | `Error: reason is {n} chars; the limit is {MAX_REASON_CHARS}. Shorten it by {n - MAX_REASON_CHARS} and propose again. Nothing was saved.` | aucun |
| sinon | `Proposed rule #{id}: '{text}'. Human will review in the Rules panel.` (inchangé) | règle `pending` + carte `rule_proposal` |

Consignes MCP (`_MCP_INSTRUCTIONS`) : « Keep rules short and imperative (max {MAX_TEXT_CHARS} chars). »
