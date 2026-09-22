/* vaultia.js — ajouts Vaultia (autonome, chargé après chat.js).
   + IA (connecter par un lien) · Modèles & raisonnement par IA · Statistiques de jetons ·
   Projets avec mémoire · bandeau « qui réfléchit » · pastilles d'initiale par marque. */
(function () {
  "use strict";
  const TOKEN = window.__SESSION_TOKEN__ || "";
  const H = { "Content-Type": "application/json", "X-Session-Token": TOKEN };
  const HT = { "X-Session-Token": TOKEN };
  const EFFORTS = [{ v: "", l: "Défaut" }, { v: "rapide", l: "Rapide" }, { v: "standard", l: "Standard" }, { v: "profond", l: "Profond" }];

  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === "style") e.style.cssText = attrs[k];
      else if (k === "onclick") e.addEventListener("click", attrs[k]);
      else if (k === "html") e.innerHTML = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    for (const kid of kids) if (kid != null) e.append(kid);
    return e;
  }
  const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + " k" : "" + n);

  function overlay(titre, corps) {
    const fond = el("div", { style: "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;" });
    const boite = el("div", { style: "background:var(--bg-panel,#1e1e24);color:var(--text,#e8e8ea);border:1px solid var(--border,#3a3a44);border-radius:12px;padding:20px 22px;width:min(520px,94vw);max-height:88vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.5);font:14px/1.5 system-ui,sans-serif;" });
    fond.addEventListener("click", (ev) => { if (ev.target === fond) fond.remove(); });
    boite.append(el("h2", { style: "margin:0 0 14px;font-size:17px;" }, titre));
    boite.append(corps); fond.append(boite); document.body.append(fond); return fond;
  }
  function champ(label, input) {
    input.style.cssText += ";display:block;width:100%;margin-top:4px;padding:7px 9px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;box-sizing:border-box;font:inherit;";
    return el("label", { style: "display:block;margin:0 0 11px;font-size:12px;opacity:.8;" }, label, input);
  }
  const btn = (txt, on, primary) => el("button", { onclick: on, style: `border:0;border-radius:8px;padding:8px 14px;font:inherit;cursor:pointer;${primary ? "background:var(--accent,#5b8def);color:#fff;" : "background:var(--border,#3a3a44);color:inherit;"}` }, txt);

  async function jget(u) { return (await fetch(u, { headers: HT })).json(); }
  async function jpost(u, body) { return (await fetch(u, { method: "POST", headers: H, body: JSON.stringify(body || {}) })).json(); }

  // ---- + IA ----
  function ouvrirAjout() {
    const f = {}; const mk = (ph) => (f[ph] = el("input", { placeholder: ph }));
    const nom = mk("identifiant (@mention)"), label = mk("Nom affiché"), lien = mk("Lien (base_url, http…/v1)"),
      modele = mk("modèle"), cle = mk("Clé — variable d'env (optionnel)");
    const couleur = el("input", { type: "color", value: "#6b7280", style: "height:34px;" });
    const sys = el("textarea", { rows: "2", placeholder: "Consigne système (optionnel)" });
    const etat = el("div", { style: "min-height:18px;margin:4px 0;font-size:12px;" });
    const go = btn("Connecter", async () => {
      etat.textContent = "Connexion…"; etat.style.color = "";
      const d = await jpost("/api/agents/add", { name: nom.value.trim().toLowerCase(), label: label.value.trim(), base_url: lien.value.trim(), model: modele.value.trim(), api_key_env: cle.value.trim(), color: couleur.value, system_prompt: sys.value.trim() });
      if (d.error) { etat.style.color = "#e5675f"; etat.textContent = "✗ " + d.error; }
      else { etat.style.color = "#59b56a"; etat.textContent = `✓ ${d.label} connecté — @${d.name}.`; }
    }, true);
    overlay("Connecter une IA", el("div", {}, champ("Identifiant", nom), champ("Nom affiché", label), champ("Lien de connexion", lien), champ("Modèle", modele), champ("Clé (variable d'env.)", cle), champ("Couleur", couleur), champ("Consigne système", sys), etat, el("div", { style: "text-align:right;" }, go)));
  }

  // ---- Modèles & raisonnement ----
  async function ouvrirModeles() {
    const status = await jget("/api/status").catch(() => ({}));
    const corps = el("div", {});
    corps.append(el("p", { style: "margin:0 0 12px;font-size:12px;opacity:.75;" }, "Modèle et niveau de raisonnement par IA. Vide = Auto/défaut. Appliqué au message suivant pour Qwen/Cursor/Gemini ; au prochain lancement pour Claude et Codex."));
    Object.keys(status).filter((n) => n !== "paused").forEach((nom) => {
      const info = status[nom] || {};
      const eff = el("select", { style: "padding:5px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;" });
      EFFORTS.forEach((o) => { const op = el("option", { value: o.v }, o.l); if ((info.effort || "") === o.v) op.selected = true; eff.append(op); });
      eff.addEventListener("change", () => jpost("/api/efforts/" + encodeURIComponent(nom), { effort: eff.value }));
      const mod = el("input", { value: info.model || "", placeholder: "Auto", style: "width:150px;padding:5px 7px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;" });
      mod.addEventListener("change", () => jpost("/api/models_choice/" + encodeURIComponent(nom), { model: mod.value.trim() }));
      const pastille = el("span", { style: `display:inline-block;width:9px;height:9px;border-radius:50%;background:${info.color || "#888"};margin-right:7px;` });
      corps.append(el("div", { style: "display:flex;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--border,#2a2a30);flex-wrap:wrap;" },
        el("span", { style: "min-width:110px;font-weight:600;" }, pastille, info.label || nom),
        el("span", { style: "font-size:11px;opacity:.6;" }, "modèle"), mod,
        el("span", { style: "font-size:11px;opacity:.6;" }, "raisonnement"), eff));
    });
    overlay("Modèles & raisonnement", corps);
  }

  // ---- Statistiques ----
  async function ouvrirStats() {
    const d = await jget("/api/stats").catch(() => ({ par_agent: {} }));
    const corps = el("div", {});
    const rows = Object.entries(d.par_agent || {}).sort((a, b) => b[1].jetons_estimes - a[1].jetons_estimes);
    const tbl = el("table", { style: "width:100%;border-collapse:collapse;font-size:13px;" });
    tbl.append(el("tr", { style: "text-align:left;opacity:.7;" }, el("th", { style: "padding:6px 4px;" }, "Participant"), el("th", {}, "Messages"), el("th", {}, "Jetons estimés")));
    rows.forEach(([nom, e]) => tbl.append(el("tr", { style: "border-top:1px solid var(--border,#2a2a30);" },
      el("td", { style: "padding:6px 4px;" }, (e.est_agent ? "🤖 " : "🧑 ") + nom),
      el("td", { style: "font-variant-numeric:tabular-nums;" }, "" + e.messages),
      el("td", { style: "font-variant-numeric:tabular-nums;" }, fmt(e.jetons_estimes)))));
    if (!rows.length) corps.append(el("p", { style: "opacity:.6;" }, "Aucun message encore."));
    else corps.append(tbl);
    corps.append(el("p", { style: "margin-top:14px;font-size:11px;opacity:.6;" }, d.note || ""));
    corps.append(el("div", { style: "text-align:right;margin-top:10px;" }, btn("Rafraîchir", () => { document.querySelector("#vaultia-ov-stats")?.remove(); ouvrirStats(); })));
    const ov = overlay("Statistiques — consommation", corps); ov.id = "vaultia-ov-stats";
  }

  // ---- Projets ----
  async function ouvrirProjets() {
    const d = await jget("/api/projects").catch(() => ({ projets: {}, actif: "" }));
    const corps = el("div", {});
    const liste = el("div", {});
    const rerender = async () => { const nd = await jget("/api/projects"); dessine(nd); };
    function dessine(data) {
      liste.innerHTML = "";
      const noms = Object.keys(data.projets || {});
      if (!noms.length) liste.append(el("p", { style: "opacity:.6;" }, "Aucun projet. Crée-en un ci-dessous."));
      noms.forEach((nom) => {
        const actif = data.actif === nom;
        const mem = el("textarea", { rows: "3", style: "width:100%;margin-top:6px;padding:7px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;box-sizing:border-box;font:inherit;" });
        mem.value = (data.projets[nom].memoire || "");
        const bloc = el("div", { style: `padding:10px;margin-bottom:10px;border:1px solid ${actif ? "var(--accent,#5b8def)" : "var(--border,#3a3a44)"};border-radius:9px;` },
          el("div", { style: "display:flex;align-items:center;gap:8px;" },
            el("strong", {}, nom), actif ? el("span", { style: "font-size:11px;color:var(--accent,#5b8def);" }, "● actif") : btn("Activer", async () => { await jpost(`/api/projects/${encodeURIComponent(nom)}/activate`); rerender(); }),
            el("span", { style: "flex:1;" }),
            btn("Supprimer", async () => { await fetch(`/api/projects/${encodeURIComponent(nom)}`, { method: "DELETE", headers: HT }); rerender(); })),
          el("div", { style: "font-size:11px;opacity:.7;margin-top:8px;" }, "Mémoire du projet (contexte injecté aux IA quand ce projet est actif)"),
          mem,
          el("div", { style: "text-align:right;margin-top:6px;" }, btn("Enregistrer la mémoire", async () => { await jpost(`/api/projects/${encodeURIComponent(nom)}/memory`, { memory: mem.value }); }, true)));
        liste.append(bloc);
      });
    }
    dessine(d);
    const nouveau = el("input", { placeholder: "Nom du nouveau projet" });
    corps.append(el("p", { style: "margin:0 0 12px;font-size:12px;opacity:.75;" }, "Un projet a sa propre mémoire, injectée à toutes les IA quand il est actif — comme un projet Claude."), liste,
      el("div", { style: "display:flex;gap:8px;margin-top:8px;" }, (nouveau.style.cssText += ";flex:1;padding:8px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;", nouveau),
        btn("Créer", async () => { if (nouveau.value.trim()) { await jpost("/api/projects", { name: nouveau.value.trim() }); nouveau.value = ""; rerender(); } }, true)));
    overlay("Projets", corps);
  }

  // ---- rail des projets a gauche (visuel facon Claude) ----
  let railOuvert = true;
  function railProjets() {
    if (document.getElementById("vaultia-rail")) return;
    const rail = el("div", { id: "vaultia-rail", style: "position:fixed;top:0;left:0;bottom:0;width:230px;z-index:900;background:var(--bg-panel,#17171c);border-right:1px solid var(--border,#2a2a30);display:flex;flex-direction:column;font:13px system-ui;overflow:hidden;" });
    const tete = el("div", { style: "padding:12px 12px 8px;display:flex;align-items:center;justify-content:space-between;" },
      el("span", { style: "font-weight:700;opacity:.85;" }, "Projets"),
      el("button", { title: "Nouveau projet", style: "background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:7px;padding:2px 9px;cursor:pointer;font-size:15px;", onclick: creerProjet }, "＋"));
    const liste = el("div", { id: "vaultia-rail-liste", style: "flex:1;overflow:auto;padding:4px 8px;" });
    const memZone = el("div", { id: "vaultia-rail-mem", style: "border-top:1px solid var(--border,#2a2a30);padding:10px 12px;display:none;" });
    rail.append(tete, liste, memZone);
    document.body.append(rail);
    ajusterMarge();
    rafraichirRail();
  }
  function ajusterMarge() {
    const app = document.getElementById("app");
    if (app) { app.style.marginLeft = railOuvert ? "230px" : "0"; app.style.transition = "margin-left .15s"; }
    const rail = document.getElementById("vaultia-rail");
    if (rail) rail.style.transform = railOuvert ? "none" : "translateX(-230px)";
  }
  function basculerRail() { railOuvert = !railOuvert; ajusterMarge(); }
  async function creerProjet() {
    const nom = prompt("Nom du nouveau projet :");
    if (nom && nom.trim()) { await jpost("/api/projects", { name: nom.trim() }); rafraichirRail(); }
  }
  async function rafraichirRail() {
    const liste = document.getElementById("vaultia-rail-liste"); if (!liste) return;
    const d = await jget("/api/projects").catch(() => ({ projets: {}, actif: "" }));
    liste.innerHTML = "";
    const noms = Object.keys(d.projets || {});
    if (!noms.length) liste.append(el("div", { style: "opacity:.55;padding:8px;font-size:12px;" }, "Aucun projet. ＋ pour en créer un."));
    noms.forEach((nom) => {
      const actif = d.actif === nom;
      const item = el("div", { style: `display:flex;align-items:center;gap:6px;padding:8px 9px;margin:2px 0;border-radius:8px;cursor:pointer;${actif ? "background:var(--accent,#5b8def);color:#fff;" : ""}`,
        onclick: async () => { await jpost(`/api/projects/${encodeURIComponent(nom)}/activate`); rafraichirRail(); ouvrirMemoire(nom, d.projets[nom].memoire || ""); } },
        el("span", { style: "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, nom),
        actif ? el("span", { title: "actif", style: "font-size:10px;" }, "●") : null);
      liste.append(item);
    });
    if (d.actif) ouvrirMemoire(d.actif, (d.projets[d.actif] || {}).memoire || ""); else document.getElementById("vaultia-rail-mem").style.display = "none";
  }
  function ouvrirMemoire(nom, memoire) {
    const z = document.getElementById("vaultia-rail-mem"); if (!z) return;
    z.style.display = "block"; z.innerHTML = "";
    const ta = el("textarea", { rows: "6", style: "width:100%;box-sizing:border-box;margin-top:6px;padding:7px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;resize:vertical;" });
    ta.value = memoire;
    z.append(el("div", { style: "font-size:11px;opacity:.7;" }, `Mémoire de « ${nom} » (injectée aux IA)`), ta,
      el("div", { style: "text-align:right;margin-top:6px;" }, btn("Enregistrer", async () => { await jpost(`/api/projects/${encodeURIComponent(nom)}/memory`, { memory: ta.value }); }, true)));
  }

  // ---- boutons du header ----

  function boutons() {
    const droite = document.querySelector(".header-right");
    if (!droite || document.getElementById("vaultia-add")) return;
    const style = "background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:8px;padding:5px 10px;margin-left:6px;cursor:pointer;font:13px system-ui;";
    [["vaultia-proj", "📁 Projets", basculerRail], ["vaultia-stats", "📊 Stats", ouvrirStats], ["vaultia-brain", "🧠 Modèles", ouvrirModeles], ["vaultia-add", "＋ IA", ouvrirAjout]]
      .forEach(([id, txt, on]) => droite.insertBefore(el("button", { id, style, onclick: on }, txt), droite.firstChild));
  }

  // ---- bandeau « qui réfléchit » au-dessus du compositeur ----
  function bandeauReflexion() {
    const ancre = document.getElementById("mention-toggles-row") || document.getElementById("input-row");
    if (!ancre || document.getElementById("vaultia-reflexion")) return;
    const bar = el("div", { id: "vaultia-reflexion", style: "display:none;padding:5px 12px;font-size:12px;color:var(--accent,#5b8def);gap:8px;align-items:center;" });
    ancre.parentNode.insertBefore(bar, ancre);
    async function tick() {
      try {
        const s = await jget("/api/status");
        const busy = Object.keys(s).filter((n) => n !== "paused" && s[n] && s[n].busy).map((n) => s[n].label || n);
        if (busy.length) { bar.style.display = "flex"; bar.innerHTML = `<span class="vaultia-spin" style="display:inline-block;width:10px;height:10px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:vaultiaSpin .8s linear infinite;"></span> ${busy.join(", ")} ${busy.length > 1 ? "réfléchissent" : "réfléchit"}…`; }
        else bar.style.display = "none";
      } catch (e) {}
    }
    if (!document.getElementById("vaultia-kf")) { const st = el("style", { id: "vaultia-kf" }); st.textContent = "@keyframes vaultiaSpin{to{transform:rotate(360deg)}}"; document.head.append(st); }
    tick(); setInterval(tick, 1500);
  }

  // ---- pastilles d'initiale par marque (badge original, coloré ; pas le logo déposé) ----
  function badgesAvatars() {
    const peindre = () => document.querySelectorAll(".avatar").forEach((a) => {
      const wrap = a.closest(".avatar-wrap"); const nom = (wrap && wrap.dataset.agent) || a.dataset.agent || "";
      const lettre = (nom || "?").trim().charAt(0).toUpperCase();
      if (a.textContent !== lettre) { a.textContent = lettre; a.style.display = "flex"; a.style.alignItems = "center"; a.style.justifyContent = "center"; a.style.fontWeight = "700"; a.style.color = "#fff"; a.style.fontSize = "13px"; }
    });
    peindre();
    new MutationObserver(peindre).observe(document.body, { childList: true, subtree: true });
  }

  function init() { boutons(); railProjets(); bandeauReflexion(); badgesAvatars(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
