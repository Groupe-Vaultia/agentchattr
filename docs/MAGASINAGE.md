# Gabarit de comparatif d'offres

v1.0 (13 oct. 2026) : gabarit N3b pour une pièce `origine: acheter` (`docs/PIECES.md` v0.6).

Une fiche par pièce. Au moins 3 offres. Grok remplit les offres. Codex contre-vérifie. Claude recommande. Charles décide. Aucun agent n'achète, n'ouvre de compte, ni ne reçoit d'information de paiement.

Un prix sans URL ou sans devis est refusé. Un chiffre sans source s'écrit « ? », avec l'endroit où le vérifier. Un relevé de plus de 30 jours est refait avant la liste d'achats.

## Pièce

Copier ce bloc pour chaque pièce. Les noms de colonnes sont ceux de la table `offres`, plus les montants du prix livré.

| Champ | Valeur |
|---|---|
| Numéro | `VLT-_____` |
| Nom | |
| Révision | |
| Spécification exigée | Ce que le calcul ou le critère impose. Une offre qui ne la tient pas est écartée. |
| Quantité (nomenclature) | |
| Unité | u, m ou kg |
| Date du relevé | AAAA-MM-JJ |

### Offres

| # | Fournisseur | Pays | Référence fabricant | Prix unitaire | Devise | Qté min | Délai (jours) | Spécification citée du fabricant | Conforme | Source | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | oui ou non | | |
| 2 | | | | | | | | | oui ou non | | |
| 3 | | | | | | | | | oui ou non | | |

`Source` est l'URL de la page relevée, ou le nom du devis. `Référence fabricant` est le SKU du fabricant, distinct du numéro `VLT-`. `Conforme` ne vaut `oui` que si la spécification citée couvre toute la spécification exigée.

### Prix livré en CAD

Chaque case a sa source, ou « ? ». On ne convertit pas une devise de tête.

| # | Prix × quantité | Livraison au Québec | Taxes | Droits | Total livré | Source du taux et de chaque ligne |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |

### Ordre du choix

1. Conformité : une offre `non` est écartée, même moins chère.
2. Plus bas total livré en CAD, parmi les offres conformes.
3. Délai.
4. À total égal : fournisseur canadien, puis politique de retour.

| # | Politique de retour | Source |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

### Recommandation

| Champ | Valeur |
|---|---|
| Offre retenue | # |
| Motif | Conformité, total livré, délai, fournisseur |
| Écarts encore ouverts | |

### Contre-vérification

| Champ | Valeur |
|---|---|
| Liens rouverts | |
| Spécification = calcul de la pièce | |
| Total livré recalculé | |
| Relevé de plus de 30 jours | aucun, ou liste des lignes à refaire |

### Décision

| Champ | Valeur |
|---|---|
| Charles | approuve ou refuse |
| Date | |
