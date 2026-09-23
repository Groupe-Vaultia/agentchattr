# Feature Specification: Refus explicite des règles trop longues

**Feature Branch**: `poc/spec-kit`

**Created**: 2026-09-22

**Status**: Draft

**Auteur**: claude · **Réviseur**: codex · **Décideur**: Charles

**Input**: Friction F11 de `docs/ORCHESTRATEUR.md` v0.5 (branche `equipe/regles`) : « Règles
tronquées sans avertissement au proposant ». Choisie comme module de l'essai spec-kit
(Charles, #rechercherepospourde #672).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - L'agent apprend que sa règle est trop longue (Priority: P1)

Un agent propose une règle dont le texte dépasse la limite. Aujourd'hui, la règle est
enregistrée coupée et l'agent reçoit « Proposed rule #N » comme si tout allait bien; la fin
de la règle est perdue sans que personne le sache. Désormais, la proposition est refusée et
l'agent reçoit un message qui donne la longueur envoyée, la limite et l'écart, pour qu'il
raccourcisse et repropose.

**Why this priority**: c'est le défaut constaté (#96) : une règle d'équipe amputée sans
avertissement, donc une règle différente de celle que Charles croit approuver.

**Independent Test**: proposer via l'outil de règles un texte de limite + 1 caractères;
constater le refus, le message chiffré, et qu'aucune règle ni carte n'a été créée.

**Acceptance Scenarios**:

1. **Given** un texte de règle plus long que la limite, **When** un agent le propose,
   **Then** la proposition est refusée, aucune règle n'est enregistrée, aucune carte de
   proposition n'apparaît dans le fil, et la réponse indique la longueur reçue et la limite.
2. **Given** un texte de règle exactement à la limite, **When** un agent le propose,
   **Then** la règle est enregistrée intégralement, sans perte d'un seul caractère.
3. **Given** une justification (reason) plus longue que sa limite, **When** un agent
   propose une règle, **Then** la proposition est refusée avec un message qui chiffre la
   justification (longueur reçue, limite).

---

### User Story 2 - Les consignes aux agents donnent la vraie limite (Priority: P2)

Les consignes envoyées aux agents à la connexion disent « max 160 chars », alors que la
limite réelle est 600 depuis 0c9a8af. Les consignes doivent donner la limite réelle, tirée
de la même source que la validation, pour ne plus jamais diverger.

**Why this priority**: une consigne fausse pousse les agents à s'autocensurer (160) ou à se
fier à un chiffre qui ne correspond pas au comportement réel.

**Independent Test**: lire les consignes du serveur et vérifier qu'elles contiennent la
limite en vigueur et non 160.

**Acceptance Scenarios**:

1. **Given** le serveur démarré, **When** un agent lit les consignes, **Then** la limite
   annoncée égale la limite appliquée.

### Edge Cases

- Espaces en début et fin : la longueur comptée est celle du texte après retrait des
  espaces de bord (comportement actuel du stockage), pour ne pas refuser un texte qui tient.
- Caractères accentués et emoji : la limite compte des caractères, pas des octets.
- Texte vide ou fait d'espaces : l'erreur actuelle « rule text is required » est conservée.
- L'interface web (humain) limite déjà la saisie à 600 caractères : hors périmètre.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Une proposition d'agent dont le texte dépasse la limite MUST être refusée
  sans rien enregistrer ni publier dans le fil.
- **FR-002**: Le message de refus MUST contenir la longueur reçue, la limite et le nombre
  de caractères à retirer.
- **FR-003**: Une proposition dont la justification dépasse sa limite MUST être refusée
  selon FR-001 et FR-002, appliqués à la justification.
- **FR-004**: Un texte à la limite ou en dessous MUST être enregistré intégralement.
- **FR-005**: Les consignes aux agents MUST annoncer la limite réelle du texte, issue de la
  même définition que celle qui sert à la validation.

### Key Entities

- **Proposition de règle** : texte, justification, auteur, canal. Limites : texte 600,
  justification 240 caractères (valeurs actuelles).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 règle enregistrée dont le texte diffère de celui que l'agent a envoyé
  (après retrait des espaces de bord).
- **SC-002**: 100 % des refus pour longueur indiquent la longueur reçue et la limite.
- **SC-003**: La limite annoncée aux agents et la limite appliquée sont identiques.
- **SC-004**: Aucun test existant qui passait sur `main` ne se met à échouer.

## Assumptions

- Refuser vaut mieux que tronquer en prévenant : une règle tronquée n'est pas celle que
  l'agent a voulue, et Charles approuverait un texte que personne n'a écrit.
- Les limites 600 et 240 restent inchangées; seul le signalement change.
- Le chemin web (humain) et la troncature de dernier recours du stockage restent tels
  quels; la carte de proposition du chemin websocket qui affiche le texte non tronqué
  (`app.py`, `rule_propose`) est notée comme suite possible, hors périmètre.
