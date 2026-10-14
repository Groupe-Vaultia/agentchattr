/* Atelier R&D · Vaultia — logique de la page.
   Ne lit que les routes du socle (FICHES-LOTS.md). Chaque route « à venir » est enveloppée :
   tant que claude n'a pas branché le lot (ou si la réponse est 404/500), l'interface affiche
   un état vide propre, sans erreur. Aucun jeton, aucune donnée sensible n'est logguée (R3). */
"use strict";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// Les 8 étapes de pilote-rd, dans l'ordre (spec v0.7).
const ETAPES = ["probleme","etat_art","concepts","conception","prototype","essais","industrialisation","lancement"];
const NOM_ETAPES = {probleme:"Problème",etat_art:"État de l'art",concepts:"Concepts",conception:"Conception",prototype:"Prototype",essais:"Essais",industrialisation:"Industrialisation",lancement:"Lancement"};
// Ce que couvre chaque étape (pilote-rd), affiché quand on clique une étape.
const DEF_ETAPES = {
  probleme: "Poser le problème : pour qui, quoi, pourquoi maintenant, et ce qui compte comme réussi.",
  etat_art: "Ce qui existe déjà (produits, code, publications) et pourquoi ça ne suffit pas.",
  concepts: "Les pistes possibles, comparées, et celle qu'on retient avec sa raison.",
  conception: "Le plan de la piste retenue : règles, découpage, interfaces, avant de produire.",
  prototype: "Construire une première version qui marche, livrée par PR et revue.",
  essais: "Éprouver le prototype en vrai : hypothèse, méthode, critère, résultat (RS&DE).",
  industrialisation: "Rendre le tout solide et durable : ménage, règles, exploitation.",
  lancement: "Mise en usage réelle et bilan.",
};
const STATUTS = {actif:"actif",veille:"en veille",termine:"terminé",arrete:"arrêté"};
const STATUT_CLS = {actif:"s-actif",veille:"s-veille",termine:"s-attente",arrete:"s-arrete"};
// Les états que S2 (jobs.py) renvoie vraiment : fait / en_cours / attend_charles / a_faire / bloque.
const ETAT_TACHE = {fait:"fait",en_cours:"en cours",attend_charles:"attend Charles",a_faire:"à faire",bloque:"bloqué"};
const ETAT_CLS = {fait:"s-fait",en_cours:"s-cours",attend_charles:"s-charles",a_faire:"s-afaire",bloque:"s-bloque"};
const ETAT_EXEC = {actif:"actif",silencieux:"silencieux",fini:"fini"};
const ETAT_EXEC_CLS = {actif:"s-actif",silencieux:"s-silence",fini:"s-fait"};
// Normalise un état de tâche (S2) vers une clé de libellé/classe connue.
const normEtat = e => (e && ETAT_TACHE[e] ? e : (e === "cours" ? "en_cours" : e === "charles" ? "attend_charles" : e === "afaire" ? "a_faire" : "a_faire"));

const state = {
  view: "projets",
  projets: {},      // id -> {nom, statut, memoire, channels}
  defaut: "",
  sel: null,        // id du projet sélectionné
  taches: [],       // tâches du projet sélectionné
  etape: null,      // étape courante du projet (calc serveur ou local)
  executions: [],   // exécutions du projet sélectionné
  jalons: [],       // jalons du projet (P1) : {id, jalon, criteres, risque, recommandation, decision, …}
  fiche: null,      // fiche projet (P2) : {objectif, niveau, trl, hypotheses, risques, questions, …}
  methodes: null,   // méthode de chaque étape (P3) : {etape: texte} via GET /api/v2/methodes — null si absent
  pieces: null,     // N3 : pièces du projet {pieces:[…]} — null si pas encore chargé
  achats: null,     // N3 : liste d'achats {lignes, sans_offre, totaux}
  cout: null,       // N3 : coût cumulé {totaux, sans_prix, a_convertir}
  alertes: [],      // U4 : alertes globales de GET /api/v2/ronde (sauvegarde, copie x1) — [] si rien
};
// N3 : statuts de pièce (spec PIECES.md) — libellé + classe de pilule.
const PIECE_STATUT = {
  a_concevoir:["à concevoir","s-afaire"], concue:["conçue","s-cours"],
  a_commander:["à commander","s-attente"], commandee:["commandée","s-cours"],
  recue:["reçue","s-fait"], fabriquee:["fabriquée","s-fait"],
  validee:["validée","s-fait"], rejetee:["rejetée","s-bloque"],
};
const ORIGINE = {acheter:"acheter", concevoir:"concevoir"};
const TYPE_PIECE = {assemblage:"assemblage", piece:"pièce", visserie:"visserie", matiere:"matière"};
const PROCEDS = {laser:"laser", soudure:"soudure", cnc:"cnc", impression_3d:"impression 3D", achat:"achat"};

// ---------- accès réseau : état vide propre si la route n'est pas encore branchée ----------
// Le serveur sert /atelier avec un jeton de session injecté (comme /). Sans lui, tout est 403.
const headers = () => {
  const h = {"Accept": "application/json"};
  const t = window.__SESSION_TOKEN__;
  if (t) h["x-session-token"] = t;
  return h;
};
function erreur(code) {
  // 404 = le lot n'est pas encore branché (état vide propre). Tout le reste (403, 400, 500…) est une
  // erreur réelle : on ne la cache pas derrière « rien à afficher ».
  return code && code !== 404 ? `Erreur ${code} — vérifie que la salle est ouverte et que ton jeton est valide.` : "";
}
async function getJSON(url) {
  try {
    const r = await fetch(url, {headers: headers()});
    if (!r.ok) return {ok: false, data: null, err: r.status, msg: erreur(r.status)};
    return {ok: true, data: await r.json()};
  } catch (_) { return {ok: false, data: null, err: 0}; }
}
async function postJSON(url, body) {
  try {
    const h = headers(); h["Content-Type"] = "application/json";
    const r = await fetch(url, {method: "POST", headers: h, body: JSON.stringify(body || {})});
    if (!r.ok) return {ok: false, data: null, err: r.status, msg: erreur(r.status)};
    return {ok: true, data: await r.json().catch(() => null)};
  } catch (_) { return {ok: false, data: null, err: 0}; }
}
function toast(m) {
  const t = $("#toast"); t.textContent = m; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => { t.hidden = true; }, 3800);
}
const heure = ts => { if (ts == null) return ""; try { return new Date(ts * 1000).toLocaleString("fr-CA", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); } catch (_) { return ""; } };

// ---------- chargement des projets ----------
async function loadProjets() {
  const r = await getJSON("/api/projects");
  if (!r.ok || !r.data || !r.data.v2) {
    state.projets = {}; state.defaut = "";
    $("#note").hidden = false;
    // 404 = pas encore branché (état vide propre) ; 403/400/500 = erreur réelle, affichée.
    $("#note").textContent = (r.msg)
      ? r.msg
      : "Le socle n'a pas encore retourné de projet (ou la route /api/projects n'est pas encore branchée). L'interface est prête : les projets apparaîtront ici dès que la salle en aura.";
    return;
  }
  const v2 = r.data.v2;
  state.projets = v2.projets || {};
  state.defaut = v2.defaut || "";
  if (!state.sel || !state.projets[state.sel]) state.sel = state.defaut || Object.keys(state.projets)[0] || null;
  $("#note").hidden = true;
}

// ---------- vue Projets : résumé + une ligne par projet ----------
function renderProjets() {
  const ids = Object.keys(state.projets);
  const actifs = ids.filter(id => state.projets[id].statut === "actif");
  const veille = ids.filter(id => state.projets[id].statut === "veille");
  const enDirect = new Set(state.executions.filter(e => e.etat === "actif" || e.etat === "silencieux").map(e => e.agent));
  const attend = ids.filter(id => (state.projets[id].taches || []).some(t => normEtat(t.etat) === "attend_charles"));

  $("#psum").innerHTML = `
    <div class="sum"><b>${actifs.length}</b><span>projets actifs</span></div>
    <div class="sum"><b>${veille.length}</b><span>en veille</span></div>
    <div class="sum"><b>${enDirect.size}</b><span>agents au travail</span></div>
    <div class="sum"><b>${attend.length}</b><span>qui t'attendent</span></div>`;

  if (!ids.length) {
    $("#prows").innerHTML = `<div class="empty">Aucun projet pour l'instant. Crée le premier ci-dessous : claude découpe le travail et assigne les agents.</div>`;
    return;
  }
  $("#prows").innerHTML = ids.map(id => {
    const p = state.projets[id];
    const taches = p.taches || [];
    const fait = taches.filter(t => normEtat(t.etat) === "fait").length;
    const cours = taches.filter(t => ["en_cours","attend_charles"].includes(normEtat(t.etat))).length;
    const afaire = taches.length - fait - cours;
    const agents = [...new Set(taches.map(t => t.responsable).filter(Boolean))];
    return `<div class="prow${id === state.sel ? " cur" : ""}" data-proj="${esc(id)}">
      <div><div class="nm">${esc(p.nom || id)}</div><div class="sub"><span class="pill ${STATUT_CLS[p.statut] || "s-attente"}">${esc(STATUTS[p.statut] || p.statut || "?")}</span></div></div>
      <div>${p.etape ? `<div class="sub">${esc(p.etape)}</div>` : `<div class="sub">étape —</div>`}<div class="bar" title="${fait} fait · ${cours} en cours · ${afaire} à faire"><i class="b-fait" style="flex:${Math.max(fait,0)}"></i><i class="b-cours" style="flex:${Math.max(cours,0)}"></i><i class="b-afaire" style="flex:${Math.max(afaire,1)}"></i></div></div>
      <div class="sub">${agents.length ? agents.map(esc).join(", ") : "—"}</div>
      <div class="chips"><button class="btn${p.statut === "veille" ? " pri" : ""}" data-status="${p.statut === "veille" ? "actif" : "veille"}" data-proj="${esc(id)}">${p.statut === "veille" ? "Réactiver" : "En veille"}</button></div>
    </div>`;
  }).join("");
}

// ---------- rail : projets + étape ----------
// Un bouton projet (point + nom + étape). `ind` = retrait (sous-projet).
function _btnProjet(id, ind) {
  const p = state.projets[id];
  return `<button class="proj${ind ? " enfant" : ""}" data-proj="${esc(id)}" aria-current="${id === state.sel}"><span class="dot ${p.statut === "actif" ? "actif" : p.statut}"></span><span class="pn" title="${esc(p.nom || id)}">${esc(p.nom || id)}</span><span class="st">${p.etape ? esc(p.etape.split(":").pop().trim()) : ""}</span></button>`;
}
// Rail en arbre : les projets sans parent en haut, leurs sous-projets (parent_id) en retrait dessous.
function renderRail() {
  const ids = Object.keys(state.projets);
  const parents = ids.filter(id => !state.projets[id].parent_id);
  const enfants = id => ids.filter(x => state.projets[x].parent_id === id);
  const html = parents.map(id =>
    _btnProjet(id, false) +
    enfants(id).map(e => _btnProjet(e, true)).join("")
  ).join("");
  // tout projet orphelin (parent_id qui ne correspond à aucun projet connu) reste visible en bas
  const orphelins = ids.filter(id => state.projets[id].parent_id && !state.projets[state.projets[id].parent_id]);
  $("#rail-proj").innerHTML = (html + (orphelins.length ? "<div class='rail-sep'></div>" : "") + orphelins.map(o => _btnProjet(o, false)).join(""))
    || `<div class="sub" style="padding:2px 8px;font-size:12px;color:var(--ink3)">aucun projet</div>`;
}

// ---------- étape du projet (calc local si le serveur ne la donne pas) ----------
function etapeDuProjet(taches) {
  for (let i = 0; i < ETAPES.length; i++) {
    if (taches.some(t => t.etape === ETAPES[i] && t.etat !== "fait")) return i;
  }
  return taches.length ? ETAPES.length : 0;
}

// ---------- vue Équipe : les agents, depuis les exécutions ----------
function renderEquipe() {
  const parAgent = {};
  for (const e of state.executions) {
    const a = parAgent[e.agent] = parAgent[e.agent] || {agent: e.agent, etat: e.etat, taches: new Set(), dernier: e.dernier_signe || e.debut};
    if (e.etat === "actif") a.etat = "actif";
    else if (a.etat !== "actif" && e.etat === "silencieux") a.etat = "silencieux";
    if (e.titre) a.taches.add(e.titre);
  }
  const agents = Object.values(parAgent);
  const actif = agents.filter(a => a.etat === "actif").length;
  const silence = agents.filter(a => a.etat === "silencieux").length;
  const attend = state.taches.filter(t => normEtat(t.etat) === "attend_charles").length;

  $("#esum").innerHTML = `
    <div class="sum"><b>${actif}</b><span>agent(s) actif(s)</span></div>
    <div class="sum"><b>${agents.length - actif - silence}</b><span>en attente ou terminé</span></div>
    <div class="sum"><b style="color:var(--warn)">${silence}</b><span>silencieux depuis 10 min</span></div>
    <div class="sum"><b style="color:var(--slate)">${attend}</b><span>tâches qui t'attendent</span></div>`;

  if (!state.executions.length && !state.taches.length) {
    $("#team").innerHTML = `<div class="empty">Aucun agent en cours sur ce projet. Quand claude assigne une tâche, l'agent apparaît ici avec son état, sa tâche et son dernier signe de vie.</div>`;
    return;
  }
  $("#team").innerHTML = agents.map(a => `
    <div class="agent">
      <div class="hd"><span class="nm">${esc(a.agent)}</span><span class="pill ${ETAT_EXEC_CLS[a.etat] || "s-attente"}">${esc(ETAT_EXEC[a.etat] || a.etat || "?")}</span></div>
      <div class="lbl">Tâche</div>
      <div class="tache">${[...a.taches].map(esc).join(" · ") || "—"}</div>
      <div class="meta"><span>signe de vie : ${esc(heure(a.dernier)) || "—"}</span></div>
    </div>`).join("");
}

// ---------- vue Carte : les 8 étapes, une tâche par nœud ----------
function renderCarte() {
  const p = state.sel ? state.projets[state.sel] : null;
  $("#carte-proj").textContent = p ? (p.nom || state.sel) : "aucun projet sélectionné";
  const taches = state.taches;

  // options du sélecteur « + Tâche »
  $("#tk-c").innerHTML = ETAPES.map((e, i) => `<option value="${e}">${i + 1}. ${NOM_ETAPES[e]}</option>`).join("");

  if (!state.sel) { $("#map").innerHTML = ""; $("#pourquoi").hidden = true; $("#pourquoi").innerHTML = ""; return; }
  const veille = p && p.statut === "veille";
  const idx = state.etape ?? etapeDuProjet(taches);
  const courante = ETAPES[idx];
  // « Pourquoi » visible sur la carte : la méthode de l'étape courante (P3), au-dessus de la grille (pas une colonne).
  // <details> fermé par défaut (1 800 caractères ne doivent pas noyer la carte), markdown rendu sûrement.
  const mCourante = (state.methodes && state.methodes[courante]) || "";
  const pq = $("#pourquoi");
  pq.innerHTML = mCourante
    ? `<details class="pourquoi-d"><summary>Méthode de l'étape : ${NOM_ETAPES[courante]}</summary><div class="pourquoi-c">${mdCourt(mCourante)}</div></details>`
    : "";
  pq.hidden = !mCourante;

  $("#map").innerHTML = ETAPES.map((e, i) => {
    const de = taches.filter(t => t.etape === e);
    const done = de.length && de.every(t => t.etat === "fait");
    const isNow = i === (state.etape ?? etapeDuProjet(taches)) && !done;
    return `<div class="col${de.length ? "" : " vide"}"><h3><button type="button" class="steph" data-step="${e}">${i + 1}. ${NOM_ETAPES[e]}</button></h3>${
      de.map(t => { const st = normEtat(t.etat); return `<div class="node${veille ? " veille" : ""}" data-node="${esc(t.id)}" data-s="${st}">
        <div class="t">${esc(t.titre)}</div>
        ${t.conclusion ? `<div class="pourquoi-t" title="${esc(t.conclusion)}">${esc(court(t.conclusion, 120))}</div>` : ""}
        <div class="w">${esc(t.responsable || "")}${t.critere ? " · " + esc(t.critere) : ""}</div>
        <div class="w"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span> <button class="btn disc" type="button" data-disc="${esc(t.id)}">Discuter</button></div>
      </div>`; }).join("") ||
      (done ? "" : `<div class="w" style="font-size:11.5px;color:var(--ink3)">aucune tâche</div>`)
    }</div>`;
  }).join("");
}

// ---------- en-tête de projet : barre d'étapes + en direct ----------
function renderProjHead() {
  const el = $("#projhead");
  if (!state.sel) { el.hidden = true; el.innerHTML = ""; return; }
  const p = state.projets[state.sel];
  const taches = state.taches;
  const idx = state.etape ?? etapeDuProjet(taches);
  const veille = p.statut === "veille";
  const live = state.executions.filter(e => e.etat === "actif" || e.etat === "silencieux");

  const steps = ETAPES.map((e, i) => {
    const cls = i < idx ? "done" : i === idx ? "now" : "";
    return `<button type="button" class="step ${cls}" data-step="${e}"><i>${i + 1}</i>${NOM_ETAPES[e]}</button>`;
  }).join("");

  el.hidden = false;
  el.innerHTML = `<div class="ph${veille ? " veille" : ""}">
    <div class="top"><b>${esc(p.nom || state.sel)}</b><span class="pill ${STATUT_CLS[p.statut] || "s-attente"}">${esc(STATUTS[p.statut] || p.statut || "?")}</span>
      ${p.memoire ? `<span class="cap" style="margin:0">${esc(p.memoire)}</span>` : ""}
      <span style="margin-left:auto;display:flex;gap:6px"><button class="btn" data-act="fiche-projet">Fiche projet</button><button class="btn" data-act="newtask">+ Tâche</button><button class="btn${p.statut === "veille" ? " pri" : ""}" data-status="${p.statut === "veille" ? "actif" : "veille"}" data-proj="${esc(state.sel)}">${p.statut === "veille" ? "Réactiver" : "En veille"}</button></span></div>
    <div class="steps">${steps}</div>
    <div class="cap" style="margin:0">${idx < ETAPES.length ? `Étape ${idx + 1} sur ${ETAPES.length} : ${NOM_ETAPES[ETAPES[idx]]}` : "Toutes les étapes sont terminées"}</div>
    ${live.length ? `<div class="live"><span class="lbl">En direct</span><ul>${live.map(e => `<li><b>${esc(e.agent)}</b> · ${esc(e.role || e.titre || "")}${e.etat === "silencieux" ? " · <span class='pill s-silence'>silencieux</span>" : ""}</li>`).join("")}</ul></div>` : ""}
  </div>`;
}

// ---------- vue Historique : [[jour, [entrées]]] ----------
function renderHist() {
  const el = $("#hlist");
  if (!state.hist) { el.innerHTML = `<li style="border:0"><span class="empty" style="grid-column:1/-1">Aucun historique pour ce projet. Les exécutions, décisions, messages et révisions apparaîtront ici, par jour.</span></li>`; return; }
  if (!Array.isArray(state.hist) || !state.hist.length) { el.innerHTML = `<li style="border:0"><span class="empty" style="grid-column:1/-1">Rien dans l'historique pour l'instant.</span></li>`; return; }
  el.innerHTML = state.hist.map(([jour, entrees]) =>
    `<div class="day">${esc(jour)}</div>` +
    entrees.map(en => `<li><time>${esc(heure(en.heure))}</time><span><span class="type">${esc(en.type || "")}</span>${esc(en.acteur || "")} — ${esc(en.resume || "")}</span></li>`).join("")
  ).join("");
}

// ---------- vue Livrable : livrables + révisions ----------
function renderLivrable() {
  const tbl = $("#liv-tbl"), cap = $("#liv-cap"), rev = $("#liv-rev");
  if (!state.liv) {
    tbl.innerHTML = ""; cap.textContent = "Les livrables et les révisions figées de ce projet apparaîtront ici (route /api/v2/projects/{id}/revisions).";
    rev.innerHTML = `<div class="empty">Aucune révision figée pour l'instant. « Approuver » fige les livrables actuels en P01, P02…</div>`;
    return;
  }
  const liv = state.liv.livrables || [];
  tbl.innerHTML = `<tr><th>Fichier</th><th>Version</th><th class="n">Empreinte</th></tr>` +
    (liv.length ? liv.map(l => `<tr><td>${esc(l.chemin)}</td><td>${esc(l.version)}</td><td class="n"><code>${esc((l.empreinte || "").slice(0, 12))}</code></td></tr>`).join("") : `<tr><td colspan="3" class="sub">aucun livrable</td></tr>`);
  cap.textContent = liv.length ? `${liv.length} livrable(s) au projet.` : "";
  const revisions = state.liv.revisions || [];
  rev.innerHTML = revisions.length
    ? revisions.slice().reverse().map(r => `<div class="rev"><div class="hd"><b>${esc(r.numero)}</b><span class="pill s-fait">figée</span><span class="cap" style="margin:0">${esc(r.approuvee_par || "")} · ${esc(heure(r.heure))}</span></div><div class="chips" style="margin-top:6px">${(r.livrables || []).map(l => `<span class="chip">${esc(l.chemin)} · v${esc(l.version)}</span>`).join("")}</div></div>`).join("")
    : `<div class="empty">Aucune révision figée. « Approuver » fige les livrables actuels.</div>`;
  // bouton Approuver (exige approuvee_par: "user" côté serveur)
  if (!$("#btn-approuver")) {
    const b = document.createElement("button");
    b.id = "btn-approuver"; b.className = "btn pri"; b.type = "button";
    b.textContent = "Approuver (figer P0" + (revisions.length + 1) + ")";
    b.style.marginBottom = "10px";
    b.onclick = async () => {
      const r = await postJSON(`/api/v2/projects/${encodeURIComponent(state.sel)}/revisions`, {approuvee_par: "user"});
      toast(r.ok ? `Révision ${r.data && r.data.numero ? r.data.numero : ""} figée.` : "Approuver n'a pas abouti (route non branchée ou refus).");
      if (r.ok) await loadProjet();
    };
    rev.parentNode.insertBefore(b, rev);
  }
}

// ---------- vue Pièces (N3) : tableau filtrable, fiche pièce, nomenclature en arbre, achats ----------
const fmtCAD = (n, dev = "CAD") => { if (n == null || isNaN(n)) return "—"; return dev + " " + Number(n).toLocaleString("fr-CA", {minimumFractionDigits: 2, maximumFractionDigits: 2}); };

function pillStatutPiece(s) {
  const [lib, cls] = PIECE_STATUT[s] || [s || "?", "s-attente"];
  return `<span class="pill ${cls}">${esc(lib)}</span>`;
}

// Tableau des pièces du projet, filtrable (numéro, nom, révision, origine, statut).
function renderPieces() {
  const el = $("#pc-tbl"), f = $("#pc-q"), sel = $("#pc-f");
  if (!el) return;
  if (!state.sel) { el.innerHTML = ""; renderAchats(); return; }
  if (!state.pieces) {
    el.innerHTML = `<tr><td colspan="6"><div class="empty">Les pièces de ce projet apparaîtront ici (route /api/v2/pieces?projet_id=). Les agents y enregistrent chaque pièce conçue ou achetée, sa révision, son statut et ses offres.</div></td></tr>`;
    renderAchats();
    return;
  }
  // options du filtre statut
  const statutsVus = [...new Set((state.pieces.pieces || []).map(p => p.statut).filter(Boolean))];
  sel.innerHTML = `<option value="">tous les statuts</option>` + statutsVus.map(s => `<option value="${esc(s)}">${esc((PIECE_STATUT[s] || [s])[0])}</option>`).join("");
  const q = (f.value || "").trim().toLowerCase();
  const fs = sel.value;
  const list = (state.pieces.pieces || []).filter(p => {
    if (fs && p.statut !== fs) return false;
    if (q) {
      const hay = [p.numero, p.nom, p.revision, p.origine, p.statut, p.sous_systeme, p.categorie].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const n = list.length;
  $("#pc-cap").textContent = n ? `${n} pièce(s)` : (state.pieces.pieces && state.pieces.pieces.length ? "aucune ne correspond au filtre" : "aucune pièce");
  el.innerHTML = n
    ? `<tr><th>N°</th><th>Nom</th><th class="n">Rév.</th><th>Origine</th><th>Statut</th><th class="n">Masse</th></tr>` +
      list.map(p => `<tr class="pc-row" data-piece="${esc(p.id)}">
        <td><code>${esc(p.numero || "")}</code></td>
        <td><b>${esc(p.nom || "")}</b>${p.sous_systeme ? `<div class="sub">${esc(p.sous_systeme)}</div>` : ""}</td>
        <td class="n">${esc(p.revision || "")}</td>
        <td>${esc(ORIGINE[p.origine] || p.origine || "")}</td>
        <td>${pillStatutPiece(p.statut)}</td>
        <td class="n">${p.masse_g != null ? esc(p.masse_g) + " g" : ""}</td>
      </tr>`).join("")
    : `<tr><td colspan="6" class="sub">aucune pièce</td></tr>`;
  renderAchats();
}

// Fiche d'une pièce : offres sourcées, où elle est utilisée (nomenclature), historique, fichier.
async function ouvrirPiece(id) {
  const base = (state.pieces && state.pieces.pieces || []).find(p => String(p.id) === String(id));
  const tete = enteteFiche(`Pièce ${base ? esc(base.numero || "") : ""}`, base ? (base.nom || "") : "");
  const chargement = `<div class="fc"><div class="lbl">Chargement…</div></div>`;
  ouvrirFiche(tete + chargement);
  const r = await getJSON(`/api/v2/pieces/${encodeURIComponent(id)}`);
  if (!$("#fiche-c")) return;
  if (!r.ok || !r.data) {
    $("#fiche-c").innerHTML = tete + `<div class="fc"><div class="cap" style="color:var(--bad)">Impossible de charger cette pièce (route non branchée ou pièce inconnue).</div></div>`;
    return;
  }
  const p = r.data;
  const meta = `<div class="fm">${pillStatutPiece(p.statut)}<span>Rév. <b>${esc(p.revision || "")}</b></span><span>Origine : <b>${esc(ORIGINE[p.origine] || p.origine || "—")}</b></span>${p.matiere ? `<span>Matière : ${esc(p.matiere)}</span>` : ""}${p.procede ? `<span>Procédé : ${esc(PROCEDS[p.procede] || p.procede)}</span>` : ""}${p.masse_g != null ? `<span>${esc(p.masse_g)} g</span>` : ""}</div>`;
  // offres sourcées
  const offres = (p.offres || []);
  const offresHtml = offres.length
    ? `<div class="fc"><div class="lbl">Offres (${offres.length})</div><ul class="fhist">${offres.map(o => `<li><time>${esc(o.devise || "CAD")}</time><span><b>${esc(o.reference || "")}</b>${o.fournisseur ? ` <span class="cap">(${esc(o.fournisseur.nom || o.fournisseur)})</span>` : ""} · ${fmtCAD(o.prix, o.devise)}${o.livraison != null ? " + liv. " + fmtCAD(o.livraison, o.devise) : ""}${lienSource(o.source)}${o.date ? ` <span class="cap">${esc(heure(o.date))}</span>` : ""}</span></li>`).join("")}</ul></div>`
    : (p.origine === "acheter" ? `<div class="fc"><div class="lbl">Offres</div><p class="cap" style="color:var(--warn)">Aucune offre sourcée. grok magasine au moins 3 offres pour cette pièce.</p></div>` : "");
  // Où elle est utilisée : les assemblages parents (champ serveur utilisee_dans), à part des enfants.
  const ud = p.utilisee_dans || [];
  const utiliseeHtml = ud.length
    ? `<div class="fc"><div class="lbl">Où elle est utilisée</div><ul class="flist">${ud.map(u => `<li><span><code>${esc(u.numero || "")}</code> <b>${esc(u.nom || "")}</b></span><span class="cap">×${esc(u.quantite != null ? u.quantite : "")}${u.unite ? " " + esc(u.unite) : ""}</span></li>`).join("")}</ul></div>`
    : `<div class="fc"><div class="lbl">Où elle est utilisée</div><p class="cap">Pas rattachée à un assemblage pour l'instant (pièce racine ou orpheline).</p></div>`;
  // dont elle est faite : l'arbre des enfants (nomenclature sous la pièce)
  const nomHtml = `<div class="fc"><div class="lbl">Dont elle est faite</div><div id="pc-arbre"><span class="cap">Chargement…</span></div></div>`;
  // historique : {champ, avant, apres, qui, date}
  const hist = (p.historical || p.historique || []);
  const histHtml = hist.length
    ? `<div class="fc"><div class="lbl">Historique</div><ul class="fhist">${hist.slice().reverse().map(h => `<li><time>${esc(heure(h.date))}</time><span>${esc(h.champ || "")} : ${esc(h.avant || "—")} → <b>${esc(h.apres || "—")}</b>${h.qui ? ` <span class="cap">(${esc(h.qui)})</span>` : ""}</span></li>`).join("")}</ul></div>`
    : "";
  const fichier = p.fichier ? `<div class="fc"><div class="lbl">Fichier</div><p><code>${esc(p.fichier)}</code>${p.empreinte ? ` · <span class="cap">sha256 ${esc(String(p.empreinte).slice(0, 12))}</span>` : ""}</p></div>` : "";
  $("#fiche-c").innerHTML = tete + meta +
    (p.objectif || p.description ? `<div class="fc"><div class="lbl">Description</div><p>${esc(p.objectif || p.description)}</p></div>` : "") +
    offresHtml + utiliseeHtml + nomHtml + fichier + histHtml;
  // charge l'arbre (nomenclature) dans la fiche
  const ar = await getJSON(`/api/v2/pieces/${encodeURIComponent(id)}/nomenclature`);
  const el = $("#pc-arbre"); if (!el) return;
  el.innerHTML = (ar.ok && ar.data) ? arbreNomenclature(ar.data, id) : `<span class="cap">Aucun lien de nomenclature (route non branchée ou pièce orpheline).</span>`;
}

// Rend l'arbre de nomenclature : nœud = pièce + quantite_cumulee + enfants[].
function arbreNomenclature(noeud, racineId) {
  const estRacine = String(noeud.id) === String(racineId);
  const self = `<div class="pc-node${estRacine ? " racine" : ""}">
    <button type="button" class="pc-toggle" data-node="${esc(noeud.id)}" aria-expanded="true">
      <span class="pc-ref"><code>${esc(noeud.numero || "")}</code> <b>${esc(noeud.nom || "")}</b></span>
      ${noeud.quantite_cumulee != null ? `<span class="pc-qt">×${esc(noeud.quantite_cumulee)}${noeud.unite ? " " + esc(noeud.unite) : ""}</span>` : ""}
      ${pillStatutPiece(noeud.statut)}
    </button>
    <div class="pc-kids">${(noeud.enfants || []).map(e => arbreNomenclature(e, racineId)).join("")}</div>
  </div>`;
  return self;
}

// Liste d'achats du projet : comparatif, total, alertes (devise à convertir, prix > 30 j).
function renderAchats() {
  const el = $("#pc-achats"); if (!el) return;
  if (!state.sel) { el.innerHTML = ""; return; }
  if (!state.achats) {
    el.innerHTML = `<div class="empty">La liste d'achats du projet apparaîtra ici (route /api/v2/projects/{id}/achats). Elle consolide les pièces « acheter », la meilleure offre sourcée, le total, et ce qui n'a pas encore d'offre.</div>`;
    return;
  }
  const lignes = state.achats.lignes || [];
  const sans = state.achats.sans_offre || [];
  const tot = state.achats.totaux || {};
  const row = l => {
    const o = l.offre; // objet : {fournisseur, reference, prix, devise, livraison, source, date, …}
    const offreCell = o
      ? `<div><b>${esc(o.reference || "")}</b>${o.fournisseur ? `<div class="sub">${esc(o.fournisseur)}</div>` : ""}</div>` +
        `<span class="cap">${fmtCAD(o.prix, o.devise)} · ${lienSource(o.source)}</span>`
      : `<span class="cap" style="color:var(--warn)">sans offre</span>`;
    return `<tr>
    <td><code>${esc(l.numero || "")}</code><div class="sub">${esc(l.nom || "")}</div></td>
    <td class="n">${esc(l.quantite != null ? l.quantite : "")}</td>
    <td>${offreCell}</td>
    <td class="n">${fmtCAD(l.total, o ? o.devise : "CAD")}</td>
    <td>${l.a_convertir ? `<span class="pill s-attente" title="devise autre que CAD ou mixte — claude source le taux">à convertir</span>` : ""}${l.age_jours > 30 ? `<span class="pill s-silence" title="prix de plus de 30 jours — grok relève de nouveau">prix à revérifier</span>` : ""}</td>
  </tr>`;
  };
  el.innerHTML =
    (lignes.length ? `<div class="tblw"><table><tr><th>Pièce</th><th class="n">Qté</th><th>Meilleure offre</th><th class="n">Total</th><th>Alertes</th></tr>${lignes.map(row).join("")}</table></div>` : `<div class="empty">Aucune pièce « acheter » pour l'instant.</div>`) +
    (sans.length ? `<div class="cap" style="color:var(--warn);margin-top:8px">Sans offre : ${sans.map(s => esc(s.numero || s.nom || "")).join(", ")}.</div>` : "") +
    // Un total par devise : on n'additionne jamais CAD et USD sans taux source (claude, revue N3).
    (Object.keys(tot).length ? `<div class="cap" style="margin-top:8px">Total achats : <b>${Object.entries(tot).map(([d, v]) => fmtCAD(v, d)).join(" + ")}</b>${tot.sans_prix ? ` · ${esc(tot.sans_prix)} sans prix` : ""}</div>` : "");
}

// ---------- chargement de tout ce qui dépend du projet sélectionné ----------
async function loadProjet() {
  const id = state.sel;
  state.taches = []; state.executions = []; state.hist = null; state.liv = null; state.etape = null;
  state.jalons = []; state.fiche = null;
  if (!id) { renderTous(); return; }

  const [t, e, h, l, j, m, pc, ac, co] = await Promise.all([
    getJSON(`/api/v2/taches?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/executions?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/historique`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/revisions`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/jalons`),          // P1
    getJSON(`/api/v2/methodes`),                                          // P3 : {etape: texte}, indépendant du projet
    getJSON(`/api/v2/pieces?projet_id=${encodeURIComponent(id)}`),         // N3 : pièces du projet
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/achats`),          // N3 : liste d'achats
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/cout`),            // N3 : coût cumulé
  ]);

  if (t.ok && t.data) {
    // v0.2 : {taches, etape, etapes} ; v0.1 : liste nue. `etape` est le nom d'étape (ex. "concepts").
    if (Array.isArray(t.data)) state.taches = t.data;
    else {
      state.taches = t.data.taches || [];
      const idx = t.data.etape ? ETAPES.indexOf(t.data.etape) : -1;
      state.etape = (idx >= 0) ? idx : (state.taches.length ? ETAPES.length : 0);
    }
  }
  if (e.ok && e.data) state.executions = Array.isArray(e.data) ? e.data : (e.data.executions || []);
  if (h.ok && h.data) state.hist = h.data;
  if (l.ok && l.data) state.liv = l.data;
  if (j.ok && j.data) state.jalons = j.data.jalons || (Array.isArray(j.data) ? j.data : []);
  // P2 : la fiche projet vit dans le projet (GET /api/projects → v2.projets[id]) ; on lit l'objet projet.
  state.fiche = state.projets[id] || null;
  // P3 : la méthode de chaque étape (docs/PILOTE.md), servie par /api/v2/methodes. Indépendant du projet.
  if (m.ok && m.data && typeof m.data === "object") state.methodes = m.data;
  // N3 : pièces, achats, coût (404 = lot pas encore branché → état vide propre).
  if (pc.ok && pc.data) state.pieces = pc.data;
  if (ac.ok && ac.data) state.achats = ac.data;
  if (co.ok && co.data) state.cout = co.data;

  // enrichit la fiche projet pour la vue Projets (étape, taches) sans re-fetch
  const p = state.projets[id];
  if (p) {
    p.taches = state.taches;
    const idx = state.etape ?? etapeDuProjet(state.taches);
    p.etape = idx < ETAPES.length ? `Étape ${idx + 1}/${ETAPES.length} · ${NOM_ETAPES[ETAPES[idx]]}` : "terminé";
  }
  renderTous();
}

// U4 : bandeau d'alertes globales (sauvegarde, copie hors tour) venant de GET /api/v2/ronde.
// `alertes` est une liste de chaînes ; rien n'est affiché quand elle est vide.
function renderAlertes() {
  const el = $("#alertes"); if (!el) return;
  const liste = state.alertes || [];
  if (!liste.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = `<b>⚠️ ${liste.length} alerte${liste.length > 1 ? "s" : ""}</b> ` +
    liste.map(a => `<span class="al">· ${esc(a)}</span>`).join("");
}

// U5 : rangée « Équipe » — qui travaille, sur quoi, depuis quand.
// Lit les tâches en cours et les exécutions pour afficher les agents actifs.
function renderEquipeRow() {
  const el = $("#equipe-row"); if (!el) return;
  const taches = state.taches || [];
  const executions = state.executions || [];
  
  // Agents actifs : ceux qui ont une tâche en_cours ou une execution actif
  const actifs = new Map();
  
  // Tâches en cours
  for (const t of taches) {
    if (t.etat === "en_cours" && t.responsable) {
      const agent = t.responsable.toLowerCase();
      if (!actifs.has(agent)) {
        actifs.set(agent, {agent, taches: [], dernier_signe: null});
      }
      actifs.get(agent).taches.push(t.titre);
    }
  }
  
  // Executions actives
  for (const e of executions) {
    if (e.etat === "actif" && e.agent) {
      const agent = e.agent.toLowerCase();
      if (!actifs.has(agent)) {
        actifs.set(agent, {agent, taches: [], dernier_signe: null});
      }
      if (e.dernier_signe) {
        actifs.get(agent).dernier_signe = e.dernier_signe;
      }
    }
  }
  
  if (!actifs.size) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  
  el.hidden = false;
  const items = Array.from(actifs.values()).map(a => {
    const depuis = a.dernier_signe ? `<span class="cap">${esc(heure(a.dernier_signe))}</span>` : "";
    let sur = "";
    if (a.taches.length) {
      const liste = a.taches.slice(0, 2).join("; ");
      const plus = a.taches.length > 2 ? ` +${a.taches.length - 2}` : "";
      sur = `<span class="cap">${esc(liste)}${plus}</span>`;
    }
    return `<span class="equipe-item"><b>${esc(a.agent)}</b>${sur}${depuis}</span>`;
  }).join("");
  
  el.innerHTML = `<b>Équipe</b> ${items}`;
}

function renderTous() {
  renderRail(); renderProjets();
  $("#projhead").hidden = true;
  renderProjHead();
  renderEquipe(); renderCarte(); renderPieces(); renderHist(); renderLivrable();
  renderAlertes();
  renderEquipeRow();
  syncNav();
}

// ---------- navigation ----------
function go(v) {
  state.view = v;
  document.querySelectorAll("#tabs [role=tab]").forEach(b => b.setAttribute("aria-selected", b.dataset.v === v));
  ["projets", "equipe", "carte", "pieces", "hist", "livrable"].forEach(x => { const s = $("#v-" + x); if (s) s.hidden = (x !== v); });
  window.scrollTo(0, 0);
  syncNav();
}
function syncNav() {
  const m = $("#msel");
  if (m) m.innerHTML = [["projets","Projets"],["equipe","Équipe"],["carte","Carte"],["pieces","Pièces"],["hist","Historique"],["livrable","Livrable"]].map(([v,l]) => `<option value="${v}"${v === state.view ? " selected" : ""}>${l}</option>`).join("");
  // rail aria-current sur la vue
  document.querySelectorAll(".rail [data-go]").forEach(b => b.setAttribute("aria-current", b.dataset.go === state.view));
}

// ---------- actions ----------
async function changerStatut(id, statut) {
  const r = await postJSON(`/api/v2/projects/${encodeURIComponent(id)}/status`, {status: statut});
  toast(r.ok ? `${id} → ${STATUTS[statut] || statut}` : `Changement refusé (route non branchée ou statut inconnu).`);
  if (r.ok) { await loadProjets(); await loadProjet(); }
}

// Upload d'un fichier vers POST /api/upload (rend {name, url}) — pour joindre des photos/documents au lancement.
async function uploadFichier(f) {
  try {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/upload", {method: "POST", headers: headers(), body: fd});
    if (!r.ok) return null;
    const d = await r.json().catch(() => null);
    return (d && d.name && d.url) ? {name: d.name, url: d.url} : null;
  } catch (_) { return null; }
}

async function nouveauProjet(e) {
  e.preventDefault();
  const nom = $("#np-nom").value.trim();
  if (!nom) { toast("Donne un nom au projet."); return; }
  const objectif = $("#np-but").value.trim();
  // P4 : c'est POST /api/v2/projects {nom, objectif, pieces_jointes} qui crée le projet ET appelle @claude.
  // Les photos/documents choisis sont d'abord déposés via POST /api/upload, puis passés en [{name, url}].
  const fichiers = Array.from($("#np-fich").files || []);
  let pieces = [];
  if (fichiers.length) {
    toast(`Dépôt de ${fichiers.length} fichier(s)…`);
    pieces = (await Promise.all(fichiers.map(uploadFichier))).filter(Boolean);
    if (pieces.length < fichiers.length) toast(`${fichiers.length - pieces.length} fichier(s) refusé(s) (type ou taille).`);
  }
  const r = await postJSON("/api/v2/projects", {nom, objectif, pieces_jointes: pieces});
  toast(r.ok ? `Projet « ${nom} » lancé. claude démarre le cadrage.` : (r.msg || "Création refusée (route non branchée ou nom déjà pris)."));
  if (r.ok) { e.target.reset(); await loadProjets(); await loadProjet(); }
}

async function nouvelleTache(e) {
  e.preventDefault();
  const titre = $("#tk-t").value.trim();
  if (!titre || !state.sel) { toast("Donne un titre à la tâche."); return; }
  // La route POST /api/v2/taches est du lot de claude ; on tente, et on le dit si absent.
  // Rôles du contrat S2 : producteur, verificateur, relecteur, proposant (pas de « responsable »).
  const r = await postJSON(`/api/v2/taches`, {projet_id: state.sel, titre, etape: $("#tk-c").value, responsable: $("#tk-r").value, equipe: [{agent: $("#tk-r").value, role: "producteur"}]});
  toast(r.ok ? "Tâche ajoutée." : "Ajout refusé (route POST /api/v2/taches non branchée pour l'instant).");
  if (r.ok) { e.target.hidden = true; await loadProjet(); }
}

// Source d'une offre : lien seulement pour http(s) ; un devis (« devis: … ») reste du texte. Jamais javascript: ni
// data: dans un href, même si une vieille donnée en contenait (revue codex msg 2409).
const lienSource = src => {
  const t = String(src || "").trim();
  if (!t) return `<span class="cap" style="color:var(--bad)">sans source</span>`;
  return /^https?:\/\/[^\s<>"]+$/i.test(t)
    ? ` <a href="${esc(t)}" target="_blank" rel="noopener noreferrer">source</a>`
    : ` <span class="cap">${esc(t)}</span>`;
};

// ---------- fiche d'une tâche / d'une étape (dialogue) ----------
// Champs de la tâche (S2), dans l'ordre de lecture ; seuls les champs remplis s'affichent.
const CHAMPS_FICHE = [
  ["resultat", "Ce qui a été fait"], ["conclusion", "Pourquoi, et ce qu'on en retient"],
  ["hypothese", "Hypothèse"], ["methode", "Méthode"], ["incertitude", "Incertitude"],
  ["critere", "Critère de réussite"], ["preuve", "Preuve"],
];
// « PR #24 » devient un lien vers la PR ; le reste est échappé.
const avecLiens = txt => esc(txt).replace(/PR #(\d+)/g,
  (m, n) => `<a href="https://github.com/Groupe-Vaultia/agentchattr/pull/${n}" target="_blank" rel="noopener">PR #${n}</a>`);
const court = (txt, n) => { const t = String(txt || ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };
// Petit rendu sûr du markdown de PILOTE.md : d'abord esc(), puis **x** → <b>, `x` → <code>.
const mdCourt = txt => esc(String(txt || ""))
  .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
  .replace(/`([^`]+)`/g, "<code>$1</code>");

function ouvrirFiche(html) {
  $("#fiche-c").innerHTML = html;
  const d = $("#fiche");
  if (!d.open) { if (d.showModal) d.showModal(); else d.setAttribute("open", ""); }
  d.scrollTop = 0;
}
function fermerFiche() { const d = $("#fiche"); if (d.close) d.close(); else d.removeAttribute("open"); }
const enteteFiche = (sur, titre) => `<div class="fh"><div><div class="lbl">${esc(sur)}</div><h2 id="fiche-t">${esc(titre)}</h2></div><button class="btn" type="button" data-act="fermer" aria-label="Fermer">Fermer</button></div>`;

let REQUETE_FICHE = 0; // garde : une réponse n'affiche que si c'est encore la bonne tâche (pas d'historique croisé)
async function ouvrirTache(id) {
  const t = state.taches.find(x => String(x.id) === String(id));
  if (!t) return;
  const n = ++REQUETE_FICHE; // ce tirage est le seul autorisé à écrire dans la fiche
  const st = normEtat(t.etat);
  const equipe = (t.equipe || []).map(m => `${esc(m.agent)} <span class="cap">(${esc(m.role)})</span>`).join(", ") || esc(t.responsable || "—");
  const champs = CHAMPS_FICHE.filter(([c]) => String(t[c] || "").trim())
    .map(([c, l]) => `<div class="fc"><div class="lbl">${l}</div><p>${avecLiens(t[c])}</p></div>`).join("")
    || `<p class="cap">Rien d'écrit encore sur cette tâche.</p>`;
  const tete = enteteFiche(`Tâche ${t.id} · ${NOM_ETAPES[t.etape] || t.etape || ""}`, t.titre);
  const meta = `<div class="fm"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span><span>Responsable : <b>${esc(t.responsable || "—")}</b></span><span>Équipe : ${equipe}</span></div>`;
  const pied = `<div class="ff"><button class="btn pri" type="button" data-disc="${esc(t.id)}">Discuter de cette tâche</button></div>`;
  ouvrirFiche(tete + meta + champs + `<div class="fc"><div class="lbl">Historique</div><ul class="fhist" id="fiche-h"><li class="cap">Chargement…</li></ul></div>` + pied);

  const [m, e] = await Promise.all([
    getJSON(`/api/v2/messages?tache_id=${encodeURIComponent(t.id)}&limit=100`),
    getJSON(`/api/v2/executions?tache_id=${encodeURIComponent(t.id)}`),
  ]);
  if (n !== REQUETE_FICHE) return; // une tâche plus récente a été ouverte : on jette cette réponse (pas d'historique croisé)
  const el = $("#fiche-h");
  if (!el) return;
  // Distinguer une erreur réseau d'un historique vraiment vide (404 = pas branché, pas une erreur).
  const reussi = (m.ok || m.err === 404) && (e.ok || e.err === 404);
  const lignes = [];
  ((m.ok && m.data && m.data.messages) || []).forEach(x => lignes.push({h: x.timestamp, html: `<b>${esc(x.sender)}</b> — ${esc(court(x.text, 400))}`}));
  ((e.ok && e.data && e.data.executions) || []).forEach(x => lignes.push({h: x.fin || x.debut,
    html: `<span class="type">exécution</span><b>${esc(x.agent)}</b>${x.role ? ` (${esc(x.role)})` : ""} — ${esc(court(x.consigne, 200))}${x.issue ? ` · ${esc(x.issue)}` : x.fin ? "" : " · en cours"}`}));
  lignes.sort((a, b) => (b.h || 0) - (a.h || 0));
  el.innerHTML = !reussi
    ? `<li class="cap" style="color:var(--bad)">Chargement de l'historique impossible (erreur réseau). Referme puis rouvre la tâche pour réessayer.</li>`
    : (lignes.length
      ? lignes.map(l => `<li><time>${esc(heure(l.h))}</time><span>${l.html}</span></li>`).join("")
      : `<li class="cap">Aucun message ni exécution rattaché à cette tâche pour l'instant. « Discuter » ouvre sa conversation : tout ce qui s'y dit s'inscrit ici.</li>`);
}

// ---------- jalons (P1) : les décisions de Charles ----------
const JALON_NOM = {J1: "Jalon J1", J2: "Jalon J2", revue: "Revue"};
const JALON_DECISIONS = {go: "Continuer", recycle: "Recycler", hold: "Mettre en veille", kill: "Arrêter"};
const JALON_CLS = {go: "s-fait", recycle: "s-cours", hold: "s-veille", kill: "s-bloque", "": "s-attente"};
const ETAT_CRITERE = {atteint: "atteint", partiel: "partiel", rate: "manqué", a_mesurer: "à mesurer"};
const CRIT_CLS = {atteint: "crit-ok", partiel: "crit-part", rate: "crit-rate", a_mesurer: "crit-mes"};

// Les étapes antérieures à un jalon (recycle_etape doit être antérieure au jalon).
// J1 : probleme, etat_art ou concepts ; J2 : jusqu'à essais.
const JALON_RECYCLE = {J1: ["probleme", "etat_art", "concepts"], J2: ["probleme", "etat_art", "concepts", "conception", "prototype", "essais"], revue: ETAPES.slice(0, 7)};

// Rend le bloc « Jalon » d'une étape : les jalons rattachés à cette étape, avec leurs boutons de décision.
function blocJalons(etape) {
  // Un jalon J1 vit à la fin de l'étape concepts (1-3), un J2 à la fin de essais, une revue avant lancement.
  const rattaches = state.jalons.filter(j =>
    (j.jalon === "J1" && etape === "concepts") ||
    (j.jalon === "J2" && etape === "essais") ||
    (j.jalon === "revue" && etape === "lancement"));
  if (!rattaches.length) return "";
  const html = rattaches.map(j => {
    const decise = !!j.decision;
    const criteres = (j.criteres || []).map(c =>
      `<li><span class="crit ${CRIT_CLS[c.etat] || "crit-mes"}">${esc(ETAT_CRITERE[c.etat] || c.etat || "?")}</span><span>${esc(c.nom || "")}</span>${c.cible ? `<span class="cap">cible ${esc(c.cible)}${c.mesure ? " · " + esc(c.mesure) : ""}</span>` : ""}</li>`).join("");
    const risques = (j.risques || []).length ? (j.risques.map(esc).join(" · ")) : "";
    const boutons = decise ? "" :
      `<div class="jb">` +
      `<div class="lbl">Ta décision</div>` +
      (j.recommandation ? `<div class="cap">recommandation de claude : <b>${esc(j.recommandation)}</b>${j.raison ? " — " + esc(j.raison) : ""}</div>` : "") +
      `<div class="jb-btns">` +
      Object.entries(JALON_DECISIONS).map(([v, l]) =>
        `<button class="btn dec${v === "go" ? " pri" : v === "kill" ? " stop" : ""}" type="button" data-dec="${esc(j.id)}" data-val="${v}">${esc(l)}</button>`).join("") +
      `</div>` +
      `<label class="lbl" for="recy-${esc(j.id)}">ou recycler vers</label><select id="recy-${esc(j.id)}" data-recy="${esc(j.id)}"><option value="">—</option>${(JALON_RECYCLE[j.jalon] || []).map(e2 => `<option value="${e2}">${NOM_ETAPES[e2]}</option>`).join("")}</select>` +
      `<label class="lbl" for="not-${esc(j.id)}">note (facultatif)</label><input id="not-${esc(j.id)}" data-not="${esc(j.id)}" placeholder="ex. : on recycle sur la masse">` +
      `</div>`;
    return `<div class="jalon">
      <div class="jalon-hd"><b>${esc(JALON_NOM[j.jalon] || j.jalon)}</b><span class="pill ${JALON_CLS[decise ? j.decision : ""] || "s-attente"}">${decise ? j.decision : "en attente de Charles"}</span>${j.decision_date ? `<span class="cap">${esc(heure(j.decision_date))}</span>` : ""}</div>
      ${criteres ? `<ul class="crits">${criteres}</ul>` : ""}
      ${risques ? `<div class="cap">Risques : ${risques}</div>` : ""}
      ${j.resultats ? `<div class="fc"><div class="lbl">Résultats</div><p>${avecLiens(j.resultats)}</p></div>` : ""}
      ${j.reste ? `<div class="fc"><div class="lbl">Reste à faire</div><p>${esc(j.reste)}</p></div>` : ""}
      ${j.decision_note ? `<div class="fc"><div class="lbl">Note de la décision</div><p>${esc(j.decision_note)}</p></div>` : ""}
      ${boutons}
    </div>`;
  }).join("");
  return `<div class="fc"><div class="lbl">Jalon(s) de cette étape</div>${html}</div>`;
}

function ouvrirEtape(e) {
  const i = ETAPES.indexOf(e);
  if (i < 0) return;
  const de = state.taches.filter(t => t.etape === e);
  const fait = de.filter(t => normEtat(t.etat) === "fait").length;
  const liste = de.length
    ? `<ul class="flist">${de.map(t => { const st = normEtat(t.etat); return `<li><button type="button" data-fiche="${esc(t.id)}"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span><span>${esc(t.titre)}</span>${t.resultat ? `<span class="cap">${esc(court(t.resultat, 160))}</span>` : ""}</button></li>`; }).join("")}</ul>`
    : `<p class="cap">Aucune tâche à cette étape pour l'instant.</p>`;
  // Ce que couvre l'étape (une ligne) + la méthode détaillée (P3, docs/PILOTE.md) si la route la sert.
  const mE = (state.methodes && state.methodes[e]) || "";
  const methode = (mE
    ? `<div class="fc"><div class="lbl">Méthode de l'étape</div><p>${mdCourt(mE)}</p></div>`
    : `<div class="fc"><div class="lbl">Ce que couvre l'étape</div><p>${esc(DEF_ETAPES[e])}</p></div>`);
  ouvrirFiche(enteteFiche(`Étape ${i + 1} sur ${ETAPES.length}`, NOM_ETAPES[e]) +
    `<div class="fc"><div class="lbl">Ce que couvre l'étape</div><p>${esc(DEF_ETAPES[e])}</p></div>` +
    methode +
    blocJalons(e) +
    `<div class="fc"><div class="lbl">Tâches (${fait}/${de.length} faites)</div>${liste}</div>`);
}

// ---------- décision sur un jalon (Charles) ----------
async function deciderJalon(jalonId, val) {
  const j = state.jalons.find(x => String(x.id) === String(jalonId));
  if (!j) return;
  const recy = val === "recycle" ? (($("#recy-" + CSS.escape(String(j.id)))?.value) || "") : "";
  if (val === "recycle" && !recy) { toast("Choisis une étape vers laquelle recycler."); return; }
  const note = (($("#not-" + CSS.escape(String(j.id)))?.value) || "").trim();
  const r = await postJSON(`/api/v2/jalons/${encodeURIComponent(j.id)}/decision`,
    {par: "user", decision: val, note, ...(val === "recycle" ? {recycle_etape: recy} : {})});
  if (r.ok) { toast(`Jalon ${j.jalon} → ${val}.`); await loadProjet(); }
  else toast(r.msg || `Décision refusée (déjà décidé, ou route non branchée).`);
}

// ---------- fiche projet (P2) : l'objectif, le niveau, les hypothèses, les risques, les questions ----------
function ouvrirFicheProjet() {
  const id = state.sel; if (!id) return;
  const p = state.projets[id] || {};
  const f = state.fiche || {};
  const meta = `<div class="fm"><span class="pill ${STATUT_CLS[p.statut] || "s-attente"}">${esc(STATUTS[p.statut] || p.statut || "?")}</span>`
    + (f.niveau ? `<span>Niveau : <b>${esc(f.niveau)}</b></span>` : "")
    + (f.trl ? `<span>TRL : <b>${esc(f.trl)}</b></span>` : "")
    + (f.horizon ? `<span>Horizon : <b>${esc(f.horizon)}</b></span>` : "")
    + (f.code ? `<span>Code : <b>${esc(f.code)}</b></span>` : "")
    + (f.type ? `<span>Type : <b>${esc(f.type)}</b></span>` : "")
    + `</div>`;
  const hypo = (f.hypotheses || []).map(h =>
    `<li><span class="pill ${h.etat === "confirmee" ? "s-fait" : h.etat === "infirmee" ? "s-bloque" : "s-attente"}">${esc(h.etat || "à vérifier")}</span><span>${esc(h.texte || "")}</span><span class="cap">source : ${esc(h.source || "?")}</span></li>`).join("");
  const risques = (f.risques || []).map(r =>
    `<li><span class="cap">${esc(r.type || "")}${r.etape ? " · " + esc(NOM_ETAPES[r.etape] || r.etape) : ""}</span><span>${esc(r.texte || "")}</span></li>`).join("");
  const questions = (f.questions || []).map(q =>
    `<li><span>${esc(q.texte || "")}</span>${q.reponse ? `<span class="cap">réponse : ${esc(q.reponse)}</span>` : `<span class="cap" style="color:var(--warn)">sans réponse</span>`}</li>`).join("");
  const c = f.criteres || [];
  // Un tableau de blocs puis join("") — la concaténation avec ?: en chaîne avalait tout après le premier bloc vide.
  const blocs = [];
  if (f.objectif || p.objectif) blocs.push(`<div class="fc"><div class="lbl">Objectif</div><p>${esc(f.objectif || p.objectif)}</p></div>`);
  if (f.livrable_attendu || p.livrable_attendu) blocs.push(`<div class="fc"><div class="lbl">Livrable attendu</div><p>${esc(f.livrable_attendu || p.livrable_attendu)}</p></div>`);
  if (c.length) blocs.push(`<div class="fc"><div class="lbl">Critères</div><ul class="flist">${c.map(x => `<li><span>${esc(x.nom || "")}</span>${x.cible ? `<span class="cap">cible : ${esc(x.cible)}</span>` : ""}</li>`).join("")}</ul></div>`);
  if (hypo) blocs.push(`<div class="fc"><div class="lbl">Hypothèses</div><ul class="flist hypo">${hypo}</ul></div>`);
  if (risques) blocs.push(`<div class="fc"><div class="lbl">Risques</div><ul class="flist">${risques}</ul></div>`);
  if (questions) blocs.push(`<div class="fc"><div class="lbl">Questions posées par claude</div><ul class="flist">${questions}</ul></div>`);
  const contenu = blocs.join("") || `<p class="cap">La fiche projet n'est pas encore remplie. claude la remplit pendant le lancement guidé (objectif, niveau, hypothèses, risques, questions).</p>`;
  ouvrirFiche(enteteFiche("Fiche projet", p.nom || id) + meta + contenu);
}

// ---------- câblage ----------
// Bouton « Discuter » : ouvre la conversation de la tâche dans la salle.
// La route crée le canal tache-<id> (rangé sous le projet) une seule fois et rend {channel}.
// On mémorise le canal pour la salle, puis on y va — sans toucher à chat.js.
async function discuter(tacheId) {
  const r = await postJSON(`/api/v2/taches/${encodeURIComponent(tacheId)}/conversation`, {});
  if (!r.ok || !r.data || !r.data.channel) { toast(r.msg || "Impossible d'ouvrir la conversation de cette tâche."); return; }
  try { localStorage.setItem("agentchattr-channel", r.data.channel); } catch (_) {}
  window.location.href = "/";
}

document.addEventListener("click", e => {
  const t = e.target;
  const tab = t.closest("#tabs [role=tab]"); if (tab) return go(tab.dataset.v);
  const g = t.closest("[data-go]"); if (g) return go(g.dataset.go);
  // Un clic sur un projet ouvre sa carte de tâches (avant : il ne faisait que le surligner).
  // Les boutons de la ligne (« En veille ») passent au gestionnaire [data-status] plus bas.
  const row = t.closest(".prow[data-proj]"); if (row && !t.closest("button")) { state.sel = row.dataset.proj; loadProjet(); go("carte"); return; }
  const rp = t.closest("[data-proj]");
  const st = t.closest("[data-status]");
  if (st) { e.stopPropagation(); return changerStatut(st.dataset.proj, st.dataset.status); }
  if (rp && (rp.classList.contains("proj") || rp.classList.contains("prow"))) { state.sel = rp.dataset.proj; loadProjet(); go(rp.classList.contains("proj") ? "carte" : state.view); return; }
  // Bouton « Discuter » sur un nœud de tâche : on ouvre la salle, pas de sélection de nœud.
  const d = t.closest("[data-disc]"); if (d) { e.stopPropagation(); return discuter(d.dataset.disc); }
  // Bouton de décision sur un jalon (Charles) : go / recycle / hold / kill.
  const dj = t.closest("[data-dec]"); if (dj) { e.stopPropagation(); return deciderJalon(dj.dataset.dec, dj.dataset.val); }
  const fe = t.closest("[data-fiche]"); if (fe) return ouvrirTache(fe.dataset.fiche);
  const sp = t.closest("[data-step]"); if (sp) return ouvrirEtape(sp.dataset.step);
  const nd = t.closest("[data-node]"); if (nd) return ouvrirTache(nd.dataset.node);
  // N3 : ligne de pièce du tableau → fiche pièce ; nœud d'arbre → replier/déplier (ou ouvrir si clic sur la réf).
  const pr = t.closest(".pc-row[data-piece]"); if (pr && !t.closest("button")) return ouvrirPiece(pr.dataset.piece);
  const pn = t.closest(".pc-toggle"); if (pn) { const kids = pn.parentNode.querySelector(":scope > .pc-kids"); if (kids) { kids.hidden = !kids.hidden; pn.setAttribute("aria-expanded", String(!kids.hidden)); } return; }
  if (t.id === "fiche") return fermerFiche();  // clic sur le fond du dialogue
  const act = t.closest("[data-act]"); if (!act) return;
  if (act.dataset.act === "fermer") return fermerFiche();
  if (act.dataset.act === "fiche-projet") return ouvrirFicheProjet();
  if (act.dataset.act === "newtask") { const f = $("#taskform"); f.hidden = !f.hidden; if (!f.hidden) $("#tk-t").focus(); }
  if (act.dataset.act === "canceltask") { $("#taskform").hidden = true; }
});
$("#msel").addEventListener("change", e => go(e.target.value));
$("#newproj").addEventListener("submit", nouveauProjet);
$("#taskform").addEventListener("submit", nouvelleTache);
// N3 : filtres du tableau des pièces (re-rendu à la volée, sans re-fetch).
$("#pc-q").addEventListener("input", renderPieces);
$("#pc-f").addEventListener("change", renderPieces);
window.addEventListener("resize", () => {});

// U4 : les alertes (sauvegarde, copie hors tour) sont globales, pas propres à un projet.
// Rechargées au démarrage, au retour sur l'onglet et toutes les 5 min : la boucle de
// sauvegarde réessaie chaque heure, une page ouverte doit donc suivre (alerte levée ou nouvelle).
// Règle P2 : on ne vide jamais le bandeau sur une erreur transitoire (5xx, réseau).
// Vider uniquement sur 404 (route absente) ou sur une réponse valide dont la liste est vide.
async function loadAlertes() {
  const r = await getJSON("/api/v2/ronde");
  if (r.err === 404) {
    // Route absente → vider
    state.alertes = [];
  } else if (r.ok && r.data && Array.isArray(r.data.alertes)) {
    state.alertes = r.data.alertes;
  }
  // sinon : garder le dernier état connu (erreur transitoire 5xx, réseau)
  renderAlertes();
}

// ---------- démarrage ----------
(async function init() {
  try { const v = localStorage.getItem("rd-view"); if (v) state.view = v; } catch (_) {}
  await loadAlertes();
  await loadProjets();
  await loadProjet();
  go(state.view || "projets");
  // U4 : suivre les alertes tant que la page est ouverte (5 min, en phase avec la boucle de sauvegarde).
  setInterval(loadAlertes, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadAlertes(); });
})();
