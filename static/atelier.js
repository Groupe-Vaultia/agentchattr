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
};

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
function renderRail() {
  const ids = Object.keys(state.projets);
  $("#rail-proj").innerHTML = ids.map(id => {
    const p = state.projets[id];
    return `<button class="proj" data-proj="${esc(id)}" aria-current="${id === state.sel}"><span class="dot ${p.statut === "actif" ? "actif" : p.statut}"></span><span class="pn" title="${esc(p.nom || id)}">${esc(p.nom || id)}</span><span class="st">${p.etape ? esc(p.etape.split(":").pop().trim()) : ""}</span></button>`;
  }).join("") || `<div class="sub" style="padding:2px 8px;font-size:12px;color:var(--ink3)">aucun projet</div>`;
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

  if (!state.sel) { $("#map").innerHTML = ""; return; }
  const veille = p && p.statut === "veille";

  $("#map").innerHTML = ETAPES.map((e, i) => {
    const de = taches.filter(t => t.etape === e);
    const done = de.length && de.every(t => t.etat === "fait");
    const isNow = i === (state.etape ?? etapeDuProjet(taches)) && !done;
    return `<div class="col${de.length ? "" : " vide"}"><h3><button type="button" class="steph" data-step="${e}">${i + 1}. ${NOM_ETAPES[e]}</button></h3>${
      de.map(t => { const st = normEtat(t.etat); return `<div class="node${veille ? " veille" : ""}" data-node="${esc(t.id)}" data-s="${st}">
        <div class="t">${esc(t.titre)}</div>
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
      <span style="margin-left:auto;display:flex;gap:6px"><button class="btn" data-act="newtask">+ Tâche</button><button class="btn${p.statut === "veille" ? " pri" : ""}" data-status="${p.statut === "veille" ? "actif" : "veille"}" data-proj="${esc(state.sel)}">${p.statut === "veille" ? "Réactiver" : "En veille"}</button></span></div>
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

// ---------- chargement de tout ce qui dépend du projet sélectionné ----------
async function loadProjet() {
  const id = state.sel;
  state.taches = []; state.executions = []; state.hist = null; state.liv = null; state.etape = null;
  if (!id) { renderTous(); return; }

  const [t, e, h, l] = await Promise.all([
    getJSON(`/api/v2/taches?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/executions?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/historique`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/revisions`),
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

  // enrichit la fiche projet pour la vue Projets (étape, taches) sans re-fetch
  const p = state.projets[id];
  if (p) {
    p.taches = state.taches;
    const idx = state.etape ?? etapeDuProjet(state.taches);
    p.etape = idx < ETAPES.length ? `Étape ${idx + 1}/${ETAPES.length} · ${NOM_ETAPES[ETAPES[idx]]}` : "terminé";
  }
  renderTous();
}

function renderTous() {
  renderRail(); renderProjets();
  $("#projhead").hidden = true;
  renderProjHead();
  renderEquipe(); renderCarte(); renderHist(); renderLivrable();
  syncNav();
}

// ---------- navigation ----------
function go(v) {
  state.view = v;
  document.querySelectorAll("#tabs [role=tab]").forEach(b => b.setAttribute("aria-selected", b.dataset.v === v));
  ["projets", "equipe", "carte", "hist", "livrable"].forEach(x => { const s = $("#v-" + x); if (s) s.hidden = (x !== v); });
  window.scrollTo(0, 0);
  syncNav();
}
function syncNav() {
  const m = $("#msel");
  if (m) m.innerHTML = [["projets","Projets"],["equipe","Équipe"],["carte","Carte"],["hist","Historique"],["livrable","Livrable"]].map(([v,l]) => `<option value="${v}"${v === state.view ? " selected" : ""}>${l}</option>`).join("");
  // rail aria-current sur la vue
  document.querySelectorAll(".rail [data-go]").forEach(b => b.setAttribute("aria-current", b.dataset.go === state.view));
}

// ---------- actions ----------
async function changerStatut(id, statut) {
  const r = await postJSON(`/api/v2/projects/${encodeURIComponent(id)}/status`, {status: statut});
  toast(r.ok ? `${id} → ${STATUTS[statut] || statut}` : `Changement refusé (route non branchée ou statut inconnu).`);
  if (r.ok) { await loadProjets(); await loadProjet(); }
}

async function nouveauProjet(e) {
  e.preventDefault();
  const nom = $("#np-nom").value.trim();
  if (!nom) { toast("Donne un nom au projet."); return; }
  const r = await postJSON("/api/projects", {name: nom, memory: $("#np-but").value.trim()});
  toast(r.ok ? `Projet « ${nom} » créé. claude le découpe.` : "Création refusée (route non branchée ou nom déjà pris).");
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

function ouvrirFiche(html) {
  $("#fiche-c").innerHTML = html;
  const d = $("#fiche");
  if (!d.open) { if (d.showModal) d.showModal(); else d.setAttribute("open", ""); }
  d.scrollTop = 0;
}
function fermerFiche() { const d = $("#fiche"); if (d.close) d.close(); else d.removeAttribute("open"); }
const enteteFiche = (sur, titre) => `<div class="fh"><div><div class="lbl">${esc(sur)}</div><h2 id="fiche-t">${esc(titre)}</h2></div><button class="btn" type="button" data-act="fermer" aria-label="Fermer">Fermer</button></div>`;

async function ouvrirTache(id) {
  const t = state.taches.find(x => String(x.id) === String(id));
  if (!t) return;
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
  const el = $("#fiche-h");
  if (!el) return;
  const lignes = [];
  ((m.ok && m.data && m.data.messages) || []).forEach(x => lignes.push({h: x.timestamp, html: `<b>${esc(x.sender)}</b> — ${esc(court(x.text, 400))}`}));
  ((e.ok && e.data && e.data.executions) || []).forEach(x => lignes.push({h: x.fin || x.debut,
    html: `<span class="type">exécution</span><b>${esc(x.agent)}</b>${x.role ? ` (${esc(x.role)})` : ""} — ${esc(court(x.consigne, 200))}${x.issue ? ` · ${esc(x.issue)}` : x.fin ? "" : " · en cours"}`}));
  lignes.sort((a, b) => (b.h || 0) - (a.h || 0));
  el.innerHTML = lignes.length
    ? lignes.map(l => `<li><time>${esc(heure(l.h))}</time><span>${l.html}</span></li>`).join("")
    : `<li class="cap">Aucun message ni exécution rattaché à cette tâche pour l'instant. « Discuter » ouvre sa conversation : tout ce qui s'y dit s'inscrit ici.</li>`;
}

function ouvrirEtape(e) {
  const i = ETAPES.indexOf(e);
  if (i < 0) return;
  const de = state.taches.filter(t => t.etape === e);
  const fait = de.filter(t => normEtat(t.etat) === "fait").length;
  const liste = de.length
    ? `<ul class="flist">${de.map(t => { const st = normEtat(t.etat); return `<li><button type="button" data-fiche="${esc(t.id)}"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span><span>${esc(t.titre)}</span>${t.resultat ? `<span class="cap">${esc(court(t.resultat, 160))}</span>` : ""}</button></li>`; }).join("")}</ul>`
    : `<p class="cap">Aucune tâche à cette étape pour l'instant.</p>`;
  ouvrirFiche(enteteFiche(`Étape ${i + 1} sur ${ETAPES.length}`, NOM_ETAPES[e]) +
    `<div class="fc"><div class="lbl">Ce que couvre l'étape</div><p>${esc(DEF_ETAPES[e])}</p></div>` +
    `<div class="fc"><div class="lbl">Tâches (${fait}/${de.length} faites)</div>${liste}</div>`);
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
  const fe = t.closest("[data-fiche]"); if (fe) return ouvrirTache(fe.dataset.fiche);
  const sp = t.closest("[data-step]"); if (sp) return ouvrirEtape(sp.dataset.step);
  const nd = t.closest("[data-node]"); if (nd) return ouvrirTache(nd.dataset.node);
  if (t.id === "fiche") return fermerFiche();  // clic sur le fond du dialogue
  const act = t.closest("[data-act]"); if (!act) return;
  if (act.dataset.act === "fermer") return fermerFiche();
  if (act.dataset.act === "newtask") { const f = $("#taskform"); f.hidden = !f.hidden; if (!f.hidden) $("#tk-t").focus(); }
  if (act.dataset.act === "canceltask") { $("#taskform").hidden = true; }
});
$("#msel").addEventListener("change", e => go(e.target.value));
$("#newproj").addEventListener("submit", nouveauProjet);
$("#taskform").addEventListener("submit", nouvelleTache);
window.addEventListener("resize", () => {});

// ---------- démarrage ----------
(async function init() {
  try { const v = localStorage.getItem("rd-view"); if (v) state.view = v; } catch (_) {}
  await loadProjets();
  await loadProjet();
  go(state.view || "projets");
})();
