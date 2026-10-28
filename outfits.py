"""今日のAIコーデ（outfits.json）を作る。

毎朝の商品更新（GitHub Actions）のあとに動く。
「メンズ・1万円」「メンズ・2万円」「レディース・1万円」「レディース・2万円」の4つ。
組み合わせ方は、コーデのページ（build.py の COORD_BODY）と同じルール：
- トップス＋ボトムス（レディースはワンピースのことも）を土台に、季節に合えばアウター、余ればバッグ・小物
- 合計は予算以下、同じ商品は2つのコーデで使わない、季節外れの商品は使わない
- 色は商品名に書いてある色から1つずつえらぶ（基本の色＋差し色は1色まで、トップスとボトムスは同じ色にしない）
日付で乱数を決めるので、同じ日に何回動かしても同じ結果になる。
"""
import datetime
import json
import random
import re
import sys

COLS = ['オフホワイト', 'アイボリー', 'エクリュ', 'ホワイト', 'ライトグレー', 'チャコール', 'グレー', 'ブラック', 'ネイビー',
        'ベージュ', 'キャメル', 'ダークブラウン', 'ブラウン', 'モカ', 'カーキ', 'オリーブ', 'ボルドー', 'ワイン', 'レッド',
        'ピンク', 'オレンジ', 'イエロー', 'グリーン', 'ミント', 'サックス', 'ブルー', 'ラベンダー', 'パープル', 'シルバー', 'ゴールド']
CNAMES = sorted(COLS, key=len, reverse=True)
NEUTRAL = {'オフホワイト', 'アイボリー', 'エクリュ', 'ホワイト', 'ライトグレー', 'チャコール', 'グレー', 'ブラック', 'ネイビー',
           'ベージュ', 'キャメル', 'ダークブラウン', 'ブラウン', 'モカ', 'カーキ', 'オリーブ'}
DARK = {'ブラック', 'チャコール', 'ネイビー', 'ダークブラウン', 'ブラウン', 'モカ', 'カーキ', 'オリーブ', 'グレー'}
LIGHT = {'オフホワイト', 'アイボリー', 'エクリュ', 'ホワイト', 'ライトグレー', 'ベージュ', 'キャメル'}
LABEL = {'tops': 'トップス', 'bottoms': 'ボトムス', 'outer': 'アウター', 'dress': 'ワンピース', 'bag': 'バッグ', 'shoes': 'シューズ', 'acc': '小物'}
STYLE_WORD = [('kirei', 'きれいめ'), ('trad', 'トラッド'), ('amekaji', 'アメカジ'), ('street', 'ストリート'),
              ('outdoor', 'アウトドア'), ('sporty', 'スポーティ'), ('mode', 'モード'), ('natural', 'ナチュラル'),
              ('feminine', 'フェミニン'), ('casual', 'カジュアル')]


def colors_of(name):
    n, out = str(name or ''), []
    for c in CNAMES:
        if c in n:
            out.append(c)
            n = n.replace(c, ' ')
    return out


def off_season(month):
    if month >= 10 or month <= 3:
        return re.compile(r'半袖|ショーツ|ショートパンツ|ハーフパンツ|タンク|ノースリーブ|サンダル|キャミ|リネン')
    if 6 <= month <= 8:
        return re.compile(r'ダウン|ウール|ボア|フリース|中わた|コート|ニット')
    return None


def assign(rng, items):
    """各商品に1色ずつ。差し色は1色まで、トップスとボトムスは同じ色にしない。"""
    opts = []
    for x in items:
        o = colors_of(x['name'])
        rng.shuffle(o)
        if not o:
            return None
        opts.append(o[:6])
    best = []

    def rec(i, acc):
        if best:
            return
        if i == len(items):
            if len([c for c in acc if c not in NEUTRAL]) > 1:
                return
            tb = [acc[k] for k, x in enumerate(items) if x['t'] in ('tops', 'bottoms')]
            if len(tb) == 2 and tb[0] == tb[1]:
                return
            best.append(list(acc))
            return
        for c in opts[i]:
            acc.append(c)
            rec(i + 1, acc)
            acc.pop()
            if best:
                return
    rec(0, [])
    return best[0] if best else None


def make(rng, items, g, budget, used, month):
    bad = off_season(month)
    pool = [x for x in items if x.get('t') and x.get('g') in (g, 'both') and x.get('price', 0) > 0
            and x['id'] not in used and not (bad and bad.search(x['name']))]
    by = {t: [x for x in pool if x['t'] == t] for t in LABEL}
    tops, bots, outs, dres = by['tops'], by['bottoms'], by['outer'], by['dress']
    cold = month >= 10 or month <= 3
    best = None
    for _ in range(3000):
        if g == 'women' and dres and rng.random() < .3:
            s = [rng.choice(dres)]
        else:
            if not tops or not bots:
                break
            s = [rng.choice(tops), rng.choice(bots)]
        total = sum(x['price'] for x in s)
        if total > budget or not assign(rng, s):
            continue

        def fit(L, p):
            nonlocal total
            if rng.random() > p:
                return
            c = [x for x in L if x['id'] not in {y['id'] for y in s} and x['price'] <= budget - total]
            rng.shuffle(c)
            for x in c[:12]:
                if assign(rng, s + [x]):
                    s.append(x)
                    total += x['price']
                    return
        if budget - total >= 2500:
            fit(outs, .95 if cold else .5)
        # バッグ・小物は、そのコーデの性別向けのものだけ（メンズにレディースのバッグを入れない）
        if budget - total >= 1500:
            fit([x for x in by['bag'] if x['g'] == g], .4)
        if budget - total >= 800:
            fit([x for x in by['acc'] if x['g'] == g], .4)
        cols = assign(rng, s)
        if not cols:
            continue
        score = sum(x.get('was') or x['price'] for x in s) * (0.9 + rng.random() * .2)
        # 落ち着いた色だけのコーデを少し優先、寒い時期はアウターがあるほうを優先
        if any(c not in NEUTRAL for c in cols):
            score *= .75
        if cold and any(x['t'] == 'outer' for x in s):
            score *= 1.3
        if not best or score > best[0]:
            best = (score, list(s), cols, total)
    return best


def style_word(s):
    cnt = {}
    for x in s:
        for k in x.get('st') or []:
            cnt[k] = cnt.get(k, 0) + 1
    for k, w in STYLE_WORD:
        if cnt.get(k, 0) >= max(1, len(s) // 2):
            return w
    return 'デイリー'


def tone_word(cols):
    if all(c in {'ブラック', 'ホワイト', 'オフホワイト', 'グレー', 'ライトグレー', 'チャコール', 'シルバー'} for c in cols):
        return 'モノトーン'
    if any(c not in NEUTRAL for c in cols):
        return '差し色'
    if 'ネイビー' in cols:
        return 'ネイビー'
    if any(c in {'ベージュ', 'ブラウン', 'ダークブラウン', 'キャメル', 'モカ', 'カーキ', 'オリーブ'} for c in cols):
        return 'アースカラー'
    return 'ベーシック'


def comment(s, cols):
    parts = [f'{LABEL[x["t"]]}は{c}' for x, c in zip(s, cols)]
    first = '、'.join(parts[:3]) + ('など' if len(parts) > 3 else '') + 'で合わせました。'
    accent = [c for c in cols if c not in NEUTRAL]
    if accent:
        second = f'{accent[0]}を1か所だけ入れて、ほかは落ち着いた色でまとめています。'
    elif any(c in DARK for c in cols) and any(c in LIGHT for c in cols):
        second = '明るい色と濃い色を組み合わせて、メリハリが出るようにしています。'
    else:
        second = '色数をおさえて、すっきり見えるようにしています。'
    return first + second


def main(feed_path='feed.json', out_path='outfits.json'):
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    rng = random.Random(now.strftime('%Y%m%d'))
    items = json.load(open(feed_path, encoding='utf8'))['items']
    used, outfits = set(), []
    for g, gl in (('men', 'メンズ'), ('women', 'レディース')):
        for budget in (10000, 20000):
            r = make(rng, items, g, budget, used, now.month)
            if not r:
                continue
            _, s, cols, total = r
            used.update(x['id'] for x in s)
            outfits.append({
                'title': f'{gl}・{budget // 10000}万円で{tone_word(cols)}の{style_word(s)}コーデ',
                'g': g, 'budget': budget,
                'items': [{'id': x['id'], 'color': c} for x, c in zip(s, cols)],
                'comment': comment(s, cols),
            })
    # 確認：id があること、色が商品名にあること、予算以下
    byid = {x['id']: x for x in items}
    for o in outfits:
        assert all(i['id'] in byid and i['color'] in byid[i['id']]['name'] for i in o['items'])
        assert sum(byid[i['id']]['price'] for i in o['items']) <= o['budget']
    if len(outfits) < 2:
        print('コーデが作れなかったので、前のままにします', file=sys.stderr)
        return
    json.dump({'updated': now.isoformat(timespec='seconds'), 'outfits': outfits},
              open(out_path, 'w', encoding='utf8'), ensure_ascii=False, indent=1)
    for o in outfits:
        print(o['title'], sum(byid[i['id']]['price'] for i in o['items']), len(o['items']))


if __name__ == '__main__':
    main(*sys.argv[1:])
