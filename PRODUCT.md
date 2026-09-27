# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Charles, propriétaire de Groupe Vaultia, est le seul utilisateur. Il dirige une équipe d'IA qui produit
des logiciels et des sites pour ses projets : claude (chef : découpe, assigne, tranche, produit), codex
(revue, tests), grok, qwencode, gemini, cursor et qwenlocal (modèle local 80B). Usage **moitié
téléphone, moitié ordinateur** : au téléphone (Pixel, via un tunnel Tailscale privé) il lit ce que les
IA ont fait, tranche les décisions, relance, joint des photos ; à l'ordinateur il suit les travaux longs.
Il se décrit comme une personne visuelle : tableau ou schéma d'abord, quelques lignes de texte ensuite,
jamais de pavés.

## Product Purpose

Une salle de commandement multi-IA : un humain et plusieurs agents dans des canaux. Charles mentionne
un agent (@claude…), les agents se répondent, le chef découpe et assigne, les choix à trancher arrivent
en cartes de décision. Réussite : en un coup d'œil, Charles sait qui travaille sur quoi et ce qui attend
sa décision, et il peut trancher depuis son téléphone.

## Positioning

Chaque IA passe par l'abonnement de Charles (le CLI de son propre compte, jamais une clé API), plus un
modèle local sur sa machine. La gouvernance est explicite : Charles décide en dernier, claude est le chef,
les rôles et les règles de salle sont versionnés (R1…Rn), et les agents partagent une mémoire commune
qui survit à leurs redémarrages.

## Operating Context

- Canaux par sujet ; projets qui regroupent des conversations et portent leur propre mémoire.
- Messages d'agents souvent longs : tableaux Markdown, blocs de code, liens, captures d'écran.
- Cartes de décision (choix cliquables), jobs (travail suivi TO DO → ACTIVE → CLOSED), règles de salle.
- Pièces jointes : photos prises au téléphone, documents (PDF, tableurs…).
- Indicateur en direct de qui réfléchit ; statistiques de consommation de jetons par IA ; choix du modèle
  et du niveau de raisonnement par IA.

## Capabilities and Constraints

- Fork public de bcurts/agentchattr (licence MIT) : FastAPI côté serveur, HTML/CSS/JS sans framework ni
  étape de build ; les fichiers statiques sont servis tels quels (numéro de version en paramètre pour le cache).
- La salle est en service pendant les travaux : une refonte ne doit casser aucune fonction existante
  (mentions, cartes de décision, jobs, règles, pièces jointes, rail des projets, statistiques).
- Dépôt public : aucune donnée de client dans le code ni dans les documents.

## Brand Commitments

- Nom : Vaultia (Groupe Vaultia). Logo « V » existant : `static/logo.png`.
- Langue : français (Québec) dans toute l'interface, en gardant les termes techniques d'usage
  (job, commit, PR, token, MCP…). L'interface actuelle mélange encore anglais et français.
- **Référence visuelle imposée par Charles (26 sept. 2026) : l'application Claude** (claude.ai et l'app
  mobile) — son calme, ses proportions de lecture, son niveau de finition. Exécutée avec l'identité
  Vaultia (logo V), jamais avec la marque d'Anthropic. Le thème suit l'appareil : clair le jour, sombre
  le soir. À éviter : trop de couleurs ou de gadgets ; un texte trop petit au téléphone.
- Ce qui doit se voir en premier dans la salle : ce qui attend la décision de Charles, qui travaille en
  ce moment, les derniers messages.

## Evidence on Hand

L'historique réel de la salle (messages, tableaux, cartes de décision, captures) sert de contenu de
référence. Il n'existe ni témoignage, ni client public, ni chiffre marketing : n'en inventer aucun.

## Product Principles

1. **L'état avant le détail** : qui travaille, ce qui attend Charles, ce qui a échoué se voient d'abord.
2. **Charles tranche au pouce** : une décision à prendre est visible et se touche du pouce sur téléphone.
3. **Une salle, deux postures** : lecture confortable au téléphone, pilotage dense à l'ordinateur.
4. **Aucune panne silencieuse** : un agent bloqué, en erreur ou hors quota le dit clairement.
