/* Visuels de la fiche de tâche : aucun jeton dans une URL produite (revue codex-1, msg 4852).
   Importe le module de production (static/visuels.js) — pas une copie.
   Exécuter : node tests/test_visuels.mjs */

import { visuels, visuelsHtml, creerChargeur } from "../static/visuels.js";

let pass = 0, fail = 0;
function check(desc, actual, expected) {
    if (actual === expected) { pass++; }
    else { fail++; console.log(`FAIL: ${desc} → ${JSON.stringify(actual)} (attendu ${JSON.stringify(expected)})`); }
}
const JETON = "jeton-secret-de-test";
const enTetes = () => ({"Accept": "application/json", "x-session-token": JETON});

// --- 1. Chemins : relatifs à la racine, jamais absolus ni « .. » ---
const msg = {
    text: "Rendu : `wt-claude5-t22/design/rendus/pistes_v13.png` ; [a](file:///home/x/atelier/cad-gemini/a.png) "
        + "https://ex.com/b.jpg ~/atelier/x/y.webp ../../etc/z.png /etc/passwd.png design/brief.md",
    attachments: [{url: "/uploads/abc.png", name: "photo.png"}, {url: "javascript:alert(1).png", name: "x"}],
};
const liste = visuels(msg);
check("pièce jointe /uploads/ gardée", liste[0].src, "/uploads/abc.png");
check("chemins cités", JSON.stringify(liste.slice(1).map(v => v.chemin)),
      JSON.stringify(["wt-claude5-t22/design/rendus/pistes_v13.png", "cad-gemini/a.png", "x/y.webp"]));
check("aucune URL javascript:", liste.some(v => String(v.src || "").startsWith("javascript")), false);
check("sans pièces jointes si pj:false", visuels(msg, {pj: false}).some(v => v.src), false);

// --- 2. HTML : la vignette de livrable naît sans src ni href, et sans jeton ---
const html = visuelsHtml(liste);
check("aucun « token » dans le HTML", /token/i.test(html), false);
check("vignette de livrable sans src", /<img class="vis-img" data-chemin="wt-claude5-t22[^>]*\ssrc=/.test(html), false);
check("pièce jointe en src direct", html.includes('src="/uploads/abc.png"'), true);
check("liste vide = rien", visuelsHtml([]), "");

// --- Faux DOM minimal : une vignette = un <img> dans un <a class="vis-l"> dans un <div class="vis"> ---
function vignette(chemin) {
    const cadre = {liens: 1, retire: false, querySelector: () => (cadre.liens ? {} : null), remove() { cadre.retire = true; }};
    const a = {href: undefined, retire: false, remove() { a.retire = true; cadre.liens--; }};
    const img = {dataset: {chemin}, isConnected: true, src: undefined,
                 closest: sel => (sel === ".vis-l" ? a : sel === ".vis" ? cadre : null)};
    return {img, a, cadre};
}
const racine = imgs => ({querySelectorAll: () => imgs});
function faux({ok = true, type = "image/png", attente = null} = {}) {
    const appels = [], revoques = [];
    let n = 0;
    const lire = async (url, opts) => {
        appels.push({url, opts});
        if (attente) await attente;
        return {ok, blob: async () => ({type})};
    };
    const url = {createObjectURL: () => `blob:http://127.0.0.1/${++n}`, revokeObjectURL: u => revoques.push(u)};
    return {appels, revoques, chargeur: creerChargeur({fetch: lire, headers: enTetes, url})};
}

// --- 3. Chargement : fetch avec l'en-tête, URL sans jeton, blob posé en src et href ---
{
    const {appels, revoques, chargeur} = faux();
    const v = vignette("wt-claude5-t22/design/rendus/pistes_v13.png");
    await chargeur.charger(racine([v.img]));
    check("un seul fetch", appels.length, 1);
    check("URL de fetch sans jeton", /token/i.test(appels[0].url), false);
    check("URL de fetch = route livrable", appels[0].url, "/api/v2/livrable?chemin=wt-claude5-t22%2Fdesign%2Frendus%2Fpistes_v13.png");
    check("jeton en en-tête", appels[0].opts.headers["x-session-token"], JETON);
    check("src = blob", v.img.src, "blob:http://127.0.0.1/1");
    check("href = même blob", v.a.href, "blob:http://127.0.0.1/1");
    check("src sans jeton", /token/i.test(v.img.src + v.a.href), false);
    // Même chemin, nouvelle vignette (rendu relu) : pas de nouveau fetch.
    const w = vignette("wt-claude5-t22/design/rendus/pistes_v13.png");
    await chargeur.charger(racine([w.img]));
    check("cache par chemin", appels.length, 1);
    check("cache : même blob", w.img.src, "blob:http://127.0.0.1/1");
    // Fermeture de la fiche : tout est révoqué, puis un nouveau chargement relit.
    await chargeur.liberer();
    check("blob révoqué à la fermeture", JSON.stringify(revoques), JSON.stringify(["blob:http://127.0.0.1/1"]));
    await chargeur.charger(racine([vignette("wt-claude5-t22/design/rendus/pistes_v13.png").img]));
    check("relu après fermeture", appels.length, 2);
}

// --- 4. Introuvable ou pas une image : la vignette et son cadre disparaissent ---
for (const [desc, opts] of [["404", {ok: false}], ["type texte", {type: "text/html"}]]) {
    const {chargeur} = faux(opts);
    const v = vignette("absent.png");
    await chargeur.charger(racine([v.img]));
    check(`${desc} : lien retiré`, v.a.retire, true);
    check(`${desc} : cadre retiré`, v.cadre.retire, true);
    check(`${desc} : aucun src`, v.img.src, undefined);
}

// --- 5. Fiche fermée pendant la lecture : le blob créé est révoqué aussitôt, rien n'est posé ---
{
    let lacher;
    const attente = new Promise(r => { lacher = r; });
    const {revoques, chargeur} = faux({attente});
    const v = vignette("lent.png");
    const enCours = chargeur.charger(racine([v.img]));
    const fin = chargeur.liberer();
    lacher();
    await enCours; await fin;
    check("course : blob révoqué", revoques.length, 1);
    check("course : aucun src posé", v.img.src, undefined);
}

console.log(`${pass} passés, ${fail} échoués`);
process.exit(fail ? 1 : 0);
