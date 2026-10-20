# Affinité de carte pour les Qwen : constat et proposition (v1.2)

v1.2 (2026-10-20, claude-2, claude-1 msg 5699, remarque claude-3 msg 5657) : § 4, `--data ~/atelier/agentchattr/data` tant que le
gardien n'est pas déployé ; § 6, les deux scripts de vitesse (`usage_qwen.py`, `vitesse_cartes_qwen.py`) pour refaire la mesure
de l'après à l'identique.

v1.1 (2026-10-19, claude-2, revue claude-3 msg 5652, claude-1 msg 5653) : gain « 71 min certaines, jusqu'à ~4 h » ; risque non
écarté d'une conversation neuve qui écrase la fente de son voisin ; règle de lots « un de {1, 2} et un de {3, 4} » ; rotation de
`acces-cartes.log` ; § 4 : attente du registre après un relais tué (gardien v1.0.6). nginx est appliqué depuis 23 h 48 (msg 5653).
v1.0 (2026-10-19, claude-2, claude-1 #tache-22 msg 5648) : première version. **Rien n'est appliqué** : ni nginx, ni
`vaultia-start.sh`, ni relance. claude-1 appliquera à chaque relance de Qwen, en fin de lot.

## 1. Constat : les pertes de cache, comptées

Routeur actuel `qwen-switch/nginx/qwen-lb.conf:16-19` : `upstream qwen { least_conn; 8081; 8082 }`, sans affinité ; `access_log off`.
Chaque carte : `llama-server -c 229376 --parallel 2`, soit 2 fentes de 114 688 jetons (`qwen-switch/lancer-q4.sh`). Il y a
4 fentes pour 4 Qwen. Aucun redémarrage de llama-server ce soir : la carte A tourne depuis 12 h 47, et le garde-fou « attend »
tant qu'une carte travaille.

Compté par `scripts/pertes_cache_qwen.py` (lecture seule de `journalctl --user -u qwen-q4-a|b`). Une **perte** est une requête
dont la fente ne contenait pas sa conversation, soit par une sélection LRU, soit par une sélection LCP qui jette plus de 10 % du
cache de la fente, avec au moins 10 000 jetons retraités :

| Depuis | Requêtes | LRU (A / B) | Changement de carte | Éviction, même carte | Ambigu (les deux possibles) | Indéterminé | **Nouvelle conversation** (relance, `/clear`) | LRU courts (< 10 k) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 17 h 00 | 1 322 | 161 (72 / 89) | 27 (55 min) | 8 (16 min) | 70 (148 min) | 16 (20 min) | 32 (31 min) | 74 |
| 21 h 40 | 492 | 39 (18 / 21) | 8 (16 min) | 0 | 10 (13 min) | 3 (3 min) | 7 (7 min) | 27 |

Les minutes sont le temps de « prompt eval » cumulé, lu dans les journaux, à environ 500 jetons/s en moyenne sur une carte libre.
Pendant un tel retraitement, la génération de l'autre fente de la même carte tombe vers 1 jeton/s (task 35224, 21 h 34 à 21 h 36).
Le cache de prompts en RAM n'aide pas : `prompt state size 1673.739 MiB exceeds cache size limit 512.000 MiB, skipping`
(`--cache-ram 512`).

**Ce qui justifie le correctif** : avec une carte fixe par Qwen, deux conversations se partagent les deux fentes de leur carte, et
chacune retrouve la sienne par LCP. Gain depuis 17 h : **71 min certaines** (27 changements de carte et 8 évictions attribués),
**jusqu'à environ 4 h** si les 86 pertes ambiguës ou indéterminées (168 min) relèvent des mêmes causes. Les nouvelles conversations
(32, 31 min) restent.

**Risque non écarté, à mesurer après la bascule** : une conversation neuve (relance ou `/clear`) a le même préfixe système (~27 k)
que ses voisines de carte, et llama-server prend la fente au plus long LCP (seuil 0,100 au journal). Un Qwen relancé peut donc
écraser le cache de son voisin de carte ; l'affinité n'empêche pas ça. `pertes_cache_qwen.py` (« éviction sur la même carte »)
et `acces-cartes.log` le montreront.

**Compromis** : à 2 Qwen fixes par carte, deux Qwen qui travaillent seuls sur la même carte laissent l'autre vide (la raison du
`least_conn`). **Règle pour les lots : quand deux Qwen seulement travaillent, prendre un de {qwencode-1, qwencode-2} (carte A) et
un de {qwencode-3, qwencode-4} (carte B).**

**Limite du comptage** : les journaux ne disent pas quel agent a envoyé la requête. Une conversation est suivie par sa longueur,
d'où les 70 cas « ambigus » entre changement de carte et éviction. Le journal d'accès proposé au § 2 lève cette limite pour la
suite : port d'entrée, donc agent, et carte servie.

## 2. nginx : deux ports à carte fixe, l'autre carte en secours

À ajouter dans le bloc `http { … }` de `qwen-lb.conf`. `:8085`, `172.30.0.1` et le relais X1 (`10.42.0.1`) ne bougent pas.
`8086` et `8087` sont libres sur toutes les adresses (`ss -ltn`, 19 oct. 23 h 38).

```nginx
  # 19 oct. 2026 (claude-2, claude-1 #tache-22 msg 5648) : affinité de carte. Un Qwen garde sa carte, donc le cache de sa
  # conversation (2 fentes par carte, 2 Qwen par carte) ; l'autre carte ne sert que si la sienne ne répond plus.
  # Journal des seuls ports 8086/8087 : quelle carte a servi, en combien de temps (pas d'en-tête, donc pas de clé).
  log_format carte '$time_iso8601 port=$server_port carte=$upstream_addr statut=$status duree=$request_time';
  upstream qwen_a {
    server 127.0.0.1:8081 max_fails=2 fail_timeout=30s;
    server 127.0.0.1:8082 backup;
  }
  upstream qwen_b {
    server 127.0.0.1:8082 max_fails=2 fail_timeout=30s;
    server 127.0.0.1:8081 backup;
  }
  server {
    listen 172.30.0.1:8086;   # carte A en premier : qwencode-1, qwencode-2
    access_log /home/charles-antoine/atelier/qwen-switch/nginx/acces-cartes.log carte;
    location / {
      proxy_pass http://qwen_a;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
      proxy_buffering off;
    }
  }
  server {
    listen 172.30.0.1:8087;   # carte B en premier : qwencode-3, qwencode-4
    access_log /home/charles-antoine/atelier/qwen-switch/nginx/acces-cartes.log carte;
    location / {
      proxy_pass http://qwen_b;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
      proxy_buffering off;
    }
  }
```

- `backup` : la carte de secours ne reçoit une requête que si la carte principale est marquée en échec (2 échecs en 30 s :
  connexion refusée pendant un redémarrage du garde-fou, par exemple). Une carte **occupée** n'échoue pas : llama-server met la
  requête en file, et l'affinité tient. Une requête POST déjà envoyée n'est pas rejouée sur l'autre carte (comportement par
  défaut de `proxy_next_upstream`) ; une connexion refusée l'est.
- **Validé** par `nginx -t` dans un préfixe jetable, sur une copie complète de la configuration (chemins réécrits vers le préfixe) :
  `syntax is ok`, `test is successful`, code 0 (nginx 1.28.3, 19 oct. 23 h 39).
- **Application**, quand claude-1 le décide :
  1. ajouter le bloc ;
  2. lancer `/usr/sbin/nginx -t -c ~/atelier/qwen-switch/nginx/qwen-lb.conf -p ~/atelier/qwen-switch/nginx/`, la commande `ExecStartPre` de `qwen-lb.service` ;
  3. lancer `systemctl --user reload qwen-lb`. C'est `nginx -s reload` : les flux en cours finissent sur les anciens workers, et `:8085` continue de servir.

## 3. Options de lancement par instance (`vaultia-start.sh` local)

La ligne `Q8085_FLAGS=…` porte la clé : **elle ne change pas**. On dérive deux variables par substitution bash, sans recopier la clé :

```bash
QA_FLAGS="${Q8085_FLAGS/172.30.0.1:8085/172.30.0.1:8086}"   # 19 oct. 2026 : carte A d'abord (affinité de carte, msg 5648)
QB_FLAGS="${Q8085_FLAGS/172.30.0.1:8085/172.30.0.1:8087}"   # carte B d'abord
tmux new-session -d -s ac-qwencode  -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $QA_FLAGS; read"
tmux new-session -d -s ac-qwencode2 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $QA_FLAGS; read"
tmux new-session -d -s ac-qwencode3 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $QB_FLAGS; read"
tmux new-session -d -s ac-qwencode4 -c "$PWD" "env PATH=\"$PATH\" $PY wrapper.py qwencode $QB_FLAGS; read"
```

Ces quatre lignes remplacent les quatre lignes `… wrapper.py qwencode $Q8085_FLAGS; read` actuelles. La substitution ne touche que
l'adresse : `--openai-base-url http://172.30.0.1:8085/v1` devient `:8086/v1` ou `:8087/v1`.

## 4. Comment le gardien les relira

- **Relance automatique** (TUI mort) : le gardien relance avec la commande d'origine de **ce** lanceur
  (`#{pane_start_command}`, déshabillée). Un lanceur créé avec `:8087` est relancé sur `:8087` : l'affinité survit.
- **Les lanceurs actuels portent `:8085`** : une relance simple les garderait sur `:8085`. Pour déplacer une instance, à sa
  relance de fin de lot : `scripts/gardien_instances.py --relancer qwencode:3 --url http://172.30.0.1:8087/v1` (avec
  `--data ~/atelier/agentchattr/data` tant que le gardien n'est pas déployé dans le clone principal : sinon le registre est
  introuvable, et la relance attend 75 s puis s'arrête, code 4) (v1.0.5,
  branche `claude2/gardien-url`, empilée sur `1ae5334`). Ce mode remplace **la seule** valeur de `--openai-base-url` dans la
  commande du lanceur et refuse si l'option manque ou est double. Il garde le reste à l'identique, clé comprise, sans l'afficher,
  et valide le tout par `bash -n`. En `--essai` sur la salle réelle (23 h 41) : qwencode-3 → `:8087`, qwencode-1 → `:8086`.
- **Course à l'emplacement** (incident de 22 h 57, claude-3 msg 5652) : un relais tué reste « actif » au registre jusqu'au
  crash-timeout (60 s, `app.py:462-468`). Relancé trop tôt, le nouveau relais prend un autre numéro et ferme le TUI d'une autre
  instance. Gardien v1.0.6 :
  - en automatique, il tue à une passe et relance à une passe suivante, quand `data/registry.json` ne montre plus l'instance
    « actif » ni « en attente » ;
  - en manuel (`--relancer`), il attend après le kill, toutes les 5 s et 75 s au plus. Au plafond, il s'arrête : TUI et lanceur
    restent en place, et le code de sortie vaut 4.
- **Limite connue** : si un lanceur `ac-*` a disparu, le gardien reprend la commande d'un lanceur **frère**, qui peut être sur
  l'autre carte. L'instance tourne alors, mais sans affinité jusqu'à sa prochaine relance avec `--url`. Les lanceurs ne
  disparaissent pas d'eux-mêmes : leur `; read` les garde après la mort du relais.
- **Risque résiduel** : une requête annexe de Qwen Code (compaction, sous-agent) peut prendre la fente de l'autre Qwen de la carte.
  C'est rare ; le journal `acces-cartes.log` et `scripts/pertes_cache_qwen.py` le montreront.

## 5. Rotation de `acces-cartes.log`

Une ligne d'environ 90 octets par requête, soit environ 1 300 requêtes en 6 h ce soir : moins de 1 Mo par jour. Pas d'urgence.
Proposition, à poser quand claude-1 le décide : un `logrotate` utilisateur (`copytruncate`, donc sans `nginx -s reopen`), lancé
chaque semaine par un minuteur `systemd --user` :

```text
# ~/atelier/qwen-switch/nginx/logrotate.conf ; lancé par : logrotate -s ~/.local/state/logrotate-qwen.state <ce fichier>
/home/charles-antoine/atelier/qwen-switch/nginx/acces-cartes.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
  copytruncate
}
```

## 6. Mesurer après

Référence d'avant la bascule (19 oct., 17 h → 20 oct., 00 h 40, msg 5698) : 1 222 requêtes, 0 jeton de réflexion ; une carte
génère ~22 jetons/s seule, ~10-11 par fente à deux ; 38-41 % du temps des fentes en calcul de prompt, dont 74 % de recalcul.

```bash
python3 scripts/usage_qwen.py "<heure de la bascule>"                  # par agent : cache, durée moyenne, sorties
python3 scripts/vitesse_cartes_qwen.py "<heure de la bascule>"          # par carte : génération seule / partagée, part du prompt
python3 scripts/pertes_cache_qwen.py "<heure de la bascule>" 10000      # attendu : changement de carte = 0
awk '{print $2, $3}' ~/atelier/qwen-switch/nginx/acces-cartes.log | sort | uniq -c   # port 8086 → 127.0.0.1:8081, 8087 → :8082
```
