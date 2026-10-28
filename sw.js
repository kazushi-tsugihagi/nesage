// ネサゲの通知係（サービスワーカー）
// サーバーからは「中身なし」の合図だけが届くので、ここでお知らせの中身を取りに行って表示する。
const CFG = "nesage-cfg";
async function cfg() {
  try { const r = await (await caches.open(CFG)).match("cfg"); return r ? await r.json() : null; } catch (e) { return null; }
}
const yen = n => "¥" + Math.round(n).toLocaleString("ja-JP");

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  e.waitUntil((async () => {
    const c = await cfg();
    let list = [];
    if (c && c.api && c.uid) {
      try { list = (await (await fetch(c.api + "/api/notices?uid=" + encodeURIComponent(c.uid), { cache: "no-store" })).json()).notices || []; } catch (err) { list = []; }
    }
    const site = self.registration.scope;
    if (!list.length) {
      return self.registration.showNotification("ネサゲ", { body: "いいねした商品が値下げしました。開いて確かめてください。", icon: site + "icon-192.png", badge: site + "icon-192.png", data: { url: site + "#liked" }, tag: "nesage-drop" });
    }
    const a = list[0];
    const more = list.length > 1 ? `　ほか${list.length - 1}件` : "";
    return self.registration.showNotification(`いいねした商品が${yen(a.old - a.new)}安くなりました`, {
      body: `${a.name}　${yen(a.old)} → ${yen(a.new)}${more}`,
      icon: site + "icon-192.png", badge: site + "icon-192.png", tag: "nesage-drop", renotify: true,
      data: { url: site + "#liked" },
    });
  })());
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || self.registration.scope;
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) { if (c.url.startsWith(self.registration.scope)) { await c.focus(); c.navigate(url); return; } }
    await self.clients.openWindow(url);
  })());
});
