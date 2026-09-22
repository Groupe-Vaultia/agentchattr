# Accès mobile à l'équipe d'agents — constats, options, recommandation

**Version : v0.3** — 2026-09-21 (claude). Changement v0.2 → v0.3 : K4 corrigé — le WebSocket ne
passe pas par le contrôle d'`Origin` (seuls les POST `/api/*` sont bloqués); L1 livré
(`allowed_origins_for`, `[server] allowed_origins`, 8 tests), en attente de revue codex;
Charles a retenu la voie A (#179), Tailscale.
Changement v0.1 → v0.2 (revue codex #156) : K8 ne
nomme plus l'infrastructure Vaultia-client (R4); K9 ajouté — l'expéditeur est déclaré par le
navigateur; §2.6 et lot L1 étendus en conséquence.
v0.1 : demande de Charles (#145) : interagir avec les agents
depuis son cellulaire, hors Wi-Fi, idéalement par un site sous `vaultia.ca`. Brainstorm
préalable : gemini #147, cursor #148, qwenlocal #149. Ce document ne code rien; il donne à
Charles de quoi choisir.

Branche `acces/mobile`, worktree `~/atelier/wt-claude-acces`. Note : `docs/` est encore dans
le `.gitignore` de `main` (friction F12); ce fichier devient commitable après le merge de la
PR `equipe/regles-v1.1`, ou avec `git add -f`.

## 1. Constats vérifiés (2026-09-21, 21:53)

| # | Constat | Preuve |
|---|---|---|
| K1 | agentchattr écoute en local seulement : `127.0.0.1:8300` (UI) et `127.0.0.1:8200` (MCP). Un drapeau `--allow-network` permet de lier une autre adresse. | `config.toml` `[server] host = "127.0.0.1"`; `ss -ltnp`; `run.py:30` |
| K2 | **Le « jeton de session » n'est pas une authentification.** Il est généré au démarrage (`secrets.token_hex(32)`) puis **injecté dans la page `/` pour quiconque la charge**; `/` et `/static/` sont publics. Quiconque atteint le port 8300 obtient le jeton, écrit comme `user`, déclenche les agents. | `run.py:57-58`, `run.py:110-116`; `app.py:195-196`, `app.py:215-216` |
| K3 | Les agents déclenchés ont un shell, git et `gh` sous l'utilisateur `charles-antoine` (claude, codex). **Accès distant au chat = accès distant à ce poste.** | `EQUIPE.md` §4–§5 |
| K4 | Le serveur refuse toute requête dont l'en-tête `Origin` n'est pas `http://127.0.0.1:8300` ou `http://localhost:8300` (403 « origin not allowed »). Les navigateurs envoient `Origin` sur tout POST. Le WebSocket, lui, **ne passe pas par ce middleware** (`BaseHTTPMiddleware` ne traite que le scope `http`, `starlette/middleware/base.py:102`) : derrière un proxy ou un tunnel, le fil s'affiche et les messages passent, mais **tout ce qui est POST échoue** — panneau Rules, téléversements, horaires, export/import. | `app.py:204-207`, `app.py:229-235`; `static/chat.js:2537` (envoi par WebSocket), `static/chat.js:2620`, `3938` (POST); WebSocket `/ws?token=` `app.py:1070-1082` |
| K5 | Le jeton passe en *query string* pour le WebSocket (`/ws?token=…`) : il finit dans les journaux de tout proxy intermédiaire. | `app.py:1073` |
| K6 | L'UI a un `viewport` mobile et un mode étroit < 900 px; pas de `manifest.json` ni de *service worker* → utilisable dans un navigateur mobile, **pas installable** comme PWA. | `static/index.html:5`; `static/style.css:4088`; `ls static` |
| K7 | `vaultia.ca` est un site statique (nginx/1.24, Ubuntu, dernier changement 2026-07-11) hébergé à `23.27.253.62` — **Ace Data Centers, Orem, Utah, États-Unis**. DNS chez easyDNS (Canada). | `curl -I https://vaultia.ca`; `dig`; `whois 23.27.253.62` |
| K8 | Ce poste (connexion résidentielle, IP dynamique) héberge aussi des services **Vaultia-client** en production — lesquels : hors périmètre de ce document (R4). Un nginx local écoute sur `0.0.0.0:80`. Pas de Tailscale ni de cloudflared installés. | `ss -ltnp`; `which` |
| K9 | **L'expéditeur d'un message est choisi par le client.** Sur le WebSocket, `sender = event.get("sender") or …` : quiconque a le jeton (K2) peut écrire sous le nom `charles`. Aujourd'hui, seul un accès local le permet; à distance, un « oui Charles » dans le fil ne prouve rien tant que l'identité n'est pas fixée côté serveur après authentification. (Relevé par codex #156.) | `app.py:1155` |

## 2. Ce que les constats imposent, quelle que soit l'option

1. **Une vraie authentification devant le port 8300** — VPN lié à l'appareil, ou SSO + MFA. Le
   jeton interne (K2) ne protège de rien; l'exposer nu sur Internet, c'est donner un shell
   sur ce poste (K3) au premier scanner venu.
2. **Un petit correctif dans le fork** : `[server] allowed_origins` configurable (K4) et, si
   proxy, respect de `X-Forwarded-Proto/Host`. Sans lui, aucune option ne fonctionne. Petit,
   testable (`tests/` existe) → bon candidat pour un deuxième cycle complet.
3. **R4** : ce poste est aussi la prod Vaultia-client (K8). Chaque port ouvert vers l'extérieur
   est une porte de plus vers cette prod. L'option qui n'ouvre **aucun port entrant** part
   avec un avantage structurel.
4. **Résidence** : le trafic du chat est du travail ouvert (R4 : agentchattr public), donc
   un relais hors Québec n'est pas une violation de R4. C'est une question d'image et de
   cohérence pour Vaultia, pas de règle — Charles tranche.
5. **R3** : jamais le jeton dans un lien partagé ou un signet (K5); sessions courtes.
6. **Identité humaine fixée côté serveur** (K9) : derrière l'authentification, le serveur
   impose le nom de l'expéditeur humain (en-tête du proxy ou session), il ne le lit plus dans
   le message. Acceptable de s'en passer pour A (seuls les appareils de Charles sont dans le
   réseau privé); **obligatoire avant B**, et avant que R2 s'appuie sur un « oui » distant.

## 3. Options

### A — Réseau privé (Tailscale ou WireGuard) + l'UI existante
- **Mécanisme** : le poste et le cellulaire rejoignent un réseau privé chiffré (WireGuard).
  Depuis le cell, Charles ouvre l'UI actuelle par l'adresse privée du poste; `tailscale serve`
  peut ajouter HTTPS et un nom stable (`*.ts.net`). Aucun port entrant ouvert chez lui.
- **Authentification** : l'appareil (clé WireGuard) + l'identité du compte Tailscale (SSO).
- **Effort** : ~1 h de Charles (installer sur le poste et le cell) + le correctif
  `allowed_origins` (claude, ~1 h, revue codex).
- **Pour** : le plus vite, le plus sûr (rien d'exposé), zéro dépendance à `vaultia.ca`.
- **Contre** : pas d'adresse publique; un tiers de l'équipe (plus tard) devrait être invité
  dans le réseau. Le plan de contrôle Tailscale est aux É.-U. (le trafic reste chiffré de
  bout en bout, relais DERP seulement si la traversée NAT échoue). Variante 100 % maison :
  WireGuard sur le poste + un port UDP ouvert + DNS dynamique — même résultat, plus de
  gestion.

### B — `chat.vaultia.ca` public : reverse proxy + Authentik (SSO/MFA)
- **Mécanisme** : enregistrement `chat.vaultia.ca` → IP du poste (DNS dynamique easyDNS,
  l'IP résidentielle change); redirection du port 443 vers le nginx déjà installé;
  certificat Let's Encrypt; **Authentik en auth-forward** devant agentchattr; WebSocket
  proxifié; correctif `allowed_origins` + en-têtes `X-Forwarded-*`.
- **Authentification** : Authentik (mot de passe + MFA), sessions courtes.
- **Effort** : ~1 jour (Charles : DNS, routeur, Authentik; claude : nginx + correctif; codex :
  revue sécurité).
- **Pour** : c'est le « site web » demandé; n'importe quel appareil; partageable à l'équipe
  plus tard; tout reste sur le poste, au Québec.
- **Contre** : ouvre un port entrant sur la machine qui héberge la prod Vaultia-client (K8,
  §2.3); dépend d'Authentik en état de marche; IP dynamique à suivre. Variante *Cloudflare
  Tunnel + Access* (proposée par gemini #147) : pas de port ouvert et plus simple, mais
  Cloudflare (É.-U.) termine le TLS et voit le trafic en clair — acceptable selon R4,
  contraire à l'image Vaultia; à Charles de juger.

### C — Passerelle messagerie (Telegram, ou Signal) vers `#general`
- **Mécanisme** : un script local, enregistré comme agent (`/api/register` est réservé à
  la boucle locale, `app.py:218-227`), lit `#general` par l'API (`/api/messages` avec
  jeton *Bearer*, `app.py:239-244`) et relaie vers un salon privé sur le cell; les réponses
  de Charles reviennent par `/api/send`. Les `choices` deviennent des boutons.
- **Pour** : aucun port entrant; notifications natives; fonctionne sur LTE instable; un
  « oui / non » au pouce.
- **Contre** : le fil transite par les serveurs du service (Telegram : Dubaï/Pays-Bas, bots
  non chiffrés de bout en bout; Signal : `signal-cli`, plus lourd). Pas de panneau Rules,
  pas de jobs, pas d'images. C'est un complément, pas le site demandé.

### D — Héberger le chat sur le serveur de `vaultia.ca` (Utah) — **rejetée**
Les agents (Claude CLI, Codex CLI, Qwen sur llama-server) et leurs worktrees vivent sur ce
poste; le serveur distant devrait de toute façon rejoindre ce poste. Et installer la salle
de commande de Vaultia en Utah contredit la thèse du projet (K7).

## 4. Recommandation

**A maintenant, B ensuite, C en option.**

- **Cette semaine — A** : l'accès hors Wi-Fi existe en une soirée, sans rien exposer, et le
  correctif `allowed_origins` qu'il exige sert aussi à B.
- **Quand l'équipe ou la démo le demande — B** sur `chat.vaultia.ca`, avec Authentik. A reste
  comme voie de secours si B tombe.
- **C** seulement si les notifications manquent à Charles après une semaine d'usage de A.

Ce que je ne recommande pas : ouvrir le port 8300 « en attendant » (K2 + K3), ni Cloudflare
Tunnel comme solution finale pour Vaultia (§3 B, variante).

## 5. Décision demandée à Charles

1. Voie : **A puis B** (recommandé) · **B directement** · **C seulement** · autre.
2. Si A : Tailscale (rapide, plan de contrôle É.-U.) ou WireGuard maison (tout au Québec,
   plus de gestion) ?
3. Si B : Authentik est-il déjà en marche sur ce poste ? (non vérifié — je n'ai pas cherché
   au-delà des noms de conteneurs, R4.)

## 6. Découpage prévu après la décision (lots, un fichier = un agent)

| Lot | Qui | Livrable | Preuve attendue |
|---|---|---|---|
| L1 | claude | `[server] allowed_origins` configurable; tests dans `tests/` — **livré** sur `acces/mobile` : `app.allowed_origins_for()`, comparaison d'`Origin` normalisée, clé documentée dans `config.toml`, `tests/test_allowed_origins.py` (8 tests). `X-Forwarded-*` : pas nécessaire pour A (Tailscale Serve termine le TLS et proxifie en local); à revoir pour B | `python -m unittest discover -s tests` : 162 tests, 1 échec **préexistant sur `main`** (`test_room_name`, rebranding), 8 nouveaux verts |
| L1b | claude | Expéditeur humain imposé côté serveur quand un en-tête d'identité authentifié est présent (K9); sans en-tête, comportement actuel | test : message avec `sender: "charles"` sans en-tête distant → refusé ou renommé |
| L2 | codex | Revue L1 + passe sécurité de l'exposition choisie | constats dans `#general` |
| L3 | Charles (commandes fournies par claude) | Installation Tailscale/WireGuard sur poste + cell **ou** DNS + routeur + Authentik | capture d'écran de l'UI depuis le cell en LTE |
| L4 | qwenlocal | Brouillon de `docs/ACCES-MOBILE-GUIDE.md` : marche à suivre pour Charles, texte seul | claude intègre |
| L5 | cursor, gemini | Avis sur la config nginx/Authentik (B) avant revue codex | — |
| L6 | claude | `manifest.json` + *service worker* minimal → icône sur l'écran d'accueil (K6) | Chrome mobile propose « Installer » |

Ordre : L1 → L2 → oui Charles → PR → merge (cycle R2) ; L3 en parallèle ; L1b avant B ; L4–L6 après.

## 7. Ce que le brainstorm a apporté

| Agent | Idée | Sort |
|---|---|---|
| gemini #147 | PWA + Cloudflare Tunnel + Authentik; bot Telegram/Signal | PWA → L6; Tunnel → variante de B, réserve résidence; bot → C |
| cursor #148 | « porte d'entrée mobile, pas un nouveau site »; auth forte, pas de PAT dans le navigateur; question (A) chat / (B) commandes / (C) les deux | Cadrage retenu tel quel; la question est reprise en §5 |
| qwenlocal #149 | Contraintes R3/R4/R6/R7; agents comme « contacts » avec statut; commandes structurées; mode hors-ligne | Contraintes → §2; statuts existent déjà dans l'UI; hors-ligne → L6 (cache du fil récent) |

| codex #156 | Tailscale Serve d'abord, test réel en LTE, puis décider si `chat.vaultia.ca` se justifie; expéditeur déclaré par le navigateur (K9) | Même chemin que §4 (A puis B); K9 → §2.6, L1b |

Ce que personne n'avait dit et qui change l'ordre des choses : K2 (le jeton n'authentifie
pas), K4 (le contrôle d'`Origin` bloque tout accès non-local sans correctif) et K9 (l'identité
de l'expéditeur est déclarée, pas vérifiée).
