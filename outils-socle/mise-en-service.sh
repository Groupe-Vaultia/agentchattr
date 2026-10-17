#!/usr/bin/env bash
# outils-socle/mise-en-service.sh — met en service, dans le clone principal, ce
# qui vient d'être fusionné sur GitHub, SANS redémarrer la salle quand ce n'est
# pas nécessaire (un redémarrage coupe tous les agents).
#
# Le serveur sert static/ en direct et relit index.html, atelier.html et
# docs/PILOTE.md à chaque requête : un changement qui ne touche que static/,
# docs/, tests/ ou des *.md est en service dès le fast-forward. Tout le reste
# (Python, config…) demande un redémarrage : le script ne l'exécute que si on
# passe --redemarrer, et toujours par la séquence sûre (gardien figé, serveur
# tué par PID, relance, attente de la salle ET des deux transports MCP des
# agents, gardien repris).
#
# v1.1 (2026-10-16, claude-1) : revue codex-2 (msg 4330). « En service » exige
# aussi MCP HTTP (:8200) et MCP SSE (:8201) : run.py les démarre dans des fils à
# part, ils peuvent tomber alors que :8300/ répond 200, et le gardien ne sonde
# que :8300 (les agents resteraient coupés sans reprise). Le journal du serveur
# est remis en 0600 avant chaque ajout (umask ne corrige pas un fichier existant).
#
# Usage, depuis le clone principal (le dossier courant fait foi) :
#   outils-socle/mise-en-service.sh [--essai] [--redemarrer]
#     --essai       tout vérifier et tout afficher sans rien modifier : git fetch
#                   seulement, ni merge ni redémarrage
#     --redemarrer  exécuter la séquence de redémarrage si elle est requise
# Codes de sortie : 0 fait ou rien à faire ; 1 arrêt (blocage, erreur) ; 2 usage.
#
# Linux seulement (/proc pour le dossier du serveur, ps -o etimes).
set -euo pipefail

PORT=8300
# Ports MCP lus de config.toml ([mcp] http_port / sse_port), 8200/8201 sinon.
port_mcp() {
  local v
  v=$(awk -F'=' -v cle="$1" '/^\[/{sec=$0} sec=="[mcp]" && $1 ~ "^"cle"[ \t]*$" {gsub(/[ \t"]/,"",$2); print $2; exit}' config.toml 2>/dev/null || true)
  printf '%s' "${v:-$2}"
}
# Ancré en fin de ligne : n'attrape ni l'aperçu (« run.py --port 8320 … ») ni
# cette commande. Jamais « pkill -f » avec un motif contenant run.py : la
# commande qui le lance le contient aussi et se tuerait elle-même.
MOTIF_SERVEUR='\.venv/bin/python run\.py$'
# « bash …/vaultia-watchdog.sh » seulement : un « less vaultia-watchdog.sh » ou
# un éditeur ouvert sur le fichier ne doit pas être figé.
MOTIF_GARDIEN='bash [^ ]*vaultia-watchdog\.sh$'

ESSAI=0
REDEMARRER=0
GARDIEN=()      # PID du gardien figés ; le piège EXIT les reprend toujours
ARRIVENT=()     # fichiers changés entre HEAD et origin/main
EN_ATTENTE=()   # déjà dans le clone, mais plus récents que le serveur en marche

dire() { printf '%s\n' "$*"; }
arret() { printf 'ARRÊT : %s\n' "$*" >&2; exit 1; }
court() { git rev-parse --short "$1"; }

usage() {
  cat <<'FIN'
Usage : outils-socle/mise-en-service.sh [--essai] [--redemarrer]
  À lancer dans le clone principal après la fusion d'une PR sur GitHub.
  --essai       vérifie et affiche tout, ne modifie rien (ni merge ni redémarrage)
  --redemarrer  exécute la séquence de redémarrage sûre si elle est requise
FIN
}

# Sans redémarrage : servi en direct (static/), relu à chaque requête
# (docs/PILOTE.md) ou jamais chargé par le serveur (docs/, tests/, *.md).
sans_redemarrage() {
  case "$1" in
    static/*|docs/*|tests/*|*.md) return 0 ;;
    *) return 1 ;;
  esac
}

# PID des serveurs de CE clone : le motif ne suffit pas (un autre clone peut
# tourner avec la même ligne de commande), le dossier courant du processus doit
# être la racine du clone.
pids_serveur() {
  local p
  for p in $(pgrep -f "$MOTIF_SERVEUR" || true); do
    if [ "$(readlink "/proc/$p/cwd" 2>/dev/null || true)" = "$RACINE" ]; then
      echo "$p"
    fi
  done
}

# Commit sur lequel était HEAD quand le serveur $1 a démarré (d'après le reflog) :
# c'est le code Python qu'il a chargé. Vide si le reflog ne remonte pas si loin.
commit_en_service() {
  local age debut
  age=$(ps -o etimes= -p "$1" | tr -d ' ')
  debut=$(( $(date +%s) - age ))
  git log -g --date=unix --format='%H %gd' HEAD \
    | awk -v t="$debut" '{ s = $2; gsub(/^HEAD@\{|\}$/, "", s); if (s + 0 <= t) { print $1; exit } }'
}

echappe_ere() { printf '%s' "$1" | sed 's/[][\.*^$(){}+?|/]/\\&/g'; }

# (6) Un static/*.js|css changé dont le ?v= qui le référence n'a pas bougé :
# le navigateur garderait l'ancien en cache.
verifier_versions() {
  local f rel motif r v_ancien v_nouveau trouve
  for f in "${ARRIVENT[@]}"; do
    case "$f" in static/*.js|static/*.css) ;; *) continue ;; esac
    git cat-file -e "$NOUVEAU:$f" 2>/dev/null || continue   # supprimé : rien à recharger
    rel=${f#static/}
    motif="(/static/|\./)$(echappe_ere "$rel")\?v=[^\"'&) >]*"
    trouve=0
    for r in $(git ls-tree --name-only "$NOUVEAU" static/ | grep -E '\.(html|js)$' || true); do
      v_nouveau=$(git show "$NOUVEAU:$r" | grep -oE "$motif" | sed 's/.*?//' | sort -u | tr '\n' ' ' || true)
      [ -n "$v_nouveau" ] || continue
      trouve=1
      v_ancien=$(git show "$ANCIEN:$r" 2>/dev/null | grep -oE "$motif" | sed 's/.*?//' | sort -u | tr '\n' ' ' || true)
      if [ "$v_nouveau" = "$v_ancien" ]; then
        dire "AVERTISSEMENT ?v= : $f a changé mais $r le référence toujours en ?${v_nouveau% } :"
        dire "  le cache du navigateur garderait l'ancien ; incrémenter ce ?v= dans $r (nouvelle PR)."
      fi
    done
    if [ "$trouve" = 0 ]; then
      dire "NOTE ?v= : $f a changé et aucun static/*.html ni static/*.js ne le référence avec ?v= :"
      dire "  s'il est chargé sans version (import ES), le navigateur peut garder l'ancien."
    fi
  done
}

afficher_sequence() {
  local pid=${1:-<PID>}
  cat <<FIN
Séquence sûre (dans $RACINE) :
  1. W=\$(pgrep -f '$MOTIF_GARDIEN' || true); [ -n "\$W" ] && kill -STOP \$W
     puis attendre que le gardien n'ait plus de curl en cours : pgrep -P \$W -x curl
  2. kill $pid    # serveur de ce clone : pgrep -f '$MOTIF_SERVEUR', dossier = ce clone
     jamais « pkill -f » avec run.py : la commande se tuerait elle-même
  3. setsid nohup .venv/bin/python run.py >> data/server.log 2>&1 < /dev/null &
  4. attendre jusqu'à 60 s que les trois répondent :
       salle     curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/               → 200
       MCP HTTP  curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT_MCP_HTTP/mcp       → un code HTTP (406 attendu)
       MCP SSE   curl -s -o /dev/null -w '%{http_code}' -m 2 http://127.0.0.1:$PORT_MCP_SSE/sse   → 200 (flux ouvert)
  5. [ -n "\$W" ] && kill -CONT \$W
FIN
}

reprendre_gardien() {
  if [ "${#GARDIEN[@]}" -gt 0 ]; then
    kill -CONT "${GARDIEN[@]}" 2>/dev/null || true
    dire "Gardien repris (PID ${GARDIEN[*]})."
    GARDIEN=()
  fi
}

executer_redemarrage() {
  local pid enfants code fin w
  local -a pids
  [ -x .venv/bin/python ] && [ -f run.py ] || arret "pas de .venv/bin/python ni de run.py dans $RACINE"
  if pgrep -f 'vaultia-start\.sh' >/dev/null; then
    arret "vaultia-start.sh tourne (redémarrage complet en cours) : ne rien toucher"
  fi
  # (b, d'abord) le serveur à couper, avant de figer quoi que ce soit
  mapfile -t pids < <(pids_serveur)
  [ "${#pids[@]}" -eq 1 ] || arret "serveur de ce clone introuvable ou multiple (${pids[*]:-aucun}) : redémarrer à la main"
  pid=${pids[0]}

  # (a) figer le gardien : sinon il voit le serveur injoignable et relance
  # vaultia-start.sh, qui tue tous les agents.
  mapfile -t GARDIEN < <(pgrep -f "$MOTIF_GARDIEN" || true)
  if [ "${#GARDIEN[@]}" -gt 0 ]; then
    trap reprendre_gardien EXIT
    trap 'exit 130' INT TERM HUP     # Ctrl-C ou kill : passer par EXIT, donc reprendre
    kill -STOP "${GARDIEN[@]}"
    dire "Gardien figé (PID ${GARDIEN[*]})."
    # Un curl du gardien encore en vol échouerait pendant la coupure et, au
    # réveil, déclencherait la relance complète : on le laisse finir (≤ 5 s).
    fin=$((SECONDS + 10))
    while :; do
      enfants=$(for w in "${GARDIEN[@]}"; do pgrep -P "$w" -x curl || true; done)
      [ -z "$enfants" ] && break
      [ "$SECONDS" -lt "$fin" ] || arret "le gardien attend encore le serveur (curl $enfants) : réessayer"
      sleep 0.2
    done
  else
    dire "Aucun gardien (vaultia-watchdog.sh) en marche."
  fi

  # (b) couper le serveur PAR PID
  dire "Arrêt du serveur PID $pid…"
  kill "$pid" || arret "kill $pid a échoué"
  fin=$((SECONDS + 15))
  while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$fin" ]; do sleep 0.5; done
  if kill -0 "$pid" 2>/dev/null; then
    dire "Toujours vivant après 15 s : kill -KILL $pid"
    kill -KILL "$pid" || true
    sleep 1
  fi

  # (c) relancer ; le journal affiche le jeton de session : fichier privé
  (umask 077; : >> data/server.log)
  chmod 600 data/server.log
  setsid nohup .venv/bin/python run.py >> data/server.log 2>&1 < /dev/null &
  dire "Serveur relancé, attente de la salle (:$PORT) et des transports MCP (:$PORT_MCP_HTTP, :$PORT_MCP_SSE), 60 s max…"

  # (d) attendre que la salle ET les deux transports MCP des agents répondent
  local code=000 http=000 sse=000
  fin=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$fin" ]; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT/" || true)
    http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT_MCP_HTTP/mcp" || true)
    # Le flux SSE reste ouvert : curl s'arrête au délai (code 28) mais a déjà reçu son 200.
    sse=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT_MCP_SSE/sse" || true)
    [ "$code" = 200 ] && [ "${http:-000}" != 000 ] && [ "$sse" = 200 ] && break
    sleep 1
  done

  # (e) reprendre le gardien, quoi qu'il arrive
  reprendre_gardien
  trap - EXIT INT TERM HUP
  [ "$code" = 200 ] || arret "la salle ne répond pas 200 en 60 s (dernier code $code) : voir data/server.log ; le gardien, repris, relancera la salle complète"
  { [ "${http:-000}" != 000 ] && [ "$sse" = 200 ]; } || arret "la salle répond, mais pas les transports MCP des agents (HTTP :$PORT_MCP_HTTP → $http, SSE :$PORT_MCP_SSE → $sse) : les agents restent coupés et le gardien, qui ne sonde que :$PORT, ne relancera pas. Voir data/server.log, puis relancer à la main (vaultia-start.sh)"
  dire "En service : serveur PID $(pids_serveur | tr '\n' ' ')· salle 200 · MCP HTTP $http · MCP SSE $sse."
}

principal() {
  local opt f l pid base
  local -a locaux bloques a_redemarrer pids
  for opt in "$@"; do
    case "$opt" in
      --essai) ESSAI=1 ;;
      --redemarrer) REDEMARRER=1 ;;
      -h|--aide) usage; return 0 ;;
      *) usage >&2; exit 2 ;;
    esac
  done

  RACINE=$(git rev-parse --show-toplevel 2>/dev/null) || arret "pas dans un dépôt git"
  cd "$RACINE"
  RACINE=$(pwd -P)
  PORT_MCP_HTTP=$(port_mcp http_port 8200)
  PORT_MCP_SSE=$(port_mcp sse_port 8201)
  if [ "$ESSAI" = 1 ]; then
    dire "== Mise en service : $RACINE   [ESSAI : ni merge ni redémarrage]"
  else
    dire "== Mise en service : $RACINE"
  fi
  [ "$(git symbolic-ref -q --short HEAD || true)" = main ] || arret "le clone n'est pas sur la branche main"

  # (1) ce qui est fusionné sur GitHub
  git fetch --quiet origin || arret "git fetch origin a échoué"
  ANCIEN=$(git rev-parse HEAD)
  NOUVEAU=$(git rev-parse origin/main)
  git merge-base --is-ancestor "$ANCIEN" "$NOUVEAU" \
    || arret "main a des commits absents d'origin/main : pas de fast-forward possible, à régler à la main"

  # (2) les fichiers qui changent
  mapfile -d '' -t ARRIVENT < <(git diff --name-only --no-renames -z "$ANCIEN" "$NOUVEAU")
  if [ "${#ARRIVENT[@]}" -eq 0 ]; then
    dire "Déjà à jour : HEAD = origin/main ($(court "$ANCIEN"))."
  else
    dire "Arrivent avec origin/main ($(court "$ANCIEN")..$(court "$NOUVEAU")), ${#ARRIVENT[@]} fichier(s) :"
    git -c core.quotepath=off diff --name-status --no-renames "$ANCIEN" "$NOUVEAU" | sed 's/^/  /'
  fi

  # (3) arrêt net si un de ces fichiers a des modifications locales (suivies ou
  # non suivies) : la fusion les écraserait ou échouerait à moitié.
  mapfile -d '' -t locaux < <(git diff --name-only --no-renames -z HEAD; git ls-files -z --others --exclude-standard)
  bloques=()
  for f in "${ARRIVENT[@]}"; do
    for l in "${locaux[@]}"; do
      if [ "$f" = "$l" ]; then bloques+=("$f"); fi
    done
  done
  if [ "${#bloques[@]}" -gt 0 ]; then
    printf 'ARRÊT : modifications locales non commitées sur des fichiers que la fusion change :\n' >&2
    printf '  %s\n' "${bloques[@]}" >&2
    printf "Rien n'a été fusionné ni redémarré. Les commiter, les mettre de côté ou les abandonner d'abord.\n" >&2
    exit 1
  fi

  # (4) fast-forward seulement, sur exactement le commit analysé
  if [ "${#ARRIVENT[@]}" -gt 0 ]; then
    if [ "$ESSAI" = 1 ]; then
      dire "ESSAI : git merge --ff-only origin/main ($(court "$NOUVEAU")) non exécuté."
    else
      git merge --ff-only --quiet "$NOUVEAU" || arret "git merge --ff-only a échoué"
      dire "Fusionné : HEAD = $(court "$NOUVEAU")."
    fi
  fi

  # (5) redémarrage requis ? Ce qui arrive, plus ce qui est déjà dans le clone
  # mais plus récent que le serveur en marche (fusion faite sans redémarrer,
  # « git pull » à la main…), d'après le reflog au démarrage du serveur.
  a_redemarrer=()
  for f in "${ARRIVENT[@]}"; do
    sans_redemarrage "$f" || a_redemarrer+=("$f")
  done
  mapfile -t pids < <(pids_serveur)
  pid=${pids[0]:-}
  if [ "${#pids[@]}" -eq 1 ]; then
    base=$(commit_en_service "$pid" || true)
    if [ -z "$base" ]; then
      dire "NOTE : version du serveur PID $pid inconnue (reflog trop court) ; seule la fusion est jugée."
    elif [ "$base" != "$ANCIEN" ]; then
      mapfile -d '' -t EN_ATTENTE < <(git diff --name-only --no-renames -z "$base" "$ANCIEN")
      for f in "${EN_ATTENTE[@]}"; do
        sans_redemarrage "$f" || a_redemarrer+=("[déjà dans le clone] $f")
      done
      dire "Le serveur PID $pid a démarré sur $(court "$base") ; HEAD était depuis passé à $(court "$ANCIEN")."
    fi
  elif [ "${#pids[@]}" -eq 0 ]; then
    dire "NOTE : aucun serveur de ce clone en marche."
  else
    dire "NOTE : plusieurs serveurs dans ce clone (${pids[*]}) : à régler à la main."
  fi

  if [ "${#a_redemarrer[@]}" -eq 0 ]; then
    dire "En service, aucun redémarrage."
  else
    dire "Redémarrage requis : hors static/, docs/, tests/ et *.md :"
    printf '  %s\n' "${a_redemarrer[@]}"
  fi

  # (6) avant tout redémarrage, pour qu'on le voie même si celui-ci échoue
  verifier_versions

  if [ "${#a_redemarrer[@]}" -gt 0 ]; then
    if [ "$REDEMARRER" = 1 ] && [ "$ESSAI" = 0 ]; then
      executer_redemarrage
    else
      afficher_sequence "$pid"
      if [ "$ESSAI" = 1 ]; then
        dire "ESSAI : séquence non exécutée."
      else
        dire "NON exécutée : relancer ce script avec --redemarrer pour l'exécuter."
      fi
    fi
  fi
}

# Tout le corps est dans des fonctions, lues en entier avant l'exécution : le
# merge peut remplacer ce fichier même pendant qu'il tourne.
principal "$@"
exit $?
