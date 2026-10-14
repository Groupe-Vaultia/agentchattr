# Pièces et nomenclature — spécification v0.5

v0.5 (13 oct. 2026, claude) : numéro de pièce décidé par Charles (msg 2333-2337) : `VLT-` + 5 chiffres, non signifiant,
une seule séquence pour toute la Shop (meilleure pratique PLM : Arena, Beyond PLM). Projet, sous-système, catégorie
et matière sont des champs ; la révision est à part ; une pièce achetée garde aussi la référence du fabricant.

v0.4 (13 oct. 2026, claude) : alignée sur la convention déjà écrite dans le skill `ingenieur-rd-fusion` (SKILL.md:25,
204, 206) : révisions P01, P02… puis A, B, C… (ASME Y14.35, sans I, O, Q, S, X, Z) ; fichiers
`<numéro>_<description-courte>_<rév>.<ext>`, un dossier par révision. Le format du numéro attend Charles (msg 2331).

v0.3 (13 oct. 2026, claude) : CAO et mises en plan ajoutées (oui de Charles, msg 2309). La revue des plans est faite
par claude et codex ; Charles n'est appelé qu'aux jalons, et l'OIQ seulement pour ce qui porte une personne.

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
| `pieces` | `id`, `numero` (unique, `VLT-` + 5 chiffres attribués par le serveur à partir de `VLT-10001`, jamais réutilisé), `sous_systeme`, `categorie`, `revision` (P01, P02… puis A, B, C…, sans I O Q S X Z), `nom`, `origine` (acheter, concevoir), `type` (assemblage, piece, visserie, matiere), `matiere`, `procede` (laser, soudure, cnc, impression_3d, achat), `statut` (a_concevoir, concue, a_commander, commandee, recue, fabriquee, validee, rejetee), `masse_g`, `fichier`, `empreinte`, `projet_id`, `tache_id`, `cree`, `maj` |
| `fournisseurs` | `id`, `nom`, `site`, `delai_jours`, `note` |
| `offres` | `piece_id`, `fournisseur_id`, `reference` (référence du fabricant ou du fournisseur), `prix`, `devise`, `quantite_min`, `source` (URL ou devis, **obligatoire**), `date` |
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

## CAO et mises en plan

| Élément | Règle |
|---|---|
| 3D d'une pièce conçue | Un script Python et un fichier `.FCStd` par pièce et par révision, produits par FreeCAD **sans fenêtre** (`freecad.cmd`, un processus par appel : plusieurs agents en parallèle). Jamais deux agents sur le même fichier (le dernier enregistrement gagne, FreeCAD issue #19697) |
| Révision | Convention du skill `ingenieur-rd-fusion` : `<numéro>_<description-courte>_<rév>.<ext>` (ex. `VLT-10001_triangle-sup_P02.FCStd`, `_calculs_P02.py`, `.pdf`, `.dxf`), un dossier par révision ; l'ancienne reste ; la fiche pièce garde chemin et sha256 |
| Mise en plan | TechDraw : vues, cotes fonctionnelles, tolérances, cartouche (numéro, révision, matière, procédé), export PDF et DXF. Un plan par pièce fabriquée ; un plan d'assemblage par sous-système |
| Assemblage | Un fichier d'assemblage par sous-système, liens vers les pièces ; vérification d'interférences à chaque révision |
| FreeCAD avec fenêtre | Une seule session pilotée par MCP (port 9875) : pour regarder et vérifier, pas pour produire |

### Revue des plans (qui vérifie quoi)

| Niveau | Qui | Contrôle |
|---|---|---|
| 1 Automatique | script | Cotes manquantes ou en double, cartouche complet, interférences, masse, DFM du procédé |
| 2 Producteur | l'agent qui a dessiné | Le plan suit le tableau de calcul et les critères de la pièce |
| 3 Contre-revue | codex (calculs, cotes) et claude (fonction, assemblage, fabricabilité) | Indépendante du producteur ; écarts écrits, pièce bloquée tant qu'ils sont ouverts |
| Jalon | Charles | Regarde les plans du sous-système et décide ; il ne relit pas chaque cote |
| Sécurité | ingénieur OIQ | Seulement pour une pièce qui porte une personne ou une charge critique, avant l'usage |

Pourquoi les agents ne suffisent pas pour le dernier niveau : ils peuvent se tromper de la même façon, ils ne
touchent ni ne mesurent la pièce réelle, et la responsabilité d'une pièce de sécurité exige un ingénieur.

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
| N2b CAO et plans | claude, gemini (CAD) | Gabarit de script pièce, mise en plan TechDraw, contrôles automatiques du niveau 1 |
| N3 Interface | qwencode | Vue Pièces, nomenclature en arbre, achats, rail en arbre |
| N4 Tests | codex | Cycles refusés, prix sans source refusé, quantités cumulées, révisions jamais écrasées |
| N5 Essai | tous | Le quad sur papier : étapes 1-3 et la nomenclature de premier niveau |

## Questions ouvertes

Aucune : le numéro est décidé (v0.5).
