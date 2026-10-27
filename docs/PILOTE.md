# Méthodes par étape

v1.4 (27 oct. 2026) : la règle du juge visuel ne nomme plus Bolt (agent retiré le 18 oct., carte rendue à Qwen) : c'est le modèle vision local qui répond sur :8085, par les mêmes outils `juge_visuel` / `juge-visuel` / `gate-visuel` (vérifié le 27 oct. : VERDICT: PASS sur VLT-10136). Bilan du 27 oct. : la salle citait un agent qui n'existait plus.
v1.3 (16 oct. 2026) : `design_initial` reprend le squelette de points durs (étape 4 du skill `designer-produit`, absente d'ici) et ajoute masses et stabilité (`cg_stabilite.py`) à la méthode, au livrable et au critère de sortie. Motif : squelette du quad (#25) à 0 NO-GO, mais sans aucun calcul de basculement.
v1.2 (15 oct. 2026) : deux règles universelles ajoutées (structure suit la fonction ; « vert » ≠ « réel »), pour que le principe s'applique à **tout produit futur**, pas seulement au quad (Charles, 15 oct.).
v1.1 (14 oct. 2026) : étape `design_initial` entre `concepts` et `conception` (skill `designer-produit`), décision de Charles msg 2945.
v1.0 (13 oct. 2026) : méthodes des 8 étapes pour la consigne `methode_etape` (lot P3, SOCLE-SHOP v1.1).

Le serveur copie la section `## <etape>` dans la consigne de la tâche. Un agent qui n'a pas le skill suit cette section. Le skill nommé s'ajoute quand l'agent l'a ; il ne remplace pas le critère de sortie.

Règles pour toutes les étapes :

- Nommer le risque que l'étape réduit avant de produire.
- Au plus 3 questions à Charles, seulement si la réponse change la cible, le coût, le délai, le risque ou une décision difficile à défaire. Le reste est une hypothèse écrite (`source: claude`, `etat: a_verifier`).
- Aucun chiffre externe sans source. Sans source : « ? » et où vérifier.
- `fait` exige une preuve : commande et sa sortie, sortie d'outil, ou fichier:ligne.
- **La structure suit la fonction, jamais l'enveloppe.** Tout objet se conçoit à partir de ses **interfaces et points durs** — où il se monte, se connecte, pivote, prend ou transmet des charges, où l'usager le touche, où ses composants s'attachent — puis la forme, puis la matière. Remplir une boîte paramétrique qui respecte l'enveloppe (empattement, voie, hauteur…) n'est PAS une conception : chaque élément de matière existe pour tenir un point dur ou en relier deux. Vaut pour un châssis, un boîtier, un bâti, un outil, un montage — tout produit. (Détail : skill `designer-produit`, étape `design_initial`.)
- **« Vert » ≠ « réel ».** Un livrable visuel ou destiné à l'usager (dessin, modèle 3D, page, pièce) n'est `fait` que **rendu ET regardé** : le plan à côté d'une vraie référence, la 3D ou la page chargée et vue (navigateur headless s'il le faut), pas seulement « le script a tourné » ou « le test passe ». L'agent signale ce qui « ne ressemble pas » ou « ne s'affiche pas » avant de livrer, au lieu de laisser Charles le découvrir.
- **Faire REGARDER le visuel par le modèle vision local (Qwen sur :8085 ; Bolt est retiré depuis le 18 oct.).** Pour appliquer « vert ≠ réel » sans attendre Charles : rends le livrable en image (plan → PNG par `pdftoppm`, 3D → capture) et fais-le juger. Outil MCP `juge_visuel` (image + critère → analyse + `VERDICT: PASS|FAIL`), ou en ligne : `juge-visuel <image> "<critère>"`, ou `gate-visuel <image> "<critère>"` pour une porte (code ≠ 0 = refus). Un visuel qui échoue le critère se corrige **avant** de livrer. Un plan SVG/PDF se rasterise d'abord.
- TRIZ est obligatoire à `concepts`, et dès qu'un essai bute sur une contradiction (améliorer A dégrade B, ou le même paramètre doit prendre deux valeurs). S'il n'y a pas de contradiction, l'écrire en une ligne et ne pas en inventer une. La matrice se consulte par `python3 ~/atelier/.claude/skills/triz/scripts/matrice.py AMÉLIORÉ DÉGRADÉ`, jamais de mémoire. Une piste TRIZ reste une hypothèse tant que le calcul, le DFM et l'essai ne l'ont pas confirmée.

## probleme

**Risque visé.** Résoudre le mauvais problème, ou cacher une solution dans l'énoncé.

**Méthode.**

1. Écrire le problème en une phrase, sans solution dedans.
2. Écrire 3 à 7 critères mesurables : nom, cible, méthode de mesure, seuil minimal. Un critère qu'on ne peut pas mesurer n'est pas un critère.
3. Écrire les contraintes : budget, échéance, volume, coût unitaire cible, outillage disponible.
4. Poser au plus 3 questions dont la réponse change le projet. Tout le reste : hypothèse écrite.
5. Choisir le niveau et le dire : léger (J2 seul), moyen (J1 et J2, défaut), lourd (J1, J2 et une revue avant le lancement). Situer le TRL (1 à 9) et l'horizon (H1, H2 ou H3). Ne pas inventer un chiffre de marché.

**Skills.** `pilote-rd`

**Livrable.** Fiche projet : problème, critères, contraintes, hypothèses, niveau, TRL, horizon.

**Critère de sortie.** La phrase de problème ne contient pas la solution. Chaque critère a une cible et une mesure. Les questions ouvertes sont au plus 3. Le niveau est nommé.

## etat_art

**Risque visé.** Refaire ce qui existe déjà, ou bâtir sur une incertitude qui n'est pas la bonne.

**Méthode.**

1. Produits et concurrents : nom, prix, forces, faiblesses. Chaque prix a une source. Sans source : « ? ».
2. Brevets : recherche préliminaire (Google Patents, base de l'OPIC). Noter les numéros utiles. Ce n'est pas un avis de liberté d'exploitation ni de brevetabilité.
3. Conclusion en une ligne : ce qui est déjà résolu, ce qui reste incertain. L'incertain est le cœur de la R&D.
4. Si le sujet est large, croiser plusieurs sources. Un résumé d'une seule page ne suffit pas.

**Skills.** `pilote-rd`, `deep-research`

**Livrable.** Tableau des produits existants avec sources, notes de brevets, conclusion en une ligne.

**Critère de sortie.** Chaque fait externe a une source ou « ? ». L'incertitude qui justifie la suite est nommée. Aucun avis de brevetabilité.

## concepts

**Risque visé.** Trois variantes de la même idée, ou un compromis là où une contradiction peut être supprimée.

**Méthode.**

1. TRIZ est obligatoire ici. Écrire le résultat idéal final : l'élément, la fonction utile, le temps et la zone, sans complication nouvelle.
2. Formuler la contradiction. Technique : améliorer A dégrade B. Physique : un même paramètre doit être les deux à la fois. S'il n'y en a aucune (le calcul ou une pièce normalisée tranche), l'écrire en une ligne et passer au point 4. Ne pas inventer une contradiction.
3. Pour une contradiction technique, consulter la matrice par le script, jamais de mémoire : `python3 ~/atelier/.claude/skills/triz/scripts/matrice.py AMÉLIORÉ DÉGRADÉ`. Pour une contradiction physique, séparer dans l'espace, dans le temps, selon la condition, ou entre le système et ses parties.
4. Écrire au moins une idée concrète par principe retenu, puis regrouper en 2 ou 3 concepts qui diffèrent par le principe, pas par les cotes. Pour chacun : ce qu'il supprime, l'hypothèse à valider, le risque principal.
5. Matrice de décision pondérée sur les critères de `probleme`, plus coût, risque et délai. Une piste TRIZ reste une hypothèse tant que le calcul, le DFM et l'essai ne l'ont pas confirmée.

**Skills.** `pilote-rd`, `triz`. Si la tâche est mécanique, ces concepts alimentent `ingenieur-rd-fusion` sans refaire ses calculs ici.

**Livrable.** Deux ou trois concepts, la contradiction ou son absence écrite, la matrice, le concept retenu et pourquoi.

**Critère de sortie.** Le concept retenu vient de la matrice. La contradiction est écrite, ou son absence l'est. Le concept retenu passe ensuite à `design_initial`.

## design_initial

**Risque visé.** Calculer et dessiner un produit juste qui ne ressemble pas à ce qu'on attend, puis devoir refaire les calculs pour en changer l'allure (cadre « boîte » du quad, msg 2909). Ou bien un produit qui a la bonne allure, mais dont l'architecture ne tient pas : points durs non reliés, centre de gravité jamais calculé (squelette du quad, #25).

**Méthode.**

1. Brief : pour qui, quel usage, quelle impression, contraintes reprises de `probleme` et du concept retenu.
2. 3 à 5 références réelles, chacune avec une image ouverte (URL) ; une cote de référence vient d'une fiche ouverte, sinon « ? ».
3. Planche de proportions chiffrée (encombrement, garde au sol, ergonomie de l'utilisateur), valeur visée et plage des références.
4. Squelette fonctionnel : points durs chiffrés dans le repère du produit, chacun sourcé ou « ? », et structure qui les relie. `verifier_points_durs.py` contrôle que chaque point dur est un nœud. Rendu à l'échelle.
5. Masses et stabilité : centre de gravité pour chaque configuration (à vide, avec l'usager, en charge) et angles de basculement, calculés par `cg_stabilite.py` à partir des masses du squelette. Les angles sont comparés à un critère sourcé (norme ouverte, ou mesures de produits réels faites de la même façon), sinon « ? ». Une hauteur de centre de gravité supposée n'est pas acceptée quand le squelette permet de la calculer.
6. 2 ou 3 pistes de style rendues à la même échelle que les références, avec ce que chacune coûte (pièces, outillage, effet sur le calcul).
7. Carte à Charles, piste recommandée en premier (R12). Le choix devient hypothèse `confirmee` et les proportions deviennent des critères de la fiche.

**Skills.** `designer-produit` (scripts `verifier_points_durs.py` et `cg_stabilite.py`). gemini en avis de style. codex relance les deux scripts sur le sha livré.

**Livrable.** `design/brief.md` : références sourcées, planche de proportions, pistes avec rendus, choix de Charles, critères. Avec lui : `design/points_durs.json`, `design/masses.json` et `design/stabilite.json`.

**Critère de sortie.**
- Charles a choisi une piste sur rendu.
- Les points durs passent `verifier_points_durs.py` (0 ouvert, 0 NO-GO) et ont été revus par un autre agent que leur auteur.
- Le centre de gravité et les angles de basculement sont calculés et tiennent un critère sourcé. Sinon, l'écart est sur la carte de Charles.
- Les proportions, les points durs (coordonnées) et la hauteur du centre de gravité deviennent des critères mesurables de la fiche et des paramètres du contrat (skill `systeme`). `conception` les reprend en entrée.

Les tâches des étapes 1 à 4 peuvent alors aller au jalon J1.

## conception

**Risque visé.** Modéliser avant de savoir si ça tient, ou relâcher une exigence en silence.

**Méthode.**

1. Reprendre les critères de `probleme` et le concept retenu. Nommer le risque que le calcul ou la spec doit réduire.
2. Pièce mécanique : aucune géométrie tant que la porte de calcul n'est pas passée (`ingenieur-rd-fusion`). Inventaire des attaches et des interfaces, cas de charge y compris un cas abusif réaliste, tableau élément / cas / sollicitation / résistance (source) / facteur / état. Un élément non conforme est corrigé ou écrit dans les limites, jamais caché. Propriété matériau : fiche citée, sinon « ? ».
3. Pièce imprimée (PETG, Bambu) : `concevoir-une-piece`. Chaque exigence a une mesure. Si une famille couvre la demande, partir d'elle. Motif connu avant idée neuve. Résistance calculée avant la construction. Géométrie par script, pas de tête. Le livrable est `conception.yaml` et les mesures du script.
4. Logiciel ou procédé : spec courte, preuve de concept minimale, critère mesurable. Pas de modèle CAO.
5. Si le dessin ou le calcul révèle une exigence intenable, ne pas la relâcher en silence. Nommer la contradiction, la traiter avec TRIZ, et laisser le point « à vérifier ».
6. Passer le procédé retenu au crible DFM. Écrire les écarts : point, règle, état, correction.

**Skills.** `pilote-rd`, `ingenieur-rd-fusion`, `concevoir-une-piece`. `triz` seulement si une contradiction apparaît.

**Livrable.** Tableau de calcul avec sources, ou spec courte pour un logiciel ou un procédé. Pour une pièce imprimée : `conception.yaml` et les mesures. Écarts DFM.

**Critère de sortie.** Aucun modèle mécanique sans tableau de calcul, aucune pièce imprimée sans exigences mesurables. Chaque propriété matériau a une source ou « ? ». Les non-conformités sont écrites.

## prototype

**Risque visé.** Construire l'ensemble avant de savoir si l'attache, le jeu ou le parcours tient.

**Méthode.**

1. Prendre le test le moins cher qui répond au risque nommé. Ordre : le calcul déjà fait, puis une simulation si le calcul ne suffit pas, puis une éprouvette, puis le prototype.
2. Pièce imprimée : éprouvette de l'attache ou du jeu avant la pièce complète. Le plan d'essais est écrit avant l'impression : essai, méthode, critère, résultat encore vide.
3. Autre pièce mécanique : fit-check ou prototype selon le procédé. Le plan d'essais est écrit avant la fabrication.
4. Logiciel : le parcours minimal qui exerce le critère, avec la commande qui le prouvera.
5. Ne pas lancer l'essai tant que l'hypothèse et le critère ne sont pas écrits.

**Skills.** `pilote-rd`. `concevoir-une-piece` pour une pièce imprimée. `ingenieur-rd-fusion` pour le plan d'essais d'une pièce mécanique.

**Livrable.** Éprouvette ou prototype, et plan d'essais (hypothèse et critère remplis, résultat vide).

**Critère de sortie.** Le plan d'essais existe avant l'essai. Chaque ligne pointe vers un critère de `probleme` ou une ligne du tableau de calcul.

## essais

**Risque visé.** Conclure sans mesure, ou changer l'hypothèse après avoir vu le résultat.

**Méthode.**

1. Avant la première exécution, écrire l'incertitude, l'hypothèse, la méthode et le critère. Sans ces quatre champs, l'exécution est refusée.
2. Faire l'essai. Écrire ensuite le résultat mesuré et la conclusion. La date est celle de l'essai, pas une reconstitution.
3. La preuve du `fait` est la commande et sa sortie, la sortie d'outil, ou le fichier:ligne. Un récit ne suffit pas.
4. Si le résultat montre une contradiction (améliorer A dégrade B, ou un paramètre devrait être les deux), TRIZ est obligatoire. Nommer la contradiction, consulter la matrice par `python3 ~/atelier/.claude/skills/triz/scripts/matrice.py AMÉLIORÉ DÉGRADÉ`, proposer deux concepts. Ne pas prendre le compromis en silence. Une piste reste une hypothèse jusqu'au prochain calcul ou essai.
5. Critère manqué : le dire, et nommer l'étape à recycler (`conception`, `prototype` ou `essais`). La boucle est normale. Chaque tour est une nouvelle révision (P01, P02…).
6. Pièce qui supporte une personne ou une charge critique : les calculs sont un pré-dimensionnement. Il faut un essai physique et une revue par un ingénieur membre de l'OIQ avant la mise en marché. L'écrire.

**Skills.** `pilote-rd`. `triz` si une contradiction apparaît. `concevoir-une-piece` ou `ingenieur-rd-fusion` si l'essai mesure une pièce.

**Livrable.** Ligne de journal : incertitude, hypothèse, méthode, critère, résultat, conclusion, prochaine action. Preuve attachée.

**Critère de sortie.** Les quatre champs d'avant-essai sont écrits avant le résultat. Le critère de `probleme` visé est atteint, ou l'échec est nommé avec l'étape de recyclage. Quand toutes les tâches d'essais sont faites, le jalon J2 peut être préparé : claude recommande, Charles décide.

## industrialisation

**Risque visé.** Savoir faire un exemplaire sans savoir le faire au coût et au volume visés.

**Méthode.**

1. Coût de revient au volume visé, comparé au coût cible écrit à `probleme`. L'écart est écrit, même s'il est défavorable.
2. Au moins deux fournisseurs pour chaque pièce critique, ou l'écrit « un seul » avec le risque.
3. Procédé, outillage, contrôle (quoi mesurer, à quelle fréquence), emballage, documentation, normes applicables. Une norme non vérifiée est « ? », avec l'endroit où vérifier.
4. Pièce imprimée : le harnais Bambu (`check`, `slice`, `inspect cost`) fournit la masse, le temps et le coût. Ne pas les estimer de tête.
5. Logiciel : la commande, la dépendance et la donnée pour le faire tourner. Aucun jeton, clé ni mot de passe dans le livrable.

**Skills.** `pilote-rd`. `concevoir-une-piece` et `ingenieur-rd-fusion` si la fabrication est mécanique.

**Livrable.** Coût comparé à la cible, fournisseurs, procédé, contrôle.

**Critère de sortie.** L'écart au coût cible est écrit. Chaque pièce critique a un second fournisseur ou un risque nommé. Aucun secret dans le livrable.

## lancement

**Risque visé.** Mettre en service sans savoir quoi mesurer ensuite.

**Méthode.**

1. Avant la mise en service, écrire les indicateurs de retour : ce qu'on mesure, la cible, la date de relecture. Au moins un indicateur lié à un critère de `probleme`.
2. Pour un niveau lourd, la revue avant lancement est un jalon `revue` : claude recommande, Charles décide.
3. Après la mise en service, chaque leçon devient une entrée de la révision suivante. Ne pas réécrire une révision déjà figée.
4. Arrêter ou mettre en veille reste un résultat valable si les indicateurs ou le jalon le disent.

**Skills.** `pilote-rd`

**Livrable.** Indicateurs de retour avec date de relecture, et la liste d'améliorations (vide au départ).

**Critère de sortie.** Les indicateurs et la date de relecture existent avant la mise en service. S'il y a une revue, la décision datée est celle de Charles.
