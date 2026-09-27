---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: ["static/style.css","static/vaultia.js","static/vaultia-mobile.css"]
---

# Salle Vaultia — surface principale (static/index.html)

Scope : la salle entière — rail des projets, en-tête (présences), onglets de canaux, fil de messages,
cartes de décision, barre « qui réfléchit », barre de saisie ; bureau et téléphone ; clair et sombre.
Mode : **Operate** (Charles pilote une équipe d'IA ; lecture et décision au pouce).
Priorités d'état (réponses de Charles, 26 sept.) : ce qui attend sa décision, qui travaille, les derniers
messages. À éviter : trop de couleurs/gadgets ; texte trop petit au téléphone. Thème : suit l'appareil.
Contraintes : aucune fonction perdue ; HTML/CSS/JS sans build ; français + termes techniques.

## Direction contract

THESIS: La salle se lit comme une conversation avec Claude, pas comme une messagerie : une colonne de lecture calme où chaque agent est une voix typographique, pas une bulle colorée. Refuse le défaut « chat sombre à bulles, violet néon, pastilles partout ».

OWN-WORLD: Fonds neutres à peine chauds — papier le jour, anthracite le soir — encre ardoise, un seul accent : l'ardoise bleu-gris du logo Vaultia (traduction de l'argile de Claude). Texte des agents en serif de lecture (Source Serif 4), interface en sans système, code en mono. Couleur d'agent réduite à son initiale ronde et à son nom. Filets fins, coins 12–20 px, ombres douces rares, icônes SVG au trait régulier, jamais d'émoji.

STORY: Charles ouvre la salle : il voit d'abord la carte qui attend sa décision et qui réfléchit, lit le fil sans effort, tranche d'un pouce, relance d'un @.

FIRST VIEWPORT: Bureau : rail repliable à gauche (projets, conversations) ; au centre, colonne de lecture ≤ 48 rem ; en bas, carte de saisie arrondie (champ en haut, outils dessous, bouton Envoyer rond ardoise à droite) ; juste au-dessus, la ligne « claude réfléchit… ». Cartes de décision en encart ardoise dans le fil. Téléphone : colonne pleine largeur, corps 17 px, même carte de saisie.

FORM: Canon imposé par Charles — l'application Claude (sortie standard assumée), exécuté à pleine finition sans gadget ; tirage 6623330f (assignation 5) lancé puis écarté par cette référence imposée. Interaction signature : la ligne « réfléchit » qui respire (pulsation douce du point de couleur de l'agent) ; grammaire de mouvement : ease-out exponentiel 180–240 ms, apparition douce des nouveaux messages, rien d'autre.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Guide d'accueil et panneaux secondaires (paramètres, jobs, règles) encore en anglais : hérités ; traduction hors de cette passe sauf libellés visibles de la surface principale.
