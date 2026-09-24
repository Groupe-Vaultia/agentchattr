/* vaultia.js — menu de gauche Vaultia (autonome, chargé après chat.js).
   Repliable · actions (+ IA, Modèles, Stats) · projets CONTENANT les conversations
   (glisser-déposer) + mémoire par projet · bandeau « qui réfléchit » · pastilles d'initiale. */
(function () {
  "use strict";
  const TOKEN = window.__SESSION_TOKEN__ || "";
  const H = { "Content-Type": "application/json", "X-Session-Token": TOKEN };
  const HT = { "X-Session-Token": TOKEN };
  const EFFORTS = [{ v: "", l: "Défaut" }, { v: "rapide", l: "Rapide" }, { v: "standard", l: "Standard" }, { v: "profond", l: "Profond" }];
  const RAIL_W = 250;

  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === "style") e.style.cssText = attrs[k];
      else if (k.slice(0, 2) === "on" && typeof attrs[k] === "function") e.addEventListener(k.slice(2), attrs[k]);
      else if (k === "html") e.innerHTML = attrs[k];
      else if (attrs[k] === true) e.setAttribute(k, "");
      else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    }
    for (const kid of kids) if (kid != null) e.append(kid);
    return e;
  }
  const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + " k" : "" + n);
  const jget = (u) => fetch(u, { headers: HT }).then((r) => r.json());
  const jpost = (u, b) => fetch(u, { method: "POST", headers: H, body: JSON.stringify(b || {}) }).then((r) => r.json());
  const sanitize = (s) => s.trim().toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 20);

  function overlay(titre, corps) {
    const fond = el("div", { style: "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10000;display:flex;align-items:center;justify-content:center;" });
    const boite = el("div", { style: "background:var(--bg-panel,#1e1e24);color:var(--text,#e8e8ea);border:1px solid var(--border,#3a3a44);border-radius:12px;padding:20px 22px;width:min(520px,94vw);max-height:88vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.5);font:14px/1.5 system-ui,sans-serif;" });
    fond.addEventListener("click", (ev) => { if (ev.target === fond) fond.remove(); });
    boite.append(el("h2", { style: "margin:0 0 14px;font-size:17px;" }, titre)); boite.append(corps);
    fond.append(boite); document.body.append(fond); return fond;
  }
  function champ(label, input) {
    input.style.cssText += ";display:block;width:100%;margin-top:4px;padding:7px 9px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;box-sizing:border-box;font:inherit;";
    return el("label", { style: "display:block;margin:0 0 11px;font-size:12px;opacity:.8;" }, label, input);
  }
  const btn = (t, on, primary) => el("button", { onclick: on, style: `border:0;border-radius:8px;padding:8px 14px;font:inherit;cursor:pointer;${primary ? "background:var(--accent,#5b8def);color:#fff;" : "background:var(--border,#3a3a44);color:inherit;"}` }, t);

  // ---------- panneaux (overlays) ----------
  function ouvrirAjout() {
    const nom = el("input", { placeholder: "identifiant (@mention)" }), label = el("input", { placeholder: "Nom affiché" }),
      lien = el("input", { placeholder: "Lien (base_url, http…/v1)" }), modele = el("input", { placeholder: "modèle" }),
      cle = el("input", { placeholder: "Clé — variable d'env (optionnel)" }), couleur = el("input", { type: "color", value: "#6b7280", style: "height:34px;" }),
      sys = el("textarea", { rows: "2", placeholder: "Consigne système (optionnel)" }), etat = el("div", { style: "min-height:18px;font-size:12px;" });
    const go = btn("Connecter", async () => {
      etat.textContent = "Connexion…"; etat.style.color = "";
      const d = await jpost("/api/agents/add", { name: sanitize(nom.value), label: label.value.trim(), base_url: lien.value.trim(), model: modele.value.trim(), api_key_env: cle.value.trim(), color: couleur.value, system_prompt: sys.value.trim() });
      if (d.error) { etat.style.color = "#e5675f"; etat.textContent = "✗ " + d.error; } else { etat.style.color = "#59b56a"; etat.textContent = `✓ ${d.label} connecté.`; }
    }, true);
    overlay("Connecter une IA", el("div", {}, champ("Identifiant", nom), champ("Nom affiché", label), champ("Lien de connexion", lien), champ("Modèle", modele), champ("Clé (variable d'env.)", cle), champ("Couleur", couleur), champ("Consigne système", sys), etat, el("div", { style: "text-align:right;margin-top:8px;" }, go)));
  }
  async function ouvrirModeles() {
    const status = await jget("/api/status").catch(() => ({}));
    const corps = el("div", {});
    corps.append(el("p", { style: "margin:0 0 12px;font-size:12px;opacity:.75;" }, "Modèle et niveau de raisonnement par IA. Vide = Auto/défaut. Immédiat pour Qwen/Cursor/Gemini ; au prochain lancement pour Claude/Codex."));
    Object.keys(status).filter((n) => n !== "paused").forEach((nom) => {
      const info = status[nom] || {};
      const eff = el("select", { style: "padding:5px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;" });
      EFFORTS.forEach((o) => { const op = el("option", { value: o.v }, o.l); if ((info.effort || "") === o.v) op.selected = true; eff.append(op); });
      eff.addEventListener("change", () => jpost("/api/efforts/" + encodeURIComponent(nom), { effort: eff.value }));
      const mod = el("input", { value: info.model || "", placeholder: "Auto", style: "width:140px;padding:5px 7px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;" });
      mod.addEventListener("change", () => jpost("/api/models_choice/" + encodeURIComponent(nom), { model: mod.value.trim() }));
      corps.append(el("div", { style: "display:flex;align-items:center;gap:8px;padding:8px 0;border-top:1px solid var(--border,#2a2a30);flex-wrap:wrap;" },
        el("span", { style: "min-width:100px;font-weight:600;" }, el("span", { style: `display:inline-block;width:9px;height:9px;border-radius:50%;background:${info.color || "#888"};margin-right:7px;` }), info.label || nom),
        el("span", { style: "font-size:11px;opacity:.6;" }, "modèle"), mod, el("span", { style: "font-size:11px;opacity:.6;" }, "raison."), eff));
    });
    overlay("Modèles & raisonnement", corps);
  }
  async function ouvrirStats() {
    const d = await jget("/api/stats").catch(() => ({ par_agent: {} }));
    const corps = el("div", {}); const rows = Object.entries(d.par_agent || {}).sort((a, b) => b[1].jetons_estimes - a[1].jetons_estimes);
    const tbl = el("table", { style: "width:100%;border-collapse:collapse;font-size:13px;" });
    tbl.append(el("tr", { style: "text-align:left;opacity:.7;" }, el("th", { style: "padding:6px 4px;" }, "Participant"), el("th", {}, "Messages"), el("th", {}, "Jetons estimés")));
    rows.forEach(([nom, e]) => tbl.append(el("tr", { style: "border-top:1px solid var(--border,#2a2a30);" }, el("td", { style: "padding:6px 4px;" }, (e.est_agent ? "🤖 " : "🧑 ") + nom), el("td", { style: "font-variant-numeric:tabular-nums;" }, "" + e.messages), el("td", { style: "font-variant-numeric:tabular-nums;" }, fmt(e.jetons_estimes)))));
    corps.append(rows.length ? tbl : el("p", { style: "opacity:.6;" }, "Aucun message encore."));
    corps.append(el("p", { style: "margin-top:14px;font-size:11px;opacity:.6;" }, d.note || ""));
    overlay("Statistiques — consommation", corps);
  }

  // ---------- le menu de gauche ----------
  const estMobile = () => window.innerWidth < 768;
  const largeurRail = () => (estMobile() ? Math.min(300, Math.round(window.innerWidth * 0.86)) : RAIL_W);
  let ouvert;
  try { const v = localStorage.getItem("vaultia-rail"); ouvert = v === null ? !estMobile() : v === "1"; } catch (e) { ouvert = !estMobile(); }
  let expanded = null;

  function ajuster() {
    const w = largeurRail(), mob = estMobile();
    const rail = document.getElementById("vaultia-rail");
    if (rail) { rail.style.width = w + "px"; rail.style.transform = ouvert ? "none" : `translateX(-${w + 2}px)`; }
    const app = document.getElementById("app");
    if (app) { app.style.transition = "margin-left .16s"; app.style.marginLeft = (ouvert && !mob) ? w + "px" : "0"; }
    const bd = document.getElementById("vaultia-backdrop");
    if (bd) bd.style.display = (ouvert && mob) ? "block" : "none";
    const t = document.getElementById("vaultia-toggle");
    if (t) t.style.left = (ouvert && !mob ? w - 34 : 6) + "px";
  }
  function basculer() { ouvert = !ouvert; try { localStorage.setItem("vaultia-rail", ouvert ? "1" : "0"); } catch (e) {} ajuster(); }
  function fermerSiMobile() { if (estMobile() && ouvert) { ouvert = false; ajuster(); } }

  function canaux() { return Array.isArray(window.channelList) ? window.channelList.slice() : ["general"]; }

  function itemCanal(nom) {
    const actif = window.activeChannel === nom;
    const it = el("div", { draggable: "true", style: `display:flex;align-items:center;gap:6px;padding:6px 8px;margin:1px 0;border-radius:7px;cursor:pointer;font-size:13px;${actif ? "background:var(--accent,#5b8def);color:#fff;" : ""}`,
      onclick: () => { if (window.switchChannel) window.switchChannel(nom); fermerSiMobile(); setTimeout(rendre, 60); },
      ondragstart: (e) => { e.dataTransfer.setData("text/canal", nom); e.dataTransfer.effectAllowed = "move"; },
    }, el("span", { style: "opacity:.6;" }, "#"), el("span", { style: "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, nom));
    if (nom !== "general") {
      it.append(el("button", { title: "Supprimer la conversation", style: "background:none;border:0;color:inherit;opacity:.5;cursor:pointer;font-size:15px;line-height:1;padding:0 2px;",
        onclick: (e) => {
          e.stopPropagation();
          if (!confirm("Supprimer la conversation \u00ab " + nom + " \u00bb ? Cette action est definitive.")) return;
          if (window.ws) window.ws.send(JSON.stringify({ type: "channel_delete", name: nom }));
          jpost("/api/projects/assign", { channel: nom, project: "" });
          if (window.activeChannel === nom && window.switchChannel) window.switchChannel("general");
          setTimeout(rendre, 400);
        } }, "\u00d7"));
    }
    return it;
  }
  function cibleDrop(elem, projet) {
    elem.addEventListener("dragover", (e) => { e.preventDefault(); elem.style.outline = "2px dashed var(--accent,#5b8def)"; });
    elem.addEventListener("dragleave", () => { elem.style.outline = ""; });
    elem.addEventListener("drop", async (e) => {
      e.preventDefault(); elem.style.outline = "";
      const canal = e.dataTransfer.getData("text/canal");
      if (canal) { await jpost("/api/projects/assign", { channel: canal, project: projet }); rendre(); }
    });
  }

  async function rendre() {
    const liste = document.getElementById("vaultia-rail-corps"); if (!liste) return;
    const d = await jget("/api/projects").catch(() => ({ projets: {}, actif: "" }));
    const projets = d.projets || {};
    const assignes = new Set(); Object.values(projets).forEach((p) => (p.channels || []).forEach((c) => assignes.add(c)));
    liste.innerHTML = "";

    const secProj = el("div", { style: "display:flex;align-items:center;justify-content:space-between;padding:4px 10px 2px;" },
      el("span", { style: "font-size:11px;text-transform:uppercase;letter-spacing:.04em;opacity:.55;" }, "Projets"),
      el("button", { title: "Nouveau projet", style: "background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:6px;padding:0 8px;cursor:pointer;font-size:14px;", onclick: async () => { const n = prompt("Nom du projet :"); if (n && n.trim()) { await jpost("/api/projects", { name: n.trim() }); rendre(); } } }, "＋"));
    liste.append(secProj);

    Object.keys(projets).forEach((nom) => {
      const p = projets[nom]; const actif = d.actif === nom; const open = expanded === nom;
      const tete = el("div", { style: `display:flex;align-items:center;gap:6px;padding:7px 9px;margin:1px 6px;border-radius:8px;cursor:pointer;${actif ? "background:rgba(91,141,239,.18);" : ""}`,
        onclick: async () => { expanded = open ? null : nom; if (!actif) await jpost(`/api/projects/${encodeURIComponent(nom)}/activate`); rendre(); } },
        el("span", { style: "opacity:.6;font-size:11px;width:10px;" }, open ? "▾" : "▸"),
        el("span", { style: "flex:1;font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, nom),
        actif ? el("span", { title: "actif", style: "color:var(--accent,#5b8def);font-size:10px;" }, "●") : null);
      cibleDrop(tete, nom);
      liste.append(tete);
      if (open) {
        const sous = el("div", { style: "margin:0 6px 6px 18px;" });
        (p.channels || []).forEach((c) => { if (canaux().includes(c)) sous.append(itemCanal(c)); });
        sous.append(el("div", { style: "padding:5px 8px;font-size:12px;opacity:.7;cursor:pointer;", onclick: async () => {
          const n = sanitize(prompt("Nom de la conversation :") || ""); if (!n) return;
          if (!canaux().includes(n) && window.ws) { if (window._setPendingChannelSwitch) window._setPendingChannelSwitch(n); window.ws.send(JSON.stringify({ type: "channel_create", name: n })); }
          setTimeout(async () => { await jpost("/api/projects/assign", { channel: n, project: nom }); rendre(); }, 400);
        } }, "＋ Conversation"));
        const mem = el("textarea", { rows: "4", style: "width:100%;box-sizing:border-box;margin-top:4px;padding:7px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;resize:vertical;font-size:12px;" });
        mem.value = p.memoire || "";
        sous.append(el("div", { style: "font-size:11px;opacity:.6;margin-top:6px;" }, "Mémoire (injectée aux IA)"), mem,
          el("div", { style: "text-align:right;margin-top:4px;" }, btn("Enregistrer", async () => { await jpost(`/api/projects/${encodeURIComponent(nom)}/memory`, { memory: mem.value }); }, true)));
        liste.append(sous);
      }
    });

    const horsTitre = el("div", { style: "padding:10px 10px 2px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;opacity:.55;" }, "Conversations");
    cibleDrop(horsTitre, "");
    liste.append(horsTitre);
    const hors = el("div", { style: "padding:0 6px;" });
    cibleDrop(hors, "");
    canaux().filter((c) => !assignes.has(c)).forEach((c) => hors.append(itemCanal(c)));
    hors.append(el("div", { style: "padding:5px 8px;font-size:12px;opacity:.7;cursor:pointer;", onclick: () => {
      const n = sanitize(prompt("Nom de la conversation :") || ""); if (n && !canaux().includes(n) && window.ws) { if (window._setPendingChannelSwitch) window._setPendingChannelSwitch(n); window.ws.send(JSON.stringify({ type: "channel_create", name: n })); setTimeout(rendre, 400); }
    } }, "＋ Conversation"));
    liste.append(hors);
  }

  function railMenu() {
    if (document.getElementById("vaultia-rail")) return;
    const rail = el("div", { id: "vaultia-rail", style: `position:fixed;top:0;left:0;bottom:0;width:${RAIL_W}px;z-index:950;background:var(--bg-panel,#15151a);border-right:1px solid var(--border,#2a2a30);display:flex;flex-direction:column;font:13px system-ui;overflow:hidden;` });
    const tete = el("div", { style: "padding:12px 12px 6px;display:flex;align-items:center;gap:8px;" }, el("img", { src: "/static/logo.png", style: "height:26px;" }));
    const actions = el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;padding:4px 10px 10px;border-bottom:1px solid var(--border,#2a2a30);" });
    [["＋ IA", ouvrirAjout], ["🧠 Modèles", ouvrirModeles], ["📊 Stats", ouvrirStats]].forEach(([t, on]) =>
      actions.append(el("button", { onclick: on, style: "flex:1 0 auto;background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:7px;padding:5px 8px;cursor:pointer;font-size:12px;" }, t)));
    const corps = el("div", { id: "vaultia-rail-corps", style: "flex:1;overflow:auto;padding:6px 0;" });
    rail.append(tete, actions, corps);
    rail.style.zIndex = "1002";
    document.body.append(rail);
    const backdrop = el("div", { id: "vaultia-backdrop", style: "display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1001;", onclick: () => { ouvert = false; ajuster(); } });
    document.body.append(backdrop);
    const toggle = el("button", { id: "vaultia-toggle", title: "Ouvrir/fermer le menu", style: "position:fixed;top:9px;z-index:1003;background:var(--bg-panel,#15151a);border:1px solid var(--border,#3a3a44);color:inherit;border-radius:8px;width:32px;height:32px;cursor:pointer;font-size:15px;", onclick: basculer }, "☰");
    document.body.append(toggle);
    window.addEventListener("resize", ajuster);
    ajuster(); rendre();
    setInterval(() => { if (ouvert) rendre(); }, 4000);
  }

  // ---------- bandeau « qui réfléchit » ----------
  function bandeauReflexion() {
    const ancre = document.getElementById("mention-toggles-row") || document.getElementById("input-row");
    if (!ancre || document.getElementById("vaultia-reflexion")) return;
    const bar = el("div", { id: "vaultia-reflexion", style: "display:none;padding:5px 12px;font-size:12px;color:var(--accent,#5b8def);gap:8px;align-items:center;" });
    ancre.parentNode.insertBefore(bar, ancre);
    if (!document.getElementById("vaultia-kf")) { const st = el("style", { id: "vaultia-kf" }); st.textContent = "@keyframes vaultiaSpin{to{transform:rotate(360deg)}}"; document.head.append(st); }
    async function tick() {
      try {
        const s = await jget("/api/status");
        const busy = Object.keys(s).filter((n) => n !== "paused" && s[n] && s[n].busy).map((n) => s[n].label || n);
        if (busy.length) { bar.style.display = "flex"; bar.innerHTML = `<span style="display:inline-block;width:10px;height:10px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:vaultiaSpin .8s linear infinite;"></span> ${busy.join(", ")} ${busy.length > 1 ? "réfléchissent" : "réfléchit"}…`; }
        else bar.style.display = "none";
      } catch (e) {}
    }
    tick(); setInterval(tick, 1500);
  }

  // ---------- pastilles d'initiale (badge original, pas de logo déposé) ----------
  function badgesAvatars() {
    const peindre = () => document.querySelectorAll(".avatar").forEach((a) => {
      const wrap = a.closest(".avatar-wrap"); const nom = (wrap && wrap.dataset.agent) || a.dataset.agent || "";
      const lettre = (nom || "?").trim().charAt(0).toUpperCase();
      if (a.textContent !== lettre) { a.textContent = lettre; a.style.display = "flex"; a.style.alignItems = "center"; a.style.justifyContent = "center"; a.style.fontWeight = "700"; a.style.color = "#fff"; a.style.fontSize = "13px"; }
    });
    peindre(); new MutationObserver(peindre).observe(document.body, { childList: true, subtree: true });
  }

  // ---------- bouton photo dans le compositeur (mobile : appareil photo + galerie) ----------
  function boutonPhoto() {
    const row = document.getElementById("input-row");
    if (!row || document.getElementById("vaultia-photo-btn")) return;
    const input = el("input", { type: "file", accept: "image/*", id: "vaultia-photo-input", multiple: "multiple", style: "display:none;" });
    input.addEventListener("change", async () => {
      const files = Array.from(input.files || []);
      for (const f of files) { if (window.uploadImage) { try { await window.uploadImage(f); } catch (e) {} } }
      input.value = "";
    });
    const btn = el("button", { id: "vaultia-photo-btn", type: "button", title: "Ajouter une photo",
      style: "background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:10px;min-width:40px;height:40px;cursor:pointer;font-size:18px;flex:0 0 auto;",
      onclick: () => input.click() }, "📷");
    row.insertBefore(btn, row.firstChild);
    row.appendChild(input);
  }

  function init() { railMenu(); bandeauReflexion(); badgesAvatars(); boutonPhoto(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
