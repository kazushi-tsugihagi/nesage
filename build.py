#!/usr/bin/env python3
"""ネサゲ：feed.json から、ブランド別・カテゴリ別の静的ページとサイトマップを作る。

使い方: python3 build.py
  - feed.json の各商品に種類（t: tops/bottoms/outer/dress/bag/shoes）を書きこむ
  - brand/<slug>/index.html, men/..., women/... を作りなおす
  - index.html の <!--LINKS--> ～ <!--/LINKS--> の中に、各ページへのリンクを入れる
  - sitemap.xml を作る
SITE_URL（環境変数）でサイトのURLを変えられる（独自ドメインに移ったとき用）。
"""
import html, json, os, re, shutil, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch import display_name  # noqa: E402
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("SITE_URL", "https://kazushi-tsugihagi.github.io/nesage/").rstrip("/") + "/"
JST = timezone(timedelta(hours=9))
MIN_ITEMS = 6
PER_PAGE = 120

TYPES = [  # 上から順に判定する
    ("acc", "アクセサリー・小物", r"ネックレス|ピアス|イヤリング|イヤーカフ|(?<![ァ-ヶー])リング|キーリング|ブレスレット|バングル|アンクレット|ヘアクリップ|ヘアゴム|ヘアアクセ|ヘアピン|カチューシャ|バレッタ|シュシュ|時計|ウォッチ|帽子|(?<!ニット)キャップ(?!スリーブ)|ハット|ビーニー|ベレー|ニット帽|ベルト(?!付|ループ)(?!.*(?:パンツ|スカート|ワンピース|ドレス|コート|ジャケット|シャツ|ブラウス))|マフラー|ストール|スヌード|手袋|グローブ|サングラス|メガネ|眼鏡|チャーム|キーホルダー|ブローチ|アクセサリー"),
    ("goods", "小物", r"ソックス|靴下|ネクタイ|水着|スイム|ルームウェア|パジャマ"),
    ("bag", "バッグ・小物", r"バッグ|トート|(?<!オフ)ショルダー|リュック|ポーチ|クラッチ|財布|ウォレット|カードケース"),
    ("shoes", "シューズ", r"スニーカー|シューズ|ブーツ|ローファー|サンダル|パンプス|ミュール"),
    ("dress", "ワンピース", r"ワンピース|(?<!パンツ )ドレス(?!パンツ|シャツ)|オールインワン|サロペット|ジャンパースカート"),
    ("outer", "アウター", r"アウター|(?<!ペチ)コート|ブルゾン|(?<!ボタン)ダウン|ジャケット|ジャンパー"),
    ("bottoms", "パンツ・スカート", r"パンツ|デニム(?!ジャケット|シャツ)|スカート|スラックス|ジーンズ|チノ|ショーツ"),
    ("tops", "トップス", r"トップス|シャツ|ブラウス|ニット|セーター|カーディガン|カットソー|スウェット|パーカー|プルオーバー|ベスト|ジレ|タンク|ポロ|フーディ|Tee|Tシャツ"),
]
TYPE_LABEL = {k: v for k, v, _ in TYPES}
GENDER_LABEL = {"men": "メンズ", "women": "レディース"}
STYLE_LABEL = {"amekaji": "アメカジ", "street": "ストリート", "casual": "カジュアル", "kirei": "きれいめ", "trad": "トラッド", "mode": "モード", "sporty": "スポーティ", "outdoor": "アウトドア", "natural": "ナチュラル", "feminine": "フェミニン"}


def type_of(name):
    for k, _, r in TYPES:
        if re.search(r, name or ""):
            return k
    return None


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def yen(n):
    return "¥{:,}".format(int(n))


CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.2 4.2L19 7"/></svg>'


def page_shell(index_html, title, desc, canonical, body, depth):
    """index.html の見た目（フォントとCSS）を借りて、1枚のページを組み立てる。"""
    fonts = re.search(r'<link rel="preconnect"[^\n]*\n<link rel="stylesheet"[^\n]*', index_html).group(0)
    css = re.search(r"<style>\n/\* レイアウト[\s\S]*?</style>", index_html).group(0)
    up = "../" * depth
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="ネサゲ">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}">
<meta name="claude:viewport-fit-sides" content="cover">
{fonts}
<style>:root{{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
{css}
<style>
.crumb{{font-size:12.5px;color:var(--sub);display:flex;gap:6px;flex-wrap:wrap;padding-top:14px}}
.crumb a{{color:var(--sub)}}
.intro{{color:var(--sub);font-size:14px;margin:4px 0 14px;max-width:70ch}}
.links{{display:flex;flex-direction:column;gap:14px;padding-block:8px 32px}}
.links h2{{font-size:15px;margin:0 0 8px}}
.links div{{display:flex;flex-wrap:wrap;gap:6px}}
.links a{{text-decoration:none}}
.topbtn{{display:inline-block;margin:6px 0 20px;font-weight:700;font-size:14px}}
</style>
</head><body>
<header><div class="wrap hrow"><a class="logo" href="{up}" aria-label="ネサゲ トップ"><span class="hole" aria-hidden="true"></span><b>ネサゲ</b><small>セレクトショップと<br>人気ブランドの値下げ</small></a></div></header>
<div class="trust"><ul class="wrap"><li>{CHECK}楽天市場の商品だけを紹介</li><li>{CHECK}毎朝6時ごろに自動で更新</li><li>{CHECK}お買い物は楽天市場の各ショップで</li><li><a href="{up}about/">ネサゲについて</a></li></ul></div>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
<nav class="fnav" aria-label="サイトの情報"><a href="{up}about/">ネサゲについて</a><a href="{up}privacy/">プライバシーポリシー</a><a href="{up}coord/">予算でコーデを作る</a></nav>
<p><b>PR</b>：このサイトはアフィリエイト広告（楽天アフィリエイト）を利用しています。リンク先で買い物をすると、サイトに紹介料が入ることがあります。</p>
<p>値段と在庫は表示した時刻のものです。今の値段は必ずリンク先のお店で確認してください。割引率は、お店が商品名に書いている「○%OFF」の表記をそのまま使っています。取り消し線の「約○円」は、その表記から計算した目安の元の値段です（お店の定価や、実際に売られていた値段を確かめたものではありません）。商品情報と画像は楽天ウェブサービスから取得しています。</p>
<p><a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">Supported by Rakuten Developers</a></p>
<p>ショップ名・ブランド名は各社のものです。このサイトは各ショップの公式サイトではありません。</p>
</div></footer>
</body></html>
"""


def card(x):
    szs = [("フリー" if z == "FREE" else z) for z in (x.get("sz") or [])]
    sz = f'<div class="sz">サイズ {" ".join(szs)}{" ・ " + esc(x["fit"]) if x.get("fit") else ""}</div>' if szs else ""
    seller = f'<div class="seller">販売：{esc(x["seller"])}</div>' if x.get("cat") in ("brand", "petit") and x.get("seller") else ""
    img = (f'<img src="{esc(x["img"])}" alt="{esc(x.get("nm") or x["name"])}" loading="lazy" referrerpolicy="no-referrer" width="400" height="400">'
           if x.get("img") else "")
    was = f'<s>約{yen(x["was"])}</s>' if x.get("was") else ""
    return f"""<article class="card"><a class="ph" href="{esc(x['url'])}" target="_blank" rel="sponsored noopener">{img}</a>
<div class="cb"><div class="shop"><span>{esc(x['shop'])}</span></div><div class="nm">{esc(x.get('nm') or x['name'])}</div>
<div class="pr"><b>{yen(x['price'])}</b>{was}</div><div class="why">お店の表示（{int(x['off'])}%OFF）から計算</div>{sz}{seller}
<div class="go"><a href="{esc(x['url'])}" target="_blank" rel="sponsored noopener">楽天で見る</a><span class="pr-mark">PR</span></div></div></article>"""


COORD_BODY = r"""
<nav class="crumb" aria-label="現在地"><a href="../">ネサゲ</a> › <span>予算でコーデを作る</span></nav>
<div class="lead"><h1>予算でコーデを作る</h1><span class="stamp" id="cStamp"></span></div>
<p class="intro">予算と好みをえらぶと、いま値下げ中の商品から、色の組み合わせまで考えたコーデを作ります。</p>
<section class="cform" aria-label="コーデの条件">
  <div class="seg" role="group" aria-label="メンズ・レディース"><button type="button" data-cg="men" aria-pressed="true">メンズ</button><button type="button" data-cg="women" aria-pressed="false">レディース</button></div>
  <div class="frm"><span class="lb">予算</span><div class="opts" role="group" aria-label="予算">
    <button type="button" class="chip" data-cb="5000">5,000円</button><button type="button" class="chip" data-cb="10000" aria-pressed="true">1万円</button><button type="button" class="chip" data-cb="15000">1.5万円</button><button type="button" class="chip" data-cb="20000">2万円</button><button type="button" class="chip" data-cb="30000">3万円</button>
    <label class="free" for="cBudget">自由に<input id="cBudget" type="number" inputmode="numeric" min="2000" max="200000" step="500" value="10000"><span>円まで</span></label>
  </div></div>
  <div class="frm"><span class="lb">雰囲気</span><div class="opts" role="group" aria-label="雰囲気">
    <button type="button" class="chip" data-cs="any" aria-pressed="true">おまかせ</button><button type="button" class="chip" data-cs="amekaji">アメカジ</button><button type="button" class="chip" data-cs="street">ストリート</button><button type="button" class="chip" data-cs="casual">カジュアル</button><button type="button" class="chip" data-cs="kirei">きれいめ</button><button type="button" class="chip" data-cs="trad">トラッド</button><button type="button" class="chip" data-cs="sporty">スポーティ</button><button type="button" class="chip" data-cs="outdoor">アウトドア</button><button type="button" class="chip" data-cs="natural">ナチュラル</button><button type="button" class="chip" data-cs="feminine">フェミニン</button>
  </div></div>
  <div class="frm"><span class="lb">サイズ</span><div class="opts" role="group" aria-label="サイズ">
    <button type="button" class="chip" data-cz="any" aria-pressed="true">指定なし</button><button type="button" class="chip" data-cz="S">S</button><button type="button" class="chip" data-cz="M">M</button><button type="button" class="chip" data-cz="L">L</button><button type="button" class="chip" data-cz="XL">XL</button><button type="button" class="chip" data-cz="XXL">XXL以上</button>
  </div></div>
  <div class="frm"><span class="lb">色</span><div class="opts" role="group" aria-label="色の組み合わせ">
    <button type="button" class="chip" data-cc="any" aria-pressed="true">おまかせ</button><button type="button" class="chip" data-cc="mono"><i class="dot" style="background:#1d1d1f"></i><i class="dot" style="background:#f4f4f2"></i>モノトーン</button><button type="button" class="chip" data-cc="earth"><i class="dot" style="background:#c9b08c"></i><i class="dot" style="background:#7a5a3c"></i>ベージュ・ブラウン</button><button type="button" class="chip" data-cc="navy"><i class="dot" style="background:#26324f"></i><i class="dot" style="background:#f4f4f2"></i>ネイビー系</button><button type="button" class="chip" data-cc="accent"><i class="dot" style="background:#9a9a9a"></i><i class="dot" style="background:#c83a4a"></i>差し色を1つ</button>
  </div></div>
  <button type="button" class="go1" id="cGo">コーデを作る</button>
</section>
<div id="cOut" aria-live="polite"></div>
<section id="aiBox" hidden><h2 class="sec">今日のAIコーデ</h2><p class="intro">毎朝、AI（Claude）が、その日の値下げ商品の中から選んだコーデです。</p><div id="aiOut"></div></section>
<p class="intro small">自動のコーデは、商品名から種類（トップス・パンツなど）・雰囲気・選べるサイズ・色を読み取って、季節に合わないもの（秋冬なら半袖やショートパンツなど）を外し、予算に収まるように組み合わせています。「この色で」は、その商品で選べる色の中からのおすすめです。サイズをえらぶと、そのサイズ（またはフリーサイズ）がある商品だけで組みます。サイズごとの在庫と、写真の色とのちがいは、お店のページで確認してください。</p>
<script>
(()=>{
const $=s=>document.querySelector(s);
const yen=n=>'¥'+Math.round(n).toLocaleString('ja-JP');
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const LABEL={tops:'トップス',bottoms:'パンツ・スカート',outer:'アウター',dress:'ワンピース',bag:'バッグ',shoes:'シューズ',acc:'アクセサリー'};
/* 色：長い名前から先に探す（オフホワイトをホワイトと読まないように） */
const COL={'オフホワイト':'#eeeae0','アイボリー':'#f1ecdc','エクリュ':'#ece4d2','ホワイト':'#f7f7f5','ライトグレー':'#c9c9c9','チャコール':'#4a4a4c','グレー':'#9a9a9a','ブラック':'#1d1d1f','ネイビー':'#26324f','ベージュ':'#d8c3a2','キャメル':'#b98a52','ダークブラウン':'#4e3524','ブラウン':'#7a5a3c','モカ':'#8b6e58','カーキ':'#7b7650','オリーブ':'#6b6b3a','ボルドー':'#6d2233','ワイン':'#6d2233','レッド':'#c83a4a','ピンク':'#e59ab0','オレンジ':'#e2853c','イエロー':'#e8c64a','グリーン':'#4f8a5c','ミント':'#9fd4bf','サックス':'#9cbbe0','ブルー':'#3d6fb6','ラベンダー':'#b9a6d8','パープル':'#7a5a9a','シルバー':'#b8bcc2','ゴールド':'#c9a64a'};
const CNAMES=Object.keys(COL).sort((a,b)=>b.length-a.length);
const NEUTRAL=new Set(['オフホワイト','アイボリー','エクリュ','ホワイト','ライトグレー','チャコール','グレー','ブラック','ネイビー','ベージュ','キャメル','ダークブラウン','ブラウン','モカ','カーキ','オリーブ']);
const THEME={
  mono:{ok:c=>['ブラック','ホワイト','オフホワイト','グレー','ライトグレー','チャコール','シルバー'].includes(c)},
  earth:{ok:c=>['ベージュ','ブラウン','ダークブラウン','キャメル','モカ','カーキ','オリーブ','アイボリー','エクリュ','オフホワイト','ホワイト'].includes(c),need:['ベージュ','ブラウン','ダークブラウン','キャメル','モカ','カーキ','オリーブ']},
  navy:{ok:c=>['ネイビー','ホワイト','オフホワイト','グレー','ライトグレー','ベージュ','サックス','ブラック'].includes(c),need:['ネイビー']},
  accent:{ok:()=>true,accent:1},
  any:{ok:()=>true,maxAccent:1}
};
function colorsOf(name){let n=String(name||''),out=[];for(const c of CNAMES){if(n.includes(c)){out.push(c);n=n.split(c).join(' ')}}return out}
/* 雰囲気：商品名のことばで点数をつける */
const STY={
  kirei:/ジャケット|テーラード|スラックス|トラウザー|ブラウス|シャツ(?!ジャケット)|プリーツ|テーパード|セットアップ|タック|ニット|カーディガン|ウール|モック|ボウタイ|ミディ|タイト|ローファー|ノーカラー/,
  casual:/デニム|スウェット|パーカー|フーディ|カーゴ|Tシャツ|Tee|カットソー|イージー|チノ|ワイド|ボーダー|コットン|リネン|オーバーオール|スニーカー/,
  sporty:/ジョガー|トラック|ナイロン|スポーツ|アノラック|ジャージ/,
  amekaji:/アメカジ|ワーク|ミリタリー|デニム|チノ|ネル|ヘビーウェイト|カレッジ/,
  street:/ストリート|オーバーサイズ|ビッグ|グラフィック|ロゴ|カーゴ|バギー/,
  outdoor:/アウトドア|マウンテン|フリース|撥水|中綿|中わた|ダウン|ボア/,
  trad:/トラッド|アイビー|オックスフォード|ボタンダウン|ブレザー|ケーブル|ツイード/,
  mode:/モード|ドレープ|ミニマル/,
  natural:/ナチュラル|リネン|ガーゼ|ワッフル/,
  feminine:/フェミニン|レース|フリル|リボン|ティアード|フラワー|フローラル/
};
let ITEMS=[],G='men',B=10000,S='any',CC='any',Z='any';
const hasSty=(x,s)=>Array.isArray(x.st)?x.st.includes(s):!!(STY[s]&&STY[s].test(x.name));
const fitsSize=x=>{if(Z==='any'||x.t==='bag'||x.t==='acc')return true;if(!(x.sz&&x.sz.length))return false;return x.sz.some(z=>z===Z||z==='FREE'||(Z==='XXL'&&/^(XXL|3XL|4XL)$/.test(z)))};
const ls={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
G=ls.get('ns_cg','men');B=ls.get('ns_cb',10000);S=ls.get('ns_cs','any');CC=ls.get('ns_cc','any');Z=ls.get('ns_cz','any');
const pick=L=>L[Math.floor(Math.pow(Math.random(),1.6)*L.length)];
const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
/* 色の割り当て：1つの商品に、選べる色の中から1色をえらぶ */
function assign(set,theme){
  const T=THEME[theme];
  const opts=set.map(x=>shuffle((x.cols||[]).filter(c=>COL[c]&&T.ok(c))));
  if(opts.some(o=>!o.length))return null;
  let best=null;
  const rec=(i,acc)=>{
    if(best)return;
    if(i===set.length){
      const accents=acc.filter(c=>!NEUTRAL.has(c));
      if(T.maxAccent!=null&&accents.length>T.maxAccent)return;
      if(T.accent&&accents.length!==T.accent)return;
      if(T.need&&!acc.some(c=>T.need.includes(c)))return;
      const tb=set.map((x,k)=>[x.t,acc[k]]).filter(([t])=>t==='tops'||t==='bottoms').map(([,c])=>c);
      if(tb.length===2&&tb[0]===tb[1])return;
      best=acc.slice();return;
    }
    for(const c of opts[i].slice(0,6)){acc.push(c);rec(i+1,acc);acc.pop();if(best)return}
  };
  rec(0,[]);return best;
}
function make(g,budget,style,theme){
  const mo=new Date().getMonth()+1;
  const offSeason=(mo>=10||mo<=3)?/半袖|ショーツ|ショートパンツ|ハーフパンツ|タンク|ノースリーブ|サンダル|キャミ|リネン/:(mo>=6&&mo<=8)?/ダウン|ウール|ボア|フリース|中わた|コート|ニット/:null;
  let pool=ITEMS.filter(x=>x.t&&(x.g===g||x.g==='both')&&!(offSeason&&offSeason.test(x.name))&&fitsSize(x)).sort((a,b)=>b.off-a.off||a.price-b.price);
  const styled=style==='any'?pool:pool.filter(x=>hasSty(x,style));
  const by=t=>{const s=styled.filter(x=>x.t===t);return s.length>=3?s:pool.filter(x=>x.t===t)};
  const tops=by('tops'),bots=by('bottoms'),outs=by('outer'),dres=by('dress'),bags=pool.filter(x=>x.t==='bag'),accs=pool.filter(x=>x.t==='acc');
  const out=[],used=new Set();
  for(let k=0;k<3;k++){
    let best=null;
    for(let i=0;i<1500;i++){
      let set=[];
      if(g==='women'&&dres.length&&Math.random()<.3)set=[pick(dres)];
      else{if(!tops.length||!bots.length)break;set=[pick(tops),pick(bots)]}
      if(set.some(x=>used.has(x.id)))continue;
      let sum=set.reduce((a,x)=>a+x.price,0);if(sum>budget)continue;
      if(!assign(set,theme))continue;
      const fit=(L,p)=>{if(Math.random()>p)return;const c=shuffle(L.filter(x=>!used.has(x.id)&&x.price<=budget-sum)).slice(0,12);for(const x of c){if(assign([...set,x],theme)){set.push(x);sum+=x.price;return}}};
      if(budget-sum>=2500)fit(outs,.85);
      if(budget-sum>=1500)fit(bags,.4);
      if(budget-sum>=800)fit(accs,.45);
      const cols=assign(set,theme);if(!cols)continue;
      const sty=style==='any'?0:set.filter(x=>hasSty(x,style)).length/set.length;
      const score=set.reduce((a,x)=>a+(x.was||x.price),0)*(0.9+Math.random()*.2)*(1+sty);
      if(!best||score>best.score)best={set,sum,score,cols};
    }
    if(!best)break;
    best.set.forEach(x=>used.add(x.id));out.push(best);
  }
  return out;
}
const dot=c=>COL[c]?`<i class="dot" style="background:${COL[c]}" aria-hidden="true"></i>`:'';
function row(x,c){
  const img=x.img?`<img src="${esc(x.img)}" alt="" loading="lazy" referrerpolicy="no-referrer">`:'';
  return `<li><a class="ci" href="${esc(x.url)}" target="_blank" rel="sponsored noopener"><span class="th">${img}</span><span class="tx"><small>${esc(LABEL[x.t]||'')}・${esc(x.shop)}</small><span class="n">${esc(x.nm||x.name)}</span>${c?`<span class="col">${dot(c)}この色で：<b>${esc(c)}</b></span>`:''}${x.sz&&x.sz.length?`<span class="szl">サイズ ${x.sz.map(z=>z==='FREE'?'フリー':z).join(' ')}${x.fit?' ・ '+esc(x.fit):''}</span>`:''}<b>${yen(x.price)}</b>${x.was?`<s>約${yen(x.was)}</s>`:''}<em>${x.off}%OFF</em></span></a></li>`;
}
function outfit(o,i,title,comment){
  const was=o.set.reduce((a,x)=>a+(x.was||x.price),0);
  const pal=(o.cols||[]).filter(Boolean);
  return `<article class="outfit"><header><h2>${esc(title||('コーデ'+(i+1)))}</h2><p>合計 <b>${yen(o.sum)}</b><span>（元の値段の目安 約${yen(was)}）</span></p></header>${pal.length?`<p class="pal">${pal.map(dot).join('')}<span>${pal.map(esc).join('・')}</span></p>`:''}${comment?`<p class="cm">${esc(comment)}</p>`:''}<ul>${o.set.map((x,k)=>row(x,(o.cols||[])[k])).join('')}</ul><p class="pr-note"><span class="pr-mark">PR</span> 商品を押すと楽天のお店のページが開きます</p></article>`;
}
function draw(){
  document.querySelectorAll('[data-cg]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cg===G)));
  document.querySelectorAll('[data-cb]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.cb===B)));
  document.querySelectorAll('[data-cs]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cs===S)));
  document.querySelectorAll('[data-cc]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cc===CC)));
  document.querySelectorAll('[data-cz]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.cz===Z)));
  $('#cBudget').value=B;
  const R=make(G,B,S,CC);
  $('#cOut').innerHTML=R.length?`<div class="outs">${R.map((o,i)=>outfit(o,i)).join('')}</div><div class="again"><button type="button" id="cAgain">ほかの組み合わせを見る</button></div>`
    :`<div class="empty">この条件（${yen(B)}まで）では、いまの値下げ商品でコーデを組めませんでした。予算を上げるか、雰囲気・サイズ・色を「おまかせ」「指定なし」にしてみてください。</div>`;
}
async function load(){
  try{const r=await fetch('../feed.json?t='+Math.floor(Date.now()/6e5),{cache:'no-cache'});const j=await r.json();ITEMS=(j.items||[]).filter(x=>x&&x.price>0);ITEMS.forEach(x=>x.cols=colorsOf(x.name));
    if(j.updated){const u=new Date(j.updated);$('#cStamp').textContent=`${u.getMonth()+1}月${u.getDate()}日の値下げ商品から`}}catch(e){ITEMS=[]}
  if(!ITEMS.length){$('#cOut').innerHTML='<div class="empty">商品データを読みこめませんでした。時間をおいて、もう一度開いてください。</div>';return}
  draw();
  try{const r=await fetch('../outfits.json?t='+Math.floor(Date.now()/6e5),{cache:'no-cache'});if(!r.ok)throw 0;const j=await r.json();
    const byId=new Map(ITEMS.map(x=>[x.id,x]));
    const A=(j.outfits||[]).map(o=>{const ids=(o.items||[]).map(v=>typeof v==='string'?v:v&&v.id);const set=ids.map(id=>byId.get(id)).filter(Boolean);if(set.length<2||set.length!==ids.length)return null;
      const cols=(o.items||[]).map((v,k)=>{const c=typeof v==='object'&&v?v.color:null;return c&&set[k].cols.includes(c)?c:null});
      return {o,set,cols,sum:set.reduce((a,x)=>a+x.price,0)}}).filter(Boolean);
    if(A.length){$('#aiBox').hidden=false;$('#aiOut').innerHTML=`<div class="outs">${A.map((a,i)=>outfit(a,i,a.o.title,a.o.comment)).join('')}</div>`}}catch(e){}
}
document.addEventListener('click',e=>{
  const g=e.target.closest('[data-cg]');if(g){G=g.dataset.cg;ls.set('ns_cg',G);draw();return}
  const b=e.target.closest('[data-cb]');if(b){B=+b.dataset.cb;ls.set('ns_cb',B);draw();return}
  const s=e.target.closest('[data-cs]');if(s){S=s.dataset.cs;ls.set('ns_cs',S);draw();return}
  const c=e.target.closest('[data-cc]');if(c){CC=c.dataset.cc;ls.set('ns_cc',CC);draw();return}
  const z=e.target.closest('[data-cz]');if(z){Z=z.dataset.cz;ls.set('ns_cz',Z);draw();return}
  if(e.target.closest('#cGo')){const v=Math.round(+$('#cBudget').value||0);if(v>=2000){B=Math.min(v,200000);ls.set('ns_cb',B)}draw();$('#cOut').scrollIntoView({behavior:'smooth',block:'start'});return}
  if(e.target.closest('#cAgain')){draw();$('#cOut').scrollIntoView({behavior:'smooth',block:'start'})}
});
$('#cBudget').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('#cGo').click()}});
load();
})();
</script>
"""

COORD_CSS = """<style>
.cform{display:flex;flex-direction:column;gap:12px;background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;margin-bottom:18px}
.cform .seg{margin-left:0;align-self:flex-start}
.free{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--sub);flex-wrap:wrap}
.free input{width:7.5em;border:1px solid var(--line);background:var(--paper);border-radius:8px;padding:6px 8px;font-size:15px;font-variant-numeric:tabular-nums}
.frm{display:grid;grid-template-columns:3.5em minmax(0,1fr);gap:8px;align-items:start}
.frm .lb{font-size:13px;color:var(--sub);font-weight:700;padding-top:6px}
.opts{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.opts .chip[aria-pressed="true"]{border-color:var(--ink);background:var(--ink);color:var(--paper)}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;border:1px solid rgba(0,0,0,.18);flex:none;vertical-align:-1px}
.chip .dot+.dot{margin-left:-6px}
.pal{margin:0;display:flex;align-items:center;gap:4px;font-size:12.5px;color:var(--sub);flex-wrap:wrap}
.pal span{margin-left:4px}
.ci .col{flex-basis:100%;font-size:12px;display:flex;align-items:center;gap:5px;color:var(--sub)}
.ci .szl{flex-basis:100%;font-size:11.5px;color:var(--sub)}
.ci .col b{color:var(--ink);font-size:12px}
.go1{align-self:flex-start;border:0;background:var(--tag);color:var(--tagInk);font-weight:700;font-size:15px;border-radius:999px;padding:10px 26px;cursor:pointer}
.outs{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
@media (max-width:440px){.outs{grid-template-columns:minmax(0,1fr)}}
.outfit{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:12px 14px;display:flex;flex-direction:column;gap:8px;min-width:0}
.outfit header{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}
.outfit h2{margin:0;font-size:16px;font-family:var(--display);font-weight:400}
.outfit header p{margin:0;font-size:13px;color:var(--sub);font-variant-numeric:tabular-nums}
.outfit header b{color:var(--tag);font-size:18px}
.outfit .cm{margin:0;font-size:13px;line-height:1.6}
.outfit ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.ci{display:grid;grid-template-columns:76px minmax(0,1fr);gap:10px;text-decoration:none;align-items:start}
.ci .th{width:76px;height:76px;border-radius:6px;overflow:hidden;background:var(--bg);display:block}
.ci .th img{width:100%;height:100%;object-fit:cover;display:block}
.ci .tx{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 6px;min-width:0;font-variant-numeric:tabular-nums}
.ci .tx small{flex-basis:100%;font-size:11.5px;color:var(--sub);font-weight:700}
.ci .n{flex-basis:100%;font-size:13px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ci .tx b{color:var(--tag);font-size:15px}
.ci .tx s{font-size:12px;color:var(--sub)}
.ci .tx em{font-style:normal;font-size:11.5px;font-weight:700;color:var(--tag)}
.pr-note{margin:0;font-size:11.5px;color:var(--sub);display:flex;gap:6px;align-items:center}
.again{display:flex;justify-content:center;padding:16px 0 8px}
.again button{border:1px solid var(--ink);background:var(--paper);border-radius:999px;padding:10px 24px;font-weight:700;cursor:pointer}
.sec{font-size:18px;margin:26px 0 0}
.small{font-size:12.5px;margin-top:18px}
</style>"""


def main():
    feed_path = os.path.join(ROOT, "feed.json")
    feed = json.load(open(feed_path, encoding="utf8"))
    items = feed.get("items") or []
    for x in items:
        t = type_of(x.get("name"))
        x["t"] = None if t == "goods" else t
        x["nm"] = display_name(x.get("name"), x.get("shop"))
    # 同じ商品が別のお店（楽天ファッションと公式ショップなど）で重なっていたら1つにする
    seen_keys, uniq = set(), []
    for x in items:
        img = re.sub(r"\?.*$", "", (x.get("img") or "")).rsplit("/", 1)[-1]
        k1 = (x["shop"], re.sub(r"\s+", "", x["nm"]).lower(), x["price"])
        k2 = (x["shop"], img, x["price"]) if img else None
        if k1 in seen_keys or (k2 and k2 in seen_keys):
            continue
        seen_keys.add(k1)
        if k2:
            seen_keys.add(k2)
        uniq.append(x)
    feed["items"] = items = uniq
    data = json.dumps(feed, ensure_ascii=False, separators=(",", ":"))
    json.loads(data)
    open(feed_path, "w", encoding="utf8").write(data)

    index_path = os.path.join(ROOT, "index.html")
    index_html = open(index_path, encoding="utf8").read()
    upd = datetime.fromisoformat(feed["updated"]) if feed.get("updated") else datetime.now(JST)
    when = f"{upd.month}月{upd.day}日"
    key = lambda x: (-x["off"], x["price"])

    pages = []  # (path, title, desc, intro, items, crumbs)

    # ブランド別
    brands = {}
    for x in items:
        brands.setdefault(x["shop"], []).append(x)
    brand_pages = []
    for b, L in sorted(brands.items(), key=lambda kv: -len(kv[1])):
        if len(L) < MIN_ITEMS:
            continue
        p = f"brand/{slug(b)}/"
        brand_pages.append((b, p, len(L)))
        top = max(x["off"] for x in L)
        pages.append((p, f"{b}のセール・値下げ商品まとめ（最大{top}%OFF）｜ネサゲ",
                      f"{b}の値下げ中の服を{len(L)}件まとめています。最大{top}%OFF。毎朝自動で更新。{when}時点。",
                      f"{b}の、いま値下げ中の商品を割引が大きい順に並べています。毎朝自動で新しくなります（{when}時点）。",
                      sorted(L, key=key), [("ブランド", None), (b, None)]))

    # メンズ・レディース、その中の種類別
    cat_pages = []
    for g in ("men", "women"):
        L = [x for x in items if x["g"] in (g, "both")]
        if len(L) >= MIN_ITEMS:
            p = f"{g}/"
            cat_pages.append((GENDER_LABEL[g], p, len(L)))
            pages.append((p, f"{GENDER_LABEL[g]}服のセール・値下げ商品まとめ｜ネサゲ",
                          f"セレクトショップと人気ブランドの{GENDER_LABEL[g]}の値下げ商品を{len(L)}件まとめています。毎朝自動で更新。{when}時点。",
                          f"{GENDER_LABEL[g]}の、いま値下げ中の商品を割引が大きい順に並べています（{when}時点）。",
                          sorted(L, key=key), [(GENDER_LABEL[g], None)]))
        for t, label, _ in TYPES:
            if t == "goods":
                continue
            LL = [x for x in L if x["t"] == t]
            if len(LL) < MIN_ITEMS:
                continue
            p = f"{g}/{t}/"
            cat_pages.append((f"{GENDER_LABEL[g]}の{label}", p, len(LL)))
            pages.append((p, f"{GENDER_LABEL[g]}の{label} セール・値下げまとめ｜ネサゲ",
                          f"{GENDER_LABEL[g]}の{label}の値下げ商品を{len(LL)}件まとめています。BEAMS・UNITED ARROWSなど。毎朝自動で更新。{when}時点。",
                          f"{GENDER_LABEL[g]}の{label}で、いま値下げ中の商品を割引が大きい順に並べています（{when}時点）。",
                          sorted(LL, key=key), [(GENDER_LABEL[g], f"{g}/"), (label, None)]))

    # 雰囲気別
    style_pages = []
    for k, label in STYLE_LABEL.items():
        L = [x for x in items if k in (x.get("st") or [])]
        if len(L) < MIN_ITEMS:
            continue
        p = f"style/{k}/"
        style_pages.append((label, p, len(L)))
        pages.append((p, f"{label}服のセール・値下げ商品まとめ｜ネサゲ",
                      f"{label}な服の値下げ商品を{len(L)}件まとめています（メンズ・レディース）。セレクトショップと人気ブランドから。毎朝自動で更新。{when}時点。",
                      f"{label}な雰囲気の、いま値下げ中の商品を割引が大きい順に並べています。雰囲気は、お店の商品説明から自動で読み取った目安です（{when}時点）。",
                      sorted(L, key=key), [("雰囲気", None), (label, None)]))

    def links_html(depth):
        up = "../" * depth
        bl = "".join(f'<a class="chip" href="{up}{p}">{esc(n)}<span style="color:var(--sub)">{c}</span></a>' for n, p, c in brand_pages)
        sl = "".join(f'<a class="chip" href="{up}{p}">{esc(n)}<span style="color:var(--sub)">{c}</span></a>' for n, p, c in style_pages)
        cl = "".join(f'<a class="chip" href="{up}{p}">{esc(n)}<span style="color:var(--sub)">{c}</span></a>' for n, p, c in cat_pages)
        return (f'<nav class="links" aria-label="ページ一覧"><section><h2>ブランドから探す</h2><div>{bl}</div></section>'
                f'<section><h2>カテゴリから探す</h2><div>{cl}</div></section>'
                f'<section><h2>雰囲気から探す</h2><div>{sl}</div></section>'
                f'<section><h2>コーデを作る</h2><div><a class="chip" href="{up}coord/">予算に合わせてコーデを作る</a></div></section></nav>')

    # 古いページを消してから作りなおす
    for d in ("brand", "men", "women", "style"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    for p, title, desc, intro, L, crumbs in pages:
        depth = p.count("/")
        up = "../" * depth
        cr = '<a href="{0}">ネサゲ</a>'.format(up) + "".join(
            f' › <a href="{up}{href}">{esc(n)}</a>' if href else f" › <span>{esc(n)}</span>" for n, href in crumbs)
        h1 = title.split("｜")[0]
        body = (f'<nav class="crumb" aria-label="現在地">{cr}</nav>'
                f'<div class="lead"><h1>{esc(h1)}</h1><span class="stamp">{len(L)}件・{when} 更新</span></div>'
                f'<p class="intro">{esc(intro)}</p>'
                f'<a class="topbtn" href="{up}">検索や保存は、ネサゲのトップから →</a>'
                f'<div class="grid">{"".join(card(x) for x in L[:PER_PAGE])}</div>'
                f'{links_html(depth)}')
        out = os.path.join(ROOT, p, "index.html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w", encoding="utf8").write(page_shell(index_html, title, desc, SITE + p, body, depth))

    # コーデのページ
    os.makedirs(os.path.join(ROOT, "coord"), exist_ok=True)
    coord_html = page_shell(index_html, "予算でコーデを作る（1万円コーデなど）｜ネサゲ",
                            "予算とメンズ・レディースをえらぶと、セレクトショップや人気ブランドの値下げ商品からコーデを作ります。毎朝AIが選ぶ今日のコーデも。",
                            SITE + "coord/", COORD_BODY + links_html(1), 1).replace("</head>", COORD_CSS + "\n</head>", 1)
    open(os.path.join(ROOT, "coord", "index.html"), "w", encoding="utf8").write(coord_html)

    # ネサゲについて／プライバシーポリシー
    n_items, n_brands = len(items), len({x["shop"] for x in items})
    about = f"""<nav class="crumb" aria-label="現在地"><a href="../">ネサゲ</a> › <span>ネサゲについて</span></nav>
<article class="doc"><h1>ネサゲについて</h1>
<p>ネサゲは、セレクトショップや人気ブランドの服で、いま値下げ中のものを毎朝まとめて紹介しているサイトです。いまは{n_brands}ブランド・約{n_items:,}件の商品を載せています。</p>
<h2>商品の集め方</h2>
<ul><li>毎朝6時ごろ、楽天市場の商品データ（楽天ウェブサービス）から、商品名に「○%OFF」と書かれている値下げ中の服を自動で集めています。</li>
<li>「人気ブランド」と「プチプラ」は、楽天ファッションや、ブランドの公式ショップなど、楽天市場の中で信頼できるお店が売っている商品だけにしています。</li>
<li>値段・在庫・割引は、集めた時点のものです。いまの値段は、かならず楽天市場のお店のページで確かめてください。</li></ul>
<h2>お買い物について</h2>
<ul><li>ネサゲでは商品を売っていません。「楽天で見る」を押すと楽天市場のお店のページが開き、お買い物はそのお店とのやりとりになります。</li>
<li>ネサゲが、お名前・住所・カード番号などを聞くことはありません。</li></ul>
<h2>広告（PR）について</h2>
<p>ネサゲは楽天アフィリエイトを利用しています。ネサゲのリンクから楽天市場でお買い物があると、ネサゲに紹介料が入ることがあります。商品の値段が高くなることはありません。</p>
<h2>運営</h2>
<p>ネサゲは個人で運営しているサイトです。ショップ名・ブランド名は各社のもので、ネサゲは各ショップやブランドの公式サイトではありません。</p>
</article>"""
    privacy = """<nav class="crumb" aria-label="現在地"><a href="../">ネサゲ</a> › <span>プライバシーポリシー</span></nav>
<article class="doc"><h1>プライバシーポリシー</h1>
<h2>集める情報</h2>
<p>ネサゲは、会員登録やお問い合わせフォームを使っておらず、お名前・メールアドレス・住所などの個人情報を集めていません。</p>
<h2>この端末の中だけに残る情報</h2>
<p>お気に入りのお店、保存した商品、えらんだ条件（割引・サイズなど）は、ご利用のブラウザの中（ローカルストレージ）だけに記録しています。ネサゲのサーバーには送られず、ブラウザの設定から消すことができます。</p>
<h2>アフィリエイトについて</h2>
<p>ネサゲは楽天アフィリエイトを利用しています。「楽天で見る」から楽天市場のページに移ると、紹介料の計算のため、楽天がクッキーなどを使うことがあります。くわしくは楽天グループのプライバシーポリシーをご覧ください。</p>
<h2>アクセスの記録</h2>
<p>ネサゲは GitHub Pages で公開しています。ページを表示するとき、GitHub がアクセスの記録（IPアドレスなど）を残すことがあります。くわしくは GitHub のプライバシーに関する説明をご覧ください。</p>
<h2>変更</h2>
<p>このポリシーは、必要に応じて変えることがあります。変えたときは、このページでお知らせします。</p>
</article>"""
    DOC_CSS = "<style>.doc{max-width:70ch;padding-block:8px 32px}.doc h1{font-size:22px;margin:10px 0 12px}.doc h2{font-size:16px;margin:22px 0 6px}.doc p,.doc li{font-size:14.5px;line-height:1.8}.doc ul{padding-left:1.2em;margin:0}</style>"
    for slug_, title_, desc_, body_ in (("about", "ネサゲについて｜ネサゲ", "ネサゲの商品の集め方、お買い物の流れ、広告（PR）、運営について。", about),
                                       ("privacy", "プライバシーポリシー｜ネサゲ", "ネサゲのプライバシーポリシー。個人情報は集めていません。", privacy)):
        os.makedirs(os.path.join(ROOT, slug_), exist_ok=True)
        open(os.path.join(ROOT, slug_, "index.html"), "w", encoding="utf8").write(
            page_shell(index_html, title_, desc_, SITE + slug_ + "/", body_, 1).replace("</head>", DOC_CSS + "\n</head>", 1))

    # トップページにリンクを入れる
    block = "<!--LINKS-->" + links_html(0) + "<!--/LINKS-->"
    if "<!--LINKS-->" in index_html:
        index_html = re.sub(r"<!--LINKS-->[\s\S]*?<!--/LINKS-->", lambda m: block, index_html)
    else:
        index_html = index_html.replace("</main>", block + "\n</main>", 1)
    open(index_path, "w", encoding="utf8").write(index_html)

    # サイトマップ
    today = upd.date().isoformat()
    urls = ["", "coord/", "about/", "privacy/"] + [p for p, *_ in pages]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"<url><loc>{esc(SITE + u)}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>\n" for u in urls) + "</urlset>\n"
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf8").write(sm)
    print(f"pages={len(pages)} brands={len(brand_pages)} cats={len(cat_pages)} typed={sum(1 for x in items if x['t'])}/{len(items)}")


if __name__ == "__main__":
    main()
