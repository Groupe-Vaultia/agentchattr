---

description: "Task list for 001-rule-length-feedback"
---

# Tasks: Refus explicite des règles trop longues

**Input**: Design documents from `/specs/001-rule-length-feedback/`

**Prerequisites**: plan.md, spec.md, research.md, contracts/

**Tests**: requis par la constitution (IV : un test qui échoue avant, passe après).

**Auteur**: claude · **Réviseur**: codex

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Branche locale `poc/spec-kit` depuis `origin/main`, sans upstream, dans `wt-claude`
- [X] T002 Base de référence : `python -m unittest discover -s tests` → 154 tests, 5 échecs préexistants (plan.md)

## Phase 2: Foundational

Aucune (pas de prérequis partagé).

## Phase 3: User Story 1 — L'agent apprend que sa règle est trop longue (P1) 🎯 MVP

**Goal**: refus chiffré, rien d'enregistré, pour le texte et la justification.

**Independent Test**: `python -m unittest tests.test_rule_length_feedback -v`

- [X] T003 [US1] Tests dans `tests/test_rule_length_feedback.py` : texte limite+1 refusé
  sans règle ni carte; texte à la limite enregistré intact; justification limite+1 refusée;
  espaces de bord non comptés; accents comptés en caractères. Constat : échouent avant T004.
- [X] T004 [US1] `mcp_bridge.py` `chat_rules` : validation des longueurs avant
  `rules.propose`, messages selon `contracts/chat_rules-propose.md`

**Checkpoint**: T003 passe.

## Phase 4: User Story 2 — Les consignes donnent la vraie limite (P2)

**Independent Test**: test `test_instructions_announce_real_limit`

- [X] T005 [US2] Test : `_MCP_INSTRUCTIONS` contient `max {MAX_TEXT_CHARS} chars` et pas `max 160`
- [X] T006 [US2] `mcp_bridge.py` : importer les limites depuis `rules` et les injecter dans `_MCP_INSTRUCTIONS`

## Phase 5: Polish

- [X] T007 Non-régression : suite complète, mêmes 5 échecs préexistants, aucun nouveau
- [ ] T008 Revue codex du diff (`git diff origin/main...poc/spec-kit`)
- [ ] T009 Go claude, puis oui de Charles nommé pour `poc/spec-kit` avant tout push (R2)

## Dependencies & Execution Order

T001 → T002 → T003 → T004 → (T005 → T006) → T007 → T008 → T009.
US2 est indépendante de US1 mais touche le même fichier (`mcp_bridge.py`) : exécution
séquentielle, un seul agent (constitution V). Aucune tâche [P].

## Implementation Strategy

MVP = US1 seule (défaut F11). US2 est un correctif de cohérence, livré dans le même lot
car il touche le même fichier et fait moins de 5 lignes.
