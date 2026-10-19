/* Visuels d'un message, montrés dans la fiche de tâche (Charles, 19 oct. 2026).
   Images jointes (/uploads/, publiques) et chemins d'image cités dans le texte (`wt-x/design/rendus/a.png`,
   file:///…/atelier/…), lus par /api/v2/livrable. Jamais de jeton dans un src ou un href (revue codex-1,
   msg 4852) : l'image est lue par fetch avec l'en-tête x-session-token, puis affichée par URL blob,
   révoquée à la fermeture de la fiche. Testé par tests/test_visuels.mjs. */

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
export const RE_IMG = /(?:file:\/\/)?[\w./~-]*\w\.(?:png|jpe?g|gif|webp|svg)\b/gi;

// Liste des visuels d'un message : {src, nom} pour une pièce jointe, {chemin, nom} pour un livrable.
export function visuels(m, {pj = true} = {}) {
  const vus = new Set(), out = [];
  if (pj) (m.attachments || []).forEach(a => {
    const u = String(a && a.url || "");
    if (u.startsWith("/uploads/") && /\.(png|jpe?g|gif|webp)$/i.test(u) && !vus.has(u)) { vus.add(u); out.push({src: u, nom: a.name || u.split("/").pop()}); }
  });
  (String(m.text || "").match(RE_IMG) || []).forEach(c => {
    // La route refuse un chemin absolu : on garde la partie relative à la racine de l'atelier.
    const rel = c.replace(/^file:\/\//, "").replace(/^(?:~|\/\S*?)?\/atelier\//, "");
    if (/^[/~]/.test(rel) || rel.split("/").includes("..") || vus.has(rel)) return;
    vus.add(rel); out.push({chemin: rel, nom: rel.split("/").pop()});
  });
  return out;
}

// Une vignette de livrable naît sans src ni href : le chargeur les pose une fois le blob lu.
export const visuelsHtml = (liste, cls = "") => liste.length ? `<div class="vis${cls ? " " + cls : ""}">${liste.map(v => v.chemin
  ? `<a class="vis-l" target="_blank" rel="noopener" title="${esc(v.nom)}"><img class="vis-img" data-chemin="${esc(v.chemin)}" alt="${esc(v.nom)}"></a>`
  : `<a class="vis-l" href="${esc(v.src)}" target="_blank" rel="noopener" title="${esc(v.nom)}"><img class="vis-img" src="${esc(v.src)}" alt="${esc(v.nom)}" loading="lazy"></a>`).join("")}</div>` : "";

// Retire une vignette, et son cadre s'il n'en reste aucune.
export function retirerVignette(img) {
  const cadre = img.closest(".vis");
  img.closest(".vis-l")?.remove();
  if (cadre && !cadre.querySelector(".vis-l")) cadre.remove();
}

// Chargeur de blobs : un fetch par chemin tant que la fiche reste ouverte ; liberer() révoque tout.
// Les dépendances sont injectées (fetch, en-têtes, URL) pour le test hors navigateur.
export function creerChargeur({fetch: lire = globalThis.fetch, headers, url = globalThis.URL}) {
  let gen = 0;
  const blobs = new Map(); // chemin -> Promise<string|null>
  const blob = chemin => {
    if (!blobs.has(chemin)) {
      const g = gen;
      blobs.set(chemin, lire(`/api/v2/livrable?chemin=${encodeURIComponent(chemin)}`, {headers: headers()})
        .then(r => r.ok ? r.blob() : null)
        .then(b => {
          if (!b || !/^image\//.test(b.type)) return null;
          const u = url.createObjectURL(b);
          if (g !== gen) { url.revokeObjectURL(u); return null; } // fiche fermée pendant la lecture
          return u;
        })
        .catch(() => null));
    }
    return blobs.get(chemin);
  };
  return {
    charger(racine) {
      const imgs = racine ? Array.from(racine.querySelectorAll("img.vis-img[data-chemin]:not([src])")) : [];
      return Promise.all(imgs.map(img => blob(img.dataset.chemin).then(u => {
        if (!img.isConnected) return;
        if (!u) return retirerVignette(img);
        img.src = u;
        const a = img.closest(".vis-l");
        if (a) a.href = u;
      })));
    },
    liberer() {
      gen++;
      const vieux = [...blobs.values()];
      blobs.clear();
      return Promise.all(vieux.map(p => p.then(u => { if (u) url.revokeObjectURL(u); })));
    },
  };
}
