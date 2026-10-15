"""Ronde du gestionnaire (SOCLE-SHOP.md S6). 12 octobre 2026.

v1 (12 oct. 2026, claude) : fonction pure. La ronde planifiee (schedules.py, toutes les 30 min) lit
GET /api/v2/ronde, puis agit : relancer ou reassigner une execution silencieuse, debloquer une tache, signaler a
Charles ce qui l'attend. « Rien a faire » se dit en une ligne. Seuls les projets actifs comptent : un projet en
veille, arrete ou termine n'a pas de ronde.

v2 (13 oct. 2026, claude, SOCLE-SHOP v1.1 P1/P4) : la ronde devient le moteur. Elle rend aussi `jalons_en_attente`
(prepares, sans decision de Charles), `jalons_dus` (claude doit les preparer) et `prochaines` (taches a lancer sans
attendre Charles, avec la methode de leur etape). Un projet dont un jalon est du ou en attente n'a pas de
`prochaines` : la porte du jalon est fermee tant que Charles n'a pas dit go.

v3 (14 oct. 2026, claude, msg 2475-2477) : `agents_inactifs` dit quels agents en ligne n'ont rien fait depuis
SEUIL_INACTIF secondes, pour que claude leur donne un lot au lieu de les laisser attendre.

v4 (14 oct. 2026, grok, msg 2647) : `taches_muettes` signale chaque tache en_cours dont le dernier
message du canal tache-<id> a au moins une heure.
"""

SEUIL_INACTIF = 20 * 60  # 20 min sans activite = l'agent attend un lot

ETAPES = ("probleme", "etat_art", "concepts", "design_initial", "conception", "prototype", "essais", "industrialisation", "lancement")
# Jalon -> etapes dont toutes les taches doivent etre faites pour qu'il soit du.
_AVANT = {"J1": ETAPES[:4], "J2": ("essais",), "revue": ("industrialisation",)}
_JALONS_PAR_NIVEAU = {"leger": ("J2",), "moyen": ("J1", "J2"), "lourd": ("J1", "J2", "revue")}


def _jalons_dus(pid: str, niveau: str, taches: list[dict], jalons: list[dict]) -> tuple[list[str], list[dict]]:
    """Rend (jalons dus, recyclages a preparer). Apres un recycle (revue codex msg 2300), le jalon ne redevient du
    qu'une fois des taches de reprise creees apres la decision, a l'etape visee ou apres, et toutes faites. Sans
    tache de reprise, la ronde demande a claude de les creer (`recyclages`) au lieu de rebloquer le meme jalon."""
    dus, recyclages = [], []
    for nom in _JALONS_PAR_NIVEAU.get(niveau, _JALONS_PAR_NIVEAU["moyen"]):
        decides = sorted((j for j in jalons if j["jalon"] == nom and j.get("decision")),
                         key=lambda j: j.get("decision_date") or 0)
        if decides and decides[-1]["decision"] == "go":
            continue
        avant = [t for t in taches if t.get("etape") in _AVANT[nom]]
        if decides and decides[-1]["decision"] == "recycle":
            d = decides[-1]
            reprise = [t for t in taches if (t.get("created_at") or 0) > (d.get("decision_date") or 0)
                       and t.get("etape") in ETAPES[ETAPES.index(d["recycle_etape"]):]]
            if not reprise:
                recyclages.append({"projet_id": pid, "jalon": nom, "etape": d["recycle_etape"], "jalon_id": d["id"]})
                continue
            avant = reprise
        if nom == "J1" and not any(t.get("etape") == "design_initial" and t.get("etat") == "fait" for t in avant):
            continue  # PILOTE.md v1.1 : pas de J1 sans silhouette choisie par Charles (revue codex-2 msg 2963)
        if avant and all(t.get("etat") == "fait" for t in avant):
            dus.append(nom)
    return dus, recyclages


def _etape_courante(taches: list[dict]) -> str:
    ouvertes = {t.get("etape") for t in taches if t.get("etat") != "fait"}
    return next((e for e in ETAPES if e in ouvertes), "")


def ronde(projets: dict, taches: list[dict], executions: list[dict], jalons: list[dict] = (),
          methodes: dict | None = None) -> dict:
    """projets : {id: {nom, statut, …}} (forme v2). taches : celles de jobs.taches. executions : vues de
    ExecutionStore.lister (avec `etat`). Rend des listes courtes, prêtes a afficher."""
    actifs = {pid for pid, p in projets.items() if p.get("statut", "actif") == "actif"}
    t_actives = [t for t in taches if t.get("projet_id") in actifs]
    resume = lambda t: {"tache_id": t["id"], "projet_id": t["projet_id"], "titre": t.get("titre", ""),
                        "responsable": t.get("responsable", "")}
    sortie = {
        "silencieuses": [{"execution_id": e["id"], "tache_id": e["tache_id"], "projet_id": e["projet_id"],
                          "agent": e["agent"], "dernier_signe": e["dernier_signe"]}
                         for e in executions if e.get("etat") == "silencieux" and e.get("projet_id") in actifs],
        "attend_charles": [resume(t) for t in t_actives if t.get("etat") == "attend_charles"],
        "bloquees": [resume(t) for t in t_actives if t.get("etat") == "bloque"],
        "essais_incomplets": [resume(t) for t in t_actives if t.get("etape") == "essais"
                              and t.get("etat") != "fait"
                              and not all(str(t.get(c, "")).strip()
                                          for c in ("incertitude", "hypothese", "methode", "critere"))],
        "projets_sans_tache": sorted(pid for pid in actifs
                                     if not any(t.get("projet_id") == pid and t.get("etat") != "fait"
                                                for t in taches)),
    }
    methodes = methodes or {}
    occupes = {e["agent"] for e in executions if e.get("etat") in ("actif", "silencieux")}
    sortie["jalons_en_attente"] = [{"jalon_id": j["id"], "projet_id": j["projet_id"], "jalon": j["jalon"],
                                    "recommandation": j["recommandation"]}
                                   for j in jalons if j["projet_id"] in actifs and not j.get("decision")]
    sortie["jalons_dus"], sortie["recyclages"], sortie["prochaines"] = [], [], []
    for pid in sorted(actifs):
        tp = [t for t in taches if t.get("projet_id") == pid]
        jp = [j for j in jalons if j["projet_id"] == pid]
        if any(not j.get("decision") for j in jp):
            continue  # en attente de Charles : ni jalon a preparer, ni tache a lancer
        dus, recy = _jalons_dus(pid, projets[pid].get("niveau") or "moyen", tp, jp)
        if recy:
            sortie["recyclages"] += recy
            continue
        if dus:
            sortie["jalons_dus"].append({"projet_id": pid, "jalon": dus[0]})
            continue
        etape = _etape_courante(tp)
        sortie["prochaines"] += [{"projet_id": pid, "tache_id": t["id"], "titre": t.get("titre", ""), "etape": etape,
                                  "responsable": t.get("responsable", ""), "methode_etape": methodes.get(etape, "")}
                                 for t in tp if t.get("etape") == etape and t.get("etat") == "a_faire"
                                 and t.get("responsable") not in occupes]
    sortie["rien_a_faire"] = not any(sortie[k] for k in sortie)
    return sortie


def taches_muettes(taches: list[dict], derniers_messages: dict, maintenant: float,
                   seuil: float = 3600) -> list[dict]:
    """Taches `en_cours` dont le dernier message de `tache-<id>` date d'au moins `seuil` secondes.

    `derniers_messages` associe le nom du canal a l'epoch du dernier message. Sans message, la tache
    n'a pas de date : elle n'est pas signalee.
    """
    out = []
    for tache in taches:
        if tache.get("etat") != "en_cours":
            continue
        try:
            tid = int(tache["id"])
        except (KeyError, TypeError, ValueError):
            continue
        ts = derniers_messages.get(f"tache-{tid}")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            continue
        silence = float(maintenant) - float(ts)
        if silence >= seuil:
            out.append({
                "tache_id": tid,
                "projet_id": tache.get("projet_id", ""),
                "titre": tache.get("titre", ""),
                "responsable": tache.get("responsable", ""),
                "silence_s": int(silence),
            })
    out.sort(key=lambda ligne: ligne["tache_id"])
    return out


def agents_inactifs(en_ligne: set[str], derniere_activite: dict[str, float], maintenant: float, demarrage: float,
                    exclus: tuple[str, ...] = ("claude",), seuil: float = SEUIL_INACTIF) -> list[dict]:
    """Agents en ligne sans activite depuis `seuil` s. Sans activite connue, on compte depuis le demarrage du
    serveur (l'historique d'activite ne survit pas a une relance). `exclus` : le gestionnaire lui-meme."""
    out = []
    for nom in sorted(en_ligne):
        if nom in exclus:
            continue
        depuis = max(derniere_activite.get(nom, 0), demarrage)
        if maintenant - depuis >= seuil:
            out.append({"agent": nom, "inactif_min": int((maintenant - depuis) // 60)})
    return out
