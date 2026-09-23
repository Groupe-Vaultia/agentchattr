# agentchattr (fork Groupe-Vaultia) Constitution

## Core Principles

### I. Charles tranche, claude produit, codex révise
Charles est propriétaire et décideur final. claude découpe, tranche et produit; codex révise,
teste et appuie; qwenlocal rédige sur un lot assigné; cursor et gemini donnent un avis.
Chaque artefact spec-kit (spec, plan, tâches) nomme son auteur et son réviseur.
Justification : règle R1 v1.5 (`docs/EQUIPE.md`).

### II. Aucun push ni merge sans le oui de Charles
Le cycle est : branche locale → revue codex → go claude → oui de Charles, nommé par branche →
PR → merge par Charles. Une branche de travail n'a pas d'upstream vers `main`.
Aucun force-push.
Justification : règle R2 v1.5.

### III. Zéro secret, périmètre des données respecté
Aucun jeton, PAT, clé, mot de passe ni config Authentik dans une spec, un plan, une tâche,
un commit ou un canal. Ce dépôt est public : le travail cloud y est permis. Vaultia-client
(données, prod, Authentik, logs) reste local et n'est jamais lu par un agent cloud.
Justification : règles R3 et R4 v1.5.

### IV. Preuve ou rien (NON-NEGOTIABLE)
« Vérifié » veut dire une commande et sa sortie, une sortie d'outil MCP ou un `fichier:ligne`.
Chaque tâche d'implémentation se termine par la commande de test qui la prouve. Un
changement de comportement arrive avec un test `unittest` qui échoue avant et passe après.
Un agent sans outils rédige, ne vérifie pas, et le dit.
Justification : règle R6 v1.5; les tests du dépôt sont en `unittest` (`tests/`).

### V. Isolation et petits lots
Qui écrit travaille dans son worktree `wt-<agent>`, jamais dans le clone principal.
Un fichier, un agent à la fois. Pas de `git stash` nu : commit WIP. Une fonctionnalité
spec-kit couvre un seul changement révisable en une passe.
Justification : règle R7 v1.5.

## Contraintes techniques

- Python 3, FastAPI, serveur MCP (`mcp>=1.0,<2.0`); pas de nouvelle dépendance sans
  justification dans le plan.
- Les tests se lancent avec `python -m unittest discover -s tests` depuis le venv du clone.
- Les échecs préexistants de `main` sont listés dans le plan et ne sont pas masqués.
- Les messages destinés aux agents (outils MCP) disent la vérité sur les limites réelles
  (longueurs, droits), pas une valeur périmée.

## Flux de travail spec-kit

`specs/NNN-nom/` contient `spec.md` → `plan.md` → `tasks.md`, dans cet ordre, sur une
branche locale. Chaque étape est relue avant la suivante. Le détail vit dans le dépôt;
le fil de discussion ne reçoit qu'un résumé court et la décision attendue de Charles (R5, R9).

## Governance

Cette constitution applique `docs/EQUIPE.md` (règles v1.5) au flux spec-kit; en cas de
conflit, `docs/EQUIPE.md` et les cartes Rules actives l'emportent. Toute modification
incrémente la version (semver) et dit en une ligne ce qui change (R8). La revue codex
vérifie la conformité aux principes I à V.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): à ratifier par Charles | **Last Amended**: 2026-09-22
