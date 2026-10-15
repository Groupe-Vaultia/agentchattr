/* G5 — Test de la sélection des fantômes.
   Importe le module de production (static/fantomes.js) — pas une copie.
   Exécuter : node tests/test_g5_fantomes.mjs */

import { choisirFantomes, FANTOMES_VEH, BBOX_DEF } from "../static/fantomes.js";

let pass = 0, fail = 0;
function check(desc, actual, expected) {
    if (actual === expected) { pass++; }
    else { fail++; console.log(`FAIL: ${desc} → ${actual} (attendu ${expected})`); }
}

// --- Test 1 : sans nomenclature → 10 fantômes par défaut ---
const sans = choisirFantomes(null);
check("sans nomenclature = 10", sans.length, 10);
check("sans nomenclature = FANTOMES_VEH", sans.length, FANTOMES_VEH.length);

// --- Test 2 : nomenclature vide → 10 fantômes ---
const vide = choisirFantomes([]);
check("nomenclature vide = 10", vide.length, 10);

// --- Test 3 : Roue AV G ≠ Roue AV D (exact) ---
const av = choisirFantomes([
    { nom: "Roue AV G", enfants: [] },
    { nom: "Roue AV D", enfants: [] },
]);
const g = av.find(f => f.nom === "Roue AV G");
const d = av.find(f => f.nom === "Roue AV D");
check("Roue AV G existe", !!g, true);
check("Roue AV D existe", !!d, true);
check("G != D (yMin différents)", g.bbox.yMin !== d.bbox.yMin, true);
check("G bbox = FANTOMES_VEH[0]", g.bbox === FANTOMES_VEH[0].bbox, true);
check("D bbox = FANTOMES_VEH[1]", d.bbox === FANTOMES_VEH[1].bbox, true);

// --- Test 4 : cas ambigu → fallback BBOX_DEF ---
const ambigu = choisirFantomes([{ nom: "Roue AV", enfants: [] }]);
check("ambigu = 1 fantôme", ambigu.length, 1);
check("ambigu → BBOX_DEF", ambigu[0].bbox === BBOX_DEF, true);

// --- Test 5 : match unique par mots ---
const unique = choisirFantomes([{ nom: "Selle", enfants: [] }]);
check("Selle = 1 fantôme", unique.length, 1);
check("Selle != BBOX_DEF", unique[0].bbox !== BBOX_DEF, true);

// --- Test 6 : GLB présent → pas de fantôme pour ce sous-ensemble ---
const avec_glb = choisirFantomes([
    { nom: "Selle", enfants: [{ fichier: "selle.glb" }] },
    { nom: "Guidon", enfants: [] },
]);
check("avec GLB = 1 fantôme", avec_glb.length, 1);
check("fantôme restant = Guidon", avec_glb[0].nom, "Guidon");

// --- Test 7 : tous les sous-ensembles ont un GLB → 0 fantôme ---
const tous_glb = choisirFantomes([
    { nom: "Roue AV G", enfants: [{ fichier: "roue.glb" }] },
    { nom: "Selle", enfants: [{ fichier: "selle.glb" }] },
]);
check("tous GLB = 0 fantôme", tous_glb.length, 0);

console.log(`\nTests G5 fantômes : ${pass}/${pass+fail} pass`);
process.exit(fail ? 1 : 0);
