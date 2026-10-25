#!/usr/bin/env python3
"""ネサゲ：楽天市場の商品検索APIから、セレクトショップの値下げ中の服を集めて
index.html の <script id="feed"> の items を書きかえる。

使い方: RAKUTEN_APP_ID=... RAKUTEN_ACCESS_KEY=... [RAKUTEN_AFFILIATE_ID=...] \
        python3 fetch.py index.html   （または feed.json）
items 以外（calendar など）はそのまま残す。HTML のほかの部分は変えない。
"""
import json, os, re, subprocess, sys, time, urllib.parse
from datetime import datetime, timezone, timedelta

API = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
ORIGIN = os.environ.get("RAKUTEN_ORIGIN", "https://claude.ai")
JST = timezone(timedelta(hours=9))

# (表示名, 名前にふくまれる目印) …より細かいブランドを先に書く
BRANDS = [
    ("green label relaxing", ["green label relaxing"]),
    ("BEAUTY&YOUTH", ["BEAUTY&YOUTH", "BEAUTY & YOUTH", "ビューティ＆ユース", "ビューティアンドユース"]),
    ("coen", ["coen", "コーエン"]),
    ("ADAM ET ROPÉ", ["ADAM ET ROPE", "ADAM ET ROPÉ", "アダムエロペ"]),
    ("JUNRed", ["JUNRed", "ジュンレッド"]),
    ("Spick and Span", ["Spick and Span", "Spick & Span", "スピックアンドスパン"]),
    ("BEAMS", ["BEAMS", "ビームス"]),
    ("UNITED ARROWS", ["UNITED ARROWS", "ユナイテッドアローズ"]),
    ("SHIPS", ["SHIPS", "シップス"]),
    ("JOURNAL STANDARD", ["JOURNAL STANDARD", "ジャーナルスタンダード"]),
    ("EDIFICE", ["EDIFICE", "エディフィス"]),
    ("IENA", ["IENA", "イエナ"]),
    ("URBAN RESEARCH", ["URBAN RESEARCH", "アーバンリサーチ"]),
    ("nano・universe", ["nano・universe", "nano universe", "ナノユニバース"]),
    ("FREAK'S STORE", ["FREAK'S STORE", "フリークスストア"]),
]
SEARCH = ["BEAMS", "UNITED ARROWS", "SHIPS", "JOURNAL STANDARD", "EDIFICE", "IENA",
          "URBAN RESEARCH", "nano universe", "FREAK'S STORE", "green label relaxing",
          "BEAUTY&YOUTH", "coen", "ADAM ET ROPE", "JUNRed", "Spick and Span"]
PAGES = 3
GENRES = {"men": 551177, "women": 100371}  # メンズファッション / レディースファッション
MAX_ITEMS = 600
OFF_RE = re.compile(r"(\d{1,2})\s*[%％]\s*OFF", re.I)
TAG_RE = re.compile(r"【[^】]*】|\[[^\]]*\]")


def call(params):
    p = dict(params, applicationId=os.environ["RAKUTEN_APP_ID"], formatVersion=2)
    aff = os.environ.get("RAKUTEN_AFFILIATE_ID")
    if aff:
        p["affiliateId"] = aff
    url = API + "?" + urllib.parse.urlencode(p)
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "-m", "25", url,
                            "-H", "accessKey: " + os.environ["RAKUTEN_ACCESS_KEY"],
                            "-H", "Origin: " + ORIGIN, "-H", "Referer: " + ORIGIN + "/"],
                           capture_output=True, text=True)
        try:
            j = json.loads(r.stdout)
        except Exception:
            j = {"error": "bad_response", "error_description": (r.stdout or r.stderr)[:200]}
        if "Items" in j:
            return j
        if attempt < 2 and ("too_many" in json.dumps(j).lower() or j.get("error") == "bad_response"):
            time.sleep(3)
            continue
        raise RuntimeError(json.dumps(j, ensure_ascii=False)[:300])


# 人気ブランド：楽天ファッション（楽天の公式ファッションモール）か、ブランドの公式ショップで売っているものだけ
FAMOUS = [
    ("MICHAEL KORS", ["MICHAEL KORS", "マイケル・コース", "マイケルコース"]),
    ("MARC JACOBS", ["MARC JACOBS", "マークジェイコブス"]),
    ("kate spade new york", ["kate spade", "ケイトスペード"]),
    ("ARMANI EXCHANGE", ["ARMANI EXCHANGE", "アルマーニ エクスチェンジ", "アルマーニエクスチェンジ"]),
    ("EMPORIO ARMANI", ["EMPORIO ARMANI", "エンポリオ・アルマーニ", "エンポリオアルマーニ"]),
    ("Paul Smith", ["Paul Smith", "ポール・スミス", "ポールスミス"]),
    ("TOMMY HILFIGER", ["TOMMY HILFIGER", "トミー ヒルフィガー", "トミーヒルフィガー"]),
    ("POLO RALPH LAUREN", ["RALPH LAUREN", "ラルフローレン", "ラルフ ローレン"]),
    ("FRED PERRY", ["FRED PERRY", "フレッドペリー"]),
    ("New Balance", ["New Balance", "ニューバランス"]),
    ("GAP", ["GAP", "ギャップ"]),
]
FAMOUS_SEARCH = ["MICHAEL KORS", "MARC JACOBS", "kate spade", "ARMANI EXCHANGE", "EMPORIO ARMANI",
                 "Paul Smith", "TOMMY HILFIGER", "RALPH LAUREN", "FRED PERRY", "New Balance", "GAP"]
FAMOUS_GENRES = {"men": 551177, "women": 100371, "both": 216131}  # 216131 = バッグ・小物・ブランド雑貨
FAMOUS_PAGES = 2
FAMOUS_MAX = 300
FAMOUS_PER_BRAND = 40
TRUSTED_SHOPS = {"stylife", "stylifemen", "stylifekids"}  # 楽天ファッション


def brand_of(name, table=None):
    low = name.lower()
    for label, keys in (table or BRANDS):
        for k in keys:
            kl = k.lower()
            if kl == "gap":
                if re.search(r"(?<![a-z])gap(?![a-z])", low):
                    return label
            elif kl in low:
                return label
    return None


def trusted(it, label):
    code = (it.get("shopCode") or "").lower()
    name = (it.get("shopName") or "").lower()
    if code in TRUSTED_SHOPS:
        return True
    if "公式" in name or "official" in name:
        return True
    head = label.lower().split()[0]
    return head in name.replace("・", " ")


def clean(name):
    n = TAG_RE.sub(" ", name)
    n = re.sub(r"\s+", " ", n).strip()
    return n[:140]


def collect(found, errors, seen, now_ms, cat, table, search, genres, pages, need_trust):
    for g, genre in genres.items():
        for kw in search:
          for page in range(1, pages + 1):
            try:
                j = call({"keyword": kw + " SALE", "genreId": genre, "hits": 30, "page": page,
                          "availability": 1, "imageFlag": 1})
            except Exception as e:
                errors.append(f"{cat}/{g}/{kw}: {e}")
                time.sleep(1.2)
                continue
            for it in j.get("Items", []):
                name = it.get("itemName", "")
                mo = OFF_RE.search(name)
                brand = brand_of(name, table)
                if not mo or not brand:
                    continue
                if need_trust and not trusted(it, brand):
                    continue
                off = int(mo.group(1))
                price = int(it.get("itemPrice") or 0)
                if off < 10 or off > 90 or price <= 0:
                    continue
                imgs = it.get("mediumImageUrls") or []
                img = imgs[0] if imgs else None
                if isinstance(img, dict):
                    img = img.get("imageUrl")
                if img:
                    img = re.sub(r"\?_ex=\d+x\d+", "?_ex=400x400", img)
                code = it.get("itemCode")
                key = (brand, clean(name), price)
                if code in found or any(v["_k"] == key for v in found.values()):
                    continue
                was = int(round(price / (1 - off / 100), -1))
                found[code] = {
                    "id": code, "g": g, "cat": cat, "shop": brand, "name": clean(name),
                    "price": price, "was": was, "off": off, "src": "name",
                    "since": seen.get(code, now_ms), "img": img,
                    "url": it.get("affiliateUrl") or it.get("itemUrl"),
                    "seller": it.get("shopName") or "",
                    "_k": key,
                }
            time.sleep(1.1)
            if page >= int(j.get("pageCount") or 1):
                break


def main(path):
    is_json = path.endswith(".json")
    html = open(path, encoding="utf8").read() if os.path.exists(path) else "{}"
    if is_json:
        m = None
        feed = json.loads(html or "{}")
    else:
        m = re.search(r'(<script id="feed" type="application/json">)(.*?)(</script>)', html, re.S)
        if not m:
            sys.exit("feed block not found")
        feed = json.loads(m.group(2) or "{}")
    seen = feed.get("seen") or {}
    now_ms = int(time.time() * 1000)

    errors = []
    sel, fam = {}, {}
    collect(sel, errors, seen, now_ms, "select", BRANDS, SEARCH, GENRES, PAGES, False)
    collect(fam, errors, seen, now_ms, "brand", FAMOUS, FAMOUS_SEARCH, FAMOUS_GENRES, FAMOUS_PAGES, True)
    for k in list(fam):
        if k in sel:
            del fam[k]
    found = dict(sel)
    found.update(fam)

    if not found:
        print("no items found; feed left unchanged", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(2)

    key = lambda x: (-x["off"], x["price"])
    fam_items, per = [], {}
    for x in sorted(fam.values(), key=key):  # 1ブランドにかたよらないように、ブランドごとに上限
        if per.get(x["shop"], 0) >= FAMOUS_PER_BRAND:
            continue
        per[x["shop"]] = per.get(x["shop"], 0) + 1
        fam_items.append(x)
    items = sorted(sel.values(), key=key)[:MAX_ITEMS] + fam_items[:FAMOUS_MAX]
    for x in items:
        x.pop("_k", None)
    feed["items"] = items
    feed["seen"] = {x["id"]: x["since"] for x in items}
    feed["updated"] = datetime.now(JST).isoformat(timespec="seconds")
    feed.setdefault("calendar", [])

    data = json.dumps(feed, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    json.loads(data)  # 書く前に必ず確かめる
    out = data if is_json else html[:m.start(2)] + data + html[m.end(2):]
    open(path, "w", encoding="utf8").write(out)
    by = {}
    for x in items:
        by[x["shop"]] = by.get(x["shop"], 0) + 1
    print(f"items={len(items)} select={sum(x['cat']=='select' for x in items)} brand={sum(x['cat']=='brand' for x in items)} "
          f"both={sum(x['g']=='both' for x in items)} "
          f"men={sum(x['g']=='men' for x in items)} "
          f"women={sum(x['g']=='women' for x in items)} new={sum(x['since']==now_ms for x in items)}")
    print("by shop:", by)
    for e in errors:
        print("warn:", e)


if __name__ == "__main__":
    main(sys.argv[1])
