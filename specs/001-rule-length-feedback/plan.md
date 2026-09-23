# Implementation Plan: Refus explicite des règles trop longues

**Branch**: `poc/spec-kit` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-rule-length-feedback/spec.md`

**Auteur**: claude · **Réviseur**: codex

## Summary

L'outil MCP `chat_rules(action="propose")` vérifie la longueur du texte et de la
justification **avant** d'appeler `RuleStore.propose`. Hors limite : il retourne une erreur
chiffrée, sans enregistrer de règle ni publier de carte. Les consignes MCP tirent la limite de
`rules.MAX_TEXT_CHARS` au lieu du « 160 » écrit en dur. `RuleStore` garde sa troncature
comme garde-fou de dernier recours pour les autres chemins (voir [research.md](research.md)).

## Technical Context

**Language/Version**: Python 3.14 (venv du clone principal)

**Primary Dependencies**: `mcp` FastMCP (`mcp>=1.0,<2.0`); aucune nouvelle dépendance

**Storage**: `rules.json` via `RuleStore` (inchangé)

**Testing**: `unittest`, `python -m unittest discover -s tests`

**Target Platform**: serveur Linux local (agentchattr)

**Project Type**: service web + serveur MCP

**Performance Goals**: N/A (une comparaison de longueur)

**Constraints**: le message d'erreur reste en anglais, comme les autres erreurs de
`mcp_bridge.py` (« Error: … »)

**Scale/Scope**: 2 fichiers de code (`mcp_bridge.py`, `rules.py` inchangé sauf lecture des
constantes), 1 fichier de test nouveau

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Vérification | État |
|---|---|---|
| I. Rôles | Auteur claude, réviseur codex, décideur Charles nommés en tête de spec et de plan | ✅ |
| II. Push/merge | Branche locale `poc/spec-kit`, upstream retiré (`git branch --unset-upstream`) | ✅ |
| III. Secrets/données | Aucun secret; dépôt public, travail cloud permis | ✅ |
| IV. Preuve | Tests qui échouent avant et passent après; base de référence : 154 tests, 5 échecs préexistants (voir ci-dessous) | ✅ |
| V. Isolation | Travail dans `wt-claude`; un seul agent écrit | ✅ |

**Échecs préexistants sur `origin/main` (a2963ef)**, hors périmètre, à ne pas masquer :
`test_session_reclaim` ×3, `test_identity_contract` ×1, `test_room_name` ×1
(`python -m unittest discover -s tests` → `Ran 154 tests … FAILED (failures=3, errors=2, skipped=1)`).

Re-check post-design : inchangé, ✅.

## Project Structure

### Documentation (this feature)

```text
specs/001-rule-length-feedback/
├── spec.md
├── plan.md              # ce fichier
├── research.md          # décisions et alternatives
├── contracts/
│   └── chat_rules-propose.md
├── quickstart.md        # scénarios de validation
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

`data-model.md` omis : aucune entité nouvelle ni modifiée (limites existantes réutilisées).

### Source Code (repository root)

```text
mcp_bridge.py                         # validation dans chat_rules + consignes
rules.py                              # constantes MAX_TEXT_CHARS / MAX_REASON_CHARS (lues, inchangées)
tests/test_rule_length_feedback.py    # nouveau
```

**Structure Decision**: projet unique à plat, tests `unittest` dans `tests/`, comme le reste du dépôt.

## Complexity Tracking

Aucune violation.
