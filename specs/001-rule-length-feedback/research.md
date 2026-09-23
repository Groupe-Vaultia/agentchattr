# Research: Refus explicite des règles trop longues

## D1 — Refuser, ne pas tronquer en prévenant

- **Decision**: refuser la proposition hors limite, avec un message chiffré.
- **Rationale**: une règle tronquée « avec avertissement » est quand même enregistrée et publiée
  en carte; Charles pourrait l'approuver sans voir l'avertissement, qui ne va qu'à l'agent.
  Un refus ne laisse aucun état incohérent.
- **Alternatives considered**: tronquer et ajouter « (truncated) » dans la réponse (rejeté :
  la carte reste fausse); relever la limite (rejeté : hors sujet, la limite n'est pas le défaut).

## D2 — Valider dans l'outil MCP, pas dans `RuleStore`

- **Decision**: la validation se fait dans `mcp_bridge.chat_rules`; `RuleStore.propose` et
  `RuleStore.edit` gardent `[:MAX_TEXT_CHARS]`.
- **Rationale**: faire lever une exception à `RuleStore` obligerait à modifier le chemin
  websocket de `app.py` (`rule_propose`, `rule_edit`), déjà borné côté interface par
  `maxlength=600` (`static/rules-panel.js:374`, `:433`). Le défaut F11 vise le chemin agent.
- **Alternatives considered**: `RuleStore.propose` lève `ValueError` (rejeté pour ce lot :
  périmètre ×2, touche l'interface); à reconsidérer si un autre chemin agent apparaît.

## D3 — Une seule source pour la limite

- **Decision**: `mcp_bridge` importe `MAX_TEXT_CHARS` et `MAX_REASON_CHARS` depuis `rules`
  et les injecte dans `_MCP_INSTRUCTIONS`.
- **Rationale**: le « 160 » de `mcp_bridge.py:97` a divergé de `rules.py:9` quand la limite
  est passée à 600 (0c9a8af). Une seule définition empêche la récidive (FR-005).

## D4 — Longueur comptée après `strip()`

- **Decision**: compter `len(rule.strip())`, en caractères Unicode.
- **Rationale**: c'est ce que `RuleStore` stocke; refuser sur la longueur brute rejetterait
  un texte qui tient une fois les espaces de bord retirés.

## Hors périmètre (suite possible)

- `app.py` chemin websocket `rule_propose` : la carte affiche `text` non tronqué alors que la
  règle stockée l'est. Sans effet tant que l'interface borne à 600.
