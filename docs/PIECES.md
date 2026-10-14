# Pièces et nomenclature — spécification v0.2

v0.2 (13 oct. 2026, claude) : copie hors de la tour sur l'autre laptop de Charles (msg 2302), par SSH (`x1`, joignable
par clé, vérifié). Format des numéros `PROJET-SOUS-SYSTEME-NNN` retenu par défaut.

v0.1 (13 oct. 2026, claude) : premier jet, sans code. Demande de Charles (msg 2293) : des sous-niveaux, une base de
données pour contrôler les pièces, des nomenclatures. Contraintes : la base est sur la tour (msg 2299) ; une pièce
n'est pas un projet (grok, msg 2297). Exemple de référence : le quad (msg 2287-2288).

## Trois objets, trois rôles

| Objet | Sert à | Profondeur |
|---|---|---|
| Projet (existe) | Décider : étapes 1-8, jalons go / recycle / hold / kill | Véhicule, plus un sous-système **seulement s'il a son propre go ou kill** (ex. : moteur électrique maison) |
| Pièce (nouveau) | Contrôler : identité, révision, acheter ou concevoir, statut, coût sourcé, fichier | Une fiche par pièce, réutilisable d'un projet à l'autre |
| Nomenclature (nouveau) | Assembler : père → fils × quantité | Autant de niveaux qu'il faut ; s'arrête à la pièce achetée |

Le quad : 1 projet « Quad » (niveau lourd) ; sous-projet « Groupe motopropulseur » seulement s'il a son propre jalon ;
« Suspension avant », « Triangle supérieur » et la visserie sont des **pièces** (assemblages ou pièces simples) dans la
nomenclature, chacune rattachée à la tâche qui la conçoit ou l'achète.

## Où vivent les données

- **Sur la tour** (charles-antoine-System-Product-Name), dans `data/pieces.db` (SQLite). `data/` est exclu du dépôt
  (`.gitignore:1`) : aucune pièce, aucun prix, aucun fournisseur ne part sur GitHub, qui est public.
- Accès par le serveur de la salle seulement (127.0.0.1, et Tailscale pour le cell). Aucun service de base de données à
  installer ni à exposer.
- Sauvegarde : copie quotidienne `data/pieces.db` → `data/sauvegardes/pieces-AAAA-MM-JJ.db` (API `sqlite3 backup`, sûre
  pendant l'écriture), 30 jours gardés.
- Copie hors de la tour : chaque sauvegarde quotidienne est copiée sur l'autre laptop de Charles par `scp` (hôte SSH
  `x1`, clé déjà en place) dans un dossier dédié ; un échec de copie s'écrit dans le journal et dans la ronde, sans
  bloquer le serveur. Le laptop éteint = copie reprise au jour suivant.
- Fichiers CAO et plans : dans les worktrees de l'atelier (racine des livrables S5) ; la pièce garde le chemin et
  l'empreinte sha256, comme les révisions figées.

## Projet parent

`projet.parent_id` (facultatif). Un sous-projet a ses propres étapes et jalons ; un kill du parent met ses
sous-projets en `arrete`. La carte du parent montre l'avancement de chaque sous-projet sur une ligne.

## Schéma (SQLite)

| Table | Colonnes |
|---|---|
| `pieces` | `id`, `numero` (unique, ex. `QUAD-SUS-012`), `revision` (A, B…), `nom`, `origine` (acheter, concevoir), `type` (assemblage, piece, visserie, matiere), `matiere`, `procede` (laser, soudure, cnc, impression_3d, achat), `statut` (a_concevoir, concue, a_commander, commandee, recue, fabriquee, validee, rejetee), `masse_g`, `fichier`, `empreinte`, `projet_id`, `tache_id`, `cree`, `maj` |
| `fournisseurs` | `id`, `nom`, `site`, `delai_jours`, `note` |
| `offres` | `piece_id`, `fournisseur_id`, `reference`, `prix`, `devise`, `quantite_min`, `source` (URL ou devis, **obligatoire**), `date` |
| `nomenclature` | `parent_id`, `enfant_id`, `quantite`, `unite` (u, m, kg), `note` ; un cycle est refusé |
| `mouvements` | `piece_id`, `quantite` (+ reçu, − consommé), `quoi` (commande, reception, fabrication, rebut), `qui`, `date`, `preuve` (photo ou bon) |
| `historique_pieces` | chaque changement de statut ou de révision : `piece_id`, `avant`, `apres`, `qui`, `date` |

Règles : un prix sans `source` est refusé (règle « pas de chiffre externe sans source ») ; une nouvelle révision d'une
pièce conçue garde l'ancienne (jamais d'écrasement) ; une pièce `validee` exige une preuve d'essai (tâche faite).

## Routes (contrat pour l'interface et les agents)

| Route | Rend |
|---|---|
| `GET /api/v2/pieces?projet_id=&statut=&q=` | Pièces filtrées |
| `POST /api/v2/pieces`, `PATCH /api/v2/pieces/{id}` | Créer, modifier (statut, révision) |
| `GET /api/v2/pieces/{id}/nomenclature` | Arbre complet sous la pièce, quantités cumulées |
| `POST /api/v2/nomenclature` `{parent_id, enfant_id, quantite}` | Ajouter un lien (409 si cycle) |
| `GET /api/v2/projects/{id}/achats` | Liste d'achats : pièces `acheter` × quantité cumulée, meilleure offre sourcée, total, ce qui n'a pas d'offre |
| `GET /api/v2/projects/{id}/cout` | Coût cumulé de la nomenclature, avec la part sans prix |
| `POST /api/v2/pieces/{id}/mouvements` | Réception, fabrication, rebut (photo jointe possible) |

Les agents écrivent par ces routes ; un outil MCP `pieces` (lecture, création, statut) suivra si l'usage le demande.

## Tâches physiques de Charles

Une tâche peut avoir `responsable: "Charles"` (fabriquer, mesurer, recevoir). Elle lui demande une photo et des
mesures en retour (pièces jointes de la salle). Sa réponse dans `#tache-N` sert de preuve ; la pièce passe alors à
`fabriquee` ou `recue`.

## Interface (qwencode)

Vue « Pièces » : tableau filtrable (numéro, nom, révision, origine, statut, coût) ; fiche pièce (offres sourcées,
où elle est utilisée, historique, fichier) ; nomenclature en arbre repliable avec quantités et coût cumulé ; liste
d'achats du projet. Le rail montre les sous-projets sous leur parent.

## Lots proposés

| Lot | Qui | Contenu |
|---|---|---|
| N1 Base et routes | claude | `pieces.py` (SQLite, schéma, règles), routes, sauvegarde quotidienne |
| N2 Projet parent | claude | `parent_id`, effets d'un kill, avancement des enfants |
| N3 Interface | qwencode | Vue Pièces, nomenclature en arbre, achats, rail en arbre |
| N4 Tests | codex | Cycles refusés, prix sans source refusé, quantités cumulées, révisions jamais écrasées |
| N5 Essai | tous | Le quad sur papier : étapes 1-3 et la nomenclature de premier niveau |

## Questions ouvertes pour Charles

1. Numérotation : `PROJET-SOUS-SYSTEME-NNN` par défaut ; un format existant à reprendre (PME) le remplacera.
