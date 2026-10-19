/* Fichiers protégés de l'atelier, sans jeton dans l'URL (revue codex-1, msg 4852 ; lot claude-1, msg 4867).
   - Visuels d'un message, montrés dans la fiche de tâche : images jointes (/uploads/, publiques) et chemins
     d'image cités dans le texte (`wt-x/design/rendus/a.png`, file:///…/atelier/…), lus par /api/v2/livrable.
   - Toute image protégée (vignette, plan de pièce, visualiseur) : <img data-blob="URL"> sans src.
   - Tout téléchargement protégé : <a data-telecharger="URL" download="nom">, lu au clic.
   Le fichier est lu par fetch avec l'en-tête x-session-token, puis montré ou enregistré par URL blob ;
   les blobs des images sont révoqués à la fermeture de la fiche. Testé par tests/test_visuels.mjs. */

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
export const RE_IMG = /(?:file:\/\/)?[\w./~-]*\w\.(?:png|jpe?g|gif|webp|svg)\b/gi;
export const urlLivrable = chemin => `/api/v2/livrable?chemin=${encodeURIComponent(chemin)}`;

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
  ? `<a class="vis-l" target="_blank" rel="noopener" title="${esc(v.nom)}"><img class="vis-img" data-blob="${esc(urlLivrable(v.chemin))}" alt="${esc(v.nom)}"></a>`
  : `<a class="vis-l" href="${esc(v.src)}" target="_blank" rel="noopener" title="${esc(v.nom)}"><img class="vis-img" src="${esc(v.src)}" alt="${esc(v.nom)}" loading="lazy"></a>`).join("")}</div>` : "";

// Plans d'une pièce (Charles, 19 oct. 2026 : la fiche du cadre montrait la feuille de notes) : les feuilles SVG de la
// dernière révision qui en a, feuille 1 d'abord (…_P05.svg, puis …_P05-F2.svg, -F3), et pour chaque format le
// fichier de la révision la plus récente (le SVG téléchargeable est la feuille 1).
export function choisirPlans(fichiers) {
  const num = f => parseInt(String(f.revision || "").replace(/\D/g, ""), 10) || 0;
  const feuille = f => { const m = String(f.nom).match(/-F(\d+)\.svg$/i); return m ? +m[1] : 1; };
  const estSvg = f => /\.svg$/i.test(f.nom);
  const tries = (fichiers || []).slice().sort((a, b) => num(b) - num(a)); // plus récente d'abord (tri stable)
  const revision = (tries.find(estSvg) || tries[0] || {}).revision || "";
  const feuilles = tries.filter(f => estSvg(f) && f.revision === revision)
    .map(f => ({...f, feuille: feuille(f)})).sort((a, b) => a.feuille - b.feuille);
  const formats = ["pdf", "step", "stp", "glb", "svg", "dxf"]
    .map(ext => tries.find(f => f.nom.toLowerCase().endsWith("." + ext) && !(ext === "svg" && feuille(f) > 1)))
    .filter(Boolean);
  return {revision, feuilles, total: Math.max(0, ...feuilles.map(f => f.feuille)), formats};
}

// Retire une vignette, et son cadre s'il n'en reste aucune.
export function retirerVignette(img) {
  const cadre = img.closest(".vis");
  img.closest(".vis-l")?.remove();
  if (cadre && !cadre.querySelector(".vis-l")) cadre.remove();
}

// Chargeur : un fetch par URL tant que la fiche reste ouverte ; liberer() révoque tout.
// Les dépendances sont injectées (fetch, en-têtes, URL, document) pour le test hors navigateur.
export function creerChargeur({fetch: lire = globalThis.fetch, headers, url = globalThis.URL, document: doc = globalThis.document}) {
  let gen = 0;
  const blobs = new Map(); // URL -> Promise<string|null>
  const blob = src => {
    if (!blobs.has(src)) {
      const g = gen;
      blobs.set(src, lire(src, {headers: headers()})
        .then(r => r.ok ? r.blob() : null)
        .then(b => {
          if (!b || !/^image\//.test(b.type)) return null;
          const u = url.createObjectURL(b);
          if (g !== gen) { url.revokeObjectURL(u); return null; } // fiche fermée pendant la lecture
          return u;
        })
        .catch(() => null));
    }
    return blobs.get(src);
  };
  return {
    charger(racine) {
      const imgs = racine ? Array.from(racine.querySelectorAll("img[data-blob]:not([src])")) : [];
      return Promise.all(imgs.map(img => blob(img.dataset.blob).then(u => {
        if (!img.isConnected) return;
        if (u) {
          img.src = u;
          const a = img.closest(".vis-l");
          if (a) a.href = u;
        } else if (img.classList.contains("vis-img")) retirerVignette(img);
        else { img.insertAdjacentHTML("afterend", `<p class="cap">Image introuvable.</p>`); img.remove(); }
      })));
    },
    liberer() {
      gen++;
      const vieux = [...blobs.values()];
      blobs.clear();
      return Promise.all(vieux.map(p => p.then(u => { if (u) url.revokeObjectURL(u); })));
    },
    // Lit le fichier au clic et l'enregistre sous `nom` ; rend false si la lecture échoue.
    async telecharger(src, nom) {
      try {
        const r = await lire(src, {headers: headers()});
        if (!r.ok) return false;
        const u = url.createObjectURL(await r.blob());
        const a = doc.createElement("a");
        a.href = u; a.download = nom || ""; a.rel = "noopener";
        doc.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => url.revokeObjectURL(u), 60000); // le temps que le navigateur ouvre le téléchargement
        return true;
      } catch (_) { return false; }
    },
  };
}
