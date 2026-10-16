import { choisirFantomes, BBOX_DEF } from './fantomes.js';
/* Atelier R&D · Vaultia — logique de la page (v3, 2026-10-16).
   Deux pages :
   - « Aujourd'hui » (#/) : tous projets confondus, ce qui t'attend (tâches attend_charles + jalons sans
     décision), qui travaille (tâches en cours ou bloquées, silences de la ronde), puis les projets ;
   - la page projet (#/p/<id>[/onglet]) : frise des étapes (filtre du tableau), tableau des tâches par état,
     pièces, historique, livrables.
   Ne lit que les routes du socle. Une route absente (404) donne un état vide propre ; toute autre erreur
   s'affiche. Aucun jeton, aucune donnée sensible n'est loggué (R3). */
"use strict";

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// ---------- icônes (grille 24, trait 1,75, bouts arrondis) ----------
const ICO = {
  chev: '<path d="m9.5 6 6 6-6 6"/>',
  chat: '<path d="M19.5 12a7.5 7.5 0 0 1-10.9 6.7L4.5 19.5l.9-3.8A7.5 7.5 0 1 1 19.5 12Z"/>',
  check: '<path d="m5.5 12.5 4 4 9-9"/>',
  alerte: '<path d="M12 4.5 3 19.5h18Z"/><path d="M12 10v4M12 16.8v.2"/>',
  jalon: '<path d="M12 3.5 20.5 12 12 20.5 3.5 12Z"/>',
  fermer: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  pause: '<path d="M9.5 6.5v11M14.5 6.5v11"/>',
  play: '<path d="M8.5 6v12l9.5-6Z"/>',
  bas: '<path d="m6 9.5 6 6 6-6"/>',
};
const ico = (n, cls = "ico") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICO[n]}</svg>`;

// ---------- étapes (pilote-rd) : la liste vient du serveur (`etapes`), celle-ci est le repli ----------
let ETAPES = ["probleme","etat_art","concepts","design_initial","conception","prototype","essais","industrialisation","lancement"];
const NOM_ETAPES = {probleme:"Problème",etat_art:"État de l'art",concepts:"Concepts",design_initial:"Design initial",conception:"Conception",prototype:"Prototype",essais:"Essais",industrialisation:"Industrialisation",lancement:"Lancement"};
const nomEtape = e => NOM_ETAPES[e] || String(e || "").replace(/_/g, " ");
// Ce que couvre chaque étape, en une ligne.
const DEF_ETAPES = {
  probleme: "Poser le problème : pour qui, quoi, pourquoi maintenant, et ce qui compte comme réussi.",
  etat_art: "Ce qui existe déjà (produits, code, publications) et pourquoi ça ne suffit pas.",
  concepts: "Les pistes possibles, comparées, et celle qu'on retient avec sa raison.",
  design_initial: "L'allure, la silhouette et le squelette de points durs, avant tout calcul de structure.",
  conception: "Le plan de la piste retenue : règles, découpage, interfaces, avant de produire.",
  prototype: "Construire une première version qui marche, livrée par PR et revue.",
  essais: "Éprouver le prototype en vrai : hypothèse, méthode, critère, résultat (RS&DE).",
  industrialisation: "Rendre le tout solide et durable : ménage, règles, exploitation.",
  lancement: "Mise en usage réelle et bilan.",
};
const STATUTS = {actif:"actif",veille:"en veille",termine:"terminé",arrete:"arrêté"};
const STATUT_CLS = {actif:"s-actif",veille:"s-veille",termine:"s-attente",arrete:"s-arrete"};
// Les états que S2 (jobs.py) renvoie : fait / en_cours / attend_charles / a_faire / bloque.
const ETAT_TACHE = {fait:"fait",en_cours:"en cours",attend_charles:"t'attend",a_faire:"à faire",bloque:"bloqué"};
const ETAT_CLS = {fait:"s-fait",en_cours:"s-cours",attend_charles:"s-charles",a_faire:"s-afaire",bloque:"s-bloque"};
const ETAT_EXEC = {actif:"actif",silencieux:"silencieux",fini:"fini"};
const normEtat = e => (e && ETAT_TACHE[e] ? e : (e === "cours" ? "en_cours" : e === "charles" ? "attend_charles" : e === "afaire" ? "a_faire" : "a_faire"));
// Colonnes du tableau, dans l'ordre de lecture : ce qui t'attend d'abord.
const COLONNES = [
  ["attend_charles", "T'attend"], ["en_cours", "En cours"], ["bloque", "Bloqué"], ["a_faire", "À faire"], ["fait", "Fait"],
];
const ONGLETS = ["taches", "pieces", "hist", "livrables"];
const SILENCE_S = 2 * 3600; // une tâche en cours sans nouvelle depuis 2 h est signalée

const state = {
  route: {page: "jour"},
  projets: {},       // id -> {nom, statut, objectif, parent_id, …}
  defaut: "",
  par: {},           // id -> {taches:[], etape:index|null, jalons:[]}  (chargé pour tous les projets)
  ronde: null,       // GET /api/v2/ronde
  alertes: [],       // ronde.alertes (sauvegarde, copie hors tour)
  agents: {},        // GET /api/status : {nom: {busy, color, label, role}}
  methodes: null,    // {etape: texte} (docs/PILOTE.md)
  maj: 0,            // heure de la dernière mise à jour globale (ms)
  // projet ouvert
  sel: null, taches: [], jalons: [], etape: null, fiche: null,
  executions: [], hist: null, liv: null, pieces: null, achats: null, cout: null,
  filtre: null,      // étape filtrée sur le tableau
  faitOuvert: false, // colonne « Fait » dépliée
  v3d: null, v3dSig: "",
};
// N3 : statuts de pièce (spec PIECES.md) — libellé + classe de pastille.
const PIECE_STATUT = {
  a_concevoir:["à concevoir","s-afaire"], concue:["conçue","s-cours"],
  a_commander:["à commander","s-attente"], commandee:["commandée","s-cours"],
  recue:["reçue","s-fait"], fabriquee:["fabriquée","s-fait"],
  validee:["validée","s-fait"], rejetee:["rejetée","s-bloque"],
};
const ORIGINE = {acheter:"acheter", concevoir:"concevoir"};
const PROCEDS = {laser:"laser", soudure:"soudure", cnc:"cnc", impression_3d:"impression 3D", achat:"achat"};

// ---------- réseau : état vide propre si la route n'est pas encore branchée ----------
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
  return code && code !== 404 ? `Erreur ${code} : vérifie que la salle est ouverte et que ton jeton est valide.` : "";
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

// ---------- temps ----------
const heure = ts => { if (ts == null) return ""; try { return new Date(ts * 1000).toLocaleString("fr-CA", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); } catch (_) { return ""; } };
const hm = ts => { if (ts == null) return ""; try { return new Date(ts * 1000).toLocaleTimeString("fr-CA", {hour:"2-digit",minute:"2-digit"}); } catch (_) { return ""; } };
function duree(s) {
  s = Math.max(0, s);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `${Math.round(s / 3600)} h`;
  return `${Math.round(s / 86400)} j`;
}
function ilya(ts) {
  if (!ts) return "";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "à l'instant";
  if (s < 86400) return `il y a ${duree(s)}`;
  const j = Math.round(s / 86400);
  return j === 1 ? "hier" : `il y a ${j} j`;
}
const jourLong = d => d.toLocaleDateString("fr-CA", {weekday: "long", day: "numeric", month: "long"});
const pluriel = (n, un, plusieurs) => `${n} ${n > 1 ? plusieurs : un}`;

// ---------- agents (couleur d'identité depuis /api/status, comme la salle) ----------
// La couleur peut venir de l'instance 1 (« claude » → « claude-1 ») ; l'état occupé, jamais : il est propre à l'instance.
function agentInfo(nom, exact = false) {
  const n = String(nom || "");
  const direct = state.agents[n] || state.agents[n.toLowerCase()];
  if (direct || exact) return direct || null;
  const base = n.toLowerCase().replace(/-\d+$/, "");
  return state.agents[base] || state.agents[base + "-1"] || null;
}
function agent(nom, petit = false) {
  if (!nom) return `<span class="ag${petit ? " petit" : ""}">—</span>`;
  const a = agentInfo(nom);
  const c = a && /^#[0-9a-f]{3,8}$/i.test(a.color || "") ? a.color : "";
  const libelle = /^charles$/i.test(nom) || nom === "user" ? "Charles" : nom;
  return `<span class="ag${petit ? " petit" : ""}"${c ? ` style="--c:${c}"` : ""}><i></i>${esc(libelle)}</span>`;
}
const occupe = nom => { const a = agentInfo(nom, true); return !!(a && a.busy); };

// ---------- chargement global : projets, ronde, agents, tâches et jalons de chaque projet ----------
async function chargerGlobal() {
  const [p, r, s, m] = await Promise.all([
    getJSON("/api/projects"),
    getJSON("/api/v2/ronde"),
    getJSON("/api/status"),
    state.methodes ? Promise.resolve(null) : getJSON("/api/v2/methodes"),
  ]);
  if (!p.ok || !p.data || !p.data.v2) {
    state.projets = {}; state.defaut = "";
    $("#note").hidden = false;
    // 404 = pas encore branché (état vide propre) ; 403/400/500 = erreur réelle, affichée.
    $("#note").textContent = p.msg || "Le socle n'a pas encore retourné de projet. L'atelier est prêt : les projets apparaîtront ici dès que la salle en aura.";
  } else {
    state.projets = p.data.v2.projets || {};
    state.defaut = p.data.v2.defaut || "";
    $("#note").hidden = true;
  }
  // U4 : on ne vide jamais les alertes sur une erreur transitoire (5xx, réseau) ; seulement sur 404 ou liste vide.
  if (r.err === 404) { state.ronde = null; state.alertes = []; }
  else if (r.ok && r.data) { state.ronde = r.data; if (Array.isArray(r.data.alertes)) state.alertes = r.data.alertes; }
  if (s.ok && s.data && typeof s.data === "object") state.agents = s.data;
  if (m && m.ok && m.data && typeof m.data === "object") state.methodes = m.data;

  const ids = Object.keys(state.projets);
  const res = await Promise.all(ids.map(id => Promise.all([
    getJSON(`/api/v2/taches?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/jalons`),
  ])));
  const par = {};
  ids.forEach((id, i) => {
    const [t, j] = res[i];
    const d = {taches: [], etape: null, jalons: [], ok: t.ok};
    if (t.ok && t.data) {
      // v0.2 : {taches, etape, etapes} ; v0.1 : liste nue. `etape` est le nom d'étape (ex. "concepts").
      if (Array.isArray(t.data)) d.taches = t.data;
      else {
        if (Array.isArray(t.data.etapes) && t.data.etapes.length && t.data.etapes.every(e => typeof e === "string")) ETAPES = t.data.etapes;
        d.taches = t.data.taches || [];
        const idx = t.data.etape ? ETAPES.indexOf(t.data.etape) : -1;
        d.etape = idx >= 0 ? idx : (d.taches.length ? ETAPES.length : 0);
      }
    }
    if (j.ok && j.data) d.jalons = j.data.jalons || (Array.isArray(j.data) ? j.data : []);
    par[id] = d;
  });
  state.par = par;
  state.maj = Date.now();
}
// Étape courante calculée localement si le serveur ne la donne pas.
function etapeDuProjet(taches) {
  for (let i = 0; i < ETAPES.length; i++) {
    if (taches.some(t => t.etape === ETAPES[i] && t.etat !== "fait")) return i;
  }
  return taches.length ? ETAPES.length : 0;
}
const idxEtape = id => { const d = state.par[id]; if (!d) return 0; return d.etape ?? etapeDuProjet(d.taches); };
// Silences : tâches muettes de la ronde (pas de message dans tache-<id>) et exécutions silencieuses.
function silences() {
  const m = new Map();
  const r = state.ronde || {};
  (r.taches_muettes || []).forEach(x => m.set(String(x.tache_id), x.silence_s || SILENCE_S));
  (r.silencieuses || []).forEach(x => { if (!m.has(String(x.tache_id))) m.set(String(x.tache_id), SILENCE_S); });
  return m;
}
const actif = id => (state.projets[id] || {}).statut !== "veille" && (state.projets[id] || {}).statut !== "arrete" && (state.projets[id] || {}).statut !== "termine";

// ---------- chargement du projet ouvert : ce qui ne sert qu'à sa page ----------
async function chargerProjet() {
  const id = state.sel;
  if (!id) return;
  const [e, h, l, pc, ac, co] = await Promise.all([
    getJSON(`/api/v2/executions?projet_id=${encodeURIComponent(id)}`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/historique`),
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/revisions`),
    getJSON(`/api/v2/pieces?projet_id=${encodeURIComponent(id)}`),       // N3 : pièces du projet
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/achats`),        // N3 : liste d'achats
    getJSON(`/api/v2/projects/${encodeURIComponent(id)}/cout`),          // N3 : coût cumulé
  ]);
  if (id !== state.sel) return; // un autre projet a été ouvert entre-temps
  state.executions = e.ok && e.data ? (Array.isArray(e.data) ? e.data : (e.data.executions || [])) : [];
  state.hist = h.ok && h.data ? h.data : null;
  state.liv = l.ok && l.data ? l.data : null;
  state.pieces = pc.ok && pc.data ? pc.data : null;
  state.achats = ac.ok && ac.data ? ac.data : null;
  state.cout = co.ok && co.data ? co.data : null;
}
// Recopie dans `state` ce qui a été chargé pour tous les projets (tâches, étape, jalons, fiche).
function synchroSel() {
  const d = state.par[state.sel] || {taches: [], etape: null, jalons: []};
  state.taches = d.taches; state.jalons = d.jalons; state.etape = d.etape;
  state.fiche = state.projets[state.sel] || null;
}

// =====================================================================================
// Rail
// =====================================================================================
function attentesDe(id) {
  const d = state.par[id]; if (!d) return 0;
  return d.taches.filter(t => normEtat(t.etat) === "attend_charles").length + d.jalons.filter(j => !j.decision).length;
}
function renderRail() {
  const ids = Object.keys(state.projets);
  const ligne = (id, enfant) => {
    const p = state.projets[id];
    const n = attentesDe(id);
    const i = idxEtape(id);
    const st = n ? `<b class="badge" title="${pluriel(n, "décision t'attend", "décisions t'attendent")}">${n}</b>`
      : `<span class="st">${!actif(id) ? esc(STATUTS[p.statut] || p.statut) : (state.par[id] && state.par[id].taches.length ? (i < ETAPES.length ? esc(nomEtape(ETAPES[i])) : "terminé") : "")}</span>`;
    const courant = state.route.page === "projet" && state.sel === id;
    return `<a class="proj${enfant ? " enfant" : ""}${actif(id) ? "" : " endormi"}" href="#/p/${encodeURIComponent(id)}"${courant ? ' aria-current="page"' : ""}><span class="pn" title="${esc(p.nom || id)}">${esc(p.nom || id)}</span>${st}</a>`;
  };
  // Arbre : les projets sans parent, leurs sous-projets (parent_id) en retrait ; actifs d'abord.
  const ordre = (a, b) => (actif(b) - actif(a)) || attentesDe(b) - attentesDe(a);
  const racines = ids.filter(id => !state.projets[id].parent_id || !state.projets[state.projets[id].parent_id]).sort(ordre);
  const enfants = id => ids.filter(x => state.projets[x].parent_id === id);
  $("#rail-proj").innerHTML = racines.map(id => ligne(id, false) + enfants(id).map(e => ligne(e, true)).join("")).join("")
    || `<div class="rail-vide">Aucun projet</div>`;
  const total = ids.reduce((n, id) => n + attentesDe(id), 0);
  const b = $("#badge-jour"); b.hidden = !total; b.textContent = total;
  $$('.rail [data-nav="jour"]').forEach(a => { if (state.route.page === "jour") a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
}

// =====================================================================================
// Aujourd'hui
// =====================================================================================
function renderAlertes() {
  const el = $("#alertes"); if (!el) return;
  const liste = state.alertes || [];
  if (!liste.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = `${ico("alerte")}<div><b>${pluriel(liste.length, "alerte", "alertes")}</b><ul>${liste.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>`;
}

function renderJour() {
  const ids = Object.keys(state.projets);
  const sil = silences();
  // 1. Ce qui t'attend : tâches attend_charles et jalons sans décision, la plus ancienne d'abord.
  const attend = [];
  for (const id of ids) {
    const d = state.par[id]; if (!d) continue;
    d.taches.filter(t => normEtat(t.etat) === "attend_charles").forEach(t => attend.push({type: "tache", id, t, h: t.updated_at || t.created_at}));
    d.jalons.filter(j => !j.decision).forEach(j => attend.push({type: "jalon", id, j, h: j.date}));
  }
  attend.sort((a, b) => (a.h || 0) - (b.h || 0));
  // 2. Au travail : tâches en cours ou bloquées des projets actifs ; les silencieuses d'abord.
  const travail = [];
  for (const id of ids) {
    if (!actif(id)) continue;
    (state.par[id] ? state.par[id].taches : []).forEach(t => {
      const st = normEtat(t.etat);
      if (st === "en_cours" || st === "bloque") travail.push({id, t, st, silence: sil.get(String(t.id)) || 0});
    });
  }
  travail.sort((a, b) => (b.st === "bloque") - (a.st === "bloque") || (b.silence > 0) - (a.silence > 0) || (b.t.updated_at || 0) - (a.t.updated_at || 0));

  $("#jour-date").textContent = jourLong(new Date()).replace(/^./, c => c.toUpperCase());
  $("#maj").textContent = state.maj ? `À jour à ${new Date(state.maj).toLocaleTimeString("fr-CA", {hour: "2-digit", minute: "2-digit"})}` : "";
  const muettes = travail.filter(x => x.silence >= SILENCE_S).length;
  const bloquees = travail.filter(x => x.st === "bloque").length;
  const morceaux = [
    attend.length ? `<b>${pluriel(attend.length, "décision t'attend", "décisions t'attendent")}</b>` : "Rien ne t'attend",
    travail.length ? pluriel(travail.length, "tâche en cours", "tâches en cours") : "aucune tâche en cours",
  ];
  if (bloquees) morceaux.push(`<b>${pluriel(bloquees, "bloquée", "bloquées")}</b>`);
  if (muettes) morceaux.push(`${pluriel(muettes, "sans nouvelles depuis plus de 2 h", "sans nouvelles depuis plus de 2 h")}`);
  $("#jour-resume").innerHTML = morceaux.join(" · ") + ".";

  // T'attend
  $("#n-attend").textContent = attend.length || "";
  $("#attend").innerHTML = attend.length
    ? `<div class="liste attend">${attend.map(x => {
        const p = state.projets[x.id] || {};
        if (x.type === "jalon") {
          const j = x.j;
          const fin = j.jalon === "J1" ? "fin des concepts" : j.jalon === "J2" ? "fin des essais" : "avant le lancement";
          return `<div class="ligne" role="button" tabindex="0" data-ouvrir-etape="${esc(etapeDuJalon(j.jalon))}" data-p="${esc(x.id)}">
            <div><div class="ligne-t"><span class="tag-jalon">${ico("jalon")}${esc(JALON_NOM[j.jalon] || j.jalon)}</span> · décider de la suite</div>
            <div class="ligne-m"><span>${esc(p.nom || x.id)}</span><span class="sep">·</span><span>${esc(fin)}</span>${j.recommandation ? `<span class="sep">·</span><span>claude recommande : ${esc(JALON_DECISIONS[j.recommandation] || j.recommandation)}</span>` : ""}${x.h ? `<span class="sep">·</span><span>depuis ${esc(ilya(x.h).replace(/^il y a /, ""))}</span>` : ""}</div></div>
            <div class="ligne-a">${ico("chev", "chev")}</div></div>`;
        }
        const t = x.t;
        return `<div class="ligne" role="button" tabindex="0" data-fiche="${esc(t.id)}" data-p="${esc(x.id)}">
          <div><div class="ligne-t">${esc(t.titre)}</div>
          <div class="ligne-m"><span>${esc(p.nom || x.id)}</span><span class="sep">·</span><span>${esc(nomEtape(t.etape))}</span><span class="sep">·</span>${agent(t.responsable, true)}${x.h ? `<span class="sep">·</span><span>depuis ${esc(ilya(x.h).replace(/^il y a /, ""))}</span>` : ""}</div></div>
          <div class="ligne-a"><button class="btn mini" type="button" data-disc="${esc(t.id)}">${ico("chat")}Discuter</button>${ico("chev", "chev")}</div></div>`;
      }).join("")}</div>`
    : `<div class="vide"><b>Rien ne t'attend.</b> Quand un agent a besoin de ta décision, elle arrive ici en premier.</div>`;

  // Au travail
  $("#n-travail").textContent = travail.length || "";
  $("#travail").innerHTML = travail.length
    ? `<div class="liste travail">${travail.map(x => {
        const p = state.projets[x.id] || {};
        const t = x.t;
        const etat = x.st === "bloque" ? `<span class="pill s-bloque">bloqué</span>`
          : x.silence >= SILENCE_S ? `<span class="pill s-silence" title="Aucun message dans la conversation de la tâche">rien depuis ${esc(duree(x.silence))}</span>`
          : `<span class="quand">${esc(ilya(t.updated_at))}</span>`;
        return `<div class="ligne" role="button" tabindex="0" data-fiche="${esc(t.id)}" data-p="${esc(x.id)}">
          <div>${agent(t.responsable)}${occupe(t.responsable) ? `<span class="ag-occupe">en train d'écrire</span>` : ""}</div>
          <div><div class="ligne-t">${esc(t.titre)}</div><div class="ligne-m"><span>${esc(p.nom || x.id)}</span><span class="sep">·</span><span>${esc(nomEtape(t.etape))}</span></div></div>
          <div class="ligne-a">${etat}${ico("chev", "chev")}</div></div>`;
      }).join("")}</div>`
    : `<div class="vide"><b>Personne n'est sur une tâche en ce moment.</b> Quand claude assigne une tâche, l'agent apparaît ici avec son dernier signe de vie.</div>`;

  // Projets
  const poids = id => (state.par[id] && state.par[id].taches.length ? 1000 : 0) + attentesDe(id) * 10 + (state.par[id] ? state.par[id].taches.filter(t => normEtat(t.etat) === "en_cours").length : 0);
  const actifs = ids.filter(actif).sort((a, b) => poids(b) - poids(a)), dormants = ids.filter(id => !actif(id));
  $("#n-projets").textContent = ids.length || "";
  const ligneProjet = id => {
    const p = state.projets[id];
    const d = state.par[id] || {taches: []};
    const i = idxEtape(id);
    const n = d.taches.length;
    const fait = d.taches.filter(t => normEtat(t.etat) === "fait").length;
    const cours = d.taches.filter(t => normEtat(t.etat) === "en_cours").length;
    const bloque = d.taches.filter(t => normEtat(t.etat) === "bloque").length;
    const att = attentesDe(id);
    const etape = !n ? "Pas encore de tâche" : i < ETAPES.length ? `Étape ${i + 1} sur ${ETAPES.length} · ${nomEtape(ETAPES[i])}` : "Toutes les étapes terminées";
    const chips = [
      att ? `<span class="pill s-charles">${pluriel(att, "t'attend", "t'attendent")}</span>` : "",
      bloque ? `<span class="pill s-bloque">${pluriel(bloque, "bloquée", "bloquées")}</span>` : "",
      cours ? `<span class="pill s-cours">${cours} en cours</span>` : "",
    ].join("");
    return `<a class="ligne${actif(id) ? "" : " endormi"}" href="#/p/${encodeURIComponent(id)}">
      <div style="min-width:0"><div class="p-nom">${esc(p.nom || id)}${actif(id) ? "" : `<span class="pill ${STATUT_CLS[p.statut] || "s-attente"}">${esc(STATUTS[p.statut] || p.statut)}</span>`}</div>${p.objectif ? `<div class="p-obj" title="${esc(p.objectif)}">${esc(p.objectif)}</div>` : ""}</div>
      <div>${frise(i, n)}<div class="p-etape"><span>${esc(etape)}</span>${n ? `<span>${fait}/${n} faites</span>` : ""}</div></div>
      <div class="p-chips">${chips}</div>
      ${ico("chev", "chev")}</a>`;
  };
  $("#projets").innerHTML = ids.length
    ? `<div class="liste projets">${actifs.map(ligneProjet).join("")}</div>` +
      (dormants.length ? `<div class="sous-titre">En veille ou terminés</div><div class="liste projets">${dormants.map(ligneProjet).join("")}</div>` : "")
    : `<div class="vide"><b>Aucun projet pour l'instant.</b> Lance le premier : claude découpe le travail et assigne les agents.</div>`;
}
// Petite frise : une case par étape, pleine si passée, demi-teinte pour l'étape en cours.
function frise(i, n) {
  return `<div class="frise" style="--n:${ETAPES.length}" aria-hidden="true">${ETAPES.map((_, k) => `<i class="${!n ? "" : k < i ? "fait" : k === i ? "now" : ""}"></i>`).join("")}</div>`;
}

// =====================================================================================
// Page projet
// =====================================================================================
function renderProjet() {
  const id = state.sel; const p = state.projets[id];
  if (!p) return;
  synchroSel();
  const taches = state.taches;
  const idx = state.etape ?? etapeDuProjet(taches);
  $("#fil-nom").textContent = p.nom || id;
  $("#p-nom").textContent = p.nom || id;
  $("#p-statut").innerHTML = actif(id) ? "" : `<span class="pill ${STATUT_CLS[p.statut] || "s-attente"}">${esc(STATUTS[p.statut] || p.statut || "?")}</span>`;
  const bv = $("#p-veille");
  const enVeille = p.statut === "veille";
  bv.dataset.proj = id; bv.dataset.status = enVeille ? "actif" : "veille";
  bv.innerHTML = enVeille ? `${ico("play")}<span class="lib">Réactiver</span>` : `${ico("pause")}<span class="lib">Mettre en veille</span>`;
  bv.setAttribute("aria-label", enVeille ? "Réactiver le projet" : "Mettre le projet en veille");
  const obj = $("#p-objectif"); obj.hidden = !p.objectif; obj.textContent = p.objectif || "";

  // En direct : les exécutions actives ou silencieuses de ce projet.
  const live = state.executions.filter(e => e.etat === "actif" || e.etat === "silencieux");
  const vus = new Map();
  live.forEach(e => { if (!vus.has(e.agent) || e.etat === "actif") vus.set(e.agent, e); });
  const dir = $("#p-direct");
  dir.hidden = !vus.size;
  dir.innerHTML = vus.size ? `<span>En direct</span>${[...vus.values()].map(e => `<span>${agent(e.agent, true)}${e.role ? ` <span class="role">${esc(e.role)}</span>` : ""}${e.etat === "silencieux" ? ` <span class="pill s-silence">silencieux</span>` : ""}</span>`).join("")}` : "";

  renderEtapes(idx);
  // compteurs des onglets
  $("#o-taches").textContent = taches.length || "";
  $("#o-pieces").textContent = state.pieces && state.pieces.pieces ? (state.pieces.pieces.length || "") : "";
  $("#o-livrables").textContent = state.liv && state.liv.livrables ? (state.liv.livrables.length || "") : "";
  $("#tk-c").innerHTML = ETAPES.map((e, i) => `<option value="${esc(e)}"${i === Math.min(idx, ETAPES.length - 1) ? " selected" : ""}>${i + 1}. ${esc(nomEtape(e))}</option>`).join("");
  renderTableau();
  renderOnglet();
}

// Où vit un jalon sur la frise : J1 à la fin des concepts, J2 à la fin des essais, la revue avant le lancement.
const etapeDuJalon = j => j === "J1" ? "concepts" : j === "J2" ? "essais" : "industrialisation";
function renderEtapes(idx) {
  const taches = state.taches;
  const ol = $("#p-etapes");
  ol.style.setProperty("--n", ETAPES.length);
  ol.innerHTML = ETAPES.map((e, i) => {
    const de = taches.filter(t => t.etape === e);
    const cls = i < idx ? "fait" : i === idx ? "now" : "";
    const jal = state.jalons.filter(j => etapeDuJalon(j.jalon) === e);
    const enAttente = jal.some(j => !j.decision);
    const marque = jal.length ? `<button type="button" class="jal ${enAttente ? "attend" : "decide"}" data-ouvrir-etape="${esc(e)}" title="${esc(jal.map(j => (JALON_NOM[j.jalon] || j.jalon) + (j.decision ? " : décidé (" + (JALON_DECISIONS[j.decision] || j.decision) + ")" : " : t'attend")).join(" · "))}" aria-label="Jalon">${ico("jalon", "")}</button>` : "";
    return `<li class="${cls}"><button type="button" class="etape" data-filtre="${esc(e)}" aria-pressed="${(state.route.onglet || "taches") === "taches" && state.filtre === e}" title="${esc(DEF_ETAPES[e] || "")}"><i>${i < idx ? ico("check", "") : i + 1}</i><span>${esc(nomEtape(e))}</span><span class="nb">${de.length ? `${de.filter(t => normEtat(t.etat) === "fait").length}/${de.length}` : ""}</span></button>${marque}</li>`;
  }).join("");
  if (ol.dataset.projet !== state.sel) {
    ol.dataset.projet = state.sel;
    const w = ol.parentElement, now = ol.querySelector(".now");
    if (now && w.scrollWidth > w.clientWidth) w.scrollLeft = Math.max(0, now.offsetLeft - (w.clientWidth - now.offsetWidth) / 2);
  }
  const info = $("#p-etape-info");
  const f = (state.route.onglet || "taches") === "taches" ? state.filtre : null;
  if (f) {
    const i = ETAPES.indexOf(f);
    const n = taches.filter(t => t.etape === f).length;
    info.className = "etape-info filtre";
    info.innerHTML = `<span class="def"><b>Filtré sur l'étape ${i + 1} · ${esc(nomEtape(f))}</b> : ${pluriel(n, "tâche", "tâches")}. ${esc(DEF_ETAPES[f] || "")}</span><button class="btn mini" type="button" data-ouvrir-etape="${esc(f)}">Méthode et jalons</button><button class="btn mini discret" type="button" data-filtre="">${ico("fermer")}Toutes les étapes</button>`;
  } else {
    info.className = "etape-info";
    const e = ETAPES[idx];
    info.innerHTML = idx < ETAPES.length
      ? `<span class="def"><b>Étape ${idx + 1} sur ${ETAPES.length} · ${esc(nomEtape(e))}</b> : ${esc(DEF_ETAPES[e] || "")}</span><button class="btn mini" type="button" data-ouvrir-etape="${esc(e)}">Méthode et jalons</button>`
      : `<span class="def"><b>Toutes les étapes sont terminées.</b></span>`;
  }
}

function renderTableau() {
  const sil = silences();
  const taches = state.filtre ? state.taches.filter(t => t.etape === state.filtre) : state.taches;
  const veille = !actif(state.sel);
  const cols = COLONNES.filter(([k]) => state.filtre ? taches.some(t => normEtat(t.etat) === k) : (k !== "bloque" || taches.some(t => normEtat(t.etat) === "bloque")));
  if (state.filtre && !taches.length) {
    $("#tableau").style.setProperty("--cols", 1);
    $("#tableau").innerHTML = `<div class="vide"><b>Aucune tâche à l'étape ${ETAPES.indexOf(state.filtre) + 1} · ${esc(nomEtape(state.filtre))}.</b> Elle n'a pas encore commencé, ou elle n'a pas demandé de tâche.</div>`;
    return;
  }
  const el = $("#tableau");
  el.style.setProperty("--cols", cols.length);
  if (!state.taches.length) {
    el.style.setProperty("--cols", 1);
    el.innerHTML = `<div class="vide"><b>Aucune tâche dans ce projet.</b> claude découpe le travail au lancement ; tu peux aussi en ajouter une avec « Tâche ».</div>`;
    return;
  }
  el.innerHTML = cols.map(([k, titre]) => {
    let liste = taches.filter(t => normEtat(t.etat) === k);
    // les plus récentes en haut ; « Fait » replié au-delà de 4
    liste.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    const total = liste.length;
    let plus = "";
    if (k === "fait" && total > 4 && !state.faitOuvert) { liste = liste.slice(0, 4); plus = `<button class="btn mini discret plus-fait" type="button" data-act="fait-tout">${ico("bas")}Voir les ${total - 4} autres</button>`; }
    else if (k === "fait" && total > 4) plus = `<button class="btn mini discret plus-fait" type="button" data-act="fait-tout">Replier</button>`;
    const vides = {attend_charles: "Rien ne t'attend ici.", en_cours: "Personne n'y travaille.", a_faire: "Rien en file.", fait: "Rien de terminé encore."};
    return `<section class="col" aria-label="${esc(titre)}"><div class="col-h">${esc(titre)}<span class="compte">${total || ""}</span></div><div class="col-c">${
      liste.map(t => carte(t, k, sil, veille)).join("") || `<div class="col-vide">${vides[k] || "—"}</div>`}${plus}</div></section>`;
  }).join("");
}
function carte(t, k, sil, veille) {
  const s = sil.get(String(t.id)) || 0;
  const cls = k === "attend_charles" ? " attend" : k === "bloque" ? " bloque" : k === "fait" ? " fait" : "";
  const texte = k === "fait" ? (t.conclusion || t.resultat) : k === "attend_charles" ? (t.conclusion || t.critere) : "";
  const quand = k === "en_cours" && s >= SILENCE_S ? `<span class="pill s-silence">rien depuis ${esc(duree(s))}</span>` : `<span class="quand">${esc(ilya(t.updated_at))}</span>`;
  return `<article class="carte${cls}"${veille ? ' style="opacity:.7"' : ""} role="button" tabindex="0" data-fiche="${esc(t.id)}" aria-label="${esc(t.titre)}">
    ${k !== "fait" ? `<button class="ibtn disc" type="button" data-disc="${esc(t.id)}" aria-label="Discuter de cette tâche" title="Discuter">${ico("chat")}</button>` : ""}
    ${state.filtre ? "" : `<div class="carte-e">${ETAPES.indexOf(t.etape) + 1 || "?"}. ${esc(nomEtape(t.etape))}</div>`}
    <div class="carte-t">${esc(t.titre)}</div>
    ${texte ? `<div class="carte-p">${esc(court(texte, 220))}</div>` : ""}
    <div class="carte-m">${agent(t.responsable, true)}${quand}</div>
  </article>`;
}

// ---------- onglets ----------
function renderOnglet() {
  const o = state.route.onglet || "taches";
  renderEtapes(state.etape ?? etapeDuProjet(state.taches));
  $$("#onglets [role=tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.onglet === o)));
  ONGLETS.forEach(x => { $("#t-" + x).hidden = x !== o; });
  if (o === "pieces") { renderPieces(); renderVue3D(); }
  if (o === "hist") renderHist();
  if (o === "livrables") renderLivrable();
}

// ---------- historique : [[jour, [entrées]]] ----------
const TYPE_HIST = {execution: "exécution", message: "message", decision: "décision", jalon: "jalon", revision: "révision", tache: "tâche"};
function renderHist() {
  const el = $("#hlist");
  if (!state.hist) { el.innerHTML = `<div class="vide"><b>Pas d'historique pour ce projet.</b> Les exécutions, décisions, messages et révisions apparaîtront ici, jour par jour.</div>`; return; }
  if (!Array.isArray(state.hist) || !state.hist.length) { el.innerHTML = `<div class="vide">Rien dans l'historique pour l'instant.</div>`; return; }
  el.innerHTML = state.hist.map(([jour, entrees]) => {
    let lib = jour;
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(jour || "");
    if (m) { const d = new Date(+m[1], +m[2] - 1, +m[3]); lib = jourLong(d).replace(/^./, c => c.toUpperCase()); }
    return `<div class="jour-h">${esc(lib)}</div>` + (entrees || []).map(en =>
      `<div class="ev"><time>${esc(hm(en.heure))}</time><div><div class="ev-h">${agent(en.acteur, true)}<span class="ev-type">${esc(TYPE_HIST[en.type] || en.type || "")}</span></div><div class="ev-r" title="Cliquer pour tout lire">${livInline(aplatir(en.resume))}</div></div></div>`).join("");
  }).join("");
}

// ---------- livrables + révisions ----------
function renderLivrable() {
  const tbl = $("#liv-tbl"), cap = $("#liv-cap"), rev = $("#liv-rev"), b = $("#btn-approuver");
  const revisions = (state.liv && state.liv.revisions) || [];
  b.textContent = "Approuver (figer P" + String(revisions.length + 1).padStart(2, "0") + ")";
  if (!state.liv) {
    cap.textContent = "";
    rev.innerHTML = `<div class="vide">Aucune révision figée pour l'instant. « Approuver » fige les livrables actuels en P01, P02…</div>`;
    $("#liv-tbl").innerHTML = `<tr><td><div class="vide">Les livrables du projet apparaîtront ici dès que les agents en déposeront.</div></td></tr>`;
    return;
  }
  const liv = state.liv.livrables || [];
  tbl.innerHTML = liv.length
    ? `<tr><th>Fichier</th><th>Version</th><th class="n">Empreinte</th><th></th></tr>` + liv.map(l => `<tr><td style="overflow-wrap:anywhere">${esc(l.chemin)}</td><td>${esc(l.version)}</td><td class="n"><code>${esc((l.empreinte || "").slice(0, 12))}</code></td><td class="n"><button class="btn mini" type="button" data-voir="${esc(l.chemin)}">Voir</button></td></tr>`).join("")
    : `<tr><td><div class="vide">Aucun livrable pour l'instant.</div></td></tr>`;
  cap.textContent = liv.length ? pluriel(liv.length, "fichier", "fichiers") : "";
  rev.innerHTML = revisions.length
    ? revisions.slice().reverse().map(r => `<div class="rev"><div class="hd"><b>${esc(r.numero)}</b><span class="pill s-fait">figée</span><span class="cap">${esc(r.approuvee_par === "user" ? "Charles" : r.approuvee_par || "")} · ${esc(heure(r.heure))}</span></div><div class="chips" style="margin-top:8px">${(r.livrables || []).map(l => `<span class="chip">${esc(l.chemin)} · v${esc(l.version)}</span>`).join("")}</div></div>`).join("")
    : `<div class="vide">Aucune révision figée. « Approuver » fige les livrables actuels.</div>`;
}
async function approuver() {
  const r = await postJSON(`/api/v2/projects/${encodeURIComponent(state.sel)}/revisions`, {approuvee_par: "user"});
  toast(r.ok ? `Révision ${r.data && r.data.numero ? r.data.numero : ""} figée.` : "Approuver n'a pas abouti (route non branchée ou refus).");
  if (r.ok) await rafraichir();
}

// ---------- pièces (N3) : tableau filtrable, fiche pièce, nomenclature en arbre, achats ----------
const fmtCAD = (n, dev = "CAD") => { if (n == null || isNaN(n)) return "—"; return dev + " " + Number(n).toLocaleString("fr-CA", {minimumFractionDigits: 2, maximumFractionDigits: 2}); };
function pillStatutPiece(s) {
  const [lib, cls] = PIECE_STATUT[s] || [s || "?", "s-attente"];
  return `<span class="pill ${cls}">${esc(lib)}</span>`;
}
function renderPieces() {
  const el = $("#pc-tbl"), f = $("#pc-q"), sel = $("#pc-f");
  if (!el) return;
  if (!state.sel) { el.innerHTML = ""; renderAchats(); return; }
  if (!state.pieces) {
    el.innerHTML = `<tr><td><div class="vide">Les pièces de ce projet apparaîtront ici. Les agents y enregistrent chaque pièce conçue ou achetée, sa révision, son statut et ses offres.</div></td></tr>`;
    renderAchats(); renderEclatee();
    return;
  }
  const choisi = sel.value;
  const statutsVus = [...new Set((state.pieces.pieces || []).map(p => p.statut).filter(Boolean))];
  sel.innerHTML = `<option value="">Tous les statuts</option>` + statutsVus.map(s => `<option value="${esc(s)}"${s === choisi ? " selected" : ""}>${esc((PIECE_STATUT[s] || [s])[0])}</option>`).join("");
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
  const coupe = !q && !fs && !state.pcTout && n > 25;
  const vue = coupe ? list.slice(0, 25) : list;
  $("#pc-cap").textContent = n ? pluriel(n, "pièce", "pièces") : (state.pieces.pieces && state.pieces.pieces.length ? "aucune ne correspond au filtre" : "aucune pièce");
  el.innerHTML = n
    ? `<tr><th>N°</th><th>Nom</th><th class="n">Rév.</th><th>Origine</th><th>Statut</th><th class="n">Masse</th></tr>` +
      vue.map(p => `<tr class="pc-row" data-piece="${esc(p.id)}" tabindex="0">
        <td><code>${esc(p.numero || "")}</code></td>
        <td><b>${esc(p.nom || "")}</b>${p.sous_systeme ? `<div class="sub">${esc(p.sous_systeme)}</div>` : ""}</td>
        <td class="n">${esc(p.revision || "")}</td>
        <td>${esc(ORIGINE[p.origine] || p.origine || "")}</td>
        <td>${pillStatutPiece(p.statut)}</td>
        <td class="n">${p.masse_g != null ? esc(p.masse_g) + " g" : ""}</td>
      </tr>`).join("") +
      (coupe ? `<tr><td colspan="6"><button class="btn mini discret" type="button" data-act="pc-tout">${ico("bas")}Voir les ${n - 25} autres pièces</button></td></tr>` : "")
    : `<tr><td><div class="vide">Aucune pièce.</div></td></tr>`;
  renderAchats();
  renderEclatee();
}

// U6 : sous-ensembles — un bloc par enfant de l'assemblage de tête, avec la part de pièces faites.
let ECLATEE_N = 0;
async function renderEclatee() {
  const el = $("#pc-eclatee"); if (!el) return;
  const n = ++ECLATEE_N;
  if (!state.sel) { el.innerHTML = ""; return; }
  const pieces = state.pieces && state.pieces.pieces || [];
  const racine = pieces.find(p => p.type === "assemblage" && !p.sous_systeme);
  if (!racine) { el.innerHTML = `<p class="cap">Aucun assemblage de tête pour ce projet.</p>`; return; }
  const r = await getJSON(`/api/v2/pieces/${encodeURIComponent(racine.id)}/nomenclature`);
  if (n !== ECLATEE_N) return;
  if (!r.ok || !r.data) {
    el.innerHTML = r.err === 404 ? `<p class="cap">Aucune nomenclature pour l'instant.</p>`
      : `<p class="cap" style="color:var(--v-danger)">${r.err ? "Erreur " + r.err : "Erreur réseau"} : impossible de charger la nomenclature.</p>`;
    return;
  }
  const fait = new Set(["validee", "fabriquee", "recue"]);
  const compter = noeud => {
    let total = 0, faits = 0;
    for (const e of (noeud.enfants || [])) {
      if (e.statut === "rejetee") continue;
      total++;
      if (fait.has(e.statut)) faits++;
      const sub = compter(e);
      total += sub.total; faits += sub.faits;
    }
    return {total, faits};
  };
  const se = r.data.enfants || [];
  if (!se.length) { el.innerHTML = `<p class="cap">Aucun sous-ensemble dans la nomenclature.</p>`; return; }
  el.innerHTML = se.map(s => {
    const {total, faits} = compter(s);
    const part = total ? faits / total : 0;
    return `<button type="button" class="eclatee-bloc" data-piece="${esc(s.id)}" title="${esc(s.nom)} : ${faits}/${total} pièces faites">
      <b>${esc(s.nom)}</b><span class="jauge"><i style="width:${Math.round(part * 100)}%"></i></span><span class="cap">${faits}/${total} faites</span></button>`;
  }).join("");
}

// Fiche d'une pièce : offres sourcées, où elle est utilisée, nomenclature, plans, historique.
async function ouvrirPiece(id) {
  const base = (state.pieces && state.pieces.pieces || []).find(p => String(p.id) === String(id));
  const tete = enteteFiche(`Pièce ${base ? base.numero || "" : ""}`, base ? (base.nom || "") : "");
  ouvrirFiche(tete + `<div class="fc"><p class="cap">Chargement…</p></div>`);
  const r = await getJSON(`/api/v2/pieces/${encodeURIComponent(id)}`);
  if (!$("#fiche-c")) return;
  if (!r.ok || !r.data) {
    $("#fiche-c").innerHTML = tete + `<div class="fc"><p class="cap" style="color:var(--v-danger)">Impossible de charger cette pièce (route non branchée ou pièce inconnue).</p></div>`;
    return;
  }
  const p = r.data;
  const meta = `<div class="fm">${pillStatutPiece(p.statut)}<span>Rév. <b>${esc(p.revision || "")}</b></span><span>Origine : <b>${esc(ORIGINE[p.origine] || p.origine || "—")}</b></span>${p.matiere ? `<span>Matière : ${esc(p.matiere)}</span>` : ""}${p.procede ? `<span>Procédé : ${esc(PROCEDS[p.procede] || p.procede)}</span>` : ""}${p.masse_g != null ? `<span>${esc(p.masse_g)} g</span>` : ""}</div>`;
  const offres = (p.offres || []);
  const offresHtml = offres.length
    ? `<div class="fc"><span class="lbl">Offres (${offres.length})</span><ul class="fhist">${offres.map(o => `<li><time>${esc(o.devise || "CAD")}</time><span><b>${esc(o.reference || "")}</b>${o.fournisseur ? ` <span class="cap">(${esc(o.fournisseur.nom || o.fournisseur)})</span>` : ""} · ${fmtCAD(o.prix, o.devise)}${o.livraison != null ? " + liv. " + fmtCAD(o.livraison, o.devise) : ""}${lienSource(o.source)}${o.date ? ` <span class="cap">${esc(heure(o.date))}</span>` : ""}</span></li>`).join("")}</ul></div>`
    : (p.origine === "acheter" ? `<div class="fc"><span class="lbl">Offres</span><p class="cap" style="color:var(--v-warning)">Aucune offre sourcée. grok magasine au moins 3 offres pour cette pièce.</p></div>` : "");
  const ud = p.utilisee_dans || [];
  const utiliseeHtml = ud.length
    ? `<div class="fc"><span class="lbl">Où elle est utilisée</span><ul class="flist">${ud.map(u => `<li><span><code>${esc(u.numero || "")}</code> <b>${esc(u.nom || "")}</b></span><span class="cap" style="margin:0">×${esc(u.quantite != null ? u.quantite : "")}${u.unite ? " " + esc(u.unite) : ""}</span></li>`).join("")}</ul></div>`
    : `<div class="fc"><span class="lbl">Où elle est utilisée</span><p class="cap">Pas rattachée à un assemblage pour l'instant (pièce racine ou orpheline).</p></div>`;
  const nomHtml = `<div class="fc"><span class="lbl">Dont elle est faite</span><div id="pc-arbre"><p class="cap">Chargement…</p></div></div>`;
  const hist = (p.historical || p.historique || []);
  const histHtml = hist.length
    ? `<div class="fc"><span class="lbl">Historique</span><ul class="fhist">${hist.slice().reverse().map(h => `<li><time>${esc(heure(h.date))}</time><span>${esc(h.champ || "")} : ${esc(h.avant || "—")} → <b>${esc(h.apres || "—")}</b>${h.qui ? ` <span class="cap">(${esc(h.qui)})</span>` : ""}</span></li>`).join("")}</ul></div>`
    : "";
  const fichier = p.fichier ? `<div class="fc"><span class="lbl">Fichier</span><p><code>${esc(p.fichier)}</code>${p.empreinte ? ` · <span class="cap">sha256 ${esc(String(p.empreinte).slice(0, 12))}</span>` : ""}</p></div>` : "";
  const fichiersDiv = `<div class="fc"><span class="lbl">Plans</span><div id="pc-fichiers"><p class="cap">Chargement…</p></div></div>`;
  $("#fiche-c").innerHTML = tete + meta +
    (p.objectif || p.description ? `<div class="fc"><span class="lbl">Description</span><p class="prose">${esc(p.objectif || p.description)}</p></div>` : "") +
    offresHtml + utiliseeHtml + nomHtml + fichiersDiv + fichier + histHtml;
  const ar = await getJSON(`/api/v2/pieces/${encodeURIComponent(id)}/nomenclature`);
  const el = $("#pc-arbre"); if (!el) return;
  el.innerHTML = (ar.ok && ar.data) ? arbreNomenclature(ar.data, id) : `<p class="cap">Aucun lien de nomenclature (route non branchée ou pièce orpheline).</p>`;
  // U6 : plans (SVG, PDF, STEP) via la route A1
  const fr = await getJSON(`/api/v2/pieces/${encodeURIComponent(id)}/fichiers`);
  const fel = $("#pc-fichiers"); if (!fel) return;
  if (fr.err === 404) {
    fel.innerHTML = `<p class="cap">Aucun plan pour l'instant.</p>`;
  } else if (!fr.ok) {
    fel.innerHTML = `<p class="cap" style="color:var(--v-danger)">${fr.err ? "Erreur " + fr.err : "Erreur réseau"} : impossible de charger les plans.</p>`;
  } else if (fr.data && fr.data.fichiers && fr.data.fichiers.length) {
    const tok = encodeURIComponent(window.__SESSION_TOKEN__ || "");
    const url = f => `/api/v2/pieces/${encodeURIComponent(id)}/fichiers/${encodeURIComponent(f.revision || "P01")}/${encodeURIComponent(f.nom)}?token=${tok}`;
    const svg = fr.data.fichiers.find(f => f.nom.endsWith(".svg"));
    const liens = ["pdf", "step", "stp", "glb", "svg", "dxf"].map(ext => {
      const f = fr.data.fichiers.find(x => x.nom.toLowerCase().endsWith("." + ext));
      return f ? `<a href="${url(f)}" download="${esc(f.nom)}" class="btn mini" target="_blank" rel="noopener">${ext.toUpperCase()}</a>` : "";
    }).filter(Boolean).join("");
    const imgHtml = svg ? `<img class="plan-img" src="${url(svg)}" alt="Plan ${esc(svg.nom)}">` : `<p class="cap">Aucun plan SVG à afficher.</p>`;
    fel.innerHTML = imgHtml + (liens ? `<div class="chips" style="margin-top:10px">${liens}</div>` : "");
  } else {
    fel.innerHTML = `<p class="cap">Aucun plan pour l'instant.</p>`;
  }
}
function arbreNomenclature(noeud, racineId) {
  const estRacine = String(noeud.id) === String(racineId);
  return `<div class="pc-node${estRacine ? " racine" : ""}">
    <button type="button" class="pc-toggle" data-node-arbre="${esc(noeud.id)}" aria-expanded="true">
      <span class="pc-ref"><code>${esc(noeud.numero || "")}</code> <b>${esc(noeud.nom || "")}</b></span>
      ${noeud.quantite_cumulee != null ? `<span class="pc-qt">×${esc(noeud.quantite_cumulee)}${noeud.unite ? " " + esc(noeud.unite) : ""}</span>` : ""}
      ${pillStatutPiece(noeud.statut)}
    </button>
    <div class="pc-kids">${(noeud.enfants || []).map(e => arbreNomenclature(e, racineId)).join("")}</div>
  </div>`;
}
// Liste d'achats du projet : meilleure offre, total par devise, alertes (devise à convertir, prix > 30 j).
function renderAchats() {
  const el = $("#pc-achats"); if (!el) return;
  if (!state.sel) { el.innerHTML = ""; return; }
  if (!state.achats) {
    el.innerHTML = `<div class="vide">La liste d'achats apparaîtra ici : les pièces « acheter », leur meilleure offre sourcée, le total, et ce qui n'a pas encore d'offre.</div>`;
    return;
  }
  const lignes = state.achats.lignes || [];
  const sans = state.achats.sans_offre || [];
  const tot = state.achats.totaux || {};
  const row = l => {
    const o = l.offre;
    const offreCell = o
      ? `<div><b>${esc(o.reference || "")}</b>${o.fournisseur ? `<div class="sub">${esc(o.fournisseur)}</div>` : ""}</div><span class="sub">${fmtCAD(o.prix, o.devise)} · ${lienSource(o.source)}</span>`
      : `<span class="pill s-silence">sans offre</span>`;
    return `<tr>
    <td><code>${esc(l.numero || "")}</code><div class="sub">${esc(l.nom || "")}</div></td>
    <td class="n">${esc(l.quantite != null ? l.quantite : "")}</td>
    <td>${offreCell}</td>
    <td class="n">${fmtCAD(l.total, o ? o.devise : "CAD")}</td>
    <td>${l.a_convertir ? `<span class="pill s-attente" title="devise autre que CAD ou mixte : claude source le taux">à convertir</span>` : ""}${l.age_jours > 30 ? `<span class="pill s-silence" title="prix de plus de 30 jours : grok relève de nouveau">prix à revérifier</span>` : ""}</td>
  </tr>`;
  };
  el.innerHTML =
    (lignes.length ? `<div class="tblw"><table><tr><th>Pièce</th><th class="n">Qté</th><th>Meilleure offre</th><th class="n">Total</th><th></th></tr>${lignes.map(row).join("")}</table></div>` : `<div class="vide">Aucune pièce « acheter » pour l'instant.</div>`) +
    (sans.length ? `<p class="cap" style="color:var(--v-warning)">Sans offre : ${sans.map(s => esc(s.numero || s.nom || "")).join(", ")}.</p>` : "") +
    // Un total par devise : on n'additionne jamais CAD et USD sans taux sourcé.
    (Object.keys(tot).length ? `<p class="cap">Total des achats : <b>${Object.entries(tot).filter(([d]) => d !== "sans_prix").map(([d, v]) => fmtCAD(v, d)).join(" + ")}</b>${tot.sans_prix ? ` · ${esc(tot.sans_prix)} sans prix` : ""}</p>` : "");
}

// G5 : vue 3D de la progression — ne se (re)crée que si l'onglet Pièces est visible et que les pièces ont changé.
async function renderVue3D() {
  const el = $("#v3d-canvas"); if (!el) return;
  if (!state.sel || $("#t-pieces").hidden) return;
  if (typeof window.creerVue3D !== "function") return;
  const pieces = (state.pieces && state.pieces.pieces) || [];
  const sig = state.sel + "|" + pieces.map(p => [p.id, p.statut, p.fichier].join(":")).join(",");
  if (state.v3d && sig === state.v3dSig) return;
  state.v3dSig = sig;
  if (state.v3d) { state.v3d.destroy(); state.v3d = null; }
  $$("#v3d-wrap .v3d-legende").forEach(n => n.remove());
  const cap = $("#v3d-cap");
  if (cap) cap.textContent = "Chargement…";
  state.v3d = window.creerVue3D(el, pieceId => { ouvrirPiece(pieceId); });
  state.v3d.creerLegende(el.parentElement);
  // Positions des pièces dans le repère du véhicule (mm, Z vers le haut). Source : geometrie.py retenue() + maillage.py.
  const POS_PIECES = {
    "VLT-10002": { xMin: -20, xMax: 1366, yMin: -16, yMax: 416, zMin: -21, zMax: 316 },   // cadre treillis
    "VLT-10090": { xMin: 1435, xMax: 1560, yMin: 175, yMax: 225, zMin: -165, zMax: -95 },  // attelage (sur le bras)
    "VLT-10013": { xMin: -20, xMax: 1366, yMin: -16, yMax: 416, zMin: -21, zMax: 316 },    // tube cadre
  };
  const pieces3d = [];
  for (const p of pieces) {
    const bbox = POS_PIECES[p.numero] || BBOX_DEF;
    const entry = { id: p.id, numero: p.numero, nom: p.nom, statut: p.statut, fichier_glb: null, bbox };
    if (p.fichier && p.fichier.endsWith(".glb")) {
      // La révision du GLB vient du nom (…_P03.glb). Jeton en query : un fetch GLTF ne pose pas d'en-tête.
      const nomGlb = p.fichier.split("/").pop();
      const mRev = nomGlb.match(/_(P\d+)\.glb$/i);
      const revGlb = mRev ? mRev[1] : (p.revision || "P01");
      entry.fichier_glb = "/api/v2/pieces/" + encodeURIComponent(p.id) + "/fichiers/" +
        encodeURIComponent(revGlb) + "/" + encodeURIComponent(nomGlb) +
        "?token=" + encodeURIComponent(window.__SESSION_TOKEN__ || "");
    }
    pieces3d.push(entry);
  }
  // Fantômes : volumes schématiques des sous-ensembles non modélisés (module static/fantomes.js).
  let fantomes;
  try {
    const racine = pieces.find(p => p.type === "assemblage" && !p.sous_systeme);
    if (racine) {
      const r = await getJSON(`/api/v2/pieces/${encodeURIComponent(racine.id)}/nomenclature`);
      if (r.ok && r.data) fantomes = choisirFantomes(r.data.enfants);
    }
  } catch (_) {}
  if (!fantomes) fantomes = choisirFantomes(null);
  if (!state.v3d) return;
  await state.v3d.charger(pieces3d, fantomes);
  if (cap) cap.textContent = pieces3d.length ? pluriel(pieces3d.length, "pièce chargée", "pièces chargées") : "aucun GLB";
}

// =====================================================================================
// Fiches (dialogue latéral au bureau, feuille du bas au téléphone)
// =====================================================================================
const CHAMPS_FICHE = [
  ["resultat", "Ce qui a été fait"], ["conclusion", "Pourquoi, et ce qu'on en retient"],
  ["critere", "Critère de réussite"], ["preuve", "Preuve"],
  ["hypothese", "Hypothèse"], ["methode", "Méthode"], ["incertitude", "Incertitude"],
];
// « PR #24 » devient un lien vers la PR ; le reste est échappé.
const avecLiens = txt => esc(txt).replace(/PR #(\d+)/g,
  (m, n) => `<a href="https://github.com/Groupe-Vaultia/agentchattr/pull/${n}" target="_blank" rel="noopener">PR #${n}</a>`);
// Les résumés de l'historique et des messages aplatissent des tableaux markdown (« | a | b | |---|---| ») :
// on retire les rangées de séparation et on remplace les barres par des points médians.
const aplatir = txt => String(txt || "")
  .replace(/\|?(?:\s*:?-{3,}:?\s*\|)+/g, " ")
  .replace(/\s*\|\s*/g, " · ")
  .replace(/(?:\s*·\s*){2,}/g, " · ")
  .replace(/^\s*·\s*|\s*·\s*$/g, "")
  .replace(/\s*·\s*(…|\.\.\.)$/, "…");
const court = (txt, n) => { const t = String(txt || ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };
// Petit rendu sûr du markdown de PILOTE.md : d'abord esc(), puis **x** → <b>, `x` → <code>.
const mdCourt = txt => esc(String(txt || ""))
  .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
  .replace(/`([^`]+)`/g, "<code>$1</code>");
// Source d'une offre : lien seulement pour http(s) ; un devis reste du texte. Jamais javascript: ni data:.
const lienSource = src => {
  const t = String(src || "").trim();
  if (!t) return `<span class="cap" style="color:var(--v-danger)">sans source</span>`;
  return /^https?:\/\/[^\s<>"]+$/i.test(t)
    ? ` <a href="${esc(t)}" target="_blank" rel="noopener noreferrer">source</a>`
    : ` <span class="cap">${esc(t)}</span>`;
};

function ouvrirFiche(html) {
  $("#fiche-c").innerHTML = html;
  const d = $("#fiche");
  if (!d.open) { if (d.showModal) d.showModal(); else d.setAttribute("open", ""); }
  d.scrollTop = 0;
  // Le focus va à la fiche, pas au bouton Fermer : pas d'anneau à l'ouverture, pas de clavier qui surgit au téléphone.
  $("#fiche-c").focus({preventScroll: true});
}
function fermerFiche() { const d = $("#fiche"); if (d.close) d.close(); else d.removeAttribute("open"); }
const enteteFiche = (sur, titre) => `<div class="fh"><div><span class="lbl">${esc(sur)}</span><h2 id="fiche-t">${esc(titre)}</h2></div><button class="ibtn" type="button" data-act="fermer" aria-label="Fermer">${ico("fermer")}</button></div>`;
const trouverTache = (id, pid) => {
  const dans = p => ((state.par[p] || {}).taches || []).find(x => String(x.id) === String(id));
  if (pid && dans(pid)) return [dans(pid), pid];
  for (const p of Object.keys(state.par)) { const t = dans(p); if (t) return [t, p]; }
  return [null, null];
};

let REQUETE_FICHE = 0; // garde : une réponse n'affiche que si c'est encore la bonne tâche
async function ouvrirTache(id, pid) {
  const [t, projet] = trouverTache(id, pid || state.sel);
  if (!t) return;
  const n = ++REQUETE_FICHE;
  const st = normEtat(t.etat);
  const equipe = (t.equipe || []).map(m => `${agent(m.agent, true)} <span class="cap" style="margin:0">${esc(m.role)}</span>`).join(" ") || agent(t.responsable, true);
  const champs = CHAMPS_FICHE.filter(([c]) => String(t[c] || "").trim())
    // La preuve nomme souvent un livrable (chemin de fichier) : on le rend cliquable vers le visualiseur.
    .map(([c, l]) => `<div class="fc"><span class="lbl">${l}</span><p class="prose">${c === "preuve" ? avecLivrables(t[c]) : avecLiens(t[c])}</p></div>`).join("")
    || `<div class="fc"><p class="cap" style="margin:0">Rien d'écrit encore sur cette tâche.</p></div>`;
  const p = state.projets[projet] || {};
  const tete = enteteFiche(`${p.nom || projet} · Tâche ${t.id} · ${nomEtape(t.etape)}`, t.titre);
  const meta = `<div class="fm"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span><span>Responsable : ${agent(t.responsable, true)}</span><span>Équipe : ${equipe}</span>${t.updated_at ? `<span class="cap" style="margin:0">Modifiée ${esc(ilya(t.updated_at))}</span>` : ""}</div>`;
  const pied = `<div class="ff"><button class="btn pri" type="button" data-disc="${esc(t.id)}">${ico("chat")}Discuter de cette tâche</button></div>`;
  ouvrirFiche(tete + meta + champs + `<div class="fc"><span class="lbl">Ce qui s'est passé</span><ul class="fhist" id="fiche-h"><li class="cap">Chargement…</li></ul></div>` + pied);

  const [m, e] = await Promise.all([
    getJSON(`/api/v2/messages?tache_id=${encodeURIComponent(t.id)}&limit=100`),
    getJSON(`/api/v2/executions?tache_id=${encodeURIComponent(t.id)}`),
  ]);
  if (n !== REQUETE_FICHE) return;
  const el = $("#fiche-h");
  if (!el) return;
  const reussi = (m.ok || m.err === 404) && (e.ok || e.err === 404);
  const lignes = [];
  ((m.ok && m.data && m.data.messages) || []).forEach(x => lignes.push({h: x.timestamp, html: `${agent(x.sender, true)} <span>${livInline(court(aplatir(x.text), 400))}</span>`}));
  ((e.ok && e.data && e.data.executions) || []).forEach(x => lignes.push({h: x.fin || x.debut,
    html: `<span class="type">exécution</span>${agent(x.agent, true)}${x.role ? ` <span class="cap" style="margin:0">${esc(x.role)}</span>` : ""} : ${livInline(court(aplatir(x.consigne), 220))}${x.issue ? ` · ${esc(x.issue)}` : x.fin ? "" : " · en cours"}`}));
  lignes.sort((a, b) => (b.h || 0) - (a.h || 0));
  el.innerHTML = !reussi
    ? `<li class="cap" style="color:var(--v-danger)">Chargement de l'historique impossible (erreur réseau). Referme puis rouvre la tâche pour réessayer.</li>`
    : (lignes.length
      ? lignes.map(l => `<li><time>${esc(heure(l.h))}</time><span>${l.html}</span></li>`).join("")
      : `<li class="cap">Aucun message ni exécution rattaché à cette tâche. « Discuter » ouvre sa conversation : tout ce qui s'y dit s'inscrit ici.</li>`);
}

// ---------- jalons (P1) : les décisions de Charles ----------
const JALON_NOM = {J1: "Jalon J1", J2: "Jalon J2", revue: "Revue"};
const JALON_DECISIONS = {go: "Continuer", recycle: "Recycler", hold: "Mettre en veille", kill: "Arrêter"};
const JALON_CLS = {go: "s-fait", recycle: "s-cours", hold: "s-veille", kill: "s-bloque", "": "s-charles"};
const ETAT_CRITERE = {atteint: "atteint", partiel: "partiel", rate: "manqué", a_mesurer: "à mesurer"};
const CRIT_CLS = {atteint: "crit-ok", partiel: "crit-part", rate: "crit-rate", a_mesurer: "crit-mes"};
// L'étape de recyclage doit être antérieure au jalon.
const recyclables = j => {
  const fin = ETAPES.indexOf(etapeDuJalon(j));
  return fin >= 0 ? ETAPES.slice(0, fin + 1) : ETAPES.slice(0, -1);
};
function blocJalons(etape, jalons) {
  const rattaches = jalons.filter(j => etapeDuJalon(j.jalon) === etape);
  if (!rattaches.length) return "";
  const html = rattaches.map(j => {
    const decise = !!j.decision;
    const criteres = (j.criteres || []).map(c =>
      `<li><span class="crit ${CRIT_CLS[c.etat] || "crit-mes"}">${esc(ETAT_CRITERE[c.etat] || c.etat || "?")}</span><span>${esc(c.nom || "")}</span>${c.cible ? `<span class="cap">cible ${esc(c.cible)}${c.mesure ? " · " + esc(c.mesure) : ""}</span>` : ""}</li>`).join("");
    const risques = (j.risques || []).length ? (j.risques.map(esc).join(" · ")) : "";
    const boutons = decise ? "" :
      `<div class="jb">` +
      `<span class="lbl">Ta décision</span>` +
      (j.recommandation ? `<p class="cap" style="margin:0">claude recommande : <b>${esc(JALON_DECISIONS[j.recommandation] || j.recommandation)}</b>${j.raison ? " : " + esc(j.raison) : ""}</p>` : "") +
      `<div class="jb-btns">` +
      Object.entries(JALON_DECISIONS).map(([v, l]) =>
        `<button class="btn dec${v === "go" ? " pri" : v === "kill" ? " stop" : ""}" type="button" data-dec="${esc(j.id)}" data-val="${v}">${esc(l)}</button>`).join("") +
      `</div>` +
      `<label class="lbl" for="recy-${esc(j.id)}">Pour recycler : vers quelle étape</label><select id="recy-${esc(j.id)}" data-recy="${esc(j.id)}"><option value="">—</option>${recyclables(j.jalon).map(e2 => `<option value="${esc(e2)}">${esc(nomEtape(e2))}</option>`).join("")}</select>` +
      `<label class="lbl" for="not-${esc(j.id)}">Note (facultatif)</label><input id="not-${esc(j.id)}" data-not="${esc(j.id)}" placeholder="Ex. : on recycle sur la masse">` +
      `</div>`;
    return `<div class="jalon${decise ? " decide" : ""}">
      <div class="jalon-hd"><b>${esc(JALON_NOM[j.jalon] || j.jalon)}</b><span class="pill ${JALON_CLS[decise ? j.decision : ""] || "s-attente"}">${decise ? esc(JALON_DECISIONS[j.decision] || j.decision) : "t'attend"}</span>${j.decision_date ? `<span class="cap">${esc(heure(j.decision_date))}</span>` : ""}</div>
      ${criteres ? `<ul class="crits">${criteres}</ul>` : ""}
      ${risques ? `<p class="cap">Risques : ${risques}</p>` : ""}
      ${j.resultats ? `<div class="fc"><span class="lbl">Résultats</span><p class="prose">${avecLiens(j.resultats)}</p></div>` : ""}
      ${j.reste ? `<div class="fc"><span class="lbl">Reste à faire</span><p class="prose">${esc(j.reste)}</p></div>` : ""}
      ${j.decision_note ? `<div class="fc"><span class="lbl">Note de la décision</span><p class="prose">${esc(j.decision_note)}</p></div>` : ""}
      ${boutons}
    </div>`;
  }).join("");
  return `<div class="fc"><span class="lbl">Jalon de cette étape</span>${html}</div>`;
}
function ouvrirEtape(e, pid) {
  const projet = pid || state.sel;
  const d = state.par[projet] || {taches: [], jalons: []};
  const i = ETAPES.indexOf(e);
  if (i < 0) return;
  const de = d.taches.filter(t => t.etape === e);
  const fait = de.filter(t => normEtat(t.etat) === "fait").length;
  const liste = de.length
    ? `<ul class="flist">${de.map(t => { const st = normEtat(t.etat); return `<li><button type="button" data-fiche="${esc(t.id)}" data-p="${esc(projet)}"><span class="pill ${ETAT_CLS[st] || "s-afaire"}">${esc(ETAT_TACHE[st] || t.etat)}</span><span style="font-weight:600">${esc(t.titre)}</span>${t.resultat ? `<span class="cap" style="margin:0">${esc(court(t.resultat, 160))}</span>` : ""}</button></li>`; }).join("")}</ul>`
    : `<p class="cap" style="margin:0">Aucune tâche à cette étape pour l'instant.</p>`;
  const mE = (state.methodes && state.methodes[e]) || "";
  const p = state.projets[projet] || {};
  ouvrirFiche(enteteFiche(`${p.nom || projet} · Étape ${i + 1} sur ${ETAPES.length}`, nomEtape(e)) +
    `<div class="fc" style="border-top:0"><span class="lbl">Ce que couvre l'étape</span><p class="prose">${esc(DEF_ETAPES[e] || "")}</p></div>` +
    blocJalons(e, d.jalons) +
    `<div class="fc"><span class="lbl">Tâches (${fait}/${de.length} faites)</span>${liste}</div>` +
    (mE ? `<div class="fc"><span class="lbl">Méthode de l'étape</span><p class="prose" style="font-size:15px">${mdCourt(mE)}</p></div>` : ""));
}
async function deciderJalon(jalonId, val) {
  let j = null;
  for (const p of Object.keys(state.par)) { j = (state.par[p].jalons || []).find(x => String(x.id) === String(jalonId)); if (j) break; }
  if (!j) return;
  const recy = val === "recycle" ? (($("#recy-" + CSS.escape(String(j.id)))?.value) || "") : "";
  if (val === "recycle" && !recy) { toast("Choisis l'étape vers laquelle recycler."); return; }
  const note = (($("#not-" + CSS.escape(String(j.id)))?.value) || "").trim();
  const r = await postJSON(`/api/v2/jalons/${encodeURIComponent(j.id)}/decision`,
    {par: "user", decision: val, note, ...(val === "recycle" ? {recycle_etape: recy} : {})});
  if (r.ok) { toast(`${JALON_NOM[j.jalon] || j.jalon} : ${JALON_DECISIONS[val] || val}.`); fermerFiche(); await rafraichir(); }
  else toast(r.msg || "Décision refusée (déjà décidée, ou route non branchée).");
}

// ---------- fiche projet (P2) ----------
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
    `<li><span class="pill ${h.etat === "confirmee" ? "s-fait" : h.etat === "infirmee" ? "s-bloque" : "s-attente"}" style="align-self:flex-start">${esc(h.etat || "à vérifier")}</span><span>${esc(h.texte || "")}</span><span class="cap" style="margin:0">source : ${esc(h.source || "?")}</span></li>`).join("");
  const risques = (f.risques || []).map(r =>
    `<li><span class="cap" style="margin:0">${esc(r.type || "")}${r.etape ? " · " + esc(nomEtape(r.etape)) : ""}</span><span>${esc(r.texte || "")}</span></li>`).join("");
  const questions = (f.questions || []).map(q =>
    `<li><span>${esc(q.texte || "")}</span>${q.reponse ? `<span class="cap" style="margin:0">réponse : ${esc(q.reponse)}</span>` : `<span class="pill s-silence">sans réponse</span>`}</li>`).join("");
  const c = f.criteres || [];
  const blocs = [];
  if (f.objectif || p.objectif) blocs.push(`<div class="fc"><span class="lbl">Objectif</span><p class="prose">${esc(f.objectif || p.objectif)}</p></div>`);
  if (f.livrable_attendu || p.livrable_attendu) blocs.push(`<div class="fc"><span class="lbl">Livrable attendu</span><p class="prose">${esc(f.livrable_attendu || p.livrable_attendu)}</p></div>`);
  if (c.length) blocs.push(`<div class="fc"><span class="lbl">Critères</span><ul class="flist">${c.map(x => `<li><span>${esc(x.nom || "")}</span>${x.cible ? `<span class="cap" style="margin:0">cible : ${esc(x.cible)}</span>` : ""}</li>`).join("")}</ul></div>`);
  if (hypo) blocs.push(`<div class="fc"><span class="lbl">Hypothèses</span><ul class="flist hypo">${hypo}</ul></div>`);
  if (risques) blocs.push(`<div class="fc"><span class="lbl">Risques</span><ul class="flist">${risques}</ul></div>`);
  if (questions) blocs.push(`<div class="fc"><span class="lbl">Questions posées par claude</span><ul class="flist">${questions}</ul></div>`);
  const contenu = blocs.join("") || `<div class="fc"><p class="cap" style="margin:0">La fiche projet n'est pas encore remplie. claude la remplit au lancement guidé (objectif, niveau, hypothèses, risques, questions).</p></div>`;
  ouvrirFiche(enteteFiche("Fiche projet", p.nom || id) + meta + contenu);
}

// ---------- visualiseur de livrables : rendu markdown sûr + fiche par type ----------
// Rendu autonome, minimal et SÛR : tout contenu est échappé AVANT d'être balisé — jamais d'innerHTML de HTML brut.
function livInline(raw) {
  const codes = [];
  let s = String(raw ?? "").replace(/`([^`]+)`/g, (m, c) => { codes.push(c); return "\x00c" + (codes.length - 1) + "\x00"; });
  s = esc(s);
  s = s.replace(/!\[([^\]]*)\]\([^)\s]+\)/g, (m, alt) => `<em>[image : ${alt}]</em>`); // pas de chargement externe
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, txt, url) =>
    /^(https?:\/\/|mailto:)/i.test(url) ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${txt}</a>` : txt);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>").replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
  s = s.replace(/\x00c(\d+)\x00/g, (m, i) => `<code>${esc(codes[+i])}</code>`);
  return s;
}
function livListe(lignes) {
  const items = [];
  lignes.forEach(l => {
    const m = l.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (m) items.push({ lvl: Math.floor(m[1].replace(/\t/g, "  ").length / 2), ol: /\d/.test(m[2]), txt: m[3] });
    else if (items.length) items[items.length - 1].txt += "\n" + l.trim();
  });
  let html = ""; const open = [];
  items.forEach(it => {
    if (!open.length || it.lvl > open[open.length - 1].lvl) {
      const tag = it.ol ? "ol" : "ul"; open.push({ lvl: it.lvl, tag }); html += `<${tag} class="liv-list">`;
    } else {
      while (open.length > 1 && it.lvl < open[open.length - 1].lvl) html += `</li></${open.pop().tag}>`;
      html += "</li>";
    }
    html += `<li>${livInline(it.txt)}`;
  });
  while (open.length) html += `</li></${open.pop().tag}>`;
  return html;
}
function livMarkdown(src) {
  const lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
  const out = []; let i = 0;
  const sep = s => /^\s*\|?[\s:|-]*-{1,}[\s:|-]*$/.test(s) && s.includes("-") && s.includes("|");
  const special = s => /^\s*(#{1,6}\s|```|>|[-*+]\s|\d+[.)]\s)/.test(s) || /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(s);
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s*```+\s*\S*\s*$/);
    if (fence) {
      i++; const buf = [];
      while (i < lines.length && !/^\s*```+\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++; out.push(`<pre class="liv-code"><code>${esc(buf.join("\n"))}</code></pre>`); continue;
    }
    if (/^\s*$/.test(line)) { i++; continue; }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { const n = h[1].length; out.push(`<h${n} class="liv-h">${livInline(h[2].replace(/#+\s*$/, "").trim())}</h${n}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { out.push('<hr class="liv-hr">'); i++; continue; }
    if (line.includes("|") && i + 1 < lines.length && sep(lines[i + 1])) {
      const cells = r => r.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());
      const head = cells(line); i += 2; const rows = [];
      while (i < lines.length && lines[i].includes("|") && !/^\s*$/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      out.push(`<div class="liv-tblw"><table class="liv-tbl"><thead><tr>${head.map(c => `<th>${livInline(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${livInline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(`<blockquote class="liv-bq">${livMarkdown(buf.join("\n"))}</blockquote>`); continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && (/^\s*([-*+]|\d+[.)])\s+/.test(lines[i]) || (buf.length && /^\s+\S/.test(lines[i])))) { buf.push(lines[i]); i++; }
      out.push(livListe(buf)); continue;
    }
    const buf = [line]; i++;
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !special(lines[i])) { buf.push(lines[i]); i++; }
    out.push(`<p>${buf.map(livInline).join("<br>")}</p>`);
  }
  return out.join("\n");
}
// Le jeton va en query : un <img>/<a download> ne peut pas poser l'en-tête x-session-token.
const urlLivrable = chemin => {
  const t = window.__SESSION_TOKEN__;
  return `/api/v2/livrable?chemin=${encodeURIComponent(chemin)}` + (t ? `&token=${encodeURIComponent(t)}` : "");
};
const LIV_IMG = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
const LIV_TXT = new Set(["md", "markdown", "txt", "csv", "json"]);
const extLivrable = chemin => { const m = String(chemin || "").toLowerCase().match(/\.([a-z0-9]+)$/); return m ? m[1] : ""; };
async function ouvrirLivrable(chemin) {
  const nom = String(chemin || "").split("/").pop() || chemin;
  const ext = extLivrable(chemin);
  const tete = enteteFiche("Livrable", nom);
  const tele = `<div class="fc"><a class="btn pri" href="${esc(urlLivrable(chemin))}" download="${esc(nom)}">Télécharger</a> <p class="cap"><code>${esc(chemin)}</code></p></div>`;
  ouvrirFiche(tete + `<div class="fc"><p class="cap">Chargement…</p></div>`);
  if (LIV_IMG.has(ext)) {
    $("#fiche-c").innerHTML = tete + `<div class="fc liv-vue"><img class="liv-img" src="${esc(urlLivrable(chemin))}" alt="${esc(nom)}"></div>` + tele;
    return;
  }
  if (LIV_TXT.has(ext)) {
    const r = await getJSON(urlLivrable(chemin));
    if (!$("#fiche-c")) return;
    if (!r.ok) {
      const msg = r.err === 404 ? "Ce livrable n'existe plus sur la tour."
        : r.err === 403 ? "Chemin refusé (hors de la racine des livrables)."
        : "Impossible de charger ce livrable" + (r.err ? ` (erreur ${r.err})` : " (erreur réseau)") + ".";
      $("#fiche-c").innerHTML = tete + `<div class="fc"><p class="cap" style="color:var(--v-danger)">${esc(msg)}</p></div>` + tele;
      return;
    }
    const d = r.data || {};
    if (d.type === "trop_volumineux") {
      $("#fiche-c").innerHTML = tete + `<div class="fc"><p>${esc(d.message || "Fichier trop volumineux pour l'aperçu.")}</p></div>` + tele;
      return;
    }
    const corps = (ext === "md" || ext === "markdown")
      ? `<div class="liv-md">${livMarkdown(d.contenu || "")}</div>`
      : `<pre class="liv-code"><code>${esc(d.contenu || "")}</code></pre>`;
    $("#fiche-c").innerHTML = tete + `<div class="fc liv-vue" style="border-top:0">${corps}</div>` + tele;
    return;
  }
  // ── POINT D'EXTENSION CAO ── : ajouter ici une branche par `ext` (step, stl, fcstd…) pour un aperçu 3D.
  $("#fiche-c").innerHTML = tete +
    `<div class="fc" style="border-top:0"><p>Type <code>${esc(ext || "?")}</code> sans aperçu dans l'atelier.</p><p class="cap">Télécharge-le pour l'ouvrir.</p></div>` + tele;
}
// Rend cliquable chaque chemin de fichier d'une preuve de tâche.
const RE_LIVR = /([\w./-]+\.(?:md|markdown|txt|csv|json|png|jpe?g|gif|webp|svg|pdf|fcstd|step|stp|stl|dxf|3mf|obj|glb|iges?|igs))\b/gi;
const avecLivrables = txt => avecLiens(txt).replace(RE_LIVR, m =>
  `<a href="#" class="liv-lien" data-voir="${m}" title="Ouvrir ${m}">${m}</a>`);

// =====================================================================================
// Actions
// =====================================================================================
async function changerStatut(id, statut) {
  const r = await postJSON(`/api/v2/projects/${encodeURIComponent(id)}/status`, {status: statut});
  toast(r.ok ? `${(state.projets[id] || {}).nom || id} : ${STATUTS[statut] || statut}` : "Changement refusé (route non branchée ou statut inconnu).");
  if (r.ok) await rafraichir();
}
// Dépôt d'un fichier vers POST /api/upload (rend {name, url}) — photos et documents joints au lancement.
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
  if (!nom) { toast("Donne un nom au projet."); $("#np-nom").focus(); return; }
  const objectif = $("#np-but").value.trim();
  // P4 : POST /api/v2/projects {nom, objectif, pieces_jointes} crée le projet ET appelle @claude.
  const fichiers = Array.from($("#np-fich").files || []);
  let pieces = [];
  if (fichiers.length) {
    toast(`Dépôt de ${pluriel(fichiers.length, "fichier", "fichiers")}…`);
    pieces = (await Promise.all(fichiers.map(uploadFichier))).filter(Boolean);
    if (pieces.length < fichiers.length) toast(`${pluriel(fichiers.length - pieces.length, "fichier refusé", "fichiers refusés")} (type ou taille).`);
  }
  const b = e.target.querySelector("[type=submit]"); b.disabled = true;
  const r = await postJSON("/api/v2/projects", {nom, objectif, pieces_jointes: pieces});
  b.disabled = false;
  toast(r.ok ? `Projet « ${nom} » lancé. claude démarre le cadrage.` : (r.msg || "Création refusée (route non branchée ou nom déjà pris)."));
  if (r.ok) { e.target.reset(); e.target.hidden = true; await rafraichir(); }
}
async function nouvelleTache(e) {
  e.preventDefault();
  const titre = $("#tk-t").value.trim();
  if (!titre || !state.sel) { toast("Donne un titre à la tâche."); $("#tk-t").focus(); return; }
  // Rôles du contrat S2 : producteur, verificateur, relecteur, proposant.
  const r = await postJSON(`/api/v2/taches`, {projet_id: state.sel, titre, etape: $("#tk-c").value, responsable: $("#tk-r").value, equipe: [{agent: $("#tk-r").value, role: "producteur"}]});
  toast(r.ok ? "Tâche ajoutée." : "Ajout refusé (route POST /api/v2/taches non branchée pour l'instant).");
  if (r.ok) { e.target.reset(); e.target.hidden = true; await rafraichir(); }
}
// « Discuter » : la route crée le canal tache-<id> une seule fois et rend {channel} ; on y va dans la salle.
async function discuter(tacheId) {
  const r = await postJSON(`/api/v2/taches/${encodeURIComponent(tacheId)}/conversation`, {});
  if (!r.ok || !r.data || !r.data.channel) { toast(r.msg || "Impossible d'ouvrir la conversation de cette tâche."); return; }
  try { localStorage.setItem("agentchattr-channel", r.data.channel); } catch (_) {}
  window.location.href = "/";
}

// =====================================================================================
// Navigation (routes dans l'ancre : le bouton Retour du téléphone fonctionne)
// =====================================================================================
function lireRoute() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(s => { try { return decodeURIComponent(s); } catch (_) { return s; } });
  if (parts[0] === "p" && parts[1]) return {page: "projet", id: parts[1], onglet: ONGLETS.includes(parts[2]) ? parts[2] : "taches"};
  return {page: "jour"};
}
function rendre() {
  renderRail(); renderAlertes();
  const r = state.route;
  $("#page-jour").hidden = r.page !== "jour";
  $("#page-projet").hidden = r.page !== "projet";
  if (r.page === "jour") { renderJour(); $("#tb-titre").textContent = "Aujourd'hui"; document.title = "Aujourd'hui · Atelier · Vaultia"; }
  else { renderProjet(); const n = (state.projets[state.sel] || {}).nom || state.sel; $("#tb-titre").textContent = n; document.title = `${n} · Atelier · Vaultia`; }
}
async function appliquerRoute() {
  const avant = state.route;
  const r = lireRoute();
  if (r.page === "projet" && !state.projets[r.id]) { if (Object.keys(state.projets).length) { location.replace("#/"); return; } }
  state.route = r;
  fermerRail();
  const autreProjet = r.page === "projet" && r.id !== state.sel;
  if (autreProjet) {
    state.sel = r.id; state.filtre = null; state.faitOuvert = false; state.pcTout = false; state.v3dSig = "";
    state.executions = []; state.hist = null; state.liv = null; state.pieces = null; state.achats = null; state.cout = null;
    $("#taskform").hidden = true;
  }
  if (avant.page !== r.page || autreProjet) window.scrollTo(0, 0);
  rendre();
  // On recharge les données du projet à chaque entrée sur sa page (autre projet, ou retour depuis l'accueil) :
  // sans ça, un retour au même projet montrait pièces, historique et livrables d'avant (revue codex-2, msg 4321).
  // La vue 3D garde son garde v3dSig : elle n'est recréée que si les pièces ont changé.
  const entre = r.page === "projet" && (autreProjet || avant.page !== "projet");
  if (entre) { await chargerProjet(); if (state.route.page === "projet" && state.sel === r.id) rendre(); }
}
const allerOnglet = o => { if (state.sel) location.hash = `#/p/${encodeURIComponent(state.sel)}/${o}`; };

// Rafraîchit tout ce qui est affiché, sans fermer une fiche ni un formulaire ouvert.
let RAFRAICHIT = false;
async function rafraichir() {
  if (RAFRAICHIT) return;
  RAFRAICHIT = true;
  try {
    await Promise.all([chargerGlobal(), state.route.page === "projet" ? chargerProjet() : Promise.resolve()]);
    rendre();
  } finally { RAFRAICHIT = false; }
}

// ---------- tiroir (téléphone) ----------
function ouvrirRail() { $("#rail").classList.add("ouvert"); $("#voile").hidden = false; $("#menu").setAttribute("aria-expanded", "true"); }
function fermerRail() { $("#rail").classList.remove("ouvert"); $("#voile").hidden = true; $("#menu").setAttribute("aria-expanded", "false"); }

// ---------- câblage ----------
document.addEventListener("click", e => {
  const t = e.target;
  const lv = t.closest("[data-voir]"); if (lv) { e.preventDefault(); e.stopPropagation(); return ouvrirLivrable(lv.dataset.voir); }
  const d = t.closest("[data-disc]"); if (d) { e.preventDefault(); e.stopPropagation(); return discuter(d.dataset.disc); }
  const st = t.closest("[data-status]"); if (st && st.dataset.status) { e.stopPropagation(); return changerStatut(st.dataset.proj, st.dataset.status); }
  const dj = t.closest("[data-dec]"); if (dj) { e.stopPropagation(); return deciderJalon(dj.dataset.dec, dj.dataset.val); }
  const oe = t.closest("[data-ouvrir-etape]"); if (oe) { e.stopPropagation(); return ouvrirEtape(oe.dataset.ouvrirEtape, oe.dataset.p); }
  const fi = t.closest("[data-filtre]"); if (fi) { state.filtre = fi.dataset.filtre && fi.dataset.filtre !== state.filtre ? fi.dataset.filtre : null; renderEtapes(state.etape ?? etapeDuProjet(state.taches)); renderTableau(); if ((state.route.onglet || "taches") !== "taches") allerOnglet("taches"); return; }
  const fe = t.closest("[data-fiche]"); if (fe) return ouvrirTache(fe.dataset.fiche, fe.dataset.p);
  const og = t.closest("#onglets [data-onglet]"); if (og) return allerOnglet(og.dataset.onglet);
  const pr = t.closest(".pc-row[data-piece], .eclatee-bloc[data-piece]"); if (pr) return ouvrirPiece(pr.dataset.piece);
  const pn = t.closest(".pc-toggle"); if (pn) { const kids = pn.parentNode.querySelector(":scope > .pc-kids"); if (kids) { kids.hidden = !kids.hidden; pn.setAttribute("aria-expanded", String(!kids.hidden)); } return; }
  const er = t.closest(".ev-r"); if (er) { er.classList.toggle("ouvert"); return; }
  if (t.id === "fiche") return fermerFiche();  // clic sur le fond du dialogue
  if (t.id === "voile") return fermerRail();
  if (t.closest("#menu")) return $("#rail").classList.contains("ouvert") ? fermerRail() : ouvrirRail();
  if (t.closest(".rail a")) return fermerRail();
  const act = t.closest("[data-act]"); if (!act) return;
  const a = act.dataset.act;
  if (a === "fermer") return fermerFiche();
  if (a === "rafraichir") { act.disabled = true; rafraichir().then(() => { act.disabled = false; toast("Atelier à jour."); }); return; }
  if (a === "fiche-projet") return ouvrirFicheProjet();
  if (a === "pc-tout") { state.pcTout = true; return renderPieces(); }
  if (a === "fait-tout") { state.faitOuvert = !state.faitOuvert; return renderTableau(); }
  if (a === "nouveau-projet") {
    fermerRail();
    if (state.route.page !== "jour") location.hash = "#/";
    const f = $("#newproj"); f.hidden = false;
    setTimeout(() => { f.scrollIntoView({block: "center", behavior: "smooth"}); $("#np-nom").focus({preventScroll: true}); }, 60);
    return;
  }
  if (a === "annuler-projet") { $("#newproj").reset(); $("#newproj").hidden = true; return; }
  if (a === "newtask") { if (state.route.onglet !== "taches") allerOnglet("taches"); const f = $("#taskform"); f.hidden = !f.hidden; if (!f.hidden) $("#tk-t").focus(); return; }
  if (a === "canceltask") { $("#taskform").reset(); $("#taskform").hidden = true; }
});
// Clavier : Entrée ou Espace ouvre une ligne ou une carte (role=button), Échap ferme le tiroir.
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && $("#rail").classList.contains("ouvert")) { fermerRail(); return; }
  if ((e.key === "Enter" || e.key === " ") && e.target.matches('[role="button"][tabindex], .pc-row[tabindex]')) {
    e.preventDefault(); e.target.click();
  }
});
$("#btn-approuver").addEventListener("click", approuver);
$("#newproj").addEventListener("submit", nouveauProjet);
$("#taskform").addEventListener("submit", nouvelleTache);
$("#pc-q").addEventListener("input", renderPieces);
$("#pc-f").addEventListener("change", renderPieces);
document.addEventListener("input", e => {
  if (e.target.id === "v3d-eclate" && state.v3d) state.v3d.setEclate(parseInt(e.target.value, 10) / 100);
});
window.addEventListener("hashchange", appliquerRoute);

// ---------- démarrage ----------
(async function init() {
  await chargerGlobal();
  // Ancien signet sans ancre : on garde l'accueil « Aujourd'hui ».
  await appliquerRoute();
  // Pas de WebSocket ici : on suit la salle toutes les 60 s et au retour sur l'onglet.
  setInterval(() => { if (!document.hidden) rafraichir(); }, 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) rafraichir(); });
})();
