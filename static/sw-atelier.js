/* sw-atelier.js — reçoit les notifications poussées de l'atelier (v1.0, 2026-10-16, claude).
   Le serveur chiffre le message (RFC 8291) ; le navigateur le déchiffre avant de le remettre ici.
   Ce fichier ne met rien en cache : la salle est toujours servie fraîche (le jeton de session y est injecté). */
"use strict";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = {}; }
  e.waitUntil(self.registration.showNotification(d.titre || "Atelier Vaultia", {
    body: d.corps || "Une décision t'attend.",
    tag: d.etiquette || "atelier",
    renotify: true,
    icon: "/static/icons/icone-192.png",
    badge: "/static/icons/icone-monochrome-512.png",
    data: {url: d.url || "/atelier#/"},
  }));
});

// Un toucher sur la notification : on ramène l'atelier déjà ouvert (et on lui dit où aller), sinon on l'ouvre.
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/atelier#/", self.location.origin).href;
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(fenetres => {
    const atelier = fenetres.find(f => f.url.startsWith(self.location.origin + "/atelier"));
    if (atelier) { atelier.postMessage({aller: url}); return atelier.focus(); }
    return self.clients.openWindow(url);
  }));
});
