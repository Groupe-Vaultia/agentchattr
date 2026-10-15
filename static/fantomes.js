/* G5 — Sélection des fantômes (volumes schématiques des sous-ensembles
   non modélisés). Importable par atelier.js et par tests/test_g5_fantomes.mjs. */

// 10 volumes dans le repère du véhicule (mm, Z vers le haut).
// Source : geometrie.py retenue() + maillage.py (pivot 1100, essieu 1435.7,
// bras 360, roues AV x=40, empattement 1396, voie 1000).
export const FANTOMES_VEH = [
    { nom: "Roue AV G",  bbox: { xMin: 40-203/2, xMax: 40+203/2, yMin: -300-203/2, yMax: -300+203/2, zMin: -130-355.6, zMax: -130+355.6 } },
    { nom: "Roue AV D",  bbox: { xMin: 40-203/2, xMax: 40+203/2, yMin: 700-203/2,  yMax: 700+203/2,  zMin: -130-355.6, zMax: -130+355.6 } },
    { nom: "Roue AR G",  bbox: { xMin: 1435.7-254/2, xMax: 1435.7+254/2, yMin: -300-254/2, yMax: -300+254/2, zMin: -130-355.6, zMax: -130+355.6 } },
    { nom: "Roue AR D",  bbox: { xMin: 1435.7-254/2, xMax: 1435.7+254/2, yMin: 700-254/2,   yMax: 700+254/2,   zMin: -130-355.6, zMax: -130+355.6 } },
    { nom: "Batterie (3× 48 V)", bbox: { xMin: 430, xMax: 680, yMin: 120, yMax: 280, zMin: 20, zMax: 190 } },
    { nom: "Moteur + boîte 2 gammes", bbox: { xMin: 1100, xMax: 1260, yMin: 40, yMax: 200, zMin: -20, zMax: 140 } },
    { nom: "Bras oscillant", bbox: { xMin: 1100, xMax: 1460, yMin: -55, yMax: 455, zMin: -155, zMax: -105 } },
    { nom: "Triangles avant", bbox: { xMin: -60, xMax: -10, yMin: -300, yMax: 340, zMin: -120, zMax: 65 } },
    { nom: "Selle", bbox: { xMin: 480, xMax: 1000, yMin: 50, yMax: 350, zMin: 316, zMax: 406 } },
    { nom: "Guidon", bbox: { xMin: 25, xMax: 55, yMin: -150, yMax: 530, zMin: 300, zMax: 620 } },
];

export const BBOX_DEF = { xMin: 0, xMax: 100, yMin: -50, yMax: 50, zMin: 0, zMax: 100 };

/**
 * Choisit les fantômes à afficher.
 * @param {Array|null} nomenclature - enfants de l'assemblage racine, ou null/undefined.
 * @returns {Array<{nom: string, bbox: object}>} - liste de fantômes.
 */
export function choisirFantomes(nomenclature) {
    // Par défaut : les 10 volumes du véhicule.
    const fantomes = FANTOMES_VEH.slice();
    if (!nomenclature || !nomenclature.length) return fantomes;

    // Sous-ensembles sans GLB
    const seSansGlb = nomenclature.filter(se =>
        !(se.enfants || []).some(e => e.fichier && e.fichier.endsWith(".glb")));
    // Si tous les sous-ensembles ont un GLB, aucun fantôme.
    if (!seSansGlb.length) return [];

    fantomes.length = 0;
    for (const se of seSansGlb) {
        const nomSe = (se.nom || "").trim().toLowerCase();
        // 1. Correspondance exacte
        let match = FANTOMES_VEH.find(f => f.nom.toLowerCase() === nomSe);
        // 2. Tous les mots (y compris AV/AR/G/D), un seul candidat accepté
        if (!match) {
            const motsSe = nomSe.split(/\s+/);
            const candidats = FANTOMES_VEH.filter(f => {
                const motsF = f.nom.toLowerCase().split(/\s+/);
                return motsSe.every(m => motsF.includes(m));
            });
            if (candidats.length === 1) match = candidats[0];
        }
        fantomes.push(match ? { nom: se.nom, bbox: match.bbox } : { nom: se.nom, bbox: BBOX_DEF });
    }
    return fantomes;
}
