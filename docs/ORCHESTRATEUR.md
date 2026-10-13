# Orchestrateur multi-agents — définition de « fonctionnel v1 » et backlog des frictions

**Version : v0.5** — 2026-09-21. Changement v0.4 → v0.5 : `main` a avancé de quatre PR ce soir
(#3 à #6, branches `vaultia/*`, mergées par Charles); C3, C5 et F11 mis à jour en conséquence
(clone principal propre, limite des cartes à 600, branche `equipe/regles`).
Changement v0.3 → v0.4 (Charles #144) : C1 mesure les huit cartes v1.5 (#16–#23); état et
étape 1 mis à jour.
Changement v0.2 → v0.3 (revue codex #124) : F2 décrit le partage de l'utilisateur Linux, pas
un accès GitHub « pour tous les agents ».
Changement v0.1 → v0.2 (revue codex #112) : C1 mis à jour (12 règles actives), C2 mesure un
mécanisme réel d'injection de rôle, C5 se conclut à la PR mergée, F6 daté.
v0.1 : premier jet (claude). Objectif fixé par Charles (#74) :
« faire fonctionner l'orchestrateur ». Ce document dit ce que ça veut dire, mesurablement.

L'orchestrateur, aujourd'hui, c'est agentchattr (fork `Groupe-Vaultia`, v0.5.0) + les
règles + les conventions de `docs/EQUIPE.md`. Le projet initial de Charles était
« modèle local producteur, Claude réviseur ». L'état réel est l'inverse (voir F1) : c'est
ce que v1 doit corriger ou assumer.

## 1. Critères d'acceptation « v1 fonctionnel »

| # | Critère | Mesure | État |
|---|---|---|---|
| C1 | Règles R1–R8 actives et non tronquées | `chat_rules(list)` montre exactement 8 cartes, toutes v1.5 (#16–#23) | v1.5 activées (#144, epoch 21) ; **20 actives** à la lecture : #4–#15 pas encore désactivées |
| C2 | Rôles explicites en config, pas seulement dans le fil | Agents API : champ rôle serveur (`POST /api/roles/{agent}`, `roles.json`), injecté dans le system prompt (`wrapper_api.py:312`). Agents CLI : cartes Rules injectées dans le prompt de déclenchement (`wrapper.py:577`). Les *hats* sont visuels (`app.py:66`) et ne comptent pas. | CLI : R1 v1.5 active ✔. API : `roles.json` à renseigner pour qwenlocal; `system_prompt` de `config.local.toml` à compléter (F1) |
| C3 | Isolation des arbres de travail | Chaque agent qui écrit a son worktree; le clone principal n'a pas de modifs non commitées d'agents | wt-claude et wt-claude-acces créés; clone principal propre sur `main` à 22:10 (`git status -sb`) — le rebranding a été commité et mergé via PR #3 (0c9a8af) |
| C4 | Le producteur local produit réellement | qwenlocal peut écrire un fichier dans son worktree et le soumettre à revue, sans réseau ni push | **non** — pont chat-completion sans outils |
| C5 | Un cycle complet réussi | branche → revue codex → validation claude → oui Charles → claude pousse + ouvre la PR → **Charles merge** | en cours : `equipe/regles` (ex-`equipe/regles-v1.1`), revue codex faite (#112, #124, #156). Les PR #3–#6 mergées ce soir n'ont pas suivi ce cycle (pas de revue codex dans le fil) : elles ne comptent pas pour C5 |
| C6 | Pas de loop guard sur un cycle normal | 0 déclenchement `max_agent_hops` sur un cycle | 3 déclenchements ce soir (#47, #59, #72) |
| C7 | Aucun jeton en clair sur disque | `~/.git-credentials` absent; `credential.helper` = gh | en attente des commandes de Charles |
| C8 | Une session perdue ne perd pas l'état | Rôles, règles, décisions relisibles depuis le dépôt + panneau Rules, pas depuis le fil | ce document + EQUIPE.md |

## 2. Backlog des frictions observées le 2026-09-21

| # | Friction | Preuve | Nature | Piste |
|---|---|---|---|---|
| F1 | qwenlocal affirme des vérifications qu'il ne peut pas faire (`gh auth status`, stockage de jetons « en session ») | #41, #43, #46; `wrapper_api.py` sans outils | **Bug produit** : un agent sans outils n'est pas averti qu'il n'en a pas | Injecter dans son `system_prompt` : « tu n'as ni shell ni fichiers; ne dis jamais vérifié »; à terme, tool-calling vers un worktree bac à sable |
| F2 | Tout processus avec shell sous l'utilisateur Linux `charles-antoine` hérite du jeton `charlowal` du keyring (constaté : claude, codex; qwenlocal sans outils; cursor, gemini non vérifiés) | #45, #50; EQUIPE.md §5 | Limite d'architecture | Bot GitHub à droits minimaux (décidé, après v1.x); R2 en attendant |
| F3 | Jeton en clair `~/.git-credentials` | `git config credential.helper` = store | Config | `gh auth setup-git`; Charles exécute |
| F4 | Arbre de travail partagé entre agents; `main` sale; branche du clone changée en cours de séance | `git status` 21:24; `git worktree list` 21:30 | Convention manquante | Worktree par agent (EQUIPE.md §2) |
| F5 | Loop guard ×3 sur reformulations et relances | #47, #59, #72; `max_agent_hops = 4` | Comportement d'agents | R5 v1.5; envisager un hop count par mention plutôt que par message |
| F6 | Perte de session claude-1 → contexte perdu; demande #52 (20:59) restée sans réponse jusqu'au #66 (21:18), ~18 min | #52, #61–#66 | Robustesse | C8; état dans le dépôt, pas dans le fil |
| F7 | Deux sessions Qwen renommées par le serveur → fausse alerte sécurité | #27 | UX | Afficher « instance 2 de qwen » plutôt qu'un nom nouveau |
| F8 | Codex : `gh auth status` faux négatif dans le sandbox sans réseau | #42, #50 | Environnement | Documenter : vérifier hors sandbox avant de conclure |
| F9 | Rôles définis dans le fil, redéfinis par chaque agent | #55, #58, #76 | Gouvernance | C1 + C2 |
| F10 | Le harnais de claude refuse toute opération sur les identifiants git | 21:24 (classifier) | Garde-fou voulu | Charles exécute lui-même; claude fournit les commandes |
| F11 | Règles tronquées sans avertissement au proposant (limite 160 à l'époque; 600 depuis 0c9a8af, 21:31, serveur redémarré 22:05) | #96 (codex); `rules.py:9`, `rules.py:120` | Bug produit (la limite a changé, pas l'absence d'avertissement) | Retourner une erreur ou la longueur restante dans la réponse `propose`; documenter la limite dans l'outil |
| F12 | `docs/` est dans le `.gitignore` amont : les documents d'équipe étaient invisibles pour git | `.gitignore:20`; `git check-ignore` | Config du fork | Ligne retirée dans le fork (cette branche); à surveiller lors des merges amont |

## 3. Prochaines étapes (ordre proposé, Charles tranche)

1. Charles : désactiver #4–#15 (v1.5 #16–#23 activées au #144); commandes keyring; réponse rebranding.
2. codex : revue de `docs/EQUIPE.md` et de ce document.
3. claude : corriger selon revue → validation → demande d'autorisation à Charles → claude pousse `equipe/regles` et ouvre la PR → Charles merge (= C5).
4. claude : F1 — `system_prompt` de qwenlocal, honnête sur ses capacités (touche `config.local.toml`, gitignoré, donc changement local uniquement).
5. claude + codex : F11 — patch `mcp_bridge.py` / `rules.py` pour signaler la troncature (petit, testable, bon candidat pour un deuxième cycle).
