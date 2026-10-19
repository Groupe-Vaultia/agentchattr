// Progression des tâches sur le tableau de l'atelier (lot claude2/atelier-progression, tache-22, 2026-10-19).
// Charles : « le tableau de l'atelier n'est pas live que ça... Je ne vois pas vraiment les progressions ».
// Mêmes règles que progression.py côté serveur (tests/progression_cas.json éprouve les deux) : une progression est
// un message chat ou decision d'un agent ou de Charles, rattaché à une tâche (tache_id, sinon canal tache-<id>),
// hors système et hors rappel qu'un agent s'adresse à lui-même. Le silence ne compte que les messages d'agents.
"use strict";

export const EXTRAIT_MAX = 160;
const MENTION = /@([\w.-]+)/g;
const MENTIONS_TETE = /^(?:@[\w.-]+[\s,:]*)+/;
const MARQUE_TETE = /^(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)+/;
const SEPARATEUR = /^\|[\s|:-]*$/;
const CANAL_TACHE = /^tache-([1-9][0-9]{0,13})$/;  // comme jobs._CANAL_TACHE

export function autoAdresse(m) {
  const tete = String(m.text || "").trimStart().match(MENTIONS_TETE);
  if (!tete) return false;
  const auteur = String(m.sender || "").toLowerCase();
  return [...tete[0].matchAll(MENTION)].every(x => x[1].replace(/\.+$/, "").toLowerCase() === auteur);
}

export function tacheDuMessage(m) {
  if (Number.isInteger(m.tache_id) && m.tache_id > 0) return m.tache_id;
  const c = CANAL_TACHE.exec(String(m.channel || ""));
  return c ? Number(c[1]) : null;
}

export const estProgression = m => ["chat", "decision"].includes(m.type || "chat")
  && !!m.sender && m.sender !== "system" && !autoAdresse(m);

const espaces = s => s.split(/\s+/).filter(Boolean).join(" ");
const nettoyer = ligne => espaces(ligne.trim().replace(MENTIONS_TETE, "").replace(MARQUE_TETE, "")
  .replaceAll("**", "").replaceAll("__", "").replaceAll("`", ""));

export function extrait(texte, n = EXTRAIT_MAX) {
  const lignes = String(texte || "").split("\n").map(b => b.trim());
  let choisi = "";
  for (const b of lignes) {
    if (!b || b.startsWith("|") || b.startsWith("```")) continue;
    choisi = nettoyer(b);
    if (choisi) break;
  }
  if (!choisi) {
    const rangee = lignes.find(b => b.startsWith("|") && !SEPARATEUR.test(b)) || "";
    choisi = nettoyer(rangee.replace(/^\|+|\|+$/g, "").split("|").map(c => c.trim()).filter(Boolean).join(" · "));
  }
  const car = Array.from(choisi);
  return car.length <= n ? choisi : car.slice(0, n - 1).join("") + "…";
}

// Le message reçu par le flux devient la dernière activité de sa tâche, sur place. Rend la tâche touchée, ou null.
export function appliquerMessage(taches, m, humains) {
  const ts = m.timestamp;
  if (typeof ts !== "number" || !estProgression(m)) return null;
  const tid = tacheDuMessage(m);
  const t = tid && taches.find(x => Number(x.id) === tid);
  if (!t) return null;
  const a = t.activite || {agent: "", agent_ts: null};
  if (a.ts == null || ts >= a.ts) Object.assign(a, {id: m.id, ts, par: m.sender, extrait: extrait(m.text)});
  if (!humains.includes(m.sender) && (a.agent_ts == null || ts >= a.agent_ts)) Object.assign(a, {agent: m.sender, agent_ts: ts});
  t.activite = a;
  return t;
}

// Secondes depuis le dernier message d'agent ; null si aucun agent n'a écrit (la ronde n'a alors pas de date non plus).
export const silenceDe = (t, maintenant) => t.activite && t.activite.agent_ts != null ? Math.max(0, maintenant - t.activite.agent_ts) : null;

// Ce que la carte affiche, sans HTML : heure de la dernière activité, auteur, extrait, agents au travail.
export function etatCarte(t, maintenant, occupe = () => false) {
  const a = t.activite || null;
  const auTravail = Array.isArray(t.au_travail) ? t.au_travail : [];
  return {
    quand: Math.max(t.updated_at || 0, (a && a.ts) || 0) || null,
    par: a ? a.par : "",
    extrait: a ? a.extrait : "",
    silence: silenceDe(t, maintenant),
    auTravail,
    ecrit: auTravail.some(occupe),
  };
}

// Repère les cartes qui viennent de bouger : `vu` garde le dernier message connu de chaque tâche, `jusqua` l'heure
// (ms) où leur surbrillance s'éteint. La première vue d'une tâche ne la fait pas briller.
export function marquerBougees(taches, vu, jusqua, maintenantMs, dureeMs = 2400) {
  for (const t of taches) {
    const id = String(t.id), cle = t.activite ? t.activite.id : null;
    if (vu.has(id) && cle != null && vu.get(id) !== cle) jusqua.set(id, maintenantMs + dureeMs);
    vu.set(id, cle);
  }
  for (const [id, fin] of jusqua) if (fin <= maintenantMs) jusqua.delete(id);
}
