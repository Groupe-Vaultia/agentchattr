/* vaultia.js — la couche Vaultia de la salle (autonome, chargé après chat.js).
   Menu de gauche repliable (projets CONTENANT les conversations, glisser-déposer, mémoire par projet,
   renommer, non-lus) · IA / Modèles / Stats · ligne « qui réfléchit » + rappel des décisions en attente
   · bouton @ des mentions · titre de conversation et menu « plus » au téléphone · pastilles d'initiale
   · photo et document. L'habillage vit dans vaultia-theme.css (classes .vt-*). */
(function () {
  "use strict";
  const EFFORTS = [{ v: "", l: "Défaut" }, { v: "rapide", l: "Rapide" }, { v: "standard", l: "Standard" }, { v: "profond", l: "Profond" }];
  const RAIL_W = 256;

  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === "style") e.style.cssText = attrs[k];
      else if (k.slice(0, 2) === "on" && typeof attrs[k] === "function") e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] === true) e.setAttribute(k, "");
      else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    }
    for (const kid of kids) if (kid != null) e.append(kid);   // une chaîne devient un nœud texte : jamais de HTML
    return e;
  }

  // Icônes : un seul trait (1,75), bouts arrondis, 24×24. Jamais d'émoji comme icône.
  const SVG_NS = "http://www.w3.org/2000/svg";
  const TRACES = {
    plus: ["M12 5v14", "M5 12h14"],
    reglages: ["M4 7h9", "M19 7h1", "circle:16,7,2.2", "M4 17h3", "M13 17h7", "circle:10,17,2.2"],
    stats: ["M6 20v-6", "M12 20V5", "M18 20v-10"],
    photo: ["M4 9a2.5 2.5 0 0 1 2.5-2.5h1.6l1.5-2h4.8l1.5 2h1.6A2.5 2.5 0 0 1 20 9v7.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5z", "circle:12,12.6,3.4"],
    trombone: ["M20 11.4l-8.1 8.1a5.2 5.2 0 0 1-7.4-7.4l8.4-8.4a3.4 3.4 0 0 1 4.8 4.8l-8.2 8.2a1.7 1.7 0 0 1-2.4-2.4l7.6-7.6"],
    arobase: ["circle:12,12,3.8", "M15.8 8.2v5.1a2.7 2.7 0 0 0 5.4 0V12a9.2 9.2 0 1 0-3.6 7.3"],
    panneau: ["rect:3.5,4.5,17,15,3", "M9.5 4.5v15"],
    fermer: ["M7 7l10 10", "M17 7L7 17"],
    chevron: ["M9.5 6.5l5.5 5.5-5.5 5.5"],
    crayon: ["M15.5 5.5l3 3L9 18H6v-3z", "M13.5 7.5l3 3"],
    plusieurs: ["circle:5.5,12,1.3", "circle:12,12,1.3", "circle:18.5,12,1.3"],
    bas: ["M12 5v13", "M6.5 12.5L12 18l5.5-5.5"],
    horloge: ["circle:12,12,8.5", "M12 7.5v4.8l3.2 1.9"],
  };
  function ico(nom, taille) {
    const s = document.createElementNS(SVG_NS, "svg");
    const t = String(taille || 16);
    for (const [k, v] of [["viewBox", "0 0 24 24"], ["width", t], ["height", t], ["fill", "none"], ["stroke", "currentColor"],
      ["stroke-width", "1.75"], ["stroke-linecap", "round"], ["stroke-linejoin", "round"], ["aria-hidden", "true"], ["focusable", "false"]]) s.setAttribute(k, v);
    for (const trace of TRACES[nom] || []) {
      let e;
      if (trace.startsWith("circle:")) {
        const [cx, cy, r] = trace.slice(7).split(",");
        e = document.createElementNS(SVG_NS, "circle"); e.setAttribute("cx", cx); e.setAttribute("cy", cy); e.setAttribute("r", r);
      } else if (trace.startsWith("rect:")) {
        const [x, y, w, h, rx] = trace.slice(5).split(",");
        e = document.createElementNS(SVG_NS, "rect");
        e.setAttribute("x", x); e.setAttribute("y", y); e.setAttribute("width", w); e.setAttribute("height", h); e.setAttribute("rx", rx);
      } else {
        e = document.createElementNS(SVG_NS, "path"); e.setAttribute("d", trace);
      }
      s.append(e);
    }
    return s;
  }

  const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(1).replace(".", ",") + " k" : "" + n);
  const couleurSure = (c) => (/^#[0-9a-f]{3,8}$/i.test(c || "") ? c : "");
  const tactile = () => !!(window.matchMedia && window.matchMedia("(hover: none)").matches);
  // Jeton relu à CHAQUE appel : chat.js le rafraîchit en place après un redémarrage du serveur
  // (refreshSessionToken). Figé au chargement, il faisait tomber tout le menu en 403.
  const tok = () => window.__SESSION_TOKEN__ || "";
  async function appel(u, opts) {
    const o = opts || {};
    const faire = () => fetch(u, Object.assign({}, o, { headers: Object.assign({}, o.headers || {}, { "X-Session-Token": tok() }) }));
    let r = await faire();
    if (r.status === 403 && typeof window.refreshSessionToken === "function" && (await window.refreshSessionToken())) r = await faire();
    return r;
  }
  const jget = (u) => appel(u).then((r) => r.json());
  const jpost = (u, b) => appel(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());
  const sanitize = (s) => s.trim().toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 20);
  // Nom de conversation tel que le serveur l'accepte (^[a-z0-9][a-z0-9-]{0,19}$) : accents ramenés à
  // leur lettre (« Création » donnait « cration »), espaces en tirets.
  const nomCanal = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim()
    .replace(/[\s_]+/g, "-").replace(/[^a-z0-9-]/g, "").replace(/-+/g, "-").replace(/^-+/, "").slice(0, 20).replace(/-+$/, "");

  // ---------- fenêtres ----------
  function overlay(titre, corps, avecTermine, surFermer) {
    const fond = el("div", { class: "vt-fond", style: "position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;padding:16px;" });
    const boite = el("div", { class: "vt-boite", role: "dialog", "aria-modal": "true", "aria-label": titre, tabindex: "-1" });
    function surTouche(ev) { if (ev.key === "Escape") fermer(); }
    function fermer() { fond.remove(); document.removeEventListener("keydown", surTouche); if (surFermer) surFermer(); }
    fond.fermer = fermer;
    fond.addEventListener("click", (ev) => { if (ev.target === fond) fermer(); });
    document.addEventListener("keydown", surTouche);
    boite.append(el("div", { class: "vt-tete-boite" }, el("h2", {}, titre),
      el("button", { class: "vt-fermer", type: "button", title: "Fermer", "aria-label": "Fermer", onclick: fermer }, ico("fermer", 18))), corps);
    if (avecTermine) boite.append(pied(btn("Terminé", fermer, true)));
    fond.append(boite); document.body.append(fond);
    // Au doigt, on ne donne pas le focus au premier champ : il ferait surgir le clavier.
    const premier = corps.querySelector("input, select, textarea");
    if (!tactile() && premier) premier.focus(); else boite.focus();
    return fond;
  }
  function champ(label, input) {
    input.classList.add("vt-champ");
    return el("label", { class: "vt-etiquette" }, label, input);
  }
  const btn = (t, on, principal) => el("button", { class: "vt-btn" + (principal ? " principal" : ""), type: "button", onclick: on }, t);
  const pied = (...enfants) => el("div", { style: "display:flex;justify-content:flex-end;gap:8px;margin-top:16px;" }, ...enfants);

  // prompt(), confirm() et alert() natifs sont ignorés EN SILENCE dans un iframe sans « allow-modals » :
  // c'est le cas du navigateur simple de VS Code, où « + Conversation » ne faisait plus rien.
  // Ces trois boîtes vivent dans la page et marchent partout.
  function demander(titre, libelle, valeur) {
    return new Promise((rendre) => {
      let reponse = null;
      const saisie = el("input", { type: "text", autocomplete: "off", spellcheck: "false" });
      saisie.value = valeur || "";
      const valider = () => { reponse = saisie.value; fond.fermer(); };
      saisie.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); valider(); } });
      const corps = el("div", {}, champ(libelle, saisie), pied(btn("Annuler", () => fond.fermer()), btn("OK", valider, true)));
      const fond = overlay(titre, corps, false, () => rendre(reponse));
      saisie.focus(); saisie.select();   // comme prompt() : on tape tout de suite, au doigt aussi
    });
  }
  function confirmer(titre, message, action) {
    return new Promise((rendre) => {
      let oui = false;
      const corps = el("div", {}, el("p", {}, message),
        pied(btn("Annuler", () => fond.fermer()), btn(action || "OK", () => { oui = true; fond.fermer(); }, true)));
      const fond = overlay(titre, corps, false, () => rendre(oui));
    });
  }
  const avertir = (message, titre) => overlay(titre || "Attention", el("p", {}, message), true);

  function ouvrirAjout() {
    const nom = el("input", { placeholder: "claude-2, mon-modele…" }), label = el("input", { placeholder: "Nom affiché" }),
      lien = el("input", { placeholder: "http://…/v1" }), modele = el("input", { placeholder: "Auto" }),
      cle = el("input", { placeholder: "Nom de la variable d'environnement (optionnel)" }),
      couleur = el("input", { type: "color", value: "#6b7280", style: "height:40px;padding:4px;" }),
      sys = el("textarea", { rows: "2", placeholder: "Consigne système (optionnel)" }), etat = el("div", { class: "vt-note", role: "status", style: "min-height:18px;margin:4px 0 0;" });
    const go = btn("Connecter", async () => {
      etat.className = "vt-note"; etat.textContent = "Connexion…";
      const d = await jpost("/api/agents/add", { name: sanitize(nom.value), label: label.value.trim(), base_url: lien.value.trim(), model: modele.value.trim(), api_key_env: cle.value.trim(), color: couleur.value, system_prompt: sys.value.trim() }).catch((e) => ({ error: String(e) }));
      if (d.error) { etat.className = "vt-note vt-etat-ko"; etat.textContent = "Échec : " + d.error; }
      else { etat.className = "vt-note vt-etat-ok"; etat.textContent = `${d.label} est connecté.`; }
    }, true);
    overlay("Connecter une IA", el("div", {}, champ("Identifiant (pour la @mention)", nom), champ("Nom affiché", label), champ("Lien de connexion", lien),
      champ("Modèle", modele), champ("Clé (variable d'environnement)", cle), champ("Couleur", couleur), champ("Consigne système", sys), etat, pied(go)));
  }
  // Chaque réglage modifié dit s'il a été enregistré, sur sa ligne (aucune panne silencieuse).
  function enregistrer(statut, promesse) {
    statut.className = "vt-statut"; statut.textContent = "…";
    promesse.then((d) => {
      if (d && d.error) { statut.className = "vt-statut vt-etat-ko"; statut.textContent = "Échec : " + d.error; }
      else { statut.className = "vt-statut vt-etat-ok"; statut.textContent = "Enregistré"; setTimeout(() => { if (statut.textContent === "Enregistré") statut.textContent = ""; }, 2400); }
    }).catch((e) => { statut.className = "vt-statut vt-etat-ko"; statut.textContent = "Échec : " + e; });
  }
  async function ouvrirModeles() {
    const status = await jget("/api/status").catch(() => ({}));
    const corps = el("div", {});
    corps.append(el("p", { class: "vt-note" }, "Le modèle et le niveau de raisonnement de chaque IA. Vide = automatique. Pris en compte tout de suite pour Qwen, Cursor et Gemini ; au prochain lancement pour Claude et Codex."));
    const grille = el("div", { class: "vt-grille" },
      el("div", { class: "vt-entete vt-entete-ia" }, "IA"), el("div", { class: "vt-entete" }, "Modèle"), el("div", { class: "vt-entete" }, "Raisonnement"));
    Object.keys(status).filter((n) => n !== "paused").forEach((nom) => {
      const info = status[nom] || {};
      const statut = el("span", { class: "vt-statut", role: "status" });
      const eff = el("select", { class: "vt-champ", "aria-label": "Raisonnement de " + (info.label || nom) });
      EFFORTS.forEach((o) => { const op = el("option", { value: o.v }, o.l); if ((info.effort || "") === o.v) op.selected = true; eff.append(op); });
      eff.addEventListener("change", () => enregistrer(statut, jpost("/api/efforts/" + encodeURIComponent(nom), { effort: eff.value })));
      const mod = el("input", { class: "vt-champ", value: info.model || "", placeholder: "Auto", "aria-label": "Modèle de " + (info.label || nom) });
      mod.addEventListener("change", () => enregistrer(statut, jpost("/api/models_choice/" + encodeURIComponent(nom), { model: mod.value.trim() })));
      const pastille = el("span", { class: "vt-pastille" }); pastille.style.background = couleurSure(info.color) || "var(--v-ink-3)";
      grille.append(el("div", { class: "vt-cellule vt-nom-ia" }, el("span", { class: "vt-nom-ia-texte" }, pastille, info.label || nom), statut),
        el("div", { class: "vt-cellule" }, mod), el("div", { class: "vt-cellule" }, eff));
    });
    corps.append(grille);
    overlay("Modèles et raisonnement", corps, true);
  }
  async function ouvrirStats() {
    const d = await jget("/api/stats").catch(() => ({ par_agent: {} }));
    const corps = el("div", {}); const rows = Object.entries(d.par_agent || {}).sort((a, b) => b[1].jetons_estimes - a[1].jetons_estimes);
    const tbl = el("table", { class: "vt-table" });
    tbl.append(el("tr", {}, el("th", {}, "Participant"), el("th", { class: "num" }, "Messages"), el("th", { class: "num" }, "Jetons estimés")));
    rows.forEach(([nom, e]) => tbl.append(el("tr", {},
      el("td", {}, nom, e.est_agent ? null : el("span", { class: "vt-note", style: "margin:0 0 0 6px;" }, "toi")),
      el("td", { class: "num" }, "" + e.messages), el("td", { class: "num" }, fmt(e.jetons_estimes)))));
    corps.append(rows.length ? tbl : el("p", { class: "vt-note" }, "Aucun message pour l'instant."));
    if (d.note) corps.append(el("p", { class: "vt-note", style: "margin-top:14px;" }, d.note));
    overlay("Consommation de jetons", corps, true);
  }

  // ---------- le menu de gauche ----------
  const estMobile = () => window.matchMedia("(max-width: 768px)").matches;   // le même seuil que vaultia-mobile.css
  const largeurRail = () => (estMobile() ? Math.min(304, Math.round(window.innerWidth * 0.86)) : RAIL_W);
  let ouvert;
  try { const v = localStorage.getItem("vaultia-rail"); ouvert = v === null ? !estMobile() : v === "1"; } catch (e) { ouvert = !estMobile(); }
  let expanded = null;

  function ajuster() {
    const w = largeurRail(), mob = estMobile();
    const rail = document.getElementById("vaultia-rail");
    if (rail) { rail.style.width = w + "px"; rail.style.transform = ouvert ? "none" : `translateX(-${w + 2}px)`; rail.setAttribute("aria-hidden", ouvert ? "false" : "true"); }
    const app = document.getElementById("app");
    if (app) { app.style.transition = "margin-left .22s cubic-bezier(.16,1,.3,1)"; app.style.marginLeft = (ouvert && !mob) ? w + "px" : "0"; }
    const bd = document.getElementById("vaultia-backdrop");
    if (bd) bd.style.display = (ouvert && mob) ? "block" : "none";
    const t = document.getElementById("vaultia-toggle");
    if (t) { t.style.left = (ouvert ? w - 44 : 10) + "px"; t.setAttribute("aria-expanded", ouvert ? "true" : "false"); }
    document.body.classList.toggle("vt-rail-ouvert", ouvert && !mob);
  }
  function basculer() { ouvert = !ouvert; try { localStorage.setItem("vaultia-rail", ouvert ? "1" : "0"); } catch (e) {} ajuster(); }
  function fermerSiMobile() { if (estMobile() && ouvert) { ouvert = false; ajuster(); } }
  const auClavier = (fn) => (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(e); } };

  function canaux() { return Array.isArray(window.channelList) ? window.channelList.slice() : ["general"]; }

  // Les onglets de canaux sont masqués quand le menu est là : le menu doit donc tout porter,
  // y compris renommer (fonction d'onglet) et les non-lus.
  // Un envoi sur une WebSocket fermée se perd sans erreur : on le dit plutôt que de ne rien faire.
  function envoyer(objet) {
    if (window.ws && window.ws.readyState === 1) { window.ws.send(JSON.stringify(objet)); return true; }
    avertir("La salle n'est pas connectée au serveur. Recharge la page, puis réessaie.");
    return false;
  }
  const NOM_REFUSE = "Nom refusé : il faut au moins une lettre ou un chiffre (20 caractères au plus).";

  async function renommer(nom, projet) {
    const saisi = await demander("Renommer la conversation", "Nouveau nom", nom);
    if (saisi === null) return;
    const n = nomCanal(saisi);
    if (!n) { avertir(NOM_REFUSE); return; }
    if (n === nom) return;
    if (canaux().includes(n)) { avertir("Une conversation « " + n + " » existe déjà."); return; }
    if (!envoyer({ type: "channel_rename", old_name: nom, new_name: n })) return;
    if (window.activeChannel === nom && window._setActiveChannel) window._setActiveChannel(n);
    setTimeout(async () => { if (projet) await jpost("/api/projects/assign", { channel: n, project: projet }); rendre(); }, 400);
  }
  function itemCanal(nom, projet) {
    const actif = window.activeChannel === nom;
    const ouvrir = () => { if (window.switchChannel) window.switchChannel(nom); fermerSiMobile(); setTimeout(rendre, 60); };
    const nonLus = actif ? 0 : ((window.channelUnread || {})[nom] || 0);
    const it = el("div", { class: "vt-item" + (actif ? " actif" : "") + (nonLus ? " nonlu" : ""), draggable: "true", role: "button", tabindex: "0", "aria-current": actif ? "page" : null,
      onclick: ouvrir, onkeydown: auClavier(ouvrir),
      ondragstart: (e) => { e.dataTransfer.setData("text/canal", nom); e.dataTransfer.effectAllowed = "move"; },
    }, el("span", { class: "vt-diese" }, "#"), el("span", { class: "vt-nom" }, nom),
      nonLus ? el("span", { class: "vt-nonlu", "aria-label": nonLus + " non lu(s)" }, nonLus > 99 ? "99+" : String(nonLus)) : null);
    if (nom !== "general") {
      it.append(
        el("button", { class: "vt-geste", type: "button", title: "Renommer la conversation", "aria-label": "Renommer la conversation " + nom,
          onclick: (e) => { e.stopPropagation(); renommer(nom, projet); } }, ico("crayon", 14)),
        el("button", { class: "vt-geste vt-suppr", type: "button", title: "Supprimer la conversation", "aria-label": "Supprimer la conversation " + nom,
          onclick: async (e) => {
            e.stopPropagation();
            if (!(await confirmer("Supprimer la conversation", "Supprimer « " + nom + " » ? Cette action est définitive.", "Supprimer"))) return;
            if (!envoyer({ type: "channel_delete", name: nom })) return;
            jpost("/api/projects/assign", { channel: nom, project: "" });
            if (window.activeChannel === nom && window.switchChannel) window.switchChannel("general");
            setTimeout(rendre, 400);
          } }, ico("fermer", 14)));
    }
    return it;
  }
  function cibleDrop(elem, projet) {
    elem.addEventListener("dragover", (e) => { e.preventDefault(); elem.style.outline = "2px dashed var(--v-slate)"; elem.style.outlineOffset = "-2px"; });
    elem.addEventListener("dragleave", () => { elem.style.outline = ""; });
    elem.addEventListener("drop", async (e) => {
      e.preventDefault(); elem.style.outline = "";
      const canal = e.dataTransfer.getData("text/canal");
      if (canal) { await jpost("/api/projects/assign", { channel: canal, project: projet }); rendre(); }
    });
  }
  async function nouvelleConversation(projet) {
    const saisi = await demander("Nouvelle conversation", "Nom de la conversation");
    if (saisi === null) return;
    const n = nomCanal(saisi);
    if (!n) { avertir(NOM_REFUSE); return; }
    if (canaux().includes(n)) {
      // Elle existe déjà (même nom, ou nom tronqué à 20 caractères) : on l'ouvre au lieu de ne rien faire.
      if (window.switchChannel) window.switchChannel(n);
    } else {
      if (window._setPendingChannelSwitch) window._setPendingChannelSwitch(n);
      if (!envoyer({ type: "channel_create", name: n })) return;
    }
    fermerSiMobile();
    setTimeout(async () => { if (projet) await jpost("/api/projects/assign", { channel: n, project: projet }); rendre(); }, 400);
  }
  const ajout = (fn) => el("div", { class: "vt-ajout", role: "button", tabindex: "0", onclick: fn, onkeydown: auClavier(fn) }, ico("plus", 14), "Conversation");

  async function rendre() {
    const liste = document.getElementById("vaultia-rail-corps"); if (!liste) return;
    const d = await jget("/api/projects").catch(() => ({ projets: {}, actif: "" }));
    const projets = d.projets || {};
    const assignes = new Set(); Object.values(projets).forEach((p) => (p.channels || []).forEach((c) => assignes.add(c)));
    liste.replaceChildren();

    liste.append(el("div", { class: "vt-titre" }, el("span", {}, "Projets"),
      el("button", { class: "vt-plus", type: "button", title: "Nouveau projet", "aria-label": "Nouveau projet",
        onclick: async () => { const n = await demander("Nouveau projet", "Nom du projet"); if (n && n.trim()) { await jpost("/api/projects", { name: n.trim() }); rendre(); } } }, ico("plus", 15))));

    Object.keys(projets).forEach((nom) => {
      const p = projets[nom]; const actif = d.actif === nom; const open = expanded === nom;
      const basculerProjet = async () => { expanded = open ? null : nom; if (!actif) await jpost(`/api/projects/${encodeURIComponent(nom)}/activate`); rendre(); };
      const tete = el("div", { class: "vt-proj" + (actif ? " actif" : "") + (open ? " ouvert" : ""), role: "button", tabindex: "0", "aria-expanded": open ? "true" : "false",
        onclick: basculerProjet, onkeydown: auClavier(basculerProjet) },
        el("span", { class: "vt-chevron" }, ico("chevron", 14)),
        el("span", { class: "vt-nom" }, nom),
        actif ? el("span", { class: "vt-point", title: "Projet actif" }) : null);
      cibleDrop(tete, nom);
      liste.append(tete);
      if (open) {
        const sous = el("div", { class: "vt-sous" });
        (p.channels || []).forEach((c) => { if (canaux().includes(c)) sous.append(itemCanal(c, nom)); });
        sous.append(ajout(() => nouvelleConversation(nom)));
        const mem = el("textarea", { class: "vt-memoire", rows: "4", placeholder: "Ce que les IA doivent savoir sur ce projet…", "aria-label": "Mémoire du projet " + nom });
        mem.value = p.memoire || "";
        const statut = el("span", { class: "vt-statut", role: "status" });
        const sauver = btn("Enregistrer", () => enregistrer(statut, jpost(`/api/projects/${encodeURIComponent(nom)}/memory`, { memory: mem.value })), true);
        sous.append(el("div", { class: "vt-memoire-titre" }, "Mémoire du projet, donnée aux IA"), mem,
          el("div", { style: "display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-top:8px;" }, statut, sauver));
        liste.append(sous);
      }
    });

    const horsTitre = el("div", { class: "vt-titre" }, el("span", {}, "Conversations"));
    cibleDrop(horsTitre, "");
    liste.append(horsTitre);
    const hors = el("div", {});
    cibleDrop(hors, "");
    canaux().filter((c) => !assignes.has(c)).forEach((c) => hors.append(itemCanal(c, "")));
    hors.append(ajout(() => nouvelleConversation("")));
    liste.append(hors);
  }

  function railMenu() {
    if (document.getElementById("vaultia-rail")) return;
    const rail = el("nav", { id: "vaultia-rail", class: "vt-rail", "aria-label": "Projets et conversations",
      style: `position:fixed;top:0;left:0;bottom:0;width:${RAIL_W}px;z-index:1002;display:flex;flex-direction:column;overflow:hidden;transition:transform .22s cubic-bezier(.16,1,.3,1);` });
    const tete = el("div", { class: "vt-rail-tete" }, el("img", { src: "/static/logo.png", alt: "Vaultia" }));
    const actions = el("div", { class: "vt-actions" });
    [["plus", "IA", "Connecter une IA", ouvrirAjout], ["reglages", "Modèles", "Modèles et raisonnement", ouvrirModeles], ["stats", "Stats", "Consommation de jetons", ouvrirStats]]
      .forEach(([i, t, titre, on]) => actions.append(el("button", { class: "vt-action", type: "button", title: titre, onclick: on }, ico(i, 15), t)));
    const corps = el("div", { id: "vaultia-rail-corps", class: "vt-corps" });
    rail.append(tete, actions, corps);
    document.body.append(rail);
    const backdrop = el("div", { id: "vaultia-backdrop", class: "vt-fond", style: "display:none;position:fixed;inset:0;z-index:1001;", onclick: () => { ouvert = false; ajuster(); } });
    document.body.append(backdrop);
    const toggle = el("button", { id: "vaultia-toggle", class: "vt-bascule", type: "button", title: "Ouvrir ou fermer le menu", "aria-label": "Menu des projets",
      "aria-controls": "vaultia-rail", style: "position:fixed;top:9px;z-index:1003;", onclick: basculer }, ico("panneau", 18));
    document.body.append(toggle);
    window.addEventListener("resize", ajuster);
    ajuster(); rendre();
    setInterval(() => { if (ouvert && !document.hidden) rendre(); }, 4000);
  }

  // ---------- qui réfléchit · décisions en attente ----------
  function decisionsHorsVue() {
    const tl = document.getElementById("timeline"); if (!tl) return [];
    const vue = tl.getBoundingClientRect();
    // Messages du canal ouvert seulement (ceux des autres canaux sont masqués, boîte vide).
    const visibles = [...document.querySelectorAll("#messages > .message")].filter((m) => m.getClientRects().length);
    // Toute carte encore ouverte est en attente ; une réponse donnée en texte se ferme d'un
    // « Répondu autrement » sur la carte (fermeture silencieuse côté serveur).
    const cartes = visibles.filter((m) => m.querySelector(".decision-choice"));
    return cartes.filter((m) => { const r = m.getBoundingClientRect(); return r.bottom < vue.top + 24 || r.top > vue.bottom - 24; });
  }
  function bandeauReflexion() {
    const ancre = document.getElementById("input-row");
    if (!ancre || document.getElementById("vaultia-reflexion")) return;
    const bar = el("div", { id: "vaultia-reflexion", role: "status", "aria-live": "polite", style: "display:none;align-items:center;" });
    ancre.parentNode.insertBefore(bar, ancre);   // juste au-dessus de la carte de saisie
    // Les libellés viennent du serveur et un agent peut se renommer : ils entrent comme TEXTE (el()
    // n'insère jamais de HTML). On ne redessine que si l'état change, sinon le souffle repart à zéro.
    let dernier = null, busy = [];
    function dessiner() {
      const attente = decisionsHorsVue();
      const cle = JSON.stringify([busy, attente.length]);
      if (cle === dernier) return;
      dernier = cle;
      bar.replaceChildren();
      if (attente.length) {
        bar.append(el("button", { class: "vt-attente", type: "button", title: "Aller à la décision",
          onclick: () => attente[attente.length - 1].scrollIntoView({ behavior: "smooth", block: "center" }) },
          ico("bas", 14), attente.length > 1 ? `${attente.length} décisions en attente` : "1 décision en attente"));
      }
      busy.forEach((a) => {
        const point = el("span", { class: "vt-souffle", "aria-hidden": "true" });
        if (a.c) point.style.setProperty("--c", a.c);
        bar.append(el("span", { class: "vt-agent" }, point, a.nom));
      });
      if (busy.length) bar.append(el("span", { class: "vt-verbe" }, busy.length > 1 ? "réfléchissent…" : "réfléchit…"));
      bar.style.display = (busy.length || attente.length) ? "flex" : "none";
      document.body.classList.toggle("vt-rappel", attente.length > 0);   // la flèche « bas » s'efface
    }
    async function tick() {
      try {
        const s = await jget("/api/status");
        busy = Object.keys(s).filter((n) => n !== "paused" && s[n] && s[n].busy).map((n) => ({ nom: String(s[n].label || n), c: couleurSure(s[n].color) }));
      } catch (e) {}
      dessiner();
    }
    // Onglet en arrière-plan (téléphone verrouillé) : on n'interroge plus le serveur.
    tick();
    setInterval(() => { if (!document.hidden) tick(); }, 1500);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
    const tl = document.getElementById("timeline");
    if (tl) { let attente = 0; tl.addEventListener("scroll", () => { clearTimeout(attente); attente = setTimeout(dessiner, 120); }, { passive: true }); }
  }

  // ---------- mentions : un bouton @ au lieu d'une rangée permanente de pastilles ----------
  function boutonMentions(row) {
    if (document.getElementById("vaultia-mention-btn")) return;
    const b = el("button", { id: "vaultia-mention-btn", type: "button", title: "Choisir les agents à mentionner", "aria-label": "Mentionner des agents",
      "aria-pressed": "false", "aria-controls": "mention-toggles",
      onclick: () => { const ouvre = !document.body.classList.contains("vt-mentions"); document.body.classList.toggle("vt-mentions", ouvre); b.setAttribute("aria-pressed", ouvre ? "true" : "false"); } },
      ico("arobase", 19));
    const doc = document.getElementById("vaultia-doc-btn");
    row.insertBefore(b, doc ? doc.nextSibling : row.firstChild);
  }

  // ---------- envois programmés : dans l'en-tête (horloge au bureau, « ⋯ » au téléphone), plus sur la saisie ----------
  // La barre de chat.js (#schedules-bar) reste la source : elle est masquée (vaultia-theme.css)
  // et on la surveille pour savoir quand la liste change. La liste elle-même est schedulesList (chat.js).
  const horaires = () => (typeof schedulesList !== "undefined" && Array.isArray(schedulesList) ? schedulesList : []);
  const deux = (n) => String(n).padStart(2, "0");
  const heureFr = (d) => d.getHours() + " h " + deux(d.getMinutes());
  const jourFr = (d) => d.toLocaleDateString("fr-CA", { weekday: "short", day: "numeric", month: "short" });
  function rythme(s) {
    if (s.one_shot) {
      if (!s.next_run) return "une fois";
      const d = new Date(s.next_run * 1000), demain = new Date();
      demain.setDate(demain.getDate() + 1);
      if (d.toDateString() === new Date().toDateString()) return "une fois, aujourd'hui à " + heureFr(d);
      if (d.toDateString() === demain.toDateString()) return "une fois, demain à " + heureFr(d);
      return "une fois, le " + jourFr(d) + " à " + heureFr(d);
    }
    if (s.daily_at) { const [h, m] = String(s.daily_at).split(":"); return "chaque jour à " + (parseInt(h, 10) || 0) + " h " + (m || "00"); }
    const sec = s.interval_seconds || 0;
    const n = (div) => Math.max(1, Math.round(sec / div));
    if (sec < 3600) return n(60) === 1 ? "chaque minute" : "toutes les " + n(60) + " min";
    if (sec < 86400) return n(3600) === 1 ? "chaque heure" : "toutes les " + n(3600) + " h";
    return n(86400) === 1 ? "chaque jour" : "tous les " + n(86400) + " jours";
  }
  function prochain(s) {
    if (s.active === false) return "en pause";
    if (!s.next_run) return "";
    const ms = s.next_run * 1000 - Date.now();
    if (ms < 60000) return "part dans moins d'une minute";
    const min = Math.ceil(ms / 60000);
    if (min < 60) return "prochain dans " + min + " min";
    if (min < 24 * 60) return "prochain dans " + Math.floor(min / 60) + " h" + (min % 60 ? " " + deux(min % 60) : "");
    return "prochain le " + jourFr(new Date(s.next_run * 1000));
  }
  function surChangementHoraires(fn) {
    const barre = document.getElementById("schedules-bar");
    if (!barre) return null;
    const obs = new MutationObserver(fn);
    obs.observe(barre, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    return obs;
  }

  function ouvrirHoraires() {
    const liste = el("div", { class: "vt-horaires" });
    let aConfirmer = null, delaiConfirmer = 0;
    async function agir(b, url, methode, echec) {
      occupe(b, true);
      try {
        const r = await appel(url, { method: methode });
        if (!r.ok) throw new Error("HTTP " + r.status);
      } catch (e) {
        avertir(echec + " (" + e.message + ").");
      } finally { occupe(b, false); }
      // La liste se redessine quand le serveur diffuse le changement (la barre de chat.js bouge).
    }
    function dessiner() {
      const tout = horaires();
      liste.replaceChildren();
      if (!tout.length) {
        liste.append(el("p", { class: "vt-note" }, "Aucun envoi programmé. Le bouton horloge, à côté d'Envoyer, en programme un."));
        return;
      }
      for (const s of tout) {
        const enPause = s.active === false;
        const cibles = (s.targets || []).map((t) => "@" + t).join(" ");
        const canal = s.channel && s.channel !== (window.activeChannel || "general") ? "# " + s.channel : "";
        const pause = el("button", { class: "vt-btn", type: "button", "aria-pressed": enPause ? "true" : "false" }, enPause ? "Reprendre" : "Pause");
        pause.addEventListener("click", () => agir(pause, `/api/schedules/${encodeURIComponent(s.id)}/toggle`, "PATCH",
          enPause ? "La reprise n'a pas pris" : "La pause n'a pas pris"));
        // Supprimer en deux touches : au pouce, une seule touche effaçait l'envoi sans retour possible.
        const confirme = aConfirmer === s.id;
        const suppr = el("button", { class: "vt-btn vt-btn-danger" + (confirme ? " arme" : ""), type: "button" }, confirme ? "Confirmer" : "Supprimer");
        suppr.addEventListener("click", () => {
          clearTimeout(delaiConfirmer);
          if (aConfirmer !== s.id) {
            aConfirmer = s.id; dessiner();
            delaiConfirmer = setTimeout(() => { aConfirmer = null; dessiner(); }, 4000);
            return;
          }
          aConfirmer = null;
          agir(suppr, `/api/schedules/${encodeURIComponent(s.id)}`, "DELETE", "La suppression n'a pas pris");
        });
        liste.append(el("div", { class: "vt-horaire" + (enPause ? " en-pause" : "") },
          el("div", { class: "vt-horaire-tete" }, el("span", { class: "vt-horaire-cibles" }, cibles || "—"), canal ? el("span", { class: "vt-horaire-canal" }, canal) : null),
          el("div", { class: "vt-horaire-message", title: s.prompt || "" }, s.prompt || ""),
          el("div", { class: "vt-horaire-quand" }, [rythme(s), prochain(s)].filter(Boolean).join(" · ")),
          el("div", { class: "vt-horaire-actions" }, pause, suppr)));
      }
    }
    dessiner();
    const obs = surChangementHoraires(dessiner);
    const minuterie = setInterval(() => { if (!document.hidden) dessiner(); }, 30000);   // « prochain dans … » avance
    overlay("Envois programmés", liste, true, () => { if (obs) obs.disconnect(); clearInterval(minuterie); clearTimeout(delaiConfirmer); });
  }

  // Bureau : une horloge dans l'en-tête (le compte en pastille discrète, le prochain envoi en infobulle).
  // Au téléphone elle est masquée (vaultia-mobile.css) et la ligne « Envois programmés » de « ⋯ » la remplace.
  function horairesEntete() {
    const droite = document.querySelector("header .header-right");
    if (!droite || document.getElementById("vt-horaires-entete")) return;
    const pastille = el("span", { class: "vt-horaires-badge", "aria-hidden": "true", hidden: true });
    const b = el("button", { id: "vt-horaires-entete", class: "settings-btn", type: "button", title: "Envois programmés",
      "aria-label": "Envois programmés", onclick: ouvrirHoraires }, ico("horloge", 17), pastille);
    droite.insertBefore(b, document.getElementById("rules-toggle"));
    const maj = () => {
      const tout = horaires(), actifs = tout.filter((s) => s.active !== false);
      pastille.hidden = !tout.length; pastille.textContent = tout.length > 99 ? "99+" : String(tout.length);
      const futurs = actifs.filter((s) => s.next_run && s.next_run * 1000 > Date.now());
      const proche = futurs.length ? futurs.reduce((a, s) => (s.next_run < a.next_run ? s : a)) : null;
      const resume = !tout.length ? "Envois programmés : aucun"
        : `${tout.length} envoi${tout.length > 1 ? "s" : ""} programmé${tout.length > 1 ? "s" : ""}`
          + (tout.length > actifs.length ? ` (${tout.length - actifs.length} en pause)` : "")
          + (proche ? " · " + prochain(proche) : "");
      b.title = resume; b.setAttribute("aria-label", resume);
    };
    maj();
    surChangementHoraires(maj);
    setInterval(() => { if (!document.hidden) maj(); }, 30000);
    // La barre est masquée partout : son éclair de confirmation (chat.js) ne se voit plus. Un message le remplace.
    const barre = document.getElementById("schedules-bar");
    let eclair = false;   // un seul message par éclair, même si la barre change de classe pendant les 2 s
    if (barre) new MutationObserver(() => {
      const maintenant = barre.classList.contains("sched-flash");
      if (maintenant && !eclair && typeof window.showToast === "function")
        window.showToast(estMobile() ? "Envoi programmé. Il est dans ⋯ › Envois programmés." : "Envoi programmé. Il est sous l'horloge, en haut.", "success");
      eclair = maintenant;
    }).observe(barre, { attributes: true, attributeFilter: ["class"] });
  }

  // ---------- en-tête du téléphone : titre de la conversation + menu « plus » ----------
  function enteteTelephone() {
    const gauche = document.querySelector("header .header-left");
    const droite = document.querySelector("header .header-right");
    if (!gauche || !droite || document.getElementById("vt-titre-canal")) return;
    const titre = el("span", { id: "vt-titre-canal", class: "vt-titre-canal" });
    gauche.append(titre);
    let vu = null;
    const maj = () => { const n = window.activeChannel || "general"; if (n !== vu) { vu = n; titre.textContent = "# " + n; } };
    maj(); setInterval(() => { if (!document.hidden) maj(); }, 700);

    const menu = el("div", { id: "vt-menu-plus", class: "vt-menu", role: "menu", hidden: true });
    const fermerMenu = () => { menu.hidden = true; plus.setAttribute("aria-expanded", "false"); };
    const lignes = {};
    // Envois programmés : le compte sur la ligne seulement. Ce n'est pas une attente à traiter,
    // donc pas sur la pastille de « ⋯ » (elle resterait allumée en permanence).
    const compteHoraires = el("span", { class: "vt-menu-compte" });
    menu.append(el("button", { id: "vt-menu-horaires", class: "vt-menu-item", type: "button", role: "menuitem",
      onclick: () => { fermerMenu(); ouvrirHoraires(); } }, el("span", {}, "Envois programmés"), compteHoraires));
    const recompterHoraires = () => { const n = horaires().length; compteHoraires.textContent = n ? String(n) : ""; };
    recompterHoraires();
    surChangementHoraires(recompterHoraires);
    [["rules-toggle", "Règles de la salle", "rules-badge"], ["pins-toggle", "Épingles", null], ["help-btn", "Aide", null]].forEach(([id, texte, badge]) => {
      const compte = el("span", { class: "vt-menu-compte" });
      lignes[id] = { compte, badge };
      menu.append(el("button", { class: "vt-menu-item", type: "button", role: "menuitem",
        onclick: () => { fermerMenu(); const cible = document.getElementById(id); if (cible) cible.click(); } }, el("span", {}, texte), compte));
    });
    const plus = el("button", { id: "vt-plus-entete", class: "settings-btn", type: "button", title: "Plus", "aria-label": "Plus d'options", "aria-haspopup": "menu", "aria-expanded": "false",
      onclick: (e) => { e.stopPropagation(); const ouvre = menu.hidden; menu.hidden = !ouvre; plus.setAttribute("aria-expanded", ouvre ? "true" : "false"); } }, ico("plusieurs", 18));
    droite.append(plus);
    document.body.append(menu);
    // Les badges des boutons rangés dans « ⋯ » (règles en attente…) restent visibles : sur « ⋯ » et
    // sur leur ligne du menu. Sinon le compte « 4 » disparaissait au téléphone.
    const pastillePlus = el("span", { class: "vt-plus-badge", "aria-hidden": "true", hidden: true });
    plus.append(pastillePlus);
    const recopier = () => {
      let total = 0;
      for (const id in lignes) {
        const src = lignes[id].badge && document.getElementById(lignes[id].badge);
        const n = src && !src.classList.contains("hidden") ? (parseInt(src.textContent, 10) || 0) : 0;
        total += n;
        lignes[id].compte.textContent = n ? String(n) : "";
      }
      pastillePlus.hidden = !total; pastillePlus.textContent = total > 99 ? "99+" : String(total);
      plus.setAttribute("aria-label", total ? `Plus d'options (${total} en attente)` : "Plus d'options");
    };
    recopier();
    const regle = document.getElementById("rules-badge");
    if (regle) new MutationObserver(recopier).observe(regle, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) fermerMenu(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermerMenu(); });
  }

  // ---------- réglages : « Effacer le fil » et le crédit du projet d'origine ----------
  function reglages() {
    const barre = document.getElementById("settings-bar");
    if (!barre || document.getElementById("vt-reglage-fil")) return;
    const effacer = document.getElementById("clear-chat-btn");
    if (effacer) {
      effacer.textContent = "Effacer le fil";
      barre.append(el("div", { id: "vt-reglage-fil", class: "settings-field" }, el("label", {}, "Ce canal"), effacer));
    }
    const lien = document.querySelector(".channel-support");
    const url = lien ? lien.getAttribute("href") : "https://buymeacoffee.com/bcurts";
    barre.append(el("div", { class: "settings-field vt-credit" },
      "Vaultia est construite sur agentchattr (licence MIT). ",
      el("a", { href: url, target: "_blank", rel: "noopener" }, "Soutenir le projet d'origine")));
  }

  // ---------- pastilles d'initiale (badge original, pas de logo déposé) ----------
  function badgesAvatars() {
    const peindre = () => document.querySelectorAll(".avatar").forEach((a) => {
      const wrap = a.closest(".avatar-wrap"); const nom = (wrap && wrap.dataset.agent) || a.dataset.agent || "";
      const lettre = (nom || "?").trim().charAt(0).toUpperCase();
      if (a.textContent !== lettre) { a.textContent = lettre; a.style.display = "flex"; a.style.alignItems = "center"; a.style.justifyContent = "center"; a.style.color = "#fff"; }
    });
    peindre(); new MutationObserver(peindre).observe(document.body, { childList: true, subtree: true });
  }

  // ---------- joindre une photo ou un document ----------
  function occupe(b, oui) { if (!b) return; b.disabled = !!oui; if (oui) b.setAttribute("aria-busy", "true"); else b.removeAttribute("aria-busy"); }
  function boutonPhoto() {
    const row = document.getElementById("input-row");
    if (!row || document.getElementById("vaultia-photo-btn")) return;
    const input = el("input", { type: "file", accept: "image/*", id: "vaultia-photo-input", multiple: "multiple", style: "display:none;" });
    // Redimensionner/compresser côté navigateur : une photo de téléphone (plusieurs Mo) dépasse la
    // limite serveur. On la ramène à 1600 px / JPEG q0,85 (moins de 1 Mo).
    function compresser(file) {
      return new Promise((resolve) => {
        if (!file.type || !file.type.startsWith("image/")) { resolve(file); return; }
        const img = new Image(); const url = URL.createObjectURL(file);
        img.onload = () => {
          URL.revokeObjectURL(url);
          const max = 1600; let w = img.width, h = img.height;
          if (w > max || h > max) { const k = Math.min(max / w, max / h); w = Math.round(w * k); h = Math.round(h * k); }
          const c = document.createElement("canvas"); c.width = w; c.height = h;
          c.getContext("2d").drawImage(img, 0, 0, w, h);
          c.toBlob((blob) => {
            if (!blob) { resolve(file); return; }
            resolve(new File([blob], (file.name || "photo").replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }));
          }, "image/jpeg", 0.85);
        };
        img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
        img.src = url;
      });
    }
    input.addEventListener("change", async () => {
      const files = Array.from(input.files || []);
      const b = document.getElementById("vaultia-photo-btn");
      occupe(b, true);
      let ok = 0;
      for (const f of files) {
        try { const c = await compresser(f); if (window.uploadImage) { await window.uploadImage(c); ok++; } }
        catch (e) { /* le toast a déjà dit pourquoi ; on continue avec les suivantes */ }
      }
      occupe(b, false);
      if (files.length && ok === 0) avertir("La photo n'a pas pu être jointe. Réessaie, ou choisis une image plus petite.");
      input.value = "";
    });
    const pbtn = el("button", { id: "vaultia-photo-btn", type: "button", title: "Joindre une photo", "aria-label": "Joindre une photo", onclick: () => input.click() }, ico("photo", 19));
    row.insertBefore(pbtn, row.firstChild);
    row.appendChild(input);

    // Documents : envoi direct, sans compression (pdf, txt, csv, docx, xlsx…).
    const dinput = el("input", { type: "file", accept: ".pdf,.txt,.md,.csv,.json,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.rtf,.odt", id: "vaultia-doc-input", multiple: "multiple", style: "display:none;" });
    dinput.addEventListener("change", async () => {
      const files = Array.from(dinput.files || []);
      const b = document.getElementById("vaultia-doc-btn");
      occupe(b, true);
      let ok = 0;
      for (const f of files) { try { if (window.uploadImage) { await window.uploadImage(f); ok++; } } catch (e) {} }
      occupe(b, false);
      if (files.length && ok === 0) avertir("Le document n'a pas pu être joint : type non accepté ou fichier trop volumineux.");
      dinput.value = "";
    });
    const dbtn = el("button", { id: "vaultia-doc-btn", type: "button", title: "Joindre un document", "aria-label": "Joindre un document", onclick: () => dinput.click() }, ico("trombone", 19));
    row.insertBefore(dbtn, pbtn.nextSibling);
    row.appendChild(dinput);
    boutonMentions(row);
  }

  // ---------- nouvelle version de la salle ----------
  // Après un redémarrage, la page se reconnecte sans se recharger et garde l'ancien code ; installée
  // comme application, elle n'a même pas de bouton « recharger ». Au retour sur l'application (et aux
  // 5 min), on relit la page servie : si elle référence un fichier (?v=…) que la page ouverte n'a pas,
  // on recharge — sauf s'il y a un brouillon, alors on le propose d'un bouton.
  function miseAJour() {
    const versions = (texte) => new Set(texte.match(/\/static\/[\w.\/-]+\.(?:js|css)\?v=[\w.-]+/g) || []);
    const chargees = () => versions([...document.querySelectorAll("script[src], link[rel=stylesheet]")].map((n) => n.getAttribute("src") || n.getAttribute("href")).join(" "));
    const brouillon = () => {
      const saisie = document.getElementById("input");
      if (saisie && saisie.value.trim()) return true;
      return [...document.querySelectorAll(".decision-texte:not([hidden]) textarea")].some((t) => t.value.trim());
    };
    let propose = false;
    async function verifier() {
      if (document.hidden || propose) return;
      let html;
      try { const r = await fetch("/", { cache: "no-store" }); if (!r.ok) return; html = await r.text(); } catch (e) { return; }
      const ici = chargees();
      const nouvelles = [...versions(html)].filter((v) => !ici.has(v)).sort().join("|");
      if (!nouvelles) return;
      let deja = null;
      try { deja = sessionStorage.getItem("vt-recharge"); } catch (e) {}
      if (deja === nouvelles) return;            // déjà rechargé pour ces fichiers : pas de boucle
      if (!brouillon()) {
        try { sessionStorage.setItem("vt-recharge", nouvelles); } catch (e) {}
        location.reload();
        return;
      }
      propose = true;
      document.body.append(el("button", { id: "vt-nouvelle-version", type: "button", onclick: () => location.reload() }, "Nouvelle version de la salle · Recharger"));
    }
    document.addEventListener("visibilitychange", verifier);
    setInterval(verifier, 5 * 60 * 1000);
    setTimeout(verifier, 4000);
  }

  function init() { railMenu(); boutonPhoto(); bandeauReflexion(); horairesEntete(); enteteTelephone(); reglages(); badgesAvatars(); miseAJour(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
