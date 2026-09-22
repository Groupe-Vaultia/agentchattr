/* vaultia.js — ajouts Vaultia (21 sept. 2026) : « + IA » (connecter une IA par un lien)
   et « Raisonnement » (niveau par IA). Autonome : aucune modification de chat.js.
   Chargé après chat.js ; parle aux endpoints /api/agents/add, /api/status, /api/efforts. */
(function () {
  "use strict";
  const TOKEN = window.__SESSION_TOKEN__ || "";
  const H = { "Content-Type": "application/json", "X-Session-Token": TOKEN };
  const EFFORTS = [
    { v: "", label: "Défaut" },
    { v: "rapide", label: "Rapide" },
    { v: "standard", label: "Standard" },
    { v: "profond", label: "Profond" },
  ];

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

  function overlay(titre, corps) {
    const fond = el("div", { style: "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;" });
    const boite = el("div", { style: "background:var(--bg-panel,#1e1e24);color:var(--text,#e8e8ea);border:1px solid var(--border,#3a3a44);border-radius:12px;padding:20px 22px;width:min(460px,92vw);max-height:88vh;overflow:auto;box-shadow:0 10px 40px rgba(0,0,0,.5);font:14px/1.5 system-ui,sans-serif;" });
    fond.addEventListener("click", (ev) => { if (ev.target === fond) fond.remove(); });
    boite.append(el("h2", { style: "margin:0 0 14px;font-size:17px;" }, titre));
    boite.append(corps);
    fond.append(boite);
    document.body.append(fond);
    return fond;
  }

  function champ(label, input) {
    return el("label", { style: "display:block;margin:0 0 11px;font-size:12px;opacity:.8;" }, label,
      (input.style.cssText += ";display:block;width:100%;margin-top:4px;padding:7px 9px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;box-sizing:border-box;font:inherit;", input));
  }

  // ---- « + IA » : connecter une IA par un lien (point OpenAI-compatible) ----
  function ouvrirAjout() {
    const nom = el("input", { placeholder: "qwen-2, mixtral, openrouter…", maxlength: "31" });
    const label = el("input", { placeholder: "Nom affiché (ex. Mixtral)" });
    const lien = el("input", { placeholder: "http://172.30.0.1:8080/v1  ou  https://…/v1" });
    const modele = el("input", { placeholder: "nom du modèle (ex. qwen3-coder-next-80b)" });
    const cle = el("input", { placeholder: "Variable d'env. de la clé (optionnel, ex. OPENROUTER_API_KEY)" });
    const couleur = el("input", { type: "color", value: "#6b7280", style: "height:34px;padding:2px;" });
    const eff = el("select"); EFFORTS.forEach((o) => eff.append(el("option", { value: o.v }, o.label)));
    const sys = el("textarea", { rows: "2", placeholder: "Consigne de système (optionnel)" });
    const etat = el("div", { style: "min-height:18px;margin:6px 0 2px;font-size:12px;" });

    const valider = el("button", {
      style: "background:var(--accent,#5b8def);color:#fff;border:0;border-radius:8px;padding:9px 16px;font:inherit;cursor:pointer;",
      onclick: async () => {
        etat.textContent = "Connexion…"; etat.style.color = "";
        try {
          const r = await fetch("/api/agents/add", {
            method: "POST", headers: H,
            body: JSON.stringify({
              name: nom.value.trim().toLowerCase(), label: label.value.trim(), base_url: lien.value.trim(),
              model: modele.value.trim(), api_key_env: cle.value.trim(), color: couleur.value,
              effort: eff.value, system_prompt: sys.value.trim(),
            }),
          });
          const d = await r.json();
          if (!r.ok) { etat.style.color = "#e5675f"; etat.textContent = "✗ " + (d.error || "échec"); return; }
          etat.style.color = "#59b56a";
          etat.textContent = `✓ ${d.label} connecté — @${d.name} arrive dans la salle.`;
          valider.disabled = true;
        } catch (e) { etat.style.color = "#e5675f"; etat.textContent = "✗ " + e.message; }
      },
    }, "Connecter");

    const corps = el("div", {}, champ("Identifiant (@mention)", nom), champ("Nom affiché", label),
      champ("Lien de connexion (base_url)", lien), champ("Modèle", modele), champ("Clé — variable d'environnement", cle),
      champ("Couleur", couleur), champ("Niveau de raisonnement", eff), champ("Consigne de système", sys), etat,
      el("div", { style: "margin-top:8px;display:flex;gap:8px;justify-content:flex-end;" }, valider));
    overlay("Connecter une IA", corps);
  }

  // ---- « Raisonnement » : niveau par IA ----
  async function ouvrirRaisonnement() {
    let status = {};
    try { status = await (await fetch("/api/status", { headers: { "X-Session-Token": TOKEN } })).json(); } catch (e) {}
    const corps = el("div", {});
    corps.append(el("p", { style: "margin:0 0 12px;font-size:12px;opacity:.75;" },
      "Le niveau s'applique au message suivant pour une IA locale/API ; pour Claude et Codex, au prochain lancement de l'agent."));
    Object.keys(status).filter((n) => n !== "paused").forEach((nom) => {
      const info = status[nom] || {};
      const sel = el("select", { style: "padding:5px 8px;border-radius:7px;border:1px solid var(--border,#3a3a44);background:var(--bg,#141418);color:inherit;font:inherit;" });
      EFFORTS.forEach((o) => { const opt = el("option", { value: o.v }, o.label); if ((info.effort || "") === o.v) opt.selected = true; sel.append(opt); });
      sel.addEventListener("change", async () => {
        sel.disabled = true;
        try { await fetch("/api/efforts/" + encodeURIComponent(nom), { method: "POST", headers: H, body: JSON.stringify({ effort: sel.value }) }); }
        finally { sel.disabled = false; }
      });
      const pastille = el("span", { style: `display:inline-block;width:9px;height:9px;border-radius:50%;background:${info.color || "#888"};margin-right:7px;` });
      corps.append(el("div", { style: "display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 0;border-top:1px solid var(--border,#2a2a30);" },
        el("span", {}, pastille, info.label || nom), sel));
    });
    overlay("Niveau de raisonnement", corps);
  }

  function boutons() {
    const droite = document.querySelector(".header-right");
    if (!droite || document.getElementById("vaultia-add")) return;
    const style = "background:none;border:1px solid var(--border,#3a3a44);color:inherit;border-radius:8px;padding:5px 10px;margin-left:6px;cursor:pointer;font:13px system-ui;";
    droite.insertBefore(el("button", { id: "vaultia-brain", title: "Niveau de raisonnement par IA", style, onclick: ouvrirRaisonnement }, "🧠"), droite.firstChild);
    droite.insertBefore(el("button", { id: "vaultia-add", title: "Connecter une IA par un lien", style, onclick: ouvrirAjout }, "＋ IA"), droite.firstChild);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boutons);
  else boutons();
})();
