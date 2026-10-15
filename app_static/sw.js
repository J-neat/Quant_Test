// 퀀트 시그널 서비스 워커: 푸시 알림 + 앱 화면 캐시(서버가 꺼져 있어도 화면은 열리도록)
const CACHE = "quant-shell-v3";
const SHELL = ["/", "/static/app.css?v=3", "/static/app.js?v=3", "/static/icons/icon-192.png", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/charts/")) return;  // 데이터는 항상 서버에서
  // 화면 파일: 네트워크 우선, 실패하면 캐시
  e.respondWith(
    fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return res;
    }).catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});

self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) { data = { title: "퀀트 시그널", body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(data.title || "퀀트 시그널", {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    tag: data.tag || undefined,
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = new URL(e.notification.data?.url || "/", self.location.origin).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) {
      if ("focus" in c) { c.navigate(target); return c.focus(); }
    }
    return self.clients.openWindow(target);
  }));
});
