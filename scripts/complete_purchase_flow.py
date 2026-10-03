"""Final generated purchase tools backed only by the current verified catalog."""
import html
import json
import re
from pathlib import Path
from comparison_units import comparison_unit, quantity_label, LABELS
from price_observations import previous, update, identity, stats
from product_display import clean_display_name

SITE = Path('site')

def esc(x): return html.escape(str(x), quote=True)
def money(x): return f'¥{x:,.2f}'

STYLE = '''<style id="comparison-tools-style">
.comparison-table-wrap{overflow-x:auto;margin:12px 0;max-width:100%}.comparison-table{width:100%;border-collapse:collapse;font-size:14px;min-width:340px}.comparison-table th,.comparison-table td{padding:12px 8px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}.comparison-table td:first-child{max-width:220px;overflow-wrap:anywhere}.comparison-table th{background:#fff5ed}.comparison-table strong{white-space:nowrap;color:#9d281f}.comparison-table caption{text-align:left;font-weight:700;padding:10px 0}.product-tools{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.product-tools button,.comparison-tools button{min-height:44px;padding:10px 12px;border:1px solid #b9b0a8;border-radius:9px;background:#fff;color:#342f2c;font:inherit;cursor:pointer}.product-tools button[aria-pressed="true"]{background:#fff0d9;border-color:#9d281f}.comparison-tools{margin:14px 0;padding:16px;background:#fffaf6;border:1px solid #dfcdbf;border-radius:14px}.comparison-tools h2{margin-top:0;font-size:20px}.comparison-tools a{display:inline-block;padding:12px;min-height:44px}.comparison-tools li{padding:12px 0;border-bottom:1px solid #ddd;overflow-wrap:anywhere}.comparison-tools [hidden]{display:none}.comparison-tools button:focus-visible,.product-tools button:focus-visible{outline:3px solid #22663a;outline-offset:2px}.history-fact{font-size:13px;line-height:1.6;color:#444}.comparison-panel-actions{display:flex;flex-wrap:wrap;gap:8px}.product-name-short{font-size:14px;line-height:1.5}
</style>'''


def normalized_table(cid, category):
    if cid not in ('tissue','toilet-paper'): return ''
    groups = {}
    unknown = 0
    for rank, item in enumerate(category['items'], 1):
        unit = comparison_unit(cid, item)
        if not unit:
            unknown += 1; continue
        groups.setdefault(unit[0], []).append((unit[1], rank, item))
    parts = []
    for label, rows in groups.items():
        body = ''.join(f'<tr><td><a href="#{cid}-rank-{rank}">{esc(clean_display_name(item["name"]))}</a></td><td><strong>{money(value)}</strong><br>／{esc(label)}</td><td>{esc(quantity_label(item))}<br>{money(item["price"])}<br>送料込み</td></tr>' for value,rank,item in sorted(rows,key=lambda r:r[0]))
        parts.append(f'<div class="comparison-table-wrap" tabindex="0" role="region" aria-label="{esc(label)}単価の比較"><table class="comparison-table"><caption>{esc(label)}あたりの安い順（{len(rows)}商品）</caption><thead><tr><th scope="col">商品</th><th scope="col">条件をそろえた単価</th><th scope="col">数量・支払総額</th></tr></thead><tbody>{body}</tbody></table></div>')
    missing = f'<p>組数・長さ・重ね数を確定できない{unknown}商品は、この表から除外しています。</p>' if unknown else ''
    return '<section class="comparison-tools" id="normalized-comparison"><h2>容量の違いまでそろえて比較</h2><p>箱単価・ロール単価とは順位が変わる場合があります。シングルとダブルは別々に比較します。</p>' + ''.join(parts) + missing + '</section>' if parts else ''


def main():
    payload = json.loads((SITE/'data.json').read_text())
    history = json.loads((SITE/'price-observations.json').read_text())
    catalog = []
    for cid, category in payload['categories'].items():
        for rank, item in enumerate(category['items'], 1):
            unit = comparison_unit(cid, item)
            catalog.append({'key':identity(cid,item),'category':cid,'category_name':category['name'],'rank':rank,
                'name':clean_display_name(item['name']),'url':item['url'],'price':item['price'],
                'quantity':quantity_label(item),'unit':list(unit) if unit else None,
                'base_unit':[LABELS.get(item['metric'],item['metric']),item['unit_price']],
                'history':stats(cid,item,history),'updated_at':payload['updated_at']})
    assets = SITE/'assets'; assets.mkdir(exist_ok=True)
    (assets/'comparison-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
    (assets/'purchase-tools.js').write_text(Path('scripts/purchase_tools.js').read_text(),encoding='utf-8')
    for path in [SITE/'index.html', SITE/'today/index.html', *SITE.glob('categories/*/index.html')]:
        markup = path.read_text()
        if path.parent.parent.name == 'categories':
            cid = path.parent.name
            if cid in ('tissue','toilet-paper'):
                label = '箱単価順（組数は未統一）' if cid == 'tissue' else 'ロール単価順（長さは未統一）'
                markup = markup.replace('今日の安い順ランキング',label)
            table = normalized_table(cid,payload['categories'][cid])
            # Search visitors see the real normalized result before explanation.
            if table:
                markup = markup.replace('<section class="category-seo-guide"', table+'<section class="category-seo-guide"',1)
                # Move the long method explanation below the product list.
            guide = re.search(r'<section class="category-seo-guide".*?</section>',markup,re.S)
            if guide:
                markup = markup.replace(guide.group(),'',1).replace('<section class="category-seo-faq"',guide.group()+'<section class="category-seo-faq"',1)
        toolbar = '<section class="comparison-tools" id="purchase-tools"><h2>保存して、あとで比べる</h2><p>商品カードの「比較する」で同じ単位の候補を比較できます。保存はこのブラウザ内に残ります。</p><div class="comparison-panel-actions"><button type="button" id="show-saved">保存した商品を見る</button><button type="button" id="show-comparison">比較を見る</button></div><p id="purchase-tool-status" role="status" aria-live="polite"></p><div id="purchase-tool-panel" hidden></div><noscript><p>保存・選択比較にはJavaScriptが必要です。価格と単価の一覧はそのまま確認できます。</p></noscript></section>'
        if 'buying-answer' in markup:
            markup = re.sub(r'(<section class="purchase-answer" id="buying-answer">.*?</section>)', lambda m:m.group()+toolbar,markup,count=1,flags=re.S)
        else:
            markup = re.sub(r'(<main\b[^>]*>)',lambda m:m.group()+toolbar,markup,count=1)
        markup = markup.replace('</head>',STYLE+'</head>',1).replace('</body>','<script src="/daily-cost-jp/assets/purchase-tools.js" defer></script></body>',1)
        path.write_text(markup,encoding='utf-8')
    (SITE/'404.html').write_text('<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ページが見つかりません | 日用品コスパ比較</title><meta name="description" content="指定されたページは見つかりません。日用品のカテゴリ一覧から価格比較を続けられます。"><meta name="robots" content="noindex,follow"></head><body><main><h1>ページが見つかりません</h1><p><a href="/daily-cost-jp/">日用品コスパ比較へ</a></p><p><a href="/daily-cost-jp/categories/">カテゴリから探す</a></p></main></body></html>',encoding='utf-8')
    print('Generated normalized comparison tables, observed histories and saved/comparison tools.')

if __name__ == '__main__': main()
