# Socle de la Shop de projets — spécification v1.0

v1.0 (13 oct. 2026, claude) : la salle et l'atelier se parlent (msg 2198). Un message sans étiquette prend celle de
son canal : `tache-<id>` donne la tâche (et son projet), un canal rangé sous un projet donne le projet. Une étiquette
explicite garde la priorité ; un canal `tache-N` sans tâche n'est jamais refusé. `POST /api/v2/taches/{id}/conversation`
ouvre ou retrouve le canal de la tâche, rangé sous son projet. Un projet en veille coupe donc aussi les agents de ses
canaux.

v0.9 (13 oct. 2026, claude) : S3 branché côté serveur, sans toucher aux wrappers. Un @agent dans un message étiqueté
d'une tâche ouvre une exécution (projet actif, essai prêt), le battement « actif » vaut signe de vie (30 s au plus
souvent), et le retour au repos la termine avec l'issue neutre `terminee`. Une nouvelle tâche pour le même agent clôt
l'exécution précédente.

v0.8 (12 oct. 2026, claude) : revue codex msg 2100 : routes v1 par **nom exact d'abord**, puis ID ; nouvelles routes
`/api/v2/projects/{projet_id}/…` (memory, status, DELETE, assign) par **ID strict**. L'interface utilise les routes v2.

v0.7 (12 oct. 2026, claude) : le skill **pilote-rd** de Charles (v2.0) devient le processus de la Shop. Étapes 1-8 et
jalons J1/J2 (Go / Recycle / Hold / Kill), fiche projet (niveau, TRL, horizon), journal d'essais RS&DE, vue
Portefeuille. Statut `arrete` ajouté (Kill).

v0.6 (12 oct. 2026, claude) : « en veille » appliqué dans S1 (revue codex, msg 2047). Un message d'un projet en veille,
terminé ou inconnu reste visible, mais ne déclenche aucun agent, et une ligne système le dit.

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

## Processus : le skill pilote-rd (v0.7)

La Shop suit le processus du skill `pilote-rd` de Charles. Les 5 colonnes de la maquette (Produit → Livrable) sont
remplacées par ses étapes :

```
1 Problème → 2 État de l'art → 3 Concepts → J1 → 4 Conception → 5 Prototype → 6 Essais ↺ → J2 → 7 Industrialisation → 8 Lancement
```

| pilote-rd | Dans le socle |
|---|---|
| Étapes 1 à 8 | `tache.etape` ∈ {probleme, etat_art, concepts, conception, prototype, essais, industrialisation, lancement}. L'étape du projet est calculée (première étape avec une tâche non faite) : « Étape 4 sur 8 » |
| Jalons J1, J2 : Go / Recycle / Hold / Kill | Objet **Jalon** : `projet_id`, `jalon` (J1, J2, revue), `resultats`, `criteres[]` (cible, mesuré, état), `risques[]`, `reste` (fourchette), `recommandation` (de claude), `decision` (de **Charles** seulement), `date`. Go = continue. Recycle = la tâche revient à une étape antérieure. Hold = statut `veille`. Kill = statut `arrete` |
| Fiche projet (document maître) | `projet` gagne `code`, `niveau` (léger, moyen, lourd), `trl` (1 à 9), `horizon` (H1, H2, H3), `type`, `ambition`, `criteres[]`, `hypotheses[]`, `risques[]`. La fiche `<code>_fiche-projet_vNN` est **générée** à partir de ces champs, versionnée à chaque changement |
| Journal d'essais RS&DE | Une tâche d'essai exige `incertitude`, `hypothese`, `methode` et `critere` **avant** sa première exécution (sinon refus). `resultat` et `conclusion` viennent après. Les dates sont celles des événements, donc contemporaines par construction |
| Niveau léger / moyen / lourd | Léger : J2 seulement. Moyen : J1 et J2. Lourd : J1, J2 et une revue avant le lancement. Le niveau fixe les jalons qui sont créés |
| Mode Portefeuille | La vue Projets affiche projet / type / ambition / horizon / étape / TRL / ressources engagées (temps des exécutions, S3) / prochaine décision, plus le graphique risque-rendement |
| Indicateurs | Calculés : taux de recycle ou de kill aux jalons, durée d'une boucle d'essai, respect des dates de jalon, répartition H1/H2/H3 des ressources |
| Conception mécanique | Étapes 4 à 6 : skill `concevoir-une-piece`, production par loop-engine, harnais Bambu. Le skill `pilote-rd` renvoie à `ingenieur-rd-fusion`, son équivalent sur claude.ai : les résultats vont dans la fiche et le journal, sans refaire les calculs |

Règles du skill reprises telles quelles : une étape doit réduire un risque nommé ; pas de chiffre externe sans source ;
la décision d'un jalon appartient à Charles et elle est datée ; arrêter un projet est un résultat valable.

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
- **Nom contre ID** : après migration, `Café` a l'ID `cafe`, et un autre projet peut s'appeler exactement `cafe`.
  Les routes v1 cherchent le **nom exact d'abord**, et `creer()` ne cherche que le nom. Toute mutation qui vise un
  projet par son ID passe par `/api/v2/projects/{projet_id}/memory|status`, `DELETE /api/v2/projects/{projet_id}` ou
  `POST /api/v2/projects/assign` (`projet_id`), qui n'acceptent **que** l'ID. Inconnu = 404.

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
