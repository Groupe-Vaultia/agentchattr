/* G5 — Test de la sélection des fantômes (msg 3643, points 2 et 3).
   Exécuter : node tests/test_g5_fantomes.mjs */

const FANTOMES_VEH = [
    { nom: "Roue AV G",  bbox: { xMin: 40-101, xMax: 40+101, yMin: -300-101, yMax: -300+101, zMin: -130-355, zMax: -130+355 } },
    { nom: "Roue AV D",  bbox: { xMin: 40-101, xMax: 40+101, yMin: 700-101,  yMax: 700+101,  zMin: -130-355, zMax: -130+355 } },
    { nom: "Roue AR G",  bbox: { xMin: 1435-127, xMax: 1435+127, yMin: -300-127, yMax: -300+127, zMin: -130-355, zMax: -130+355 } },
    { nom: "Roue AR D",  bbox: { xMin: 1435-127, xMax: 1435+127, yMin: 700-127,   yMax: 700+127,   zMin: -130-355, zMax: -130+355 } },
    { nom: "Batterie (3× 48 V)", bbox: { xMin: 430, xMax: 680, yMin: 120, yMax: 280, zMin: 20, zMax: 190 } },
    { nom: "Moteur + boîte 2 gammes", bbox: { xMin: 1100, xMax: 1260, yMin: 40, yMax: 200, zMin: -20, zMax: 140 } },
    { nom: "Bras oscillant", bbox: { xMin: 1100, xMax: 1460, yMin: -55, yMax: 455, zMin: -155, zMax: -105 } },
    { nom: "Triangles avant", bbox: { xMin: -60, xMax: -10, yMin: -300, yMax: 340, zMin: -120, zMax: 65 } },
    { nom: "Selle", bbox: { xMin: 480, xMax: 1000, yMin: 50, yMax: 350, zMin: 316, zMax: 406 } },
    { nom: "Guidon", bbox: { xMin: 25, xMax: 55, yMin: -150, yMax: 530, zMin: 300, zMax: 620 } },
];
const BBOX_DEF = { xMin: 0, xMax: 100, yMin: -50, yMax: 50, zMin: 0, zMax: 100 };

// Même logique que static/atelier.js (renderVue3D)
function match(se_nom) {
    const nomSe = (se_nom || "").trim().toLowerCase();
    let match = FANTOMES_VEH.find(f => f.nom.toLowerCase() === nomSe);
    if (!match) {
        const motsSe = nomSe.split(/\s+/);
        const candidats = FANTOMES_VEH.filter(f => {
            const motsF = f.nom.toLowerCase().split(/\s+/);
            return motsSe.every(m => motsF.includes(m));
        });
        if (candidats.length === 1) match = candidats[0];
    }
    return match;
}

function testSlection(pieces, nomenclature) {
    // Fantômes par défaut
    const fantomes = FANTOMES_VEH.slice();
    if (nomenclature) {
        const seSansGlb = nomenclature.filter(se =>
            !(se.enfants || []).some(e => e.fichier && e.fichier.endsWith(".glb")));
        if (seSansGlb.length) {
            fantomes.length = 0;
            for (const se of seSansGlb) {
                const m = match(se.nom);
                fantomes.push(m ? { nom: se.nom, bbox: m.bbox } : { nom: se.nom, bbox: BBOX_DEF });
            }
        }
    }
    return fantomes;
}

let pass = 0, fail = 0;
function check(desc, actual, expected) {
    if (actual === expected) { pass++; }
    else { fail++; console.log(`FAIL: ${desc} → ${actual} (attendu ${expected})`); }
}

// --- Test 1 : sans nomenclature → 10 fantômes par défaut ---
const sans_nomenclature = testSlection([], null);
check("sans nomenclature = 10", sans_nomenclature.length, 10);

// --- Test 2 : Roue AV G ≠ Roue AV D (exact) ---
const nom_av_g = testSlection([], [
    { nom: "Roue AV G", enfants: [] },
    { nom: "Roue AV D", enfants: [] },
]);
const g = nom_av_g.find(f => f.nom === "Roue AV G");
const d = nom_av_g.find(f => f.nom === "Roue AV D");
check("Roue AV G existe", !!g, true);
check("Roue AV D existe", !!d, true);
check("G != D (yMin différents)", g.bbox.yMin !== d.bbox.yMin, true);

// --- Test 3 : cas ambigu → fallback ---
const ambigu = testSlection([], [{ nom: "Roue AV", enfants: [] }]);
check("ambigu = 1 fantôme", ambigu.length, 1);
check("ambigu → BBOX_DEF", ambigu[0].bbox === BBOX_DEF, true);

// --- Test 4 : match unique par mots ---
const unique = testSlection([], [{ nom: "Selle", enfants: [] }]);
check("Selle match unique", unique.length, 1);
check("Selle != BBOX_DEF", unique[0].bbox !== BBOX_DEF, true);

// --- Test 5 : GLB présent → pas de fantôme ---
const avec_glb = testSlection([], [
    { nom: "Selle", enfants: [{ fichier: "selle.glb" }] },
    { nom: "Guidon", enfants: [] },
]);
check("avec GLB = 1 fantôme (Guidon seulement)", avec_glb.length, 1);
check("fantôme restant = Guidon", avec_glb[0].nom, "Guidon");

console.log(`\nTests G5 fantômes : ${pass}/${pass+fail} pass`);
process.exit(fail ? 1 : 0);
