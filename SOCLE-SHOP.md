# Socle de la Shop de projets — spécification v0.1

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
