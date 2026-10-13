# Fiches de lot du socle de la Shop — v0.2

v0.2 (13 oct. 2026, 0 h, claude) : toutes les routes « à venir » existent (S2 `2a7ba6e`, S3, S4 `c80952c`, historique
`305c9da`, S5 `0b3174e`, S6 `31932e3`). S5 a été réassigné à claude, parce que le lanceur de gemini a planté (msg 2118).
Routes ajoutées pour l'interface : `GET /api/v2/messages?projet_id=&tache_id=`, `POST /api/v2/projects/{id}/livrables`
`{chemin, tache_id}`, `GET /api/v2/projects/{id}/revisions/{numero}/verifier`, `GET /api/v2/ronde`. Approuver une
révision exige `approuvee_par: "user"` (403 sinon). `GET /api/v2/taches` rend `{taches, etape, etapes}`.

v0.1 (12 oct. 2026, 23 h 30, claude) : première version. Charles veut tout réalisé pour 7 h (msg 2108). Les lots
partent maintenant, sur des branches **locales** issues de `claude/socle-shop` (`46f48ab`, S1 + spec v0.8), sans
attendre la fusion de S1. Rien n'est poussé ni fusionné sans le oui de Charles, branche par branche (R2).

## Règles communes

- **Un fichier, un agent (R7).** Vous n'écrivez que les fichiers de votre fiche. `app.py` (les routes) est à claude :
  claude branche vos modules après la revue de codex.
- Modules **purs et isolés** : pas d'import de `app`, `store`, `agents` ni des wrappers. Python 3.14, la bibliothèque
  standard seulement.
- Stockage : un fichier JSON passé au constructeur. Écriture atomique (fichier temporaire, puis `os.replace`), avec un
  `threading.Lock`. Fichier absent = vide. Fichier illisible = `ValueError` au chargement, jamais d'effacement silencieux.
- Les heures sont des `float` (`time.time()`). Les identifiants sont des `str`.
- Aucun secret, ni journal brut ni scratchpad dans une donnée (R3).
- Livraison : un commit local dans votre worktree, puis un message dans #developpement-de-pro avec la commande de
  vérification et sa sortie (R6). Codex écrit les tests (`tests/test_socle_*.py`). Vous pouvez ajouter un auto-essai
  dans `if __name__ == "__main__":`.

| Agent | Worktree | Branche | Fichiers |
|---|---|---|---|
| gemini | `~/atelier/wt-gemini-socle` | `gemini/socle-revisions` | `revisions.py` |
| grok | `~/atelier/wt-grok-socle` | `grok/socle-historique` | `historique.py` |
| qwencode | `~/atelier/wt-qwen-socle` | `qwen/socle-atelier-ui` | `static/atelier.html`, `static/atelier.js`, `static/atelier.css` |
| codex | son worktree | `codex/socle-tests` | `tests/test_socle_s2.py` … `test_socle_ui_contract.py` |
| claude | `~/atelier/wt-claude-socle` | `claude/socle-shop` | `jobs.py`, `executions.py`, routes de `app.py`, S4, S6 |

## S5 : `revisions.py` (gemini)

```python
class RevisionStore:
    def __init__(self, path: str, racine: str): ...
    # racine = dossier sous lequel tous les livrables vivent. Un chemin absolu, ou qui sort de la racine
    # (« .. », lien symbolique vers l'extérieur une fois résolu) → ValueError.

    def ajouter_livrable(self, projet_id: str, tache_id: str, chemin: str) -> dict:
        # Lit les octets du fichier À CET INSTANT, calcule le sha256.
        # Rend {"id", "projet_id", "tache_id", "chemin", "empreinte", "version", "heure"}.
        # Même (projet_id, chemin) déjà connu : même empreinte → rend l'existant, inchangé ;
        # empreinte différente → version + 1 (l'ancienne reste dans l'historique du livrable).
        # Fichier absent → FileNotFoundError.

    def livrables(self, projet_id: str) -> list[dict]:
        # La dernière version de chaque chemin du projet, triée par chemin.

    def approuver(self, projet_id: str, approuvee_par: str) -> dict:
        # RECALCULE le sha256 de chaque livrable (dernière version) au moment de l'appel, et fige ces empreintes.
        # Si un fichier a changé depuis ajouter_livrable : on enregistre une nouvelle version, puis on fige
        # celle-ci (on fige ce qui est sur le disque, pas ce qui était connu).
        # Rend {"projet_id", "numero": "P01", "livrables": [{"chemin", "empreinte", "version"}],
        #       "approuvee_par", "heure"}. Le numéro est P01, P02… par projet.
        # Aucun livrable → ValueError. Une révision figée n'est jamais modifiée.

    def revisions(self, projet_id: str) -> list[dict]:
        # Toutes les révisions du projet, de P01 à la dernière.

    def verifier(self, projet_id: str, numero: str) -> list[dict]:
        # [{"chemin", "empreinte_figee", "empreinte_actuelle" (None si absent), "intact": bool}].
        # Numéro inconnu → KeyError.
```

Critère de codex (msg 2107) : « Approuver » hache les octets présents à cet instant, et une modification du fichier
crée une nouvelle révision au prochain « Approuver » sans changer P01.

## Historique : `historique.py` (grok)

Une lecture seule, **sans stockage** : une fonction pure qui fusionne ce que les autres modules rendent.

```python
def historique(projet_id: str, *, messages=(), executions=(), revisions=(), jalons=(), decisions=(),
               limite: int = 200) -> list[dict]:
    # Ne garde que les entrées dont "projet_id" == projet_id (une entrée sans projet_id est ignorée).
    # Rend [{"heure": float, "type": "message"|"execution"|"revision"|"jalon"|"decision",
    #        "ref": str, "acteur": str, "resume": str}], du plus récent au plus ancien, tronqué à `limite`.
    # resume : 200 caractères au plus, une seule ligne (sauts de ligne → espaces), suivi de « … » si coupé.
    # Formes reçues :
    #   message   {"id", "projet_id", "sender", "text", "timestamp"}
    #   execution {"id", "projet_id", "agent", "role", "consigne", "debut", "fin", "issue"} → heure = fin or debut
    #   revision  {"projet_id", "numero", "approuvee_par", "heure", "livrables"} → resume « P01 approuvée, 3 livrables »
    #   jalon     {"id", "projet_id", "jalon", "decision", "date"}  (decision vide = en attente)
    #   decision  {"id", "projet_id", "acteur", "quoi", "heure"}    (mise en veille, tâche ajoutée…)
    # Un champ manquant ou mal typé dans une entrée : l'entrée est ignorée, jamais d'exception.

def par_jour(entrees: list[dict]) -> list[tuple[str, list[dict]]]:
    # Regroupe par date locale "AAAA-MM-JJ", jours du plus récent au plus ancien, ordre interne conservé.
```

## Interface : `static/atelier.*` (qwencode)

D'après la maquette `~/atelier/maquettes/atelier-rd-v0.6.html`, avec les 8 étapes de pilote-rd (spec v0.7). La page
est servie à `/static/atelier.html`. Elle ne lit que les routes ci-dessous. Celles marquées « à venir » existent dès que
claude a branché le lot : d'ici là, l'interface affiche un état vide propre, sans erreur.

| Route | Rend |
|---|---|
| `GET /api/projects` | `{"projets" (v1 par nom), "actif", "v2": {"projets": {id: {nom, statut, memoire, channels, …}}, "defaut"}}` : utiliser **`v2`** |
| `POST /api/projects` `{name, memory}` | crée |
| `POST /api/v2/projects/{id}/status` `{status}` | `actif` · `veille` · `termine` · `arrete` |
| `POST /api/v2/projects/{id}/memory` `{memory}` | mémoire |
| `GET /api/v2/taches?projet_id=` | `[{id, projet_id, titre, etape, etat, responsable, equipe:[{agent, role}], critere, preuve}]` |
| `GET /api/v2/executions?projet_id=` | `[{id, tache_id, projet_id, agent, role, etat: actif·silencieux·fini, debut, dernier_signe, fin, issue}]` |
| `GET /api/v2/projects/{id}/historique` | sortie de `historique.par_jour`, en JSON : `[[jour, [entrées]]]` |
| `GET /api/v2/projects/{id}/revisions` | `{"livrables": [...], "revisions": [...]}` |
| `POST /api/v2/projects/{id}/revisions` `{approuvee_par}` | la révision créée |

Les étapes, dans l'ordre : `probleme, etat_art, concepts, conception, prototype, essais, industrialisation, lancement`.
L'étape du projet = la première étape qui contient une tâche dont `etat != "fait"`, affichée « Étape 4 sur 8 : Conception ».
Projet en veille : grisé, bouton « Réactiver », pas de badge « silencieux » (ta proposition du msg 2048, retenue).
