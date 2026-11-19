"""Add a shop-first navigation to published, checked laundry ranking offers.

This does NOT compare prices of different products as if they were one
identical SKU or rank merchants overall. It reuses existing product anchors.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html import escape
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

MARKER = '<!-- laundry-shop-directory-v1 -->'
STYLE = '''<style id="laundry-shop-directory-css">
.laundry-shop-directory{margin:14px 0 18px;padding:18px;border:1px solid #d8ddd9;border-radius:14px;background:#fafbfa}
.laundry-shop-directory h2{font-size:20px;line-height:1.45;margin:0 0 8px}
.laundry-shop-directory .shop-directory-note{font-size:13px;line-height:1.75;margin:8px 0 14px}
.laundry-shop-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0;padding:0;list-style:none}
.laundry-shop-item{min-width:0}
.laundry-shop-item details{background:#fff;border:1px solid #dfe4df;border-radius:11px;overflow:hidden}
.laundry-shop-item summary{display:flex;align-items:center;gap:10px;padding:12px;cursor:pointer;min-height:54px;list-style:none;line-height:1.5}
.laundry-shop-item summary::-webkit-details-marker{display:none}
.laundry-shop-item summary strong{font-size:14px;overflow-wrap:anywhere;flex:1}
.laundry-shop-item summary small{font-size:11px;color:#625b53;white-space:nowrap}
.laundry-shop-item summary::after{content:"＋";font-size:18px;color:#4b6154}
.laundry-shop-item details[open] summary::after{content:"－"}
.laundry-shop-item summary:focus-visible,.laundry-shop-item a:focus-visible{outline:3px solid #166f81;outline-offset:2px;border-radius:4px}
.laundry-shop-item ul{margin:0;padding:0 12px;list-style:none}
.laundry-shop-item li{border-top:1px solid #ededeb;padding:10px 0}
.laundry-shop-item li+li{margin-top:0}
.laundry-shop-item a{display:block;color:#175840;font-size:13px;font-weight:700;line-height:1.55;overflow-wrap:anywhere;text-underline-offset:2px}
.laundry-shop-item li small{display:block;font-size:12px;color:#5d5854;line-height:1.5;margin-top:4px}
@media(max-width:600px){.laundry-shop-directory{padding:12px}.laundry-shop-list{grid-template-columns:1fr}}
</style>'''


def verified_groups(markup, catalog):
    """Return only exact, already-rendered and quality-gated offers."""
    category = catalog.get('categories', {}).get('laundry', {})
    items = category.get('items', [])
    if not isinstance(items, list) or not items:
        return {}
    soup = BeautifulSoup(markup, 'html.parser')
    cards = soup.select('article.product-card[id^="laundry-rank-"]')
    if len(cards) != len(items) or not 2 <= len(items) <= 12:
        return {}
    groups = defaultdict(list)
    seen_urls = set()
    for rank, (card, row) in enumerate(zip(cards, items), start=1):
        if not isinstance(row, dict) or card.get('id') != f'laundry-rank-{rank}':
            return {}
        link = card.select_one('a.buy-button')
        shop = row.get('shop')
        try:
            price = Decimal(str(row['price']))
            unit = Decimal(str(row['unit_price']))
            link_price = Decimal(link['data-shipping-price']) if link else Decimal('NaN')
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return {}
        url = row.get('url')
        if not (row.get('postage') == '送料込み' and row.get('metric') == '100g'
                and row.get('quality_version') == 1
                and price.is_finite() and price > 0 and unit.is_finite() and unit > 0
                and link and link.get('href') == url and url not in seen_urls
                and link_price == price and link.get('data-rank') == str(rank)
                and link.get('data-category-id') == 'laundry'
                and isinstance(shop, str) and 0 < len(shop.strip()) <= 90
                and card.select_one('.shop') and card.select_one('.shop').get_text(' ', strip=True) == shop.strip()):
            return {}
        seen_urls.add(url)
        name = re.sub(r'\s+', ' ', str(row.get('name', '')).strip())
        if not name:
            return {}
        groups[shop.strip()].append({'rank': rank, 'name': name, 'price': price, 'unit': unit})
    return dict(groups) if len(groups) >= 2 else {}


def render(groups):
    if not groups:
        return ''
    count = sum(len(group) for group in groups.values())
    blocks = []
    for shop in sorted(groups, key=lambda s: s.casefold()):
        entries = groups[shop]
        rows = []
        for entry in entries:
            short = entry['name'] if len(entry['name']) <= 44 else entry['name'][:43] + '…'
            rows.append(
                '<li><a href="#laundry-rank-' + str(entry['rank']) + '" title="' + escape(entry['name'], quote=True) + '">'
                + escape(short) + 'の商品詳細を見る ↓</a><small>送料込み ¥'
                + format(entry['price'], ',.0f') + ' ／ 100gあたり ¥'
                + format(entry['unit'], ',.2f') + '</small></li>'
            )
        blocks.append('<li class="laundry-shop-item"><details><summary><strong>'
                      + escape(shop) + '</strong><small>掲載' + str(len(entries))
                      + '商品</small></summary><ul>' + ''.join(rows) + '</ul></details></li>')
    return (MARKER + '<section class="laundry-shop-directory" id="laundry-shop-directory" aria-labelledby="laundry-shop-directory-title">'
            '<h2 id="laundry-shop-directory-title">掲載ショップ別に洗濯洗剤を探す</h2>'
            f'<p class="shop-directory-note">楽天で送料込み価格を確認できた掲載{count}商品の、{len(groups)}ショップ別の一覧です。'
            '各商品の購入総額と100g単価を確認できます。<strong>異なる商品を比べた「安い店ランキング」ではありません。</strong>'
            '商品タイプ・容量・使用量が違う場合、同一条件での店舗比較はできません。楽天の全店舗・在庫・地域別送料を網羅しません。</p>'
            '<ul class="laundry-shop-list">' + ''.join(blocks) + '</ul></section>')


def apply(site=Path('site')):
    path = site / 'categories/laundry/index.html'
    markup = path.read_text(encoding='utf-8')
    if MARKER in markup:
        return 'already_exists'
    groups = verified_groups(markup, json.loads((site / 'data.json').read_text(encoding='utf-8')))
    if not groups:
        return 'no_verified_shop_groups'
    match = re.search(r'<section id="buying-decisions" class="buying-decisions".*?</section>', markup, re.S)
    if not match or markup.count('</head>') != 1:
        raise ValueError('expected buying decision section missing')
    panel = render(groups)
    updated = (markup[:match.end()] + '\n' + panel + markup[match.end():]).replace('</head>', STYLE + '\n</head>', 1)
    path.write_text(updated, encoding='utf-8')
    return f'rendered:{len(groups)}shops/{sum(len(v) for v in groups.values())}offers'


if __name__ == '__main__':
    print('Laundry shop directory:', apply())
