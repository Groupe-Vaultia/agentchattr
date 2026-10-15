/* G5 — Smoke test : chaque symbole importé par atelier.js existe dans son module.
   Exécuter : node tests/test_g5_imports.mjs */

import { choisirFantomes, BBOX_DEF } from "../static/fantomes.js";

let pass = 0, fail = 0;
function check(desc, cond) {
    if (cond) pass++;
    else { fail++; console.log("FAIL: " + desc); }
}

// Symboles importés par atelier.js depuis fantomes.js
check("fantomes.js → choisirFantomes", typeof choisirFantomes === "function");
check("fantomes.js → BBOX_DEF", typeof BBOX_DEF === "object" && BBOX_DEF !== null);
check("BBOX_DEF a xMin", "xMin" in BBOX_DEF);
check("BBOX_DEF a yMin", "yMin" in BBOX_DEF);
check("BBOX_DEF a zMin", "zMin" in BBOX_DEF);

console.log("\nSmoke test imports : " + pass + "/" + (pass+fail) + " pass");
process.exit(fail ? 1 : 0);
