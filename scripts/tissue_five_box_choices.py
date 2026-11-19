"""Offer exact 5-box tissue choices without conflating them with 60-box bulk rankings.

Uses only the existing strictly quality-gated STEP5 household candidate pool.
Never claim all-market cheapest, equivalence of different brands or a fake shop
price comparison. The previously rendered purpose card and bulk ranking remain.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from comparison_units import comparison_unit
from product_display import clean_display_name
from step4_recommendations import verified_purpose_candidates
from tissue_buying_quantity import safe_box_count

MARKER = '<!-- tissue-five-box-shop-choices-v1 -->'
ANCHOR = '<section class="purchase-answer lab-answer" id="buying-answer">'
CSS = """<style id="tissue-five-box-css">
.tissue-five-box{margin:14px 0 18px;padding:17px;border:1px solid #d9dfd9;border-radius:15px;background:#fafbf9}
.tissue-five-box h2{font-size:20px;line-height:1.5;margin:0 0 8px}
.tissue-five-box p{font-size:13px;line-height:1.75;margin:8px 0}
.tissue-five-box details{background:#fff;border:1px solid #dce3db;border-radius:11px;margin-top:12px}
.tissue-five-box summary{padding:14px;min-height:48px;cursor:pointer;font-size:14px;font-weight:750}
.tissue-five-box summary:focus-visible,.tissue-five-box a:focus-visible{outline:3px solid #196879;outline-offset:3px}
.tissue-five-box-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));list-style:none;gap:10px;padding:0 12px 12px;margin:0}
.tissue-five-box-item{min-width:0;padding:12px;border:1px solid #e6e8e2;border-radius:10px}
.tissue-five-box-item strong{display:block;font-size:17px;margin-bottom:5px}
.tissue-five-box-item .shop{display:block;font-weight:700;font-size:13px}
.tissue-five-box-item .spec{font-size:12px;color:#524d48}
.tissue-five-box-item a{display:block;min-height:44px;line-height:1.5;margin-top:8px;font-size:13px;font-weight:750;color:#135c41;text-underline-offset:2px;overflow-wrap:anywhere}
@media(max-width:600px){.tissue-five-box{padding:12px}.tissue-five-box-list{grid-template-columns:1fr;padding:0 10px 10px}}
</style>"""


def select_offers(category):
    """Re-check exact 5-box offers; excluded rows never yield merchant links."""
    if not isinstance(category, dict) or category.get('error'):
        return []
    candidates = verified_purpose_candidates('tissue', category)
    seen = set()
    offers = []
    for row in candidates:
        if safe_box_count(row) != 5:
            continue
        unit = comparison_unit('tissue', row)
        if not unit or unit[0] != '100組' or not math.isfinite(unit[1]) or unit[1] <= 0:
            continue
        code = row.get('item_code')
        name = row.get('name')
        shop = row.get('shop')
        price = row.get('price')
        if not (isinstance(code, str) and code and code not in seen
                and isinstance(name, str) and name.strip()
                and isinstance(shop, str) and 0 < len(shop.strip()) <= 90
                and type(price) is int and price > 0
                and row.get('postage') == '送料込み'
                and row.get('quality_version') == 1):
            continue
        # The only allowed per-box sheet count must be explicit in the title.
        counts = {int(n) for n in re.findall(r'(\d+)\s*組', name)}
        if len(counts) != 1 or min(counts) <= 0:
            continue
        seen.add(code)
        offers.append((price, unit[1], counts.pop(), row))
    if len(offers) < 2 or len({r['shop'].strip() for _, _, _, r in offers}) < 2:
        return []
    return sorted(offers, key=lambda t: (t[0], t[1], t[3]['shop'], t[3]['item_code']))[:12]


def render(offers):
    if not offers:
        return ''
    escaped = html.escape
    rows = []
    for price, unit, pairs, row in offers:
        name = clean_display_name(row['name'])
        short = name if len(name) <= 58 else name[:57] + '…'
        rows.append(
            '<li class="tissue-five-box-item"><strong>送料込み ¥'
            + f'{price:,}' + '</strong><span class="shop">' + escaped(row['shop'].strip())
            + '</span><p class="spec">' + str(pairs) + '組×5箱 ／ 100組あたり ¥'
            + f'{unit:,.2f}' + '</p><p>' + escaped(short) + '</p>'
            + '<a class="buy-button" href="' + escaped(row['url'], quote=True)
            + '" target="_blank" rel="nofollow sponsored noopener"'
            + ' data-tissue-five-box-choice="1"'
            + ' data-conversion-source="category" data-category-id="tissue"'
            + ' data-purchase-purpose="small" data-id="' + escaped(row['item_code'], quote=True)
            + '" data-product-name="' + escaped(name, quote=True)
            + '" data-shipping-price="' + str(price)
            + '" data-unit-price-label="' + escaped(f'¥{unit:,.2f}／100組', quote=True)
            + '">楽天で価格・送料を確認する ↗</a></li>'
        )
    count = len(offers)
    shops = len({r['shop'].strip() for _, _, _, r in offers})
    return (
        MARKER + '<section class="tissue-five-box" id="tissue-five-box" aria-labelledby="tissue-five-box-title">'
        '<h2 id="tissue-five-box-title">ティッシュ5箱セットはどこで買う？</h2>'
        '<p>60箱まとめ買いとは別に、確認済みの<strong>5箱セット</strong>を比較できます。'
        f'楽天の掲載候補から{count}件・{shops}ショップを確認しました。'
        '支払総額は送料込みですが、180組・220組など箱あたりの組数や銘柄が異なります。'
        '<strong>異なる商品を同一商品の店別最安値とは扱いません。</strong></p>'
        f'<details id="tissue-five-box-details"><summary>5箱の販売候補を比較（{count}件）</summary>'
        '<ul class="tissue-five-box-list">' + ''.join(rows) + '</ul></details>'
        '<p>楽天全店の最安保証はありません。ポイント・クーポン・地域別送料・在庫は購入先で確認してください。'
        '5箱以外のまとめ買いは下の商品ランキングで確認できます。</p></section>'
    )


def apply(site=Path('site')):
    page = site / 'categories/tissue/index.html'
    source = page.read_text(encoding='utf-8')
    if MARKER in source:
        return 'already_exists'
    if source.count(ANCHOR) != 1 or source.count('</head>') != 1 or source.count('id="tissue-buy-size"') != 1:
        raise ValueError('Tissue page purchase sections not in expected order')
    if source.index('id="tissue-buy-size"') > source.index(ANCHOR):
        raise ValueError('Tissue size guide must precede the main answer')
    offers = select_offers(json.loads((site / 'data.json').read_text(encoding='utf-8')).get('categories', {}).get('tissue'))
    if not offers:
        return 'no_verified_five_box_choice'
    page.write_text(
        source.replace(ANCHOR, render(offers) + '\n' + ANCHOR, 1)
              .replace('</head>', CSS + '</head>', 1),
        encoding='utf-8')
    return f'rendered:{len(offers)}offers'


if __name__ == '__main__':
    print('Tissue five-box choices:', apply())
