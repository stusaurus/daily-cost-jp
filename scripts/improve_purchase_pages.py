"""Focused buying guidance, honest CTAs and final technical SEO safeguards."""
from __future__ import annotations

import html
import json
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

from sale_quantity import ambiguous_quantity, normalize, purchase_summary
from product_quality import filter_items

SITE = Path('site')
BASE = 'https://stusaurus.github.io/daily-cost-jp/'
PRIORITY = {
    'laundry': ('洗濯洗剤', 'laundry-detergent-cost-per-use'),
    'toilet-paper': ('トイレットペーパー', 'toilet-paper-price-per-meter'),
    'tissue': ('ティッシュ', 'tissue-price-per-box'),
}

STYLE = '''<style id="purchase-ux">
.product-card{grid-template-columns:92px minmax(0,1fr)}
.product-body,.card>div,.home-rank-name{min-width:0;overflow-wrap:anywhere}
.grid>.card{grid-template-columns:88px minmax(0,1fr)}
.buy-button,.product-result-link,.exact-rakuten,.actions a{min-height:44px;font-size:14px;line-height:1.5}
.purchase-note{font-size:12px;line-height:1.6;color:#626262;margin:6px 0 0}
.purchase-answer{padding:16px;border:1px solid #dfcdbf;border-radius:14px;background:#fffaf6;margin:14px 0}
.purchase-answer h2{font-size:20px;line-height:1.4;margin:0 0 8px}
.purchase-answer p,.purchase-answer li{font-size:14px;line-height:1.8;margin:8px 0}
.purchase-answer strong{color:#9d281f}.purchase-answer .answer-price{font-size:21px}
.purchase-links{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.purchase-links a{padding:10px 12px;min-height:44px;border:1px solid #d8d1cb;border-radius:10px;text-decoration:none;background:#fff;font-size:14px;font-weight:700}
.category-seo-guide p,.category-seo-guide li,.category-seo-faq p,.category-seo-faq summary{font-size:14px}
@media(min-width:760px){.product-card{grid-template-columns:110px minmax(0,1fr)}}
@media(max-width:380px){.product-card{grid-template-columns:72px minmax(0,1fr);gap:10px;padding:12px}.product-image{width:72px;height:72px}.grid>.card{grid-template-columns:68px minmax(0,1fr);gap:10px}.card .img,.card .pic{width:68px;height:68px}}
</style>'''


def esc(value):
    return html.escape(str(value), quote=True)


def money(value):
    return f'¥{value:,.2f}'.rstrip('0').rstrip('.')


def unit_details(category_id, item):
    """Supplemental, comparable unit from explicit title evidence only."""
    name = normalize(item.get('name', ''))
    if ambiguous_quantity(name):
        return None
    price = float(item.get('unit_price') or 0)
    if price <= 0:
        return None
    if category_id == 'tissue' and item.get('metric') == 'box':
        groups = set(re.findall(r'(\d+)\s*組', name))
        if len(groups) == 1 and int(next(iter(groups))) > 0:
            return '100組', price / int(next(iter(groups))) * 100
    if category_id == 'toilet-paper' and item.get('metric') == 'roll':
        lengths = set(re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*m(?![a-z])', name, re.I))
        types = [t for t in ('シングル', 'ダブル') if t in name]
        if len(lengths) == 1 and len(types) == 1 and float(next(iter(lengths))) > 0:
            return types[0] + '10m', price / float(next(iter(lengths))) * 10
    return None


def price_answer(category_id, data):
    name, guide = PRIORITY[category_id]
    items = filter_items(category_id, data.get('items', []))
    metric = {'100g': '100g', '100ml': '100ml', 'roll': '1ロール', 'box': '1箱', 'pack': '1パック'}.get(data.get('metric'), '同じ単位')
    if items:
        prices = [float(p['unit_price']) for p in items]
        overview = f'<p class="answer-price"><strong>{metric}あたり {money(min(prices))}〜</strong>（送料込み）</p><p>今回取得した{len(items)}商品の参考値です。中央値は{money(statistics.median(prices))}／{metric}。市場全体の最安値・相場を示すものではありません。</p>'
    else:
        overview = '<p>現在、数量を確定して比較できる候補が不足しています。商品検索で最新の販売条件を確認してください。</p>'
    supplemental = {}
    for item in items:
        detail = unit_details(category_id, item)
        if detail:
            label, value = detail
            supplemental[label] = min(value, supplemental.get(label, float('inf')))
    if supplemental:
        overview += '<p><strong>条件をそろえた目安：</strong>' + ' ／ '.join(f'{esc(k)}あたり {money(v)}〜' for k, v in supplemental.items()) + '。商品名から条件を確認できた候補だけで計算しています。</p>'
    answers = {
        'laundry': ('洗濯洗剤はどこが安い？今日の比較価格', '同じ銘柄・タイプなら、店頭の税込価格を容量で割り、下の楽天送料込み単価と比べると買い先を選べます。濃縮度が違う洗剤同士は100g単価だけで決めず、1回使用量もそろえてください。'),
        'toilet-paper': ('トイレットペーパーはいくらなら安い？', '1ロールの長さが違うと、ロール単価の安さが逆転します。シングル同士・ダブル同士で「支払総額 ÷ 総メートル数」を比較してください。下のランキングは1ロール単価順で、長さは統一していません。'),
        'tissue': ('ティッシュはどこが安い？今日の値段比較', '同じ組数なら1箱単価で比較できます。200組と250組など組数が違う場合は「支払総額 ÷ 箱数 ÷ 1箱の組数 × 100」で100組単価を比較してください。400枚（200組）は200組として計算します。'),
    }
    heading, answer = answers[category_id]
    extra = '<a data-conversion-source="product_guide" href="../../guides/attack-zero-price/">アタックZEROはどこが安い？</a>' if category_id == 'laundry' else ''
    return f'''<section class="purchase-answer" id="buying-answer"><h2>{heading}</h2>{overview}<p>{answer}</p>
<p><strong>どこで買う？</strong>店頭価格は自動収集していません。楽天候補と店頭の税込・送料込み総額を同じ内容量で比べ、必要な数量だけ買える方を選びましょう。</p>
<div class="purchase-links"><a href="#{category_id}">今日の商品・支払総額を見る ↓</a><a data-conversion-source="price_guide" href="../../guides/{guide}/">同じ単位で計算する</a>{extra}</div></section>'''


def enhance_priority(payload):
    for category_id, (name, guide) in PRIORITY.items():
        path = SITE / 'categories' / category_id / 'index.html'
        if not path.exists():
            continue
        markup = path.read_text(encoding='utf-8')
        # Replace the former 90%-of-mixed-median buy claim with qualified facts.
        markup = re.sub(r'<section class="buy-line-box">.*?</section>', '', markup, flags=re.S)
        markup = re.sub(r'<section class="purchase-answer" id="buying-answer">.*?</section>', '', markup, flags=re.S)
        markup = markup.replace('<main class="container">', '<main class="container">' + price_answer(category_id, payload.get('categories', {}).get(category_id, {})), 1)
        if category_id == 'laundry':
            q, a = 'アタックZEROはどこが安いですか？', '通常用・ドラム式用などタイプと容量、販売個数をそろえ、送料込み支払額を比較してください。複数個から選ぶ商品ページの最低価格を、大容量セットの価格として比較しないことが大切です。'
        elif category_id == 'toilet-paper':
            q, a = '1ロールが安ければお得ですか？', '長さの違うロールは、そのままでは比較できません。シングルとダブルを分けて、総メートル数あたりの価格を確認してください。'
        else:
            q, a = '200組と250組はどう値段比較しますか？', '送料込み総額を箱数と1箱の組数で割ると1組単価になります。1箱単価だけでなく100組あたりで比較すると、組数が違う商品も判断できます。'
        marker = f'<details data-purchase-faq><summary>{q}</summary><p>{a}</p></details>'
        if 'data-purchase-faq' not in markup:
            markup = markup.replace('<section class="category-seo-faq" id="category-faq">', '<section class="category-seo-faq" id="category-faq">' + marker, 1)
        demand_faq = {
            'laundry': ('安い店ランキングとして使えますか？', '掲載商品を送料込み単価順に比較する一覧です。店舗全体の安さを順位付けしたものではありません。同じタイプ・容量・販売個数の商品を選び、商品カードのショップ名と支払総額を確認してください。'),
            'tissue': ('ティッシュはどこで買うのが安いですか？', '同じ組数・箱数なら、店頭の税込価格と掲載商品の送料込み総額を比較できます。通販のまとめ買いは1箱単価が低くても支払総額が大きくなるため、保管場所と使う量も確認してください。'),
            'toilet-paper': ('トイレットペーパーの最安値を探す注意点は？', 'シングルとダブル、通常巻きと長巻きを分けて比べます。この一覧では用途や販売数量が曖昧な候補を除外していますが、全店舗を網羅した最安値ではありません。最新価格と配送先の送料を楽天で確認してください。'),
        }
        dq, da = demand_faq[category_id]
        if 'data-demand-faq' not in markup:
            markup = markup.replace('<section class="category-seo-faq" id="category-faq">', '<section class="category-seo-faq" id="category-faq"><details data-demand-faq><summary>' + dq + '</summary><p>' + da + '</p></details>', 1)
        path.write_text(markup, encoding='utf-8')


def build_attack_guide(payload):
    from add_search_landing_pages import STYLE as GUIDE_STYLE
    path = SITE / 'guides/attack-zero-price/index.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    title = 'アタックZEROはどこが安い？詰め替えの単価・送料込み価格比較'
    desc = 'アタックゼロの通常用・ドラム式用、容量・個数の違いをそろえて価格比較。100g単価の計算と楽天の最新価格検索で、店頭とどちらで買うか判断できます。'
    rows = []
    for p in filter_items('laundry', payload.get('categories', {}).get('laundry', {}).get('items', [])):
        key = normalize(p.get('name', '')).lower().replace(' ', '')
        if ('アタックzero' in key or 'アタックゼロ' in key) and p.get('metric') == '100g' and not ambiguous_quantity(p['name']) and p.get('sale_quantity_label'):
            rows.append(p)
    cards = ''.join(f'<article class="card"><h3>{esc(p["name"])}</h3><p><strong>{money(p["unit_price"])}／100g</strong><br>{esc(purchase_summary(p))}<br>{esc(p.get("shop", ""))}</p><a class="cta primary" data-conversion-source="product_guide" href="{esc(p["url"])}" target="_blank" rel="nofollow sponsored noopener">楽天でこの商品の最新価格を見る</a><p class="purchase-note">価格・在庫・地域別送料は購入前に確認してください。</p></article>' for p in rows)
    if not cards:
        cards = '<p>今回のカテゴリ取得分には、タイプ・販売個数を確定できるアタックZEROの掲載候補がありません。推測の単価は掲載せず、下の商品検索から容量を指定して確認できます。</p>'
    schema = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'Article', 'headline': title, 'description': desc, 'url': BASE + 'guides/attack-zero-price/'},
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type':'ListItem','position':1,'name':'日用品コスパ比較','item':BASE},
            {'@type':'ListItem','position':2,'name':'洗濯洗剤','item':BASE+'categories/laundry/'},
            {'@type':'ListItem','position':3,'name':'アタックZEROの価格比較','item':BASE+'guides/attack-zero-price/'}]}]}
    inputs = ''.join(f'''<fieldset><legend>候補{label}</legend><label>送料込み支払総額（円）<input id="price{i}" type="number" min="0" inputmode="decimal" placeholder="例：3000"></label><label>1袋の容量（g）<input id="grams{i}" type="number" min="0" inputmode="decimal" placeholder="例：2100"></label><label>販売袋数<input id="packs{i}" type="number" min="1" step="1" inputmode="numeric" value="1"></label></fieldset>''' for i,label in [(1,'A：店頭など'),(2,'B：楽天など')])
    markup = f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} | 日用品コスパ比較</title><meta name="description" content="{desc}"><link rel="canonical" href="{BASE}guides/attack-zero-price/"><style>{GUIDE_STYLE}
.offer-calc{{display:grid;gap:14px}}fieldset{{min-width:0;border:1px solid #ddd;border-radius:12px;padding:12px}}label{{display:block;margin:8px 0}}input{{display:block;width:100%;font:inherit;min-height:44px;padding:8px}}.small{{font-size:13px;color:#626262}}@media(min-width:600px){{.offer-calc{{grid-template-columns:1fr 1fr}}}}</style><script type="application/ld+json">{json.dumps(schema,ensure_ascii=False)}</script></head><body><main class="wrap">
<a class="back" href="../../categories/laundry/">← 洗濯洗剤の単価比較</a>
<section class="hero"><div class="eyebrow">商品名から買い先を決める</div><h1>アタックZEROはどこが安い？</h1><p>同じタイプ・容量で、店頭の税込価格と楽天の送料込み総額を比べるのが確実です。まとめ買いは1袋の価格ではなく、<strong>100gあたりの単価と実際に払う総額</strong>を確認しましょう。</p><a class="cta primary" data-conversion-source="product_guide" href="../../products/?q=アタックZERO">アタックZEROの楽天価格を検索 →</a><p class="small">このサイト内で楽天の候補を検索します。実店舗の価格や全ショップの最安値は網羅していません。</p></section>
<section class="card"><h2>まずタイプ・容量・販売個数をそろえる</h2><ul><li>「通常用」「ドラム式専用」「部屋干し」など、ラベル上のタイプを確認。</li><li>本体と詰め替え、1袋と複数袋セットを分ける。</li><li>「1〜4個から選べる」の最低表示価格を4個セットの価格とみなさない。</li><li>送料・配送先・クーポン適用条件を確認。保有ポイントは商品価格から引かずに比べる。</li></ul></section>
<section class="card"><h2>2つの候補を100g単価で比較</h2><p>同じタイプ同士で入力してください。楽天側は購入する個数を選んだ後の送料込み総額を使います。</p><div class="formula">支払総額 ÷（1袋の容量 × 袋数）× 100</div><div class="offer-calc">{inputs}</div><p id="offer-comparison" class="result" aria-live="polite">2つの価格・容量を入力してください</p><p class="small">計算例：2100g×1袋が3000円なら約142.86円／100g、1400g×1袋が2100円なら150円／100g。前者は単価が低く、後者は一度の支払いが少なくなります。この数値は計算例で、現在の販売価格ではありません。</p></section>
<section class="card"><h2>今日のカテゴリデータで比較できる候補</h2><p class="small">データ取得：{esc(payload.get('updated_at', '取得日時はカテゴリページ参照'))}</p>{cards}<a class="cta primary" data-conversion-source="product_guide" href="../../products/?q=アタックZERO%202100g">2100gの楽天価格を検索 →</a><a class="cta secondary" data-conversion-source="product_guide" href="../../products/?q=アタックZERO%20ドラム式">ドラム式用の楽天価格を検索 →</a></section>
<section class="card"><h2>いくらなら買い？</h2><p>同じタイプの送料込み候補より単価が低く、使い切れる量なら購入候補です。大容量の単価が低くても、収納場所や当月の支払総額に合わなければ少量を選ぶ判断もできます。洗剤全体の100g最安値は、濃縮度が違うアタックZEROの買い目安にはそのまま使えません。</p><a class="cta secondary" href="../laundry-detergent-cost-per-use/">1回使用量までそろえて比較する</a><a class="cta secondary" href="../../categories/laundry/">他の洗濯洗剤の送料込み価格を見る</a></section>
<section class="card"><h2>よくある質問</h2><details><summary>楽天が必ず最安値ですか？</summary><p>いいえ。店頭価格や会員限定クーポンをすべて取得していないため、最安の店は断定できません。自分の購入条件で総額と単価を比べてください。</p></details><details><summary>旧パッケージでも比較できますか？</summary><p>同じブランド名でも容量や仕様が変わることがあります。商品名だけでなく、容量・用途・JANコードなどを確認してください。</p></details></section>
<p class="small">当サイトは楽天アフィリエイトを利用しています。価格・在庫・送料条件は変動します。</p></main>
<script>(()=>{{const ids=['price1','grams1','packs1','price2','grams2','packs2'];const fields=ids.map(id=>document.getElementById(id));function calc(){{const v=fields.map(x=>Number(x.value));const out=document.getElementById('offer-comparison');if(v.some(x=>!Number.isFinite(x)||x<=0)||!Number.isInteger(v[2])||!Number.isInteger(v[5])){{out.textContent='2つの価格・容量と整数の袋数を入力してください';return;}}const a=v[0]/(v[1]*v[2])*100,b=v[3]/(v[4]*v[5])*100;out.textContent='A：'+a.toFixed(2)+'円／100g ・ B：'+b.toFixed(2)+'円／100g。'+(Math.abs(a-b)<0.005?'単価は同じです。':(a<b?'A':'B')+'の単価が約'+Math.abs(a-b).toFixed(2)+'円低いです。');}}fields.forEach(x=>x.addEventListener('input',calc));}})();</script></body></html>'''
    path.write_text(markup, encoding='utf-8')


def finish_pages():
    urls = []
    for path in sorted(SITE.rglob('*.html')):
        markup = path.read_text(encoding='utf-8')
        markup = markup.replace('>楽天市場で確認する</a>', '>楽天で最新価格・送料を確認</a>')
        markup = markup.replace('>楽天市場で価格を見る</a>', '>楽天でこの商品の価格を見る</a>')
        if 'id="purchase-ux"' not in markup:
            markup = markup.replace('</head>', STYLE + '\n</head>', 1)
        markup = re.sub(r'(<a class="buy-button"[^>]*>.*?</a>)(?!<p class="purchase-note")', r'\1<p class="purchase-note">価格・在庫・地域別送料は楽天で最終確認</p>', markup)
        def image_size(match):
            tag = match.group(0)
            if not re.search(r'\bwidth=', tag): tag = tag[:-1] + ' width="128" height="128">'
            if 'decoding=' not in tag: tag = tag[:-1] + ' decoding="async">'
            return tag
        markup = re.sub(r'<img\b[^>]*>', image_size, markup)
        if path == SITE / 'index.html' and 'id="priority-categories"' not in markup:
            links = ''.join(f'<a href="categories/{key}/" data-conversion-source="category">{label}の値段比較</a>' for key,(label,_) in PRIORITY.items())
            block = f'<section id="priority-categories" aria-label="よく買う日用品を比較"><div class="purchase-links">{links}</div></section>'
            markup = markup.replace('<main class="container">', '<main class="container">' + block, 1)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', markup)
        if canonical and canonical.group(1).startswith(BASE): urls.append(canonical.group(1))
        path.write_text(markup, encoding='utf-8')
    # Includes the pre-existing calculator guides omitted by their builder.
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    tree = ET.Element(f'{{{ns}}}urlset')
    for url in sorted(set(urls)):
        ET.SubElement(ET.SubElement(tree, f'{{{ns}}}url'), f'{{{ns}}}loc').text = url
    ET.ElementTree(tree).write(SITE / 'sitemap.xml', encoding='utf-8', xml_declaration=True)


def main():
    payload = json.loads((SITE / 'data.json').read_text(encoding='utf-8'))
    enhance_priority(payload)
    build_attack_guide(payload)
    finish_pages()
    print('Improved three priority categories, one product guide, CTAs and sitemap.')


if __name__ == '__main__':
    main()
