"""Ronde du gestionnaire (SOCLE-SHOP.md S6). 12 octobre 2026.

v1 (12 oct. 2026, claude) : fonction pure. La ronde planifiee (schedules.py, toutes les 30 min) lit
GET /api/v2/ronde, puis agit : relancer ou reassigner une execution silencieuse, debloquer une tache, signaler a
Charles ce qui l'attend. « Rien a faire » se dit en une ligne. Seuls les projets actifs comptent : un projet en
veille, arrete ou termine n'a pas de ronde.
"""


def ronde(projets: dict, taches: list[dict], executions: list[dict]) -> dict:
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
    sortie["rien_a_faire"] = not any(sortie[k] for k in sortie)
    return sortie
