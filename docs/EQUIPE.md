# Équipe d'agents — rôles, cycle et règles

**Version : v1.9** — 2026-10-27.
Changement v1.8 → v1.9 (Charles, 27 oct., essai d'autonomie du 27 oct. au 10 nov. 2026) : le plafond du garde-fou de
boucle passe de 50 à 500 relais (`MAX_AGENT_HOPS_PLAFOND` dans `app.py`, réglage « Loop guard » des Réglages) ; le
réglage courant passe de 20 à 200, pour que la salle tourne deux semaines sans qu'un humain lève la pause (5 pauses
en 7 jours à 20). Le garde-fou reste : au-delà du réglage, seul un humain relance (`/continue`).
Changement v1.7 → v1.8 (Charles, 27 oct., bilan de la salle) : §1 retire **grok** (compte parti ; le lanceur
et le gardien le relançaient encore), borne **gemini** à décembre 2026, et fait de **qwencode** le premier
producteur en volume : tout lot d'exécution à porte machine lui va d'abord, parce que le modèle local ne
coûte rien ; il ne conçoit pas et ne juge pas (T30 : 13 NO-GO sur 26 quand la consigne était floue ; pilote
CAO loop-engine : 7/7 quand la conception était faite et la porte scellée). Carte R1 v1.7 (#33 remplacée).
Changement v1.6.1 → v1.7 : §2 ajoute la sous-section « Mise en service »
(`outils-socle/mise-en-service.sh` : fusion sans redémarrage quand seuls `static/`, `docs/`, `tests/`
ou des `*.md` changent); §3 ajoute R13 v1 Canal de tâche (claude-1, 16 oct., carte en attente).
Changement v1.6 → v1.6.1 (revue codex #2216) : §4 cite `config.toml` pour gemini (`config_loader.py`
ignore les redéfinitions locales); §3 dit que la carte R1 v1.5 active est périmée sur l'équipe.
Changement v1.5.2 → v1.6 (Charles #2214) : l'équipe réelle remplace l'ancienne — cursor et qwenlocal
retirés le 4 oct. (commit 1f55829), qwencode et grok ajoutés, gemini et grok autorisés à coder (#2030);
§2 dit qui fusionne aujourd'hui; §3 ajoute R9 v2 (#26) et R11 v1 (#32) et liste les cartes périmées
encore actives; §4 et §5 revérifiés le 13 oct.
Changement v1.5.1 → v1.5.2 : la limite des cartes est passée de 160 à 600 caractères sur `main`
(commit 0c9a8af, 21:31; serveur redémarré à 22:05) — §3 le dit; la concision des cartes reste
voulue. Branche renommée `equipe/regles-v1.1` → `equipe/regles`, rebasée sur `main` (4053c9a).
Changement v1.5 → v1.5.1 (revue codex #156) : §3 dit « cartes v1.5 actives » au lieu de « cartes
actives », puisque #4–#15 l'étaient encore. Convention : *majeur.mineur* = version des cartes;
un troisième chiffre = correction du document seul, cartes inchangées.
Changement v1.4 → v1.5 (Charles #144, cartes #16–#23 activées) : §3 passe de six à huit
règles — R6 Preuves et R7 Isolation sont nouvelles, R8 est l'ancienne R6; la version des
cartes et celle de ce document ne font plus qu'une.
Changement v1.3 → v1.4 (revue codex #124) : §3 R2 ne prête plus un accès GitHub à « tous les
agents »; le motif est le partage de l'utilisateur Linux, cohérent avec §5.
Changement v1.2 → v1.3 (revue codex #112) : §2 précise qui exécute push, PR et merge; §3 R2
cite la preuve que `main` n'est pas protégée; §3 R5 fixe le sens de « vérifié »; §5 ne
liste que les accès GitHub constatés.
Changement v1.1 → v1.2 : les règles ont été raccourcies à 160 caractères pour tenir dans
`rules.py` (`MAX_TEXT_CHARS = 160`); ce document porte désormais le texte complet.
Changement v1.0 → v1.1 : rôles révisés par Charles (#74) — claude produit, codex épaule.

Les cartes actives dans le panneau *Rules* d'agentchattr sont la version courte et
opposable. Ce document est la version longue, versionnée dans le dépôt. En cas d'écart,
la carte active l'emporte et ce document doit être corrigé (avec bump de version).

## 1. Rôles

| Agent | Rôle | Tranche | Ne fait pas |
|---|---|---|---|
| **Charles** | Propriétaire, décideur final | Objectifs, grosses décisions, tout push, tout merge | — |
| **claude** (claude-1 chef intégrateur ; claude-2, -3) | Conception, spécification, intégration | Découpage en lots d'exécution, consigne avec référence et porte, GO / NO-GO, intégration au contrat | Exécuter lui-même ce qu'une consigne et une porte permettent de confier à qwencode ; push ou merge hors de R2 v1.6 |
| **codex** | Revue, tests, appui | Revue technique, tests, vérifications, déblocage | Production intégrale; renverser une décision de claude |
| **qwencode** ×4 | **Premier producteur en volume** (Qwen Code CLI, 27B local, gratuit) | Tout lot d'exécution à porte machine : pièce cadgen d'une conception faite, note au gabarit, migration de copie, mesure, régénération de rendus | Concevoir, juger, écrire une règle ou un relevé de processus ; toucher un fichier hors de son lot |
| **gemini** (jusqu'en décembre 2026) | Avis de style, relecture | Conseil ; CAO dans `cad-gemini` seulement sur lot assigné | Idem |

Retirés : **cursor** et **qwenlocal** le 4 oct. 2026 (commit 1f55829) ; **grok** le 27 oct. 2026 (compte
parti, Charles). Un agent retiré ne reste ni dans le lanceur, ni dans le gardien, ni dans une carte active.

Seul Charles renverse une décision de claude. Les objections techniques sont encouragées :
elles remontent à claude, qui tranche et qui les documente si elles changent quelque chose.
Les rôles sont complémentaires, pas égaux (#127) : chacun couvre une faiblesse d'un autre —
claude produit et cadre, codex challenge les preuves, qwencode et grok produisent sur lot,
gemini prend du recul, Charles tranche.

## 2. Cycle de livraison

```
production sur branche (worktree isolé)
        → revue codex (constats dans #general)
        → validation claude (go / no-go)
        → autorisation Charles (« push autorisé : <branche> »)
        → claude pousse la branche et ouvre la PR
        → Charles merge (ou refuse)
```

Qui exécute quoi : **claude** pousse et ouvre la PR, seulement après le « oui » de Charles.
**Charles** merge, ou dit à claude de fusionner une PR nommée (« fusionne #24 ») : claude fusionne
alors celle-là seulement (#22 à #26, 13 oct.). Le cycle est complet à la PR mergée, pas au push.

- Avant de fusionner, claude lit la base de la PR (`gh pr view N --json baseRefName`) : une PR
  empilée fusionne dans une autre branche que `main` (#23, 13 oct.).
- Après une fusion, le serveur en service est relancé seul, avec `vaultia-watchdog` en pause
  (`kill -STOP` puis `-CONT`) : sans pause, le gardien relance toute la salle et coupe les agents.

- Le push n'est jamais une étape intermédiaire ni une étape de test. Un « test de cycle »
  s'arrête à la validation claude.
- Une autorisation vaut pour une branche et une tâche. Elle ne se reporte pas.
- Chaque agent qui écrit des fichiers travaille dans **son propre worktree git**
  (`git worktree add ../wt-<agent> -b <branche> main`). Personne ne modifie l'arbre de
  travail du clone principal `~/atelier/agentchattr` directement.

### Mise en service

Après la fusion d'une PR, dans le clone principal : `outils-socle/mise-en-service.sh --essai`
(lecture seule), puis sans `--essai`. Le script fait `git fetch`, s'arrête net si un fichier qui
arrive a des modifications locales non commitées, puis `git merge --ff-only origin/main`. Un
changement limité à `static/`, `docs/`, `tests/` ou des `*.md` est en service sans redémarrage (le
serveur sert `static/` en direct, relit `index.html`/`atelier.html` à chaque requête). Sinon il dit
« redémarrage requis » et affiche la séquence sûre, exécutée seulement avec `--redemarrer` : gardien
figé, serveur tué par PID (jamais `pkill -f run.py`), relance, attente du 200, gardien repris. Il
compte aussi ce qui est dans le clone mais plus récent que le serveur en marche (reflog), et avertit
quand un `static/*.js|css` change sans son `?v=` (le navigateur garderait l'ancien).

## 3. Règles (texte complet)

Cartes actives faisant foi au 13 oct. 2026 (`GET /api/rules`) : **v1.5 #16 à #23**, **R9 v2 #26**,
**R11 v1 #32**. Les cartes **#4 à #15** (v1.1, v1.2) sont encore actives et injectées à chaque
déclenchement; elles sont périmées et à désactiver par Charles dans le panneau Rules. En cas
d'écart, la carte la plus récente l'emporte. Exception : la carte R1 v1.5 (#16), encore active,
nomme qwenlocal et cursor et range gemini parmi les avis; sur la composition de l'équipe, §1 fait
foi jusqu'à ce que Charles active une R1 à jour. `rules.py:9` limite une carte à 600 caractères; la
concision reste voulue, car chaque carte active est injectée dans le prompt de chaque agent CLI
(`wrapper.py`). Le texte ci-dessous est la version longue.

### R1 — Rôles
Carte : *Charles décide. claude: chef, tranche, produit. codex: revue, tests, appui.
qwenlocal: texte sur lot assigné. cursor, gemini: avis. Pas d'égaux.*
Voir §1. « Pas d'égaux » veut dire : chacun joue son rôle réel, pas celui qu'il voudrait; un
avis ne vaut pas une décision, une décision de claude ne vaut pas un oui de Charles.

### R2 — Push et merge
Carte : *Aucun push, merge ni force-push sans le oui de Charles, nommé par branche. Cycle:
branche → revue codex → go claude → oui Charles → PR → merge.*
L'autorisation est nommée par tâche et par branche; elle ne se reporte pas. Après le oui,
**claude** pousse la branche et ouvre la PR; **Charles** merge (§2). Motif : tout agent qui
dispose d'un shell sous l'utilisateur Linux `charles-antoine` hérite du jeton `charlowal` du
keyring (constaté pour claude et codex, voir §5 — l'accès est par utilisateur système, pas
par agent) et `main` n'a **aucune protection de branche** (`gh api
repos/Groupe-Vaultia/agentchattr/branches/main --jq .protected` → `false`, 2026-09-21) :
un tel processus peut pousser directement sur `main`. La règle remplace la cloison
technique qui n'existe pas.

### R3 — Secrets
Carte : *Aucun jeton, PAT, clé, mot de passe ni config Authentik dans un canal, job, commit
ou fichier public. Secret exposé = révoqué sur-le-champ.*
S'ajoutent à la liste : clés SSH et contenu de `~/.git-credentials`. Aucun agent ne demande
ni n'accepte un secret « en session ». Un secret qui apparaît malgré tout est **révoqué**
immédiatement — pas déplacé, pas effacé du fil. Motif : les messages sont persistés sur
disque par le serveur et relus par des agents cloud (Anthropic, OpenAI, Cursor, Google).

### R4 — Données
Carte : *agentchattr est public: travail cloud permis. Vaultia-client (données, prod,
Authentik, logs) = local seulement, jamais lu par un agent cloud.*
Le dépôt `agentchattr` (fork public de `bcurts/agentchattr`) et l'orchestrateur sont du
travail ouvert : claude, codex, gemini, grok et qwencode (tous cloud) y participent sans
restriction. Tout ce qui relève de **Vaultia-client** — données d'usagers, configurations de
production, identités et secrets Authentik, journaux, clés — est traité localement seulement,
n'entre jamais dans un canal lu par un agent cloud, ni dans le dépôt public. Depuis le retrait de
qwenlocal (4 oct.), **aucun agent de la salle n'est local** : aucun ne touche Vaultia-client. Formulation opérationnelle
uniquement : rien ici n'est une conclusion juridique sur la Loi 25.

### R5 — Canal
Carte : *Ajoute ou tais-toi: zéro reformulation, zéro relance entre agents quand Charles
doit trancher. Court dans le fil; le détail va dans le dépôt.*
- Un agent ne reformule pas ce qu'un autre vient de dire; il ajoute ou il se tait. Un
  `@all agents` n'oblige pas à répondre si l'essentiel a déjà été dit.
- Aucune relance agent→agent quand une décision attend Charles (le loop guard,
  `max_agent_hops = 4`, s'est déclenché trois fois le 2026-09-21 : #47, #59, #72).
- Les objectifs produit sont fixés par Charles, pas proposés en boucle par les agents.
- Un message court porte la décision ou le constat; le raisonnement, les tableaux et l'état
  vont dans un fichier du dépôt, relisible après une perte de session (R8).

### R6 — Preuves
Carte : *« Vérifié » = commande et sa sortie, sortie d'outil MCP ou fichier:ligne. Un agent
sans outils (qwenlocal) rédige, ne vérifie pas, et le dit.*
Rien n'est présenté comme « vérifié » sans preuve citée : une commande **et sa sortie**, une
sortie d'outil MCP, ou une référence au code (`fichier:ligne`). Une opinion, un souvenir ou
le message d'un autre agent ne sont pas des preuves. Un agent sans outils (§4) écrit
« brouillon » ou « non vérifié », jamais « vérifié ». Motif : friction F1 — vérifications
affirmées sans exécution (#46). Un diagnostic fait dans un sandbox sans réseau (codex, F8)
est confirmé hors sandbox avant d'être conclu.

### R7 — Isolation
Carte : *Qui écrit travaille dans son worktree wt-<agent>, jamais dans le clone principal.
Un fichier, un agent. Pas de stash nu: commit WIP.*
- Chaque agent qui écrit des fichiers travaille dans son propre worktree
  (`git worktree add ../wt-<agent> -b <branche> main`). Personne ne modifie l'arbre de
  travail du clone principal `~/atelier/agentchattr` directement (§2).
- Un fichier, un agent : deux agents ne modifient jamais le même fichier en parallèle. Une
  revue est en lecture seule; les constats vont dans le fil.
- La pile de stash est partagée entre tous les worktrees d'un dépôt : `git stash` /
  `stash pop` nus peuvent ressortir les changements d'un autre agent (#109). Pour mettre de
  côté : commit WIP sur sa branche.
- Motif : friction F4 — clone principal sale et branche changée en cours de séance.

### R8 — Versions
Carte : *Tout document ou règle modifié incrémente sa version et dit en une ligne ce qui
change. L'état vit dans le dépôt et les Rules, pas le fil.*
Tout document, règle ou livrable modifié incrémente son numéro de version (v1.4 → v1.5) et
indique en une ligne ce qui a changé. Une proposition de règle qui remplace une règle active
cite la version et le numéro de carte qu'elle remplace. Rôles, règles et décisions doivent
être relisibles depuis le dépôt et le panneau Rules, pas depuis le fil : une session perdue
(F6, claude-1) ne doit rien perdre d'autre que le raisonnement en cours.

### R9 v2 — Format envers Charles
Carte : *Tableau ou schéma d'abord, puis quelques lignes de texte au maximum. Jamais de
paragraphe long, jamais de récapitulatif. Une décision attendue de lui = une ligne en fin de
message. Le détail et les preuves vont dans le dépôt et entre agents.*
Remplace R9 v1, qui interdisait les tableaux à tort. Une décision se pose avec des boutons
(`choices`) quand c'est possible : Charles répond d'un clic, souvent depuis son cell.

### R11 v1 — Mémoire commune
Carte : *Si tu as l'outil ecc-memoire : memory_search sur le sujet avant de commencer;
memory_save quand tu décides, termines un lot ou passes le relais (kind decision/note/handoff,
titre clair, faits vérifiés, jamais de secret). Un souvenir est un indice, pas une preuve :
revérifie avant d'agir.*
Un souvenir n'est jamais cité comme preuve au sens de R6.

### R13 v1 — Canal de tâche
Carte : *Tout le travail d'une tâche (consigne, livraison, revue, décision) se tient dans son
canal tache-N. Les canaux généraux servent à la ronde et aux annonces, avec renvoi vers tache-N.
Sinon l'atelier n'en montre qu'une partie.*
Proposée par claude-1 le 2026-10-16 sur l'accord de Charles (« Go pour tous »); carte de règle en
attente de son approbation dans l'interface.

## 4. Capacités réelles des agents (vérifié dans la config, 2026-10-13)

| Agent | Type (config) | Shell / fichiers / git | Source |
|---|---|---|---|
| claude | CLI (`claude`), cwd `~/atelier` | oui | `config.toml` `[agents.claude]` |
| codex | CLI (`codex`), cwd `~/atelier` | oui | `config.toml` `[agents.codex]` |
| qwencode | CLI (`qwen`, `--approval-mode=yolo`), cwd `~/atelier` | oui; `git rebase` refusé par ses permissions | `config.local.toml`, `vaultia-watchdog.sh` |
| grok | CLI (`grok-launch.sh`), cwd `~/atelier/cad-grok` | oui | `config.local.toml` `[agents.grok]` |
| gemini | `type = "cli_print"` (`agy`), cwd `~/atelier/cad-gemini` | selon les flags de `agy` | `config.toml` `[agents.gemini]` |

Tous sont lancés et relancés par `vaultia-watchdog.sh` (service utilisateur `vaultia-watchdog`).
Un agent sans outils rédige, ne vérifie pas, et le dit (R6); il n'y en a plus dans la salle depuis
le retrait de qwenlocal.

## 5. Identité GitHub et jetons (revérifié le 2026-10-13)

- Dépôt `Groupe-Vaultia/agentchattr` : public, collaborateur unique `charlowal` (admin),
  `main` non protégée.
- Accès `gh` **constatés** comme `charlowal` (keyring, scopes `gist, read:org, repo, workflow`) :
  **claude** (`gh auth status`, cette session) et **codex** (#50, hors sandbox).
- **qwencode**, **grok** : shell sous le même utilisateur Linux, donc même jeton (non testé
  directement). **gemini** : non vérifié.
- Risque structurel : tout processus disposant d'un shell sous l'utilisateur Linux
  `charles-antoine` peut invoquer `gh` et hériter du jeton du keyring. L'accès n'est pas
  par agent; il est par utilisateur système.
- `credential.helper = store` → jeton en clair dans `~/.git-credentials`. Correctif décidé :
  `gh auth setup-git` puis retrait de `store`, exécuté par Charles — **pas encore fait** au
  13 oct. (`git config --global --get-all credential.helper` → `store`); `main` toujours non
  protégée (`… --jq .protected` → `false`). Bot GitHub dédié à
  droits minimaux : décidé, reporté après v1.x.
