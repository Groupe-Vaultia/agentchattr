# Socle de la Shop de projets — spécification v0.5

v0.5 (12 oct. 2026, claude) : revue de S1 par codex (msg 2039-2040) : un lot qui mêle un projet et une entrée sans projet
n'injecte aucune mémoire ; `chat_send` (MCP) accepte `projet_id` et, sans lui, reprend celui du message auquel il répond.

v0.4 (12 oct. 2026, claude) : S1 codé. 2 corrections de codex (msg 2033) : « inconnu » = 404, `store.py` et
`agents.py` dans le lot S1. Règle ajoutée : un lot de file qui mélange plusieurs projets n'injecte aucune mémoire.

v0.3 (12 oct. 2026, claude) : 2e revue de codex (msg 2029) : chaque déclenchement transporte son `projet_id`, un ID
inconnu est une erreur, `defaut` n'injecte plus rien, fixture synthétique (R4), lignes corrigées par grok (msg 2028).
Répartition approuvée par Charles, gemini et grok compris (msg 2030).

v0.2 (12 oct. 2026, claude) : ajoute la revue de codex (msg 2023) : identité stable, invariants, migration de
`projects.json`, injection de la mémoire par projet (point bloquant), tests de S1, et la répartition du code
entre les agents (msg 2024).
v0.1 (12 oct. 2026, claude) : première version. Elle reprend les décisions de Charles des messages 1995 à 2021
de #developpement-de-pro. Elle n'est pas encore codée.

## Pourquoi un socle avant l'interface

La salle sait aujourd'hui gérer un seul projet à la fois. Deux faits le montrent :

- `projects.py` a **un seul projet actif pour toute la salle** (`activer`, `memoire_active`). Sa mémoire est
  injectée à chaque agent. Si deux produits avancent en même temps, une exécution peut recevoir la mémoire de
  l'autre projet.
- `jobs.py` rattache un job à un **canal** (`create(..., channel)`), jamais à un projet. On ne peut donc pas
  attribuer une consigne, une preuve ou un livrable au bon produit.

L'interface (maquette `~/atelier/maquettes/atelier-rd-v0.6.html`) affichera ce socle. Elle ne remplace pas.

## La chaîne

```
Projet ──< Tâche ──< Exécution ──< Événement
   │          │           └──> Message (conversation unique, étiqueté projet + tâche)
   │          └──> Équipe (rôles)
   └──< Livrable ──< Révision figée
```

| Objet | Champs | Règle |
|---|---|---|
| **Projet** | `id`, `nom`, `objectif`, `livrable_attendu`, `statut` (actif · en veille · terminé), `memoire`, `cree`, `maj` | En veille, aucun agent n'est déclenché pour ce projet. La mémoire est **par projet** et n'est plus globale |
| **Tâche** (une carte) | `id`, `projet_id`, `titre`, `etape` (exigences · pièces · essais · livrable), `etat` (à faire · en cours · attend Charles · bloqué · fait), `responsable`, `equipe[]`, `critere`, `preuve` | **Un seul responsable**, qui répond du résultat. Elle ne passe à `fait` qu'avec une `preuve` (commande et sortie, sortie d'outil ou fichier:ligne, règle R6) |
| **Équipe** | `[{agent, role}]`, avec `role` parmi producteur · vérificateur · relecteur · proposant | Un fichier, un agent (R7) : deux producteurs ne touchent jamais au même fichier |
| **Exécution** | `id` (uuid), `tache_id`, `agent`, `role`, `consigne`, `memoire_injectee` (celle de **son** projet), `debut`, `dernier_signe`, `fin`, `issue` | Sans signe de vie depuis 10 min, l'exécution passe `silencieux`, jamais `actif`. Une fin tardive ou reçue en double ne la ressuscite pas (test de codex) |
| **Événement** | `execution_id`, `heure`, `outil`, `resume` | Alimente le panneau « En direct ». Jamais de journal brut ni de scratchpad, pour qu'aucun secret ne fuie (R3) |
| **Message** | les champs actuels + `projet_id`, `tache_id` | La conversation reste **unique**. Les filtres « Ce sujet / Ce projet / Tout » ne créent pas de conversations séparées |
| **Livrable** | `id`, `projet_id`, `tache_id`, `chemin`, `empreinte` (sha256), `version` | — |
| **Révision** | `projet_id`, `numero` (P01…), `livrables[]` avec empreintes, `approuvee_par`, `heure` | « Approuver » fige les empreintes visibles au moment du clic. Tout changement ultérieur va dans la révision suivante (test de codex) |

L'**étape du projet** se calcule à partir de ses tâches : c'est la première étape qui contient une tâche pas encore faite. Elle ne se saisit pas à la main.

L'**historique** se lit, il ne se tient pas à part : il regroupe les exécutions, les décisions (approbations, mises en veille, tâches
ajoutées), les messages et les révisions du projet, triés par date.

## Combinaisons d'agents (décision de Charles, msg 2021)

| Combinaison | Forme dans le socle |
|---|---|
| Producteur + vérificateur | `equipe = [{qwen, producteur}, {codex, vérificateur}]` |
| Tâches découpées en parallèle | Sous-tâches avec chacune son responsable et ses fichiers. claude assemble |
| Deux propositions concurrentes | Deux exécutions `proposant` sur la même tâche. claude tranche sur des chiffres (FEM, masse, coût) |
| Revue croisée | `{x, relecteur}` obligatoire avant `fait` pour un livrable destiné à Charles |

Contraintes mesurées :

- Qwen local fait **une exécution à la fois**. Deux appels en parallèle prennent autant de temps qu'à la suite (254 s à 60 k
  jetons, le 3 oct.). Ses exécutions passent donc en file, dans l'ordre de priorité fixé par claude.
- Les agents cloud (claude, codex, grok, gemini) peuvent travailler en parallèle, chacun sur ses fichiers.

## Production : loop-engine utilisé comme outil

- La Shop lance loop-engine par sa ligne de commande et lit son journal pour remplir les événements d'exécution.
  **Loop-engine reste inchangé** : décision de Charles du 3 oct., « la salle n'entre pas dans loop-engine ».
- Le SX1 P01 a déjà été produit ainsi : 7 tâches sur 7 réussies en 5 min 8, vérifiées par la porte CAO
  (wt-loop-cao/PILOTE-CAO.md).
- Une tâche de fabrication passe aussi par le harnais Bambu : `check` (FEM), `slice`, `inspect cost`.

## Le gestionnaire (claude)

| Moment | Ce que fait claude |
|---|---|
| Objectif reçu | Découpe en tâches avec critères, assigne le responsable et l'équipe |
| Ronde planifiée (`schedules.py`, toutes les 30 min) | Relance les exécutions silencieuses ou réassigne leur tâche, fait avancer la file de Qwen, signale ce qui attend Charles |
| Preuve reçue | Vérifie le critère, puis passe la tâche à `fait` ou la renvoie avec la correction |
| Livrable prêt | Demande la revue de codex, puis l'approbation de Charles |

## Identité et invariants (revue de codex, v0.2)

- Le **`projet_id`** est stable : un slug ASCII tiré du nom à la création (`support-x1`), unique, qui ne change
  jamais. Le nom, lui, peut changer.
- Une `tache.projet_id` doit exister. Une `execution.tache_id` doit appartenir au même projet que la tâche.
  Un `message.tache_id`, quand il est présent, doit appartenir au `message.projet_id`. Un écart est **refusé**
  (HTTP 422), jamais corrigé en silence.
- `equipe` ne contient pas deux fois le même couple (agent, rôle), et le responsable est l'un des membres.
- Pour `projet_id`, une valeur **absente** signifie « sans projet », jamais « le projet actif ». Une valeur **inconnue** est
  une erreur : 404 sur la route de mémoire, 422 sur `POST /api/send`, message refusé sur le WebSocket.

## Migration de `projects.json` (S1)

| Ancien | Nouveau |
|---|---|
| `{"projets": {nom: {memoire, cree, channels}}, "actif": nom}` | `{"version": 2, "projets": {projet_id: {nom, objectif, livrable_attendu, statut, memoire, cree, maj, channels}}, "defaut": projet_id}` |
| clé `nom` | `projet_id = slug(nom)`, `nom` conservé tel quel. En cas de collision de slug : suffixe `-2`, `-3` |
| `actif` | devient `defaut` : le projet des canaux rattachés à aucun projet. Il ne sert **plus** à injecter la mémoire d'une exécution qui a son propre projet |
| tous les projets | `statut = "actif"`, `objectif` et `livrable_attendu` vides |

- La migration se fait au premier chargement. L'ancien fichier est gardé en `projects.v1.json`, et
  l'écriture est atomique (fichier temporaire, puis `os.replace`).
- **L'API existante est conservée** : `GET /api/projects` rend encore `actif` (= `defaut`) et `projets` indexés
  par nom, en plus de `v2`. Les routes `activate`, `memory` et `assign` acceptent le nom comme l'identifiant.

## Injection de la mémoire : point bloquant (S1)

Aujourd'hui, `wrapper.py` (`_fetch_project_memory` l. 468, injection l. 576-586) et `wrapper_api.py`
(`get_project_memory`, l. 223-232) injectent la mémoire du projet global `actif` dans **chaque** déclenchement.

S1 change la règle (v0.3) : **chaque déclenchement transporte son `projet_id`**.

1. S1 ajoute un champ facultatif `projet_id` aux messages (`store.py`). Le serveur le recopie dans l'entrée de
   file de l'agent déclenché (`agents.py`, `trigger` et `trigger_sync`, qui écrivent `<agent>_queue.jsonl`). Un job (S2) le recopiera de la même façon.
2. Les deux wrappers lisent `projet_id` dans l'entrée de file, puis demandent
   `GET /api/projects/{projet_id}/memory`.
3. Règles de résolution :

| Déclenchement | Mémoire injectée |
|---|---|
| `projet_id` présent et connu | celle de ce projet, et d'aucun autre |
| `projet_id` présent mais **inconnu** | **aucune**. La route répond 404 et le wrapper l'écrit au journal, sans repli sur un autre projet |
| `projet_id` absent, canal rattaché à un projet (`assigner_canal`, canaux d'avant la Shop) | celle du projet du canal |
| `projet_id` absent, canal non rattaché (dont la conversation multi-projet de l'atelier) | **aucune** |

4. Un lot de file qui contient **plusieurs** `projet_id` différents, ou un `projet_id` et une entrée **sans** projet
   (déclenchements regroupés), n'injecte **aucune** mémoire : c'est ambigu, et on ne mélange pas les contextes.
5. Les réponses des agents par MCP (`chat_send`) portent `projet_id` : explicite, sinon celui du message de `reply_to`.
   Un ID inconnu refuse l'envoi.
6. `defaut` (l'ancien `actif`) **n'injecte plus rien**. Il reste dans `GET /api/projects` sous le nom `actif`,
   pour l'affichage des anciens clients.

Ce contrat ne dépend pas de S2. Les jobs s'y brancheront quand ils auront leur `projet_id`.

## Tests de S1 (proposés par codex, retenus)

1. Migration d'un `projects.json` v1 **synthétique** (fixture, aucune mémoire réelle : R4) vers v2 : aucun projet, mémoire ni canal perdu,
   `projects.v1.json` présent.
2. Redémarrage : le v2 se recharge à l'identique, sans nouvelle migration.
3. Deux déclenchements A et B intercalés, l'un avec `projet_id=a`, l'autre avec `projet_id=b`, dans le même canal : chacun
   reçoit **uniquement** la mémoire de son projet.
4. `projet_id` inconnu : 404 et aucune mémoire. `projet_id` absent dans un canal non rattaché : aucune mémoire,
   même si `defaut` est défini.
5. Compatibilité : les routes existantes rendent la même forme qu'avant pour un client v1.
6. Slugs en collision : `-2`, puis `-3`.

## Répartition du code entre les agents (msg 2024) : la Shop testée sur elle-même

S1 fixe le contrat (modèle, routes, migration). Une fois S1 fusionné, les autres lots se codent **en parallèle**,
chacun dans son worktree, sur des fichiers distincts (R7).

| Lot | Responsable (producteur) | Fichiers | Vérificateur |
|---|---|---|---|
| S1 projets, mémoire par déclenchement, wrappers | **claude** | `projects.py`, `store.py`, `agents.py`, `wrapper.py`, `wrapper_api.py`, routes de `app.py` | codex |
| Tests de S1 à S5, écrits d'après la spec | **codex** | `tests/test_socle_*.py` | claude |
| S2 tâches et équipe | **claude** | `jobs.py` (+ routes) | codex |
| S3 exécutions et événements | **claude** | `executions.py` (nouveau) | codex |
| S5 révisions et empreintes | **gemini** | `revisions.py` (nouveau) | codex |
| Historique, lecture seule | **grok** | `historique.py` (nouveau) | codex |
| Interface, d'après la maquette v0.6 | **qwencode** | `static/atelier.js`, `static/atelier.css` (nouveaux) | codex, puis Charles |

- gemini et grok codent par **exception à R1 v1.5, accordée par Charles** (msg 2030). Chacun a un module neuf et
  isolé, derrière les tests de codex.
- qwencode peut commencer l'interface avant S1, avec des données d'essai qui suivent le contrat des routes.
- claude garde les lots qui touchent au cœur de la salle (wrappers, jobs) : une erreur à cet endroit coupe tous
  les agents.

## Lots de travail (après le oui de Charles)

| Lot | Contenu | Producteur | Revue |
|---|---|---|---|
| S1 | `projects.py` : plusieurs projets actifs, statut, mémoire par projet. Migration de `projects.json` | claude | codex |
| S2 | `jobs.py` : `projet_id`, `etape`, `responsable`, `equipe`, `preuve`. Migration des jobs existants vers « sans projet » | claude | codex |
| S3 | Exécutions et événements : identifiant, dernier signe de vie, état silencieux, mémoire injectée par exécution | claude | codex (tests de reprise après plantage) |
| S4 | Messages étiquetés `projet_id` et `tache_id`, routes API de filtrage | claude | codex |
| S5 | Révisions figées par empreintes, historique lu | claude | codex |
| S6 | Ronde planifiée du gestionnaire | claude | codex |
| UI | Interface branchée sur S1 à S5, d'après la maquette v0.6 | qwencode | codex, puis Charles |

Cycle de chaque lot (R2) : branche → revue codex → go claude → oui de Charles → PR → merge.
