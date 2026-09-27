---
name: Vaultia
description: "Salle de commandement multi-IA de Groupe Vaultia : une colonne de lecture calme, un seul accent (l'ardoise du logo), clair le jour et sombre le soir."
colors:
  # Jour (défaut, :root). Les clés reprennent les jetons --v-* de static/vaultia-theme.css.
  paper: "#f8f7f4"
  rail: "#f1efea"
  surface: "#ffffff"
  raised: "#ffffff"
  bubble: "#edebe6"
  code: "#f0eee9"
  hover: "rgba(29, 33, 39, 0.05)"
  active: "rgba(29, 33, 39, 0.085)"
  ink: "#1d2127"
  ink-2: "#4f5661"
  ink-3: "#666d78"
  line: "#e6e3dc"
  line-2: "#d5d1c8"
  slate: "#465775"
  slate-hover: "#3a4964"
  slate-soft: "rgba(70, 87, 117, 0.09)"
  slate-line: "rgba(70, 87, 117, 0.3)"
  slate-select: "rgba(70, 87, 117, 0.2)"
  slate-inset: "rgba(70, 87, 117, 0.15)"
  on-slate: "#ffffff"
  danger: "#b0413a"
  danger-soft: "rgba(176, 65, 58, 0.1)"
  success: "#2e7a58"
  warning: "#946512"
  online: "#3f9d6e"
  overlay: "rgba(24, 24, 22, 0.42)"
  # Soir (@media (prefers-color-scheme: dark)) : mêmes jetons, redéfinis.
  paper-dark: "#1e1e1c"
  rail-dark: "#191917"
  surface-dark: "#2a2a27"
  raised-dark: "#2f2f2c"
  bubble-dark: "#32322e"
  code-dark: "#252523"
  hover-dark: "rgba(236, 234, 229, 0.06)"
  active-dark: "rgba(236, 234, 229, 0.1)"
  ink-dark: "#ecebe6"
  ink-2-dark: "#bab6ae"
  ink-3-dark: "#9c9891"
  line-dark: "#34342f"
  line-2-dark: "#45443f"
  slate-dark: "#aebbd7"
  slate-hover-dark: "#c2cde3"
  slate-soft-dark: "rgba(174, 187, 215, 0.11)"
  slate-line-dark: "rgba(174, 187, 215, 0.32)"
  slate-select-dark: "rgba(174, 187, 215, 0.24)"
  slate-inset-dark: "rgba(174, 187, 215, 0.14)"
  on-slate-dark: "#161b26"
  danger-dark: "#e5857c"
  danger-soft-dark: "rgba(229, 133, 124, 0.12)"
  success-dark: "#7cc3a0"
  warning-dark: "#e1b65b"
  online-dark: "#6cc598"
  overlay-dark: "rgba(0, 0, 0, 0.55)"
typography:
  prose:
    fontFamily: "Source Serif 4, Iowan Old Style, Charter, Georgia, Noto Serif, serif"
    fontSize: "16.5px"
    fontWeight: 400
    lineHeight: 1.64
  prose-phone:
    fontFamily: "Source Serif 4, Iowan Old Style, Charter, Georgia, Noto Serif, serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.62
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.55
  input:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  ui:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "14.5px"
    fontWeight: 400
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "17px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "15.5px"
    fontWeight: 600
    lineHeight: 1.2
  control:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "15px"
    fontWeight: 500
    lineHeight: 1.35
  sender:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "13.5px"
    fontWeight: 600
    lineHeight: 1.2
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
    lineHeight: 1.2
  meta:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI Variable Text, Segoe UI, system-ui, Roboto, Noto Sans, Ubuntu, Cantarell, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.2
    fontFeature: "\"tnum\""
  mono:
    fontFamily: "ui-monospace, SF Mono, Cascadia Code, JetBrains Mono, Fira Code, Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  sm: "6px"
  md: "9px"
  field: "10px"
  lg: "12px"
  popover: "14px"
  xl: "16px"
  dialog: "18px"
  bubble: "20px"
  composer: "22px"
  pill: "999px"
spacing:
  stack: "8px"
  inset: "14px"
  gutter-phone: "18px"
  gutter: "20px"
  message-gap-phone: "24px"
  message-gap: "26px"
  reading-column: "48rem"
components:
  send-button:
    backgroundColor: "{colors.slate}"
    textColor: "{colors.on-slate}"
    rounded: "{rounded.pill}"
    size: "36px"
  send-button-hover:
    backgroundColor: "{colors.slate-hover}"
  button-primary:
    backgroundColor: "{colors.slate}"
    textColor: "{colors.on-slate}"
    rounded: "{rounded.field}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.slate-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "8px 14px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "9px 11px"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.input}"
    rounded: "{rounded.composer}"
    padding: "10px 10px 8px 12px"
  tool-button:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.field}"
    size: "36px"
  tool-button-pressed:
    backgroundColor: "{colors.slate-soft}"
    textColor: "{colors.slate}"
  status-pill:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "5px 11px 5px 9px"
  status-pill-working:
    backgroundColor: "{colors.slate-soft}"
    textColor: "{colors.ink}"
  status-pill-offline:
    textColor: "{colors.ink-3}"
  user-bubble:
    backgroundColor: "{colors.bubble}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.bubble}"
    padding: "10px 16px"
  agent-message:
    textColor: "{colors.ink}"
    typography: "{typography.prose}"
    width: "{spacing.reading-column}"
  decision-inset:
    backgroundColor: "{colors.slate-inset}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "14px 16px 16px"
  decision-choice:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.lg}"
    padding: "11px 14px"
    height: "44px"
  decision-choice-phone:
    padding: "12px 14px"
    height: "48px"
  decision-autrement:
    textColor: "{colors.ink-2}"
    padding: "6px 4px"
    height: "36px"
  decision-reminder:
    backgroundColor: "{colors.slate-inset}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "7px 12px 7px 10px"
  reasoning-strip:
    textColor: "{colors.ink-2}"
    width: "{spacing.reading-column}"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.ink}"
    width: "256px"
  rail-item:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.md}"
    padding: "7px 10px"
  rail-item-active:
    backgroundColor: "{colors.active}"
    textColor: "{colors.ink}"
  unread-badge:
    backgroundColor: "{colors.slate}"
    textColor: "{colors.on-slate}"
    rounded: "{rounded.pill}"
    height: "20px"
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.dialog}"
    padding: "22px 24px 20px"
    width: "520px"
  phone-header:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    height: "52px"
  overflow-menu:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.popover}"
    padding: "6px"
    width: "200px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
---

# Design System: Vaultia

## Overview

**Creative North Star: "La salle de lecture"**

La salle Vaultia se lit comme une conversation avec Claude, pas comme une messagerie. La référence est imposée par Charles : l'application Claude (claude.ai et l'app mobile), son calme, ses proportions de lecture, son niveau de finition. Elle est exécutée avec l'identité Vaultia (le logo V, l'ardoise bleu-gris), jamais avec la marque d'Anthropic. Chaque agent est une *voix typographique* : sa prose en serif de lecture, sans bulle, avec son nom et son logo rond pour seule couleur. Seuls les messages de Charles ont une bulle, neutre et alignée à droite.

L'état passe avant le détail. Dans l'ordre : ce qui attend la décision de Charles (l'encart ardoise dans le fil et le rappel « N décisions en attente »), qui travaille (la ligne « réfléchit » qui respire au-dessus de la saisie), puis les derniers messages. La salle a deux postures. Au bureau, un rail repliable de 256 px et une colonne de 48rem, pour le pilotage. Au téléphone, une colonne pleine largeur, de la prose à 17 px, un en-tête d'une seule rangée de 52 px, et tout se fait au pouce.

Le matériau est sobre : des fonds neutres à peine chauds (papier le jour, anthracite le soir), des filets de 1 px, des ombres douces et rares, des coins de 6 à 22 px et des icônes SVG au trait régulier. Le thème suit l'appareil (`prefers-color-scheme`) et il n'y a pas de bascule manuelle. Rejets confirmés : le « chat sombre à bulles, violet néon, pastilles partout », trop de couleurs ou de gadgets, et un texte trop petit au téléphone.

**Key Characteristics:**
- Un seul accent, l'ardoise ; tout le reste est neutre, sauf les couleurs d'état et l'identité des agents.
- Deux voix : Source Serif 4 pour les agents, sans système pour Charles et l'interface, mono pour le code.
- Une colonne de lecture de 48rem, partagée par le fil, la ligne « réfléchit » et la carte de saisie.
- Aucun signe pour l'état normal : un agent disponible n'a pas de point, seul celui qui travaille est teinté.
- Le mouvement tient en peu de choses : le point qui respire (et l'icône d'un envoi en cours), l'arrivée douce du dernier message et des transitions d'état de 140 à 240 ms.
- La couche Vaultia (`vaultia-theme.css`, `vaultia-mobile.css`, `vaultia.js`) se pose sur agentchattr sans étape de build : les jetons d'origine (`--bg`, `--accent`, `--radius-*`…) sont rebranchés sur les jetons `--v-*`.

## Colors

Une palette de papier et d'encre, avec une seule couleur qui parle : l'ardoise du logo Vaultia, placée là où l'argile de Claude se trouverait.

### Primary
- **Ardoise Vaultia** (`slate`, #465775 le jour, #aebbd7 le soir) : le seul accent. On la trouve sur le bouton Envoyer, les boutons principaux, le soulignement de l'onglet actif, les liens, les badges de l'en-tête et des non-lus, le point du projet actif, le point de la pastille « travaille » et la flèche du rappel de décision. Elle sert aussi de `caret-color` et d'`accent-color`. Son contraste est de 7,29:1 sur blanc le jour.
- **Ardoise appuyée** (`slate-hover`, #3a4964 / #c2cde3) : le survol du bouton Envoyer et des boutons principaux.
- **Voiles d'ardoise** : `slate-soft` (9 %) pour la pastille qui travaille, les mentions, le bouton @ enfoncé et le survol du rappel ; `slate-line` (30 %) pour le contour d'un élément actif et la carte de saisie qui a le focus ; `slate-inset` (15 %) pour le fond de l'encart de décision et du rappel ; `slate-select` (20 %) pour `::selection`.
- **Encre sur ardoise** (`on-slate`, #ffffff / #161b26) : le texte et les icônes posés sur l'ardoise pleine. Le soir, l'ardoise s'éclaircit et l'encre qui s'y pose devient sombre.

### Neutral
- **Papier** (`paper`, #f8f7f4 / #1e1e1c) : le fond de la page, de l'en-tête, de la barre d'onglets et du pied. C'est aussi la `theme-color` du navigateur.
- **Rail** (`rail`, #f1efea / #191917) : le menu de gauche, un ton sous le papier.
- **Surface** (`surface`, #ffffff / #2a2a27) : ce qui se pose sur le papier (carte de saisie, choix de décision, fenêtres, menus, champs, panneaux).
- **Relief** (`raised`, #ffffff / #2f2f2c) : les surfaces élevées héritées d'agentchattr (`--bg-elevated`).
- **Bulle** (`bubble`, #edebe6 / #32322e) : les messages de Charles, et rien d'autre.
- **Fond de code** (`code`, #f0eee9 / #252523) : le code en ligne et les blocs `pre`.
- **Encre** (`ink`, #1d2127 / #ecebe6) : le texte principal, la prose des agents, les noms actifs.
- **Encre douce** (`ink-2`, #4f5661 / #bab6ae) : le texte secondaire (pastilles au repos, icônes d'outil, citations, en-têtes de tableau, « Répondu autrement »).
- **Encre discrète** (`ink-3`, #666d78 / #9c9891) : les heures, les numéros, les titres de section du rail, les messages système, le texte indicatif et les onglets inactifs.
- **Filet** (`line`, #e6e3dc / #34342f) et **filet appuyé** (`line-2`, #d5d1c8 / #45443f) : les séparateurs de 1 px. Le filet appuyé borde la carte de saisie, les choix, les champs et les boutons secondaires.
- **Survol / actif** (`hover` 5 % et `active` 8,5 % d'encre ; le soir, 6 % et 10 % de papier clair) : les états d'une rangée ou d'un bouton transparent. `active` marque la conversation ouverte dans le rail.
- **Voile** (`overlay`, 42 % / 55 %) : derrière les fenêtres et derrière le rail ouvert au téléphone.

### Status
- **Erreur** (`danger`, #b0413a / #e5857c, avec `danger-soft`) : les messages d'erreur, le micro qui enregistre, le survol de « supprimer », « Échec : … » et les toasts d'erreur.
- **Réussite** (`success`, #2e7a58 / #7cc3a0) : « Enregistré », « … est connecté ».
- **Attention** (`warning`, #946512 / #e1b65b) et **en ligne** (`online`, #3f9d6e / #6cc598) : repris des jetons d'agentchattr, pour les panneaux hérités.

### Agent colors
Les couleurs d'agent viennent de la configuration (`config.toml`), pas du thème. Elles n'apparaissent qu'à cinq endroits : la pastille de logo de 26 px, le nom de l'expéditeur (mêlé à l'encre), le point qui respire dans la ligne « réfléchit », la pastille de 8 px de la fenêtre Modèles et le texte des @mentions.

### Named Rules
**La règle de l'ardoise unique.** L'interface n'a qu'une couleur d'accent : l'ardoise. Un badge, un lien, un état actif ou un bouton principal est ardoise ou neutre, jamais d'une autre teinte ; les couleurs d'état ne servent qu'à l'erreur, la réussite et l'attention. L'argile de Claude (#da7756), qui colorait les badges d'origine, a été remplacée ; elle ne subsiste que comme couleur d'identité de l'agent claude.

**La règle des couleurs d'agent tempérées.** Un nom d'expéditeur n'est jamais peint dans la couleur brute de l'agent. Il est mêlé à l'encre : `color-mix(in srgb, <couleur d'agent> 58%, var(--v-ink))`. Ainsi mêlés, les noms de l'équipe atteignent 4,7 à 8,1:1 sur papier le jour et 5,7 à 9,1:1 le soir. Toute nouvelle couleur d'agent doit garder ce nom mêlé à 4,5:1 au moins (le jaune #f7f677 et le vert #2fe898 des agents amont Kilo et MiniMax échouent le jour).

**La règle du disponible muet.** L'état normal ne porte aucun signe. Une pastille « disponible » n'a pas de point. Une pastille « travaille » prend le voile et le contour ardoise, avec un point ardoise fixe. Une pastille « hors ligne » a un anneau creux et le texte « · hors ligne ».

### Contraste mesuré (WCAG, texte)

| Paire | Jour | Soir |
|---|---|---|
| encre / papier | 15,09 | 13,99 |
| encre douce / papier | 6,91 | 8,26 |
| encre discrète / papier | 4,87 | 5,82 |
| encre discrète / rail | 4,54 | 6,13 |
| encre discrète / fond de code | 4,50 | 5,35 |
| encre / bulle | 13,57 | 10,78 |
| ardoise / surface | 7,29 | 7,46 |
| encre sur ardoise / ardoise | 7,29 | 8,93 |
| encre douce / encart de décision | 5,54 | 6,18 |
| erreur / papier | 5,35 | 6,34 |
| réussite / surface | 5,20 | 6,97 |

**Écarts corrigés le 26 septembre 2026** (mesurés dans le navigateur, clair / soir) : l'heure et le numéro dans la bulle de Charles passent à `ink-2` (6,22 / 6,37:1) ; le toast d'erreur porte du texte `paper` (5,35 / 6,34:1) ; les @mentions reprennent l'ardoise malgré la couleur que `chat.js` écrit en ligne (`!important`, 5,40 / 5,29:1 dans la bulle de Charles, 4,85 / 5,14:1 chez les agents) ; le badge de « ⋯ » remonte à 11 px. La pastille d'agent n'est pas un écart : elle porte un logo de marque (exempté du contraste du texte), décoratif puisque le nom de l'agent est écrit à côté.

## Typography

**Display Font:** aucune. La salle n'a ni titre d'affiche ni héros.
**Body Font (prose des agents):** Source Serif 4 (auto-hébergée, `static/fonts/source-serif-4-{normal,italic}.woff2`, axes de graisse 200–900, sous-ensemble latin, `font-display: swap`, la version droite préchargée), avec Iowan Old Style, Charter, Georgia, Noto Serif et serif en repli.
**UI Font:** la sans du système (`-apple-system`, Segoe UI Variable Text, `system-ui`, Roboto, Noto Sans…).
**Label/Mono Font:** `ui-monospace` (SF Mono, Cascadia Code, JetBrains Mono, Fira Code, Menlo, Consolas).

**Character:** une serif de lecture chaleureuse pour ce que disent les agents, contre une sans système neutre pour tout ce que Charles touche. Le contraste des familles remplace le contraste des couleurs pour distinguer qui parle.

### Hierarchy
- **Headline** (650, 17px, 1,25, −0,005em) : les titres de fenêtre (« Modèles et raisonnement », « Consommation de jetons »).
- **Title** (600, 15,5px, 1,2) : le titre de la conversation dans l'en-tête du téléphone (« # general »).
- **Prose** (serif 400, 16,5px, 1,64 ; téléphone 17px, 1,62 ; `font-optical-sizing: auto`) : le texte des agents, sur une colonne de 48rem au plus. Le gras vaut 650. Les titres Markdown dans un message repassent en sans 650 (1,2em / 1,1em / 1,02em ; h4–h6 à 0,95em en encre douce) avec `text-wrap: balance`.
- **Body** (sans 400, 15,5px, 1,55 ; téléphone 16px) : les messages de Charles, dans sa bulle.
- **Input** (sans 400, 16px, 1,5) : le champ de la carte de saisie, à 16 px au bureau comme au téléphone.
- **Control** (sans 500, 15px, 1,35 ; téléphone 15,5px) : les choix d'une décision et, en 15px / 1,2, les rangées du menu « ⋯ ».
- **UI** (sans 400, 14,5px) : le corps de base de l'interface. Les rangées du rail et les champs de fenêtre sont à 14px.
- **Sender** (sans 600, 13,5px, 1,2 ; téléphone 14px) : le nom de l'expéditeur. L'onglet de canal a la même taille, en 500 (600 quand il est actif).
- **Label** (sans 500, 12,5px, 1,2) : les pastilles de présence, les bascules de mention, les actions du rail et les étiquettes de champ. La ligne « réfléchit » est à 500 13px (téléphone 15px), le rappel de décision à 600 13px (téléphone 14px).
- **Meta** (sans 400, 12px, 1,2, chiffres tabulaires ; téléphone 13px) : l'heure, les séparateurs de date (500), et le numéro `#id` à 11,5px.
- **Mono** (13px, 1,55) : les blocs de code. Le code en ligne est à 0,84em. Les tableaux Markdown sont en sans 14px, 1,45, chiffres tabulaires.

### Named Rules
**La règle des deux voix.** La serif appartient aux agents et à rien d'autre. Noms, heures, boutons, titres de message, tableaux, fenêtres et menus sont en sans système. Le réglage « Font : Monospace » d'agentchattr passe toute la prose en mono 14px.

**La règle du plancher au pouce.** Aucun texte fonctionnel sous 11 px (le build pose un plancher à 11,5px sur les pastilles et panneaux d'origine). La prose monte à 17px au téléphone et tout champ de saisie reste à 16px au moins (ce qui évite le zoom automatique).

## Layout

**Bureau.** Un rail fixe à gauche, de 256 px, repliable, dont l'état est mémorisé (`localStorage`). Quand il est ouvert, il pousse l'application avec une transition de 220 ms ; le logo de l'en-tête et la barre d'onglets disparaissent alors, puisque le rail les porte déjà. L'en-tête a une marge de 10px 18px et un filet bas. Le fil a une marge de 28px 20px 18px. `#messages` est centré sur `--v-col` (48rem), avec 26 px entre les messages. Le pied (marge 4px 20px 16px) centre chacune de ses rangées sur la même colonne de 48rem : mentions, pièces jointes, ligne « réfléchit », carte de saisie, texte indicatif.

**Téléphone (≤ 768 px, `vaultia-mobile.css`).** L'en-tête tient sur une rangée de 52 px (marge 0 8px 0 54px, qui laisse la place à la bascule du rail). Les pastilles de présence en sont retirées ; seuls les agents occupés restent visibles, dans la ligne « réfléchit ». Les onglets sont masqués, car le tiroir du rail liste les conversations. Le fil a une marge de 18px 0 14px, 24 px entre les messages, 18 px de marge latérale par message, et plus de pastilles d'avatar (le nom suffit). Le pied a une marge de 2px 12px et `max(12px, env(safe-area-inset-bottom))`. Le rail devient un tiroir de `min(304px, 86vw)` au-dessus d'un voile. Les panneaux Jobs, Règles et Épingles glissent depuis la droite en surimpression, sur `min(92vw, 340px)`. Aucun défilement horizontal de la page : le code revient à la ligne dans son bloc et les tableaux défilent dans le leur.

**Points de rupture :** 768 px (CSS `max-width: 768px` ; `vaultia.js` teste la même requête par `matchMedia`), 520 px (la grille de la fenêtre Modèles passe de 3 à 2 colonnes) et `(hover: none)` (les gestes cachés du rail restent à demi visibles).

**Superposition :** le voile du rail est à 1001, le rail à 1002, sa bascule à 1003, les panneaux du téléphone à 1200, le menu « ⋯ » à 1300 et les fenêtres à 10000.

### Named Rules
**La règle de la colonne.** Tout ce qui se lit ou s'écrit partage la même colonne de 48rem : le fil, la ligne « réfléchit », la carte de saisie. Aucun élément de lecture ne s'étale sur toute la largeur du bureau.

## Elevation & Depth

Le système est hybride. La profondeur vient d'abord de la tonalité : le rail est un ton sous le papier, et les surfaces sont blanches sur le papier le jour, plus claires que lui le soir. Les filets de 1 px séparent. Les ombres sont douces et rares. Le soir, elles deviennent noires et plus denses.

### Shadow Vocabulary
- **Posée** (`--v-shadow-sm` : `0 1px 2px rgba(29,33,39,.05)` ; soir `0 1px 2px rgba(0,0,0,.3)`) : les choix de décision, les pièces jointes, les actions de survol, le bouton Envoyer, la bascule du rail.
- **Serrée** (`--v-shadow` : `0 1px 2px rgba(29,33,39,.05), 0 2px 6px -2px rgba(29,33,39,.09)` ; soir `0 1px 2px rgba(0,0,0,.3), 0 2px 8px -2px rgba(0,0,0,.4)`) : la carte de saisie et le bouton « revenir en bas ». Elle va toujours avec un liseré.
- **Flottante** (`--v-shadow-lg` : `0 2px 6px rgba(29,33,39,.06), 0 18px 48px -12px rgba(29,33,39,.22)` ; soir `0 2px 6px rgba(0,0,0,.3), 0 20px 50px -12px rgba(0,0,0,.6)`) : les fenêtres, les menus contextuels, le menu « ⋯ », les toasts et les panneaux latéraux du téléphone.
- **Focus** (`--v-focus` : `0 0 0 3px rgba(70,87,117,.28)` ; soir `rgba(174,187,215,.3)`) : l'anneau de `:focus-visible`, avec un rayon de 8 px.

### Named Rules
**La règle du flottant sans liseré.** Ce qui flotte (fenêtre, menu, popover, toast) porte l'ombre flottante et aucune bordure. Ce qui est posé sur le papier (carte de saisie, choix, champ, pièce jointe) porte un filet de 1 px et, au plus, l'ombre posée ou serrée. Les deux ne se cumulent jamais.

**La règle du focus silencieux à l'ouverture.** La carte de saisie a le focus dès l'ouverture : elle le signale par un contour `slate-line`, pas par l'anneau. L'anneau de 3 px est réservé au focus clavier (`:focus-visible`).

## Shapes

Les coins sont doux et croissent avec la taille de l'objet : 6 px pour le code en ligne et les mentions, 9 px pour les rangées du rail, les boutons de l'en-tête et les rangées de menu, 10 px pour les boutons d'outil, les champs et les boutons, 12 px pour les choix, les blocs de code, les pièces jointes et les toasts, 14 px pour les menus et les popovers, 16 px pour l'encart de décision, 18 px pour les fenêtres, 20 px pour la bulle de Charles et 22 px pour la carte de saisie. Les pastilles, badges et compteurs sont en capsule (999 px). Les cercles sont réservés à l'identité et à l'action : la pastille de logo, le point qui respire, le point du projet actif, le bouton Envoyer. Seuls les onglets de canal sont droits : un simple soulignement de 2 px, ardoise quand l'onglet est actif. Les citations et la réponse citée ont un filet gauche de 1 px en `line-2`, jamais une bande colorée épaisse. Les icônes Vaultia (`vaultia.js`) sont en SVG, sur une grille de 24×24 au trait de 1,75, aux bouts et jonctions arrondis, en `currentColor` ; les icônes héritées de l'en-tête (grille de 16, trait de 1,2) et la flèche d'Envoyer (trait de 2) restent dans la même épaisseur apparente.

## Components

### Buttons
- **Envoyer** : un cercle ardoise de 36 px, avec une flèche vers le haut de 18 px en `on-slate` et l'ombre posée. Au survol il passe en `slate-hover`, à l'appui `scale(0.94)`. Inactif (champ vide), il tombe à 30 % d'opacité.
- **Principal** (`.vt-btn.principal`) : fond ardoise, texte `on-slate`, 600 13,5px, rayon de 10 px, marge 8px 14px. On le trouve sur « Terminé », « Enregistrer » et « Connecter ».
- **Secondaire** (`.vt-btn`) : surface, filet `line-2` (qui passe à `ink-3` au survol), encre.
- **Outil** (photo, document, @, session, micro) : un carré transparent de 36 px au rayon de 10 px, en encre douce. Au survol il prend le fond `hover` et l'encre. Le bouton @ enfoncé (`aria-pressed`) passe en `slate-soft` et ardoise. Le micro qui enregistre passe en `danger` sur `danger-soft`. Pendant un envoi, l'icône respire (`aria-busy`).
- **Transition** : 140 ms sur `--v-ease`, pour la couleur, le fond et la bordure.

### Status pills (en-tête, bureau)
- Des capsules transparentes, avec un filet `line`, en 500 12,5px et en encre douce. Au survol, fond `hover`, filet `line-2` et encre.
- « Travaille » prend le voile `slate-soft`, le contour `slate-line`, l'encre et un point ardoise fixe de 7 px. La bordure tournante d'origine est désactivée. « Hors ligne » a un anneau creux de 1,5 px et le suffixe « · hors ligne ». « Disponible » n'a pas de point.

### Messages
- **Voix d'agent** : pas de bulle, pas de fond, et pas de fond au survol. Une pastille de 26 px portant le logo de l'agent (SVG blanc sur sa couleur), masquée au téléphone : le nom, juste à côté, porte l'identité. En-tête : nom mêlé, heure, `#id`. Puis la prose en serif.
- **Bulle de Charles** : alignée à droite, sur fond `bubble`, rayon de 20 px, marge 10px 16px, largeur maximale `min(82%, 36rem)` (88 % au téléphone). L'en-tête (heure, `#id`) est aligné à droite.
- **Markdown** : les liens sont en ardoise, soulignés d'un trait de 1 px en `slate-line` qui passe à `currentColor` au survol. Le code en ligne est sur `code` avec un filet et un rayon de 6 px. Les blocs `pre` ont un filet, un rayon de 12 px et une marge de 14px 16px. Les tableaux n'ont pas de filets verticaux : seulement des rangées séparées par un filet, un en-tête 600 en encre douce, `nowrap`. Les citations sont en italique, avec un filet gauche de 1 px. Les mentions ont un fond `slate-soft` au rayon de 6 px, en 600 0,92em (le texte : voir l'écart ④).
- **Messages système, arrivées et départs** : centrés, 12,5px, en encre discrète. Les arrivées consécutives se resserrent (−16 px). Séparateurs de date : 500 12px, écrits tels quels (« Aujourd'hui »), entre deux filets.
- **Actions de survol** (répondre, à faire, suppr.) : de petites cartes en surface, avec un filet, un rayon de 7 px, l'ombre posée, en 500 12px encre discrète. Au téléphone, elles sortent du flux, en rangée, révélées au toucher ; « en job » et « copier » y sont masqués.

### Decision inset (signature)
- **Encart** : quand une bulle d'agent contient des choix, elle prend le fond `slate-inset`, un filet `color-mix(slate 50%, transparent)`, un rayon de 16 px et une marge de 14px 16px 16px (14px au téléphone).
- **Choix** : des boutons pleine largeur empilés, avec 8 px entre eux et 14 px au-dessus. Surface, filet `line-2`, rayon de 12 px, 500 15px, hauteur minimale de 44 px (48 px au téléphone), ombre posée. Au survol, le filet passe en ardoise ; à l'appui, `scale(0.99)` ; au clavier, l'anneau de focus.
- **« Répondu autrement »** : sous les choix, calé à gauche. Un bouton-texte en encre douce, 500 13,5px, souligné en `line-2` avec un décalage de 3 px, hauteur minimale de 36 px. Au survol, l'encre et le soulignement en `currentColor`. Il ferme une carte à laquelle Charles a déjà répondu par écrit.
- **Résolu** : les choix sont remplacés par une ligne 400 14px en encre douce sur fond `hover`, au rayon de 10 px, qui dit « Ton choix : **…** » ou « Répondu autrement ».

### Reasoning strip « réfléchit » (signature)
- Une ligne juste au-dessus de la carte de saisie, sur la colonne de 48rem, en `role="status"` et `aria-live="polite"`. Elle est masquée quand personne ne réfléchit et qu'aucune décision n'est hors de vue.
- Pour chaque agent occupé : un point de 8 px dans la couleur de l'agent, qui **respire** (`vt-souffle`, 1,6 s, `ease-in-out`, en boucle, de `scale(.72)` et 45 % d'opacité à `scale(1)` et 100 %), suivi du nom en 600 et en encre. Puis le verbe « réfléchit… » ou « réfléchissent… » en encre discrète. 500 13px, 15px au téléphone. La ligne n'est redessinée que si l'état change, pour que le souffle ne reparte pas à zéro.
- **Rappel de décision** (`.vt-attente`) : en tête de la même ligne, une capsule `slate-inset` avec un filet ardoise à 50 %, en 600 13px (14px au téléphone), une flèche vers le bas en ardoise et le texte « 1 décision en attente » ou « N décisions en attente ». Elle apparaît dès qu'une carte encore ouverte sort de l'écran et fait défiler jusqu'à elle. Tant qu'elle est là, le bouton « revenir en bas » se range au bord droit.

### Composer (carte de saisie)
- Une carte en surface, avec un filet `line-2`, un rayon de 22 px, une marge de 10px 10px 8px 12px et l'ombre serrée. Quand elle a le focus, son filet passe en `slate-line`.
- Le champ est sur la première rangée, pleine largeur (sans 16px, texte indicatif en encre discrète). Les outils sont dessous, à gauche : photo, document, @, session, micro. À droite : l'horloge de programmation (32 px, encre discrète) puis Envoyer.
- Les bascules de mention sont repliées par défaut : seules les mentions actives restent visibles, en capsules `slate-soft` avec un contour `slate-line`, et le bouton @ déplie la rangée. Au téléphone, cette rangée tient sur une ligne qui défile. Le texte indicatif (11,5px, centré) est masqué au téléphone.

### Navigation : le rail
- **Fond** : `rail`, avec un filet droit. En tête, le logo V (24 px). Dessous, trois actions de même largeur : « IA », « Modèles », « Stats » (filet `line-2`, rayon de 10 px, 500 12,5px, icône de 15 px ; au survol, surface et ombre posée).
- **Sections** « Projets » et « Conversations » : 600 12px en encre discrète, avec un bouton + de 24 px. Les rangées font 7px 10px, rayon de 9 px, 14px, en encre douce ; au survol, fond `hover` et encre ; la conversation ouverte a le fond `active` et passe en 600. Un projet est une rangée en 600 et en encre, avec un chevron qui pivote de 90° et un point ardoise de 6 px s'il est actif. Ouvert, il montre ses conversations, « + Conversation » et sa mémoire (une zone de texte avec « Enregistrer », dont le résultat s'affiche sur la ligne).
- **Non-lus** : une capsule ardoise de 20 px (600 11,5px, chiffres tabulaires, « 99+ » au-delà), et la rangée passe en 600.
- **Gestes** (renommer, supprimer) : des boutons de 24 px, invisibles jusqu'au survol ou au focus ; sur écran tactile, à 60–70 % d'opacité. Supprimer vire au rouge `danger` au survol. On peut glisser une conversation sur un projet : la cible se signale par un pointillé ardoise de 2 px.
- **Bascule** : un carré de 34 px sur fond papier, avec un filet `line-2`, un rayon de 10 px et l'ombre posée, fixé en haut à gauche. Au bureau, il devient transparent quand le rail est ouvert.

### Phone header et menu « ⋯ »
- Une rangée de 52 px : bascule du rail, « # conversation » (600 15,5px, tronqué par une ellipse), puis Jobs, Réglages et « ⋯ » (boutons de 38 px).
- « ⋯ » ouvre un menu fixe (sous l'en-tête, à 10 px du bord droit, 200 px au moins, surface, rayon de 14 px, ombre flottante, marge de 6 px). Ses rangées (500 15px, marge de 12 px, rayon de 9 px) sont « Règles de la salle », « Épingles » et « Aide ». Chacune affiche son compteur dans une capsule ardoise de 22 px. Le total en attente est aussi reporté dans un badge ardoise de 17 px, à l'angle de « ⋯ ». Le menu se ferme par Échap, par un clic ailleurs ou par le choix d'une rangée.

### Dialogs (fenêtres Vaultia)
- **Boîte** : surface, sans bordure, rayon de 18 px, ombre flottante, marge 22px 24px 20px, largeur `min(520px, 94vw)`, hauteur maximale 88vh, sur le voile `overlay`.
- **En-tête** : le titre (650 17px) et un bouton Fermer de 32 px. En bas, « Terminé » (principal). Échap ou un clic sur le voile ferment la fenêtre. Au doigt, le focus va à la boîte et non au premier champ, pour ne pas faire surgir le clavier.
- **Contenu** : note en 13px encre discrète ; étiquette en 500 12,5px encre douce au-dessus du champ ; champs en surface avec un filet `line-2`, un rayon de 10 px et, au focus, le contour `slate-line` plus l'anneau. Les `select` ont un chevron SVG propre au thème. Les tableaux sont en 13,5px avec des chiffres tabulaires. Chaque réglage modifié dit sur sa ligne « … », « Enregistré » (réussite) ou « Échec : … » (erreur).

### Toasts et popovers
- **Toast** : une plaque d'encre avec du texte papier, un rayon de 12 px, l'ombre flottante, en 500 13,5px. Le toast d'erreur est sur fond `danger` avec du texte `paper` (5,35:1 le jour, 6,34:1 le soir).
- **Popovers, menus @ et /, fenêtres héritées** : surface, sans bordure, rayon de 14 px, ombre flottante. L'élément survolé ou sélectionné prend le fond `hover`.

### Motion
- **Grammaire** : `--v-ease` = `cubic-bezier(0.16, 1, 0.3, 1)`, une sortie exponentielle. Les durées sont de 140 ms (`--duration-fast`) pour la couleur et le fond, et de 200 ms (`--duration-normal`) pour les bordures, les ombres et le chevron.
- **Arrivée du dernier message** : `vt-arrive` en 240 ms, de 55 % d'opacité et `translateY(4px)` à l'état final. Le rail glisse en 220 ms sur la même courbe.
- **`prefers-reduced-motion: reduce`** : l'arrivée, le souffle, les icônes occupées et le point de la pastille qui travaille sont coupés, et le défilement doux est désactivé.

### Hors du système (hérité d'agentchattr)
Les panneaux Réglages, Jobs, Règles, Épingles et Aide, la fenêtre de programmation, le lanceur de session et le guide d'accueil gardent leur structure d'origine. Ils héritent des couleurs, rayons et ombres par les jetons rebranchés, mais leurs libellés sont encore en anglais (« Loop guard », « Remind agents », « TO DO / ACTIVE / CLOSED », « Schedule message »…) et certaines icônes y sont des glyphes texte (?, +, ×, ▲▼, ←). Leur traduction et leur refonte sont hors de cette passe.

## Do's and Don'ts

### Do:
- **Do** faire passer toute couleur neuve par un jeton `--v-*`, et ne consommer les jetons d'agentchattr (`--bg`, `--accent`, `--text-dim`…) que comme des alias de `--v-*`.
- **Do** redéfinir chaque nouveau jeton dans le bloc `@media (prefers-color-scheme: dark)`, et vérifier ses paires de texte à 4,5:1 le jour et le soir.
- **Do** écrire la prose des agents en `var(--v-read)` à 16,5px / 1,64 (17px / 1,62 au téléphone), dans la colonne `--v-col` de 48rem.
- **Do** donner l'ombre flottante sans bordure à ce qui flotte, et un filet de 1 px avec au plus l'ombre posée à ce qui est posé.
- **Do** dessiner les icônes en SVG en ligne : grille de 24×24, trait de 1,75, bouts arrondis, `currentColor`.
- **Do** garder les choix de décision en pleine largeur, à 44 px de haut au moins (48 px au téléphone).
- **Do** inscrire toute nouvelle animation dans le bloc `prefers-reduced-motion`, et régler toute transition d'état sur `--v-ease`, entre 140 et 240 ms.
- **Do** écrire l'interface en français (Québec), en gardant les termes techniques d'usage (job, PR, token, MCP).

### Don't:
- **Don't** mettre les messages d'agent dans une bulle ou sur un fond coloré : seule la bulle de Charles existe, et elle est neutre (`bubble`). Seule exception : l'encart ardoise d'une décision, qui signale ce qui attend Charles.
- **Don't** introduire une deuxième teinte d'accent, ni peindre un badge, un lien ou un état actif avec la couleur d'un agent.
- **Don't** faire respirer un indicateur d'agent ailleurs que dans la ligne « réfléchit » (la pastille « travaille » garde un point fixe). La seule autre respiration admise est celle de l'icône photo ou document pendant un envoi (`aria-busy`, 1,1 s).
- **Don't** signaler l'état normal : pas de point « disponible », pas de pastille ajoutée pour ce qui va bien.
- **Don't** utiliser un émoji comme icône.
- **Don't** descendre un texte fonctionnel sous 11 px, ni un champ de saisie sous 16 px au téléphone.
- **Don't** reprendre la marque d'Anthropic ou l'argile de Claude comme identité : le logo V et l'ardoise seulement.
