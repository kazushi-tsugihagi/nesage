// ネサゲのサーバー（Cloudflare Workers）
// - いいねの数を数える／いいねした商品を覚える
// - ブラウザの通知の登録を受け取る
// - 毎朝、feed.json を見て、いいねした商品が安くなっていたら通知を送る
//
// 通知は「中身なし」で送り、受け取った側（sw.js）が /api/notices に取りに来る。
// こうすると、通知の中身を暗号化する処理がいらず、しくみが小さくてすむ。

const UID = /^[a-z0-9]{16,40}$/;
const ITEM = /^[\w:.\-]{1,80}$/;
const MAX_ITEMS = 200;

function cors(env, req) {
  const origin = req.headers.get("Origin") || "";
  const allowed = (env.ORIGIN || "").split(",").map(s => s.trim()).filter(Boolean);
  const ok = allowed.includes(origin);
  return {
    "Access-Control-Allow-Origin": ok ? origin : (allowed[0] || ""),
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8", ...(headers || {}) },
  });
}

async function body(req) {
  const text = await req.text();
  if (text.length > 60000) throw new Error("too_large");
  return JSON.parse(text || "{}");
}

// ---- 通知（Web Push / VAPID） ----
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const enc = s => new TextEncoder().encode(s);

export async function vapidAuth(endpoint, env, now) {
  const aud = new URL(endpoint).origin;
  const exp = Math.floor((now || Date.now()) / 1000) + 12 * 3600;
  const header = b64u(enc(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const payload = b64u(enc(JSON.stringify({ aud, exp, sub: env.VAPID_SUBJECT || env.SITE })));
  const key = await crypto.subtle.importKey("jwk", JSON.parse(env.VAPID_PRIVATE_JWK),
    { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc(header + "." + payload));
  return `vapid t=${header}.${payload}.${b64u(sig)}, k=${env.VAPID_PUBLIC}`;
}

async function sendPush(sub, env) {
  const res = await fetch(sub.endpoint, {
    method: "POST",
    headers: { Authorization: await vapidAuth(sub.endpoint, env), TTL: "86400", Urgency: "normal", "Content-Length": "0" },
  });
  return res.status;
}

// ---- 毎朝の値下げチェック ----
export async function checkPrices(env) {
  const res = await fetch(env.FEED_URL + "?t=" + Date.now(), { cf: { cacheTtl: 0 } });
  if (!res.ok) return { error: "feed " + res.status };
  const feed = await res.json();
  const byId = new Map((feed.items || []).map(x => [x.id, x]));
  const { results: watches } = await env.DB.prepare("SELECT uid, item, name, base FROM watches").all();
  const now = Date.now();
  const touched = new Set();
  const stmts = [];
  for (const w of watches) {
    const x = byId.get(w.item);
    if (!x || !(x.price > 0)) continue;
    if (x.price < w.base) {
      stmts.push(env.DB.prepare("INSERT INTO notices (uid, item, name, old, new, url, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
        .bind(w.uid, w.item, x.nm || x.name || w.name || "", w.base, x.price, x.url || "", now));
      stmts.push(env.DB.prepare("UPDATE watches SET base = ?1 WHERE uid = ?2 AND item = ?3").bind(x.price, w.uid, w.item));
      touched.add(w.uid);
    } else if (x.price > w.base) {
      // 値段が戻ったら、そこを新しい基準にする（次に下がったときに知らせるため）
      stmts.push(env.DB.prepare("UPDATE watches SET base = ?1 WHERE uid = ?2 AND item = ?3").bind(x.price, w.uid, w.item));
    }
  }
  for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
  // 古いお知らせは消す（30日）
  await env.DB.prepare("DELETE FROM notices WHERE created < ?1").bind(now - 30 * 864e5).run();
  let sent = 0, gone = 0;
  for (const uid of touched) {
    const sub = await env.DB.prepare("SELECT endpoint FROM subs WHERE uid = ?1").bind(uid).first();
    if (!sub) continue;
    try {
      const st = await sendPush(sub, env);
      if (st === 404 || st === 410) { await env.DB.prepare("DELETE FROM subs WHERE uid = ?1").bind(uid).run(); gone++; }
      else if (st < 300) sent++;
    } catch (e) { /* 1人の失敗で止めない */ }
  }
  return { watches: watches.length, dropped: touched.size, sent, gone };
}

// ---- API ----
export async function handle(req, env, ctx) {
  const url = new URL(req.url);
  const h = cors(env, req);
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
  const p = url.pathname;
  try {
    if (p === "/api/vapid" && req.method === "GET") {
      return json({ key: env.VAPID_PUBLIC || null }, 200, { ...h, "Cache-Control": "public, max-age=3600" });
    }

    if (p === "/api/likes" && req.method === "GET") {
      const cache = caches.default;
      const key = new Request(url.origin + "/api/likes");
      let hit = await cache.match(key);
      if (!hit) {
        const { results } = await env.DB.prepare("SELECT item, COUNT(*) AS n FROM likes GROUP BY item").all();
        const counts = {};
        for (const r of results) counts[r.item] = r.n;
        hit = json({ counts }, 200, { "Cache-Control": "public, max-age=60" });
        ctx && ctx.waitUntil(cache.put(key, hit.clone()));
      }
      return new Response(hit.body, { status: 200, headers: { ...Object.fromEntries(hit.headers), ...h } });
    }

    if (p === "/api/like" && req.method === "POST") {
      const b = await body(req);
      if (!UID.test(b.uid || "") || !ITEM.test(b.item || "")) return json({ error: "bad_request" }, 400, h);
      if (b.on) {
        await env.DB.batch([
          env.DB.prepare("INSERT OR IGNORE INTO likes (uid, item, created) VALUES (?1, ?2, ?3)").bind(b.uid, b.item, Date.now()),
          env.DB.prepare("INSERT OR IGNORE INTO watches (uid, item, name, base) VALUES (?1, ?2, ?3, ?4)")
            .bind(b.uid, b.item, String(b.name || "").slice(0, 120), Math.max(0, Math.round(+b.price || 0))),
        ]);
      } else {
        await env.DB.batch([
          env.DB.prepare("DELETE FROM likes WHERE uid = ?1 AND item = ?2").bind(b.uid, b.item),
          env.DB.prepare("DELETE FROM watches WHERE uid = ?1 AND item = ?2").bind(b.uid, b.item),
        ]);
      }
      const r = await env.DB.prepare("SELECT COUNT(*) AS n FROM likes WHERE item = ?1").bind(b.item).first();
      return json({ count: r ? r.n : 0 }, 200, h);
    }

    if (p === "/api/sync" && req.method === "POST") {
      // その端末でいいねしている商品の一覧をまとめて送ってもらう（あとから通知を有効にした人のため）
      const b = await body(req);
      if (!UID.test(b.uid || "") || !Array.isArray(b.items)) return json({ error: "bad_request" }, 400, h);
      const items = b.items.filter(x => x && ITEM.test(x.id || "")).slice(0, MAX_ITEMS);
      const stmts = items.map(x => env.DB.prepare("INSERT OR IGNORE INTO watches (uid, item, name, base) VALUES (?1, ?2, ?3, ?4)")
        .bind(b.uid, x.id, String(x.name || "").slice(0, 120), Math.max(0, Math.round(+x.price || 0))));
      stmts.push(...items.map(x => env.DB.prepare("INSERT OR IGNORE INTO likes (uid, item, created) VALUES (?1, ?2, ?3)").bind(b.uid, x.id, Date.now())));
      for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
      return json({ ok: true, n: items.length }, 200, h);
    }

    if (p === "/api/subscribe" && req.method === "POST") {
      const b = await body(req);
      const s = b.sub || {};
      let ep;
      try { ep = new URL(s.endpoint || ""); } catch (e) { ep = null; }
      if (!UID.test(b.uid || "") || !ep || ep.protocol !== "https:") return json({ error: "bad_request" }, 400, h);
      await env.DB.prepare("INSERT INTO subs (uid, endpoint, created) VALUES (?1, ?2, ?3) ON CONFLICT(uid) DO UPDATE SET endpoint = excluded.endpoint")
        .bind(b.uid, ep.toString(), Date.now()).run();
      return json({ ok: true }, 200, h);
    }

    if (p === "/api/unsubscribe" && req.method === "POST") {
      const b = await body(req);
      if (!UID.test(b.uid || "")) return json({ error: "bad_request" }, 400, h);
      await env.DB.prepare("DELETE FROM subs WHERE uid = ?1").bind(b.uid).run();
      return json({ ok: true }, 200, h);
    }

    if (p === "/api/notices" && req.method === "GET") {
      const uid = url.searchParams.get("uid") || "";
      if (!UID.test(uid)) return json({ error: "bad_request" }, 400, h);
      const { results } = await env.DB.prepare("SELECT id, item, name, old, new, url, created FROM notices WHERE uid = ?1 AND seen = 0 ORDER BY created DESC LIMIT 20").bind(uid).all();
      if (results.length && url.searchParams.get("peek") !== "1") {
        await env.DB.prepare("UPDATE notices SET seen = 1 WHERE uid = ?1 AND seen = 0").bind(uid).run();
      }
      return json({ notices: results }, 200, { ...h, "Cache-Control": "no-store" });
    }

    if (p === "/" || p === "/api") return json({ ok: true, service: "nesage-api" }, 200, h);
    return json({ error: "not_found" }, 404, h);
  } catch (e) {
    return json({ error: "server_error" }, 500, h);
  }
}

export default {
  fetch: (req, env, ctx) => handle(req, env, ctx),
  scheduled: (event, env, ctx) => { ctx.waitUntil(checkPrices(env)); },
};
