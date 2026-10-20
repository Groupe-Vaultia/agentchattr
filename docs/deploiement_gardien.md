# Déploiement du gardien multi-instance : procédure (v1.1)

v1.1 (2026-10-19, claude-2, claude-1 msg 5644, remarques non bloquantes de claude-3 msg 5643) : § 6c dans un worktree neuf
(R7) ; § 2, l'arrêt du gardien se tient en quelques minutes, hors d'une passe d'agent ; ligne « script » au tableau de rappel.
v1.0 (2026-10-19, claude-2, claude-1 #tache-22 msg 5640) : première version. Prête à exécuter **après le oui de Charles**
(carte msg 5626), nommé par branche. Rien de ce document n'a été exécuté. Branches : `claude2/verifier-relais` (`f19ba27`, GO N2
claude-3 msg 5605) et `claude2/gardien-multi-instance` (posée dessus ; v1.0.2 `358b375`, GO N2 claude-3 msg 5617 ; v1.0.3 =
ce document et `--simuler-absent`, en revue N2).

**Le gardien est un service systemd utilisateur**, et non un processus lancé à la main. Constaté le 19 oct. à 23 h 20 :

| Contrôle | Sortie |
|---|---|
| `ps -o ppid,lstart,args -p 32442` | parent 7918 = `/usr/lib/systemd/systemd --user`, démarré le 17 oct. à 09:03:37, `bash …/vaultia-watchdog.sh` |
| `systemctl --user show vaultia-watchdog -p MainPID -p NRestarts -p FragmentPath` | `MainPID=32442`, `NRestarts=0`, `~/.config/systemd/user/vaultia-watchdog.service` |
| l'unité | `Restart=always`, `RestartSec=10`, `KillMode=process`, `ExecStart=…/agentchattr/vaultia-watchdog.sh` |
| script à déployer | `scripts/gardien_instances.py` **v1.0.3** (dernier changement du script : `7490c63`) et `scripts/verifier_relais.py` v1.0 (`f19ba27`) ; ce document v1.1 est la seule différence du commit suivant |

Donc : **ne pas tuer le PID 32442 ni lancer un `setsid nohup`**. systemd relancerait le service 10 s plus tard, et deux gardiens
tourneraient ensemble. On l'arrête et on le relance par `systemctl --user`. `KillMode=process` n'arrête que le bash du gardien :
le serveur, les relais et les TUI (sessions tmux) ne sont pas ses enfants et restent en place.

Le serveur n'est pas touché : les deux branches ne modifient ni `app.py` ni les relais. Aucune relance du serveur n'est à prévoir
(docs/EQUIPE.md l.72 ne s'applique pas).

## 1. Push, PR, merge (sur le oui de Charles)

Depuis n'importe quel worktree du dépôt (les branches sont partagées) :

```bash
cd ~/atelier/wt-claude2-gardien
git push origin claude2/verifier-relais claude2/gardien-multi-instance

# PR 1 : le détecteur, en lecture seule
gh pr create --repo Groupe-Vaultia/agentchattr --base main --head claude2/verifier-relais \
  --title "Détecteur de relais morts (scripts/verifier_relais.py)" --body-file <corps 1>
gh pr view <N1> --repo Groupe-Vaultia/agentchattr --json baseRefName,headRefOid   # base main, tête f19ba27…
gh pr merge <N1> --repo Groupe-Vaultia/agentchattr --merge

# PR 2 : le gardien, une fois la PR 1 fusionnée (son diff ne montre alors que le gardien)
gh pr create --repo Groupe-Vaultia/agentchattr --base main --head claude2/gardien-multi-instance \
  --title "Gardien multi-instance : une décision par instance, plus de pkill" --body-file <corps 2>
gh pr view <N2> --repo Groupe-Vaultia/agentchattr --json baseRefName,headRefOid,files
gh pr merge <N2> --repo Groupe-Vaultia/agentchattr --merge
```

**Contrôles** :
- `baseRefName` = `main` pour les deux PR, à lire **avant** chaque `gh pr merge` (PR empilées : docs/EQUIPE.md l.69-70) ;
- fichiers de la PR 2 : `scripts/gardien_instances.py`, `tests/test_gardien_instances.py`, `vaultia-watchdog.sh`,
  `docs/deploiement_gardien.md`, et rien d'autre ;
- `gh pr view <N> --json state,mergeCommit` → `MERGED` ; noter les deux SHA de fusion, dont `<M2>`, la fusion de la PR 2 ;
- si `gh` reste figé : jeton par la variable d'environnement, sans jamais l'afficher (mémoire « oui hors salon »).

## 2. Clone principal : arrêter, mettre à jour, vérifier

Entre `stop` (ici) et `start` (§ 3), plus rien ne relance une session tombée : **enchaîner les § 2 et 3 en quelques minutes, hors
d'une passe d'agent** (pas pendant qu'un agent attend une relance, ni au milieu d'un lot qui crée des sessions tmux).

```bash
systemctl --user stop vaultia-watchdog
systemctl --user is-active vaultia-watchdog        # attendu : inactive
cd ~/atelier/agentchattr
git status --short     # attendu : M docs/PILOTE.md, M vaultia-start.sh, M vaultia-watchdog.sh, plus des non suivis
git diff --stat vaultia-watchdog.sh                # attendu : 1 ligne (commentaire « bolt retire le 18 oct. », l.43)
git checkout -- vaultia-watchdog.sh                # seule modification locale jetée (décision claude-1, carte 5626)
git pull --ff-only origin main
```

**Contrôles** :
- `git log --oneline -1` = `<M2>` ;
- `git status --short` : `docs/PILOTE.md` et `vaultia-start.sh` **toujours modifiés** (ni lus ni touchés par la fusion) ;
- `bash -n vaultia-watchdog.sh` : aucune sortie ;
- `.venv/bin/python -m unittest tests.test_gardien_instances tests.test_verifier_relais` → `Ran 31 tests … OK`. Ces tests
  isolent tmux (socket jetable `-S`) : ils ne touchent pas la salle.

Pourquoi arrêter avant le `pull` : bash relit son script au fil de l'exécution. git remplace le fichier (nouvel inode), donc
l'ancien bash garderait l'ancien texte, mais l'arrêt supprime tout doute et toute passe faite à moitié pendant la mise à jour.

## 3. Répétition à blanc, puis démarrage

```bash
.venv/bin/python scripts/gardien_instances.py --essai claude:3 codex:2 qwencode:4 grok:1
```

Attendu : **aucune ligne « relance -> »**. Seulement « relais mort (TUI vivant) » pour les Qwen encore sans relais, ou
« démarrage » pour un lanceur de moins de 120 s. À 23 h 21 : qwencode-3 et qwencode-4 « relais mort (TUI vivant) », rien
d'autre. **Si une ligne « relance -> » apparaît, ne pas démarrer** : comprendre d'abord (session disparue, appariement).

```bash
systemctl --user start vaultia-watchdog
systemctl --user show vaultia-watchdog -p MainPID -p ActiveEnterTimestamp   # nouveau PID, heure de maintenant
```

## 4. Contrôles pendant les 2 minutes suivantes

```bash
avant=$(command grep -c "agent CLI relance" data/watchdog.log)     # 43 le 19 oct. à 23 h 21
sleep 120
tail -n 20 data/watchdog.log
command grep -c "agent CLI relance" data/watchdog.log              # = $avant (le nouveau script n'écrit plus ce message)
command grep "gardien : " data/watchdog.log | tail -n 8            # aucune ligne « relance -> »
python3 scripts/verifier_relais.py; echo "code=$?"                 # mêmes relais morts qu'avant, pas un de plus
```

Attendu dans le journal : « gardien demarre », puis, toutes les 30 s, une ligne « relais mort (TUI vivant) » par Qwen sans
relais. Ce bruit cesse quand ces relais sont relancés (§ 5). Les lignes « pont relance : bolt » de l'ancien gardien (toutes les
30 s depuis le 18 oct.) disparaissent : le script du dépôt ne lance plus de pont bolt.

## 5. Relance des relais morts : en fin de lot, une instance à la fois

```bash
.venv/bin/python scripts/gardien_instances.py --relancer qwencode:4 --essai   # lire le plan
.venv/bin/python scripts/gardien_instances.py --relancer qwencode:4           # tue le relais, ferme TUI et lanceur, relance
sleep 20; python3 scripts/verifier_relais.py                                   # qwencode-4 « ok » avant de passer au suivant
```

- La relance **ferme le TUI** et perd son contexte : c'est une décision humaine, en fin de lot. Elle applique aussi
  `contextWindowSize` (relu au démarrage de Qwen, msg 5599).
- Refus (code 3) si un worktree connu de l'instance a des modifications non commitées : commit WIP d'abord. `--force` seulement
  après avoir vu ce qu'il contient : à 22 h 53, qwencode-3 avait `cad-bolt` (2 fichiers) et `wt-qwencode3-freins` (1).
- Pendant la relance, le gardien en service voit un lanceur de moins de 120 s sans TUI : « démarrage », il n'y touche pas.

## 6. Retour arrière

| Niveau | Commandes | Effet |
|---|---|---|
| **a. Immédiat, sans push** (recommandé en cas de doute) | `systemctl --user stop vaultia-watchdog` | la salle tourne sans gardien : serveur, relais et TUI restent en place ; rien n'est relancé tout seul |
| b. Ancien script, en local | `cd ~/atelier/agentchattr && git checkout 1d9b21e -- vaultia-watchdog.sh && systemctl --user start vaultia-watchdog` | revient au gardien du 17 oct. **avec ses défauts** : `pkill` de toute une famille, qwencode relancé sans les options `:8085`. Laisse le clone modifié jusqu'au revert formel |
| c. Revert formel (oui de Charles, R2) | voir ci-dessous | `main` revient au gardien précédent ; le détecteur (PR 1, lecture seule) peut rester |

```bash
cd ~/atelier/agentchattr && git fetch origin
git worktree add ../wt-claude2-revert -b claude2/revert-gardien origin/main   # worktree neuf (R7) : aucune branche de travail touchée
cd ../wt-claude2-revert
git revert -m 1 <M2> --no-edit                   # fusion de la PR 2 seulement
git push origin claude2/revert-gardien
gh pr create --repo Groupe-Vaultia/agentchattr --base main --head claude2/revert-gardien --title "Revert : gardien multi-instance"
gh pr merge <N3> --repo Groupe-Vaultia/agentchattr --merge
systemctl --user stop vaultia-watchdog && cd ~/atelier/agentchattr && git pull --ff-only origin main && systemctl --user start vaultia-watchdog
```

## 7. Le cas de ce soir, répété sans danger

`--simuler-absent` retire une session de la lecture **réelle** de tmux, et `--essai` montre ce que ferait le gardien sans rien
faire (l'option est refusée sans `--essai`). Sortie du 19 oct. à 23 h 21, branche v1.0.3 :

```text
$ scripts/gardien_instances.py --essai --simuler-absent agentchattr-qwencode-3 claude:3 codex:2 qwencode:4 grok:1
gardien (essai) : qwencode-3 (ac-qwencode3 / pas de TUI) : relance -> fermer ac-qwencode3 ; relancer ac-qwencode3
gardien (essai) : qwencode-4 (ac-qwencode4 / agentchattr-qwencode-4) : relais mort (TUI vivant) ; …

$ scripts/gardien_instances.py --essai --simuler-absent agentchattr-qwencode claude:3 codex:2 qwencode:4 grok:1
gardien (essai) : qwencode-1 (ac-qwencode / pas de TUI) : relance -> tuer PID 1684916 ; fermer ac-qwencode ; relancer ac-qwencode
gardien (essai) : qwencode-3 (…) : relais mort (TUI vivant) ; …
gardien (essai) : qwencode-4 (…) : relais mort (TUI vivant) ; …
```

| Panne | Ancien gardien (`1d9b21e`) | Nouveau gardien |
|---|---|---|
| le TUI de qwencode-3 meurt | **rien** : `cli qwencode` ne regarde que `agentchattr-qwencode` | relance de qwencode-3 seul, avec la commande d'origine de `ac-qwencode3` (8 s de confirmation) ; qwencode-1, -2 et -4 intacts |
| le TUI de qwencode-1 meurt | `pkill` des relais des **4** instances, puis relance de `ac-qwencode` seul, avec `--approval-mode=yolo` sans les options `:8085` (`data/watchdog.log:6149`, 17 h 10 ; `:6843`, 22 h 57) | tue le seul PID du relais de qwencode-1, relance `ac-qwencode` avec sa commande d'origine ; les 3 autres intacts |
| un relais meurt, son TUI vit | rien | signalé à chaque passe, sans action (relancer fermerait le TUI) |

Les mêmes cas sont figés en tests sans tmux réel (`tests/test_gardien_instances.py` : `test_tui_mort_une_seule_instance_touchee`,
`test_simuler_absent`, `test_ce_soir_relais_mort_tui_vivant_signale_seulement`), et la relance par la commande déshabillée est
vérifiée sur un vrai tmux jetable (`test_brut_mort_ne_deshabille_vivant`).
