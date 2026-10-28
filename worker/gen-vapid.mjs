// 通知用の鍵（VAPID）を作る。公開鍵は base64url、秘密鍵は JWK で出す
const kp = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
const raw = new Uint8Array(await crypto.subtle.exportKey("raw", kp.publicKey));
const pub = Buffer.from(raw).toString("base64url");
const jwk = await crypto.subtle.exportKey("jwk", kp.privateKey);
const out = process.argv[2];
if (out === "public") console.log(pub);
else if (out === "private") console.log(JSON.stringify(jwk));
else { const fs = await import("fs"); fs.writeFileSync("vapid-public.txt", pub); fs.writeFileSync("vapid-private.json", JSON.stringify(jwk)); }
