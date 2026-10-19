// Progression en direct sur le tableau de l'atelier (tache-22, msg 4925-4926, 2026-10-19).
// Charles : « la tableau de l'atelier n'est pas live que ça... Je ne vois pas vraiment les progressions ».
// A : mêmes règles que progression.py (cas communs dans progression_cas.json) ; B : ce que la carte affiche ;
// C : un message du flux met la carte à jour sur place, et la carte qui bouge brille un moment.
// Lancer : node tests/test_progression.mjs
import { readFileSync } from "node:fs";
import {
    estProgression, tacheDuMessage, extrait, appliquerMessage, silenceDe, etatCarte, marquerBougees,
} from "../static/progression.js";

let ok = 0, ko = 0;
function check(nom, obtenu, attendu) {
    const a = JSON.stringify(obtenu), b = JSON.stringify(attendu);
    if (a === b) { ok++; return; }
    ko++;
    console.log(`ÉCHEC ${nom}\n  obtenu  ${a}\n  attendu ${b}`);
}
const CAS = JSON.parse(readFileSync(new URL("./progression_cas.json", import.meta.url), "utf8"));

// --- A. Règles communes avec le serveur ---
for (const c of CAS.est_progression) check(`A progression : ${c.cas}`, estProgression(c.msg), c.attendu);
for (const c of CAS.tache_du_message) check(`A tâche du message : ${JSON.stringify(c.msg)}`, tacheDuMessage(c.msg), c.attendu);
for (const c of CAS.extrait) check(`A extrait : ${c.cas}`, extrait(c.texte), c.attendu);
{
    // Les messages appliqués un à un (comme le flux) donnent la même activité que le calcul du serveur.
    const a = CAS.activites;
    const taches = Object.keys(a.attendu).map(id => ({id: Number(id)}));
    for (const m of a.messages) appliquerMessage(taches, m, a.humains);
    for (const t of taches) {
        const {id, ts, par, extrait: ex, agent, agent_ts} = t.activite;
        check(`A activité de la tâche ${t.id}`, {id, ts, par, extrait: ex, agent, agent_ts}, a.attendu[String(t.id)]);
    }
    const coupe = extrait("é".repeat(200));
    check("A extrait : coupe en caractères, pas en unités UTF-16", Array.from(coupe).length, 160);
}

// --- B. Ce que la carte affiche ---
{
    const t = {id: 29, updated_at: 1000, responsable: "claude-2", au_travail: ["claude-2", "codex-1"],
               activite: {id: 9, ts: 5000, par: "claude-1", extrait: "Livraison reçue", agent: "claude-1", agent_ts: 5000}};
    const e = etatCarte(t, 5600, n => n === "codex-1");
    check("B heure = dernier message, pas updated_at (la carte disait « il y a 14 h »)", e.quand, 5000);
    check("B auteur et extrait", [e.par, e.extrait], ["claude-1", "Livraison reçue"]);
    check("B silence depuis le dernier message d'agent", e.silence, 600);
    check("B au travail", e.auTravail, ["claude-2", "codex-1"]);
    check("B écrit : un des agents au travail est occupé", e.ecrit, true);
    check("B personne d'occupé : n'écrit pas", etatCarte(t, 5600).ecrit, false);
    const vieille = etatCarte({id: 3, updated_at: 7000, activite: {id: 1, ts: 5000, par: "user", extrait: "x", agent: "", agent_ts: null}}, 8000);
    check("B un changement de la tâche plus récent que le message garde son heure", vieille.quand, 7000);
    check("B Charles seul a écrit : pas de silence calculé (repli sur la ronde)", vieille.silence, null);
    const nue = etatCarte({id: 4}, 8000);
    check("B tâche sans message ni date", [nue.quand, nue.par, nue.extrait, nue.silence, nue.auTravail, nue.ecrit], [null, "", "", null, [], false]);
    check("B silence jamais négatif (horloge du téléphone en retard)", silenceDe({activite: {agent_ts: 9000}}, 8000), 0);
}

// --- C. Le flux met la carte à jour sur place ---
{
    const t21 = {id: 21, activite: {id: 4298, ts: 100, par: "codex-1", extrait: "NO-GO v6", agent: "codex-1", agent_ts: 100}};
    const t29 = {id: 29};
    const taches = [t21, t29];
    const charles = appliquerMessage(taches, {id: 4874, sender: "user", type: "chat", channel: "tache-21", timestamp: 200, text: "@qwencode-1 Modélise"}, ["user"]);
    check("C le message de Charles touche sa tâche", charles && charles.id, 21);
    check("C … devient la dernière activité", [t21.activite.id, t21.activite.par, t21.activite.extrait], [4874, "user", "Modélise"]);
    check("C … sans rajeunir le dernier signe d'agent (t21 restait « rien depuis 2 h »)", [t21.activite.agent, t21.activite.agent_ts], ["codex-1", 100]);
    const agent = appliquerMessage(taches, {id: 4923, sender: "claude-2", type: "chat", channel: "tache-29", tache_id: 29, timestamp: 300, text: "Reçu"}, ["user"]);
    check("C première activité d'une tâche qui n'en avait pas", agent === t29 ? t29.activite : null,
          {agent: "claude-2", agent_ts: 300, id: 4923, ts: 300, par: "claude-2", extrait: "Reçu"});
    check("C message système : rien ne change", appliquerMessage(taches, {id: 1, sender: "system", type: "system", channel: "tache-29", timestamp: 400, text: "x"}, ["user"]), null);
    check("C rappel que le chef s'adresse : rien ne change", appliquerMessage(taches, {id: 2, sender: "claude-1", channel: "tache-29", timestamp: 400, text: "@claude-1 Point d'étape"}, ["user"]), null);
    check("C tâche absente de la page : rien ne change", appliquerMessage(taches, {id: 3, sender: "claude-3", channel: "tache-27", timestamp: 400, text: "x"}, ["user"]), null);
    check("C message sans heure : rien ne change", appliquerMessage(taches, {id: 5, sender: "claude-3", channel: "tache-29", text: "x"}, ["user"]), null);
    appliquerMessage(taches, {id: 4000, sender: "claude-2", channel: "tache-29", timestamp: 250, text: "plus ancien"}, ["user"]);
    check("C un message plus ancien arrivé en retard ne remplace pas le plus récent", t29.activite.id, 4923);

    // La carte qui bouge brille 2,4 s ; la première vue ne brille pas ; la surbrillance s'éteint à l'heure.
    const vu = new Map(), jusqua = new Map();
    marquerBougees(taches, vu, jusqua, 10_000);
    check("C première vue : rien ne brille", [...jusqua.keys()], []);
    appliquerMessage(taches, {id: 4930, sender: "claude-1", channel: "tache-29", timestamp: 500, text: "GO"}, ["user"]);
    marquerBougees(taches, vu, jusqua, 11_000);
    check("C nouveau message : la carte 29 brille jusqu'à 13,4 s", [...jusqua.entries()], [["29", 13_400]]);
    marquerBougees(taches, vu, jusqua, 12_000);
    check("C re-rendu sans nouveau message : la surbrillance continue", jusqua.get("29"), 13_400);
    marquerBougees(taches, vu, jusqua, 13_400);
    check("C après 2,4 s : éteinte", jusqua.size, 0);
}

// --- C. L'atelier branche bien le flux sur la carte (lecture du source) ---
{
    const src = readFileSync(new URL("../static/atelier.js", import.meta.url), "utf8");
    check("C atelier.js importe progression.js", /from '\.\/progression\.js\?v=\d+'/.test(src), true);
    check("C le flux applique le message à la carte", /appliquerMessage\(Object\.values\(state\.par\)/.test(src), true);
    check("C plus d'heure de carte prise de updated_at seul hors « Fait »", /ilya\(t\.updated_at\)\)\}<\/span>`;\n\s+return `<article/.test(src), false);
}

console.log(`${ok} passés, ${ko} échoués`);
process.exit(ko ? 1 : 0);
