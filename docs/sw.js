const C = "degen-v2", SHELL = ["./", "index.html", "ui.css?v=2", "ui.js?v=2", "manifest.webmanifest", "icon.svg"];
self.addEventListener("install", e => { self.skipWaiting(); e.waitUntil(caches.open(C).then(c => c.addAll(SHELL))); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => clients.claim())));
self.addEventListener("fetch", e => {   // network-first, cache fallback (offline); same-origin GETs only, feed cached under one key
  const u = new URL(e.request.url); if (e.request.method !== "GET" || u.origin !== location.origin) return;
  const key = u.pathname.endsWith("signals.json") ? u.origin + u.pathname : e.request;
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const cp = r.clone(); caches.open(C).then(c => c.put(key, cp)); } return r; })
    .catch(() => caches.match(key)));
});
