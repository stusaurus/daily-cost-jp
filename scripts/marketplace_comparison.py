"""Render the marketplace comparison as an optional layer over the Rakuten build."""
import html
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from marketplace_offers import Product, cheapest_offer, rakuten_offer, yahoo_offer
from yahoo_shopping import YahooShopping, YahooUnavailable

MARKER = 'id="marketplace-comparison"'
MAIN = '<main class="container" id="lab-content">'
NAV_MARKER = 'id="marketplace-navigation"'
FRAGMENT = "#marketplace-comparison"
ANCHOR = '<section class="purchase-answer lab-answer" id="buying-answer">'
CREDIT = """<!-- Begin Yahoo! JAPAN Web Services Attribution Snippet -->
<span style="margin:15px 15px 15px 15px"><a href="https://developer.yahoo.co.jp/sitemap/">Webサービス by Yahoo! JAPAN</a></span>
<!-- End Yahoo! JAPAN Web Services Attribution Snippet -->"""

REFILL = r"(?:詰|つ)め?(?:替|か)え?"
ATTACK_ZERO = r"アタック\s*(?:zero|ゼロ)"
PRODUCTS = {
    "laundry": (
        Product("4901301440815", "アタックZERO 部屋干し 詰め替え", 2000, "g",
                (ATTACK_ZERO, REFILL, r"部屋\s*干し(?!臭)"), r"ドラム式|レギュラー|業務用"),
        Product("4901301466235", "アタックZERO ドラム式専用 詰め替え", 2300, "g",
                (ATTACK_ZERO, REFILL, r"ドラム式(?:洗濯機)?専用"), r"部屋\s*干し(?!臭)|レギュラー|業務用"),
        Product("4987176304834", "さらさ 液体洗剤 詰め替え", 1490, "g",
                (r"さらさ", REFILL, r"洗(?:濯|たく)(?:用)?洗剤|衣(?:料|類)用洗剤|洗剤ジェル"),
                r"柔軟剤(?!不使用|なし|不要)|部屋干し専用"),
    ),
    "softener": (
        Product("4987176184566", "さらさ 柔軟剤 詰め替え", 1350, "ml",
                (r"さらさ", REFILL, r"柔軟剤"), r"洗(?:濯|たく)(?:用)?洗剤|洗剤ジェル"),
    ),
    "dish": (
        Product("4901301429940", "キュキュット オレンジの香り 詰め替え", 1380, "ml",
                (r"キュキュット", r"オレンジ", REFILL),
                r"クリア除菌|マスカット|グレープフルーツ|レモン|無香|ヴァーベナ|本体"),
    ),
    "toilet-cleaner": (
        Product("4901301424938", "トイレマジックリン エレガントローズ 詰め替え", 300, "ml",
                (r"トイレ\s*マジックリン", r"エレガント\s*ローズ", REFILL),
                r"ローズ以外|フレッシュハーブ|シトラス|ミント|本体"),
    ),
}

NAV_CSS = """<style id="marketplace-navigation-style">
#marketplace-navigation{margin:18px 0;padding:12px 15px;border:1px solid #cadfd6;border-radius:10px;background:#f1f8f5;color:#173c31}
#marketplace-navigation h2{margin:0 0 6px;font-size:16px;line-height:1.5}
.marketplace-navigation-links{display:flex;flex-wrap:wrap;gap:6px 10px}
.marketplace-navigation-link{display:inline-flex;align-items:center;min-height:44px;padding:6px 10px;
  border:1px solid #457d68;border-radius:6px;background:white;color:#104b3b;text-decoration:none;font-weight:650;font-size:14px}
.marketplace-navigation-link:hover{text-decoration:underline;background:#e4f2eb;color:#104b3b}
</style>"""
CSS = """<style id="marketplace-comparison-style">
#marketplace-comparison{padding:clamp(14px,3vw,26px);margin:24px 0;border:1px solid #cadfd6;border-radius:18px;background:#f1f8f5;color:#173c31}
#marketplace-comparison h2{margin:0 0 8px;font-size:clamp(21px,3vw,27px);line-height:1.35}
#marketplace-comparison p{margin:6px 0;line-height:1.65}
.marketplace-products{display:grid;gap:14px;margin:16px 0}
.marketplace-product{background:white;border:1px solid #d8e4de;border-radius:12px;padding:14px;min-width:0}
.marketplace-product h3{margin:0 0 4px;font-size:17px;line-height:1.4}
.marketplace-prices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
.marketplace-offer{border:1px solid #d8e4de;border-radius:10px;padding:10px;min-width:0}
.marketplace-offer h4{margin:0;font-size:15px}
.marketplace-shop{font-size:13px;overflow-wrap:anywhere}
.marketplace-figures{margin:6px 0 10px}
.marketplace-figures div{display:flex;flex-wrap:wrap;justify-content:space-between;column-gap:8px;font-size:14px}
.marketplace-figures dd{margin:0;font-variant-numeric:tabular-nums}
.marketplace-total{font-weight:750}
.marketplace-buy{display:flex;align-items:center;justify-content:center;min-height:44px;padding:6px;text-align:center;
  border:1px solid #447f6a;border-radius:8px;color:#104b3b;font-size:14px;font-weight:700;text-decoration:none}
.marketplace-buy:hover{background:#eef8f3;text-decoration:underline}
.marketplace-buy:focus-visible{outline:2px solid #154f40;outline-offset:2px}
.marketplace-footnote{font-size:13px}
@media(max-width:540px){.marketplace-prices{grid-template-columns:1fr}}
</style>"""


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def select(category, listings, client, *, include=PRODUCTS):
    products = []
    diagnostic = {}
    for product in include[category]:
        rakuten = defaultdict(list)
        yahoo = defaultdict(list)
        for row in listings:
            result = rakuten_offer(category, row, product)
            if result:
                count, offer = result
                rakuten[count].append(offer)
        if not rakuten:
            continue
        hits = client.search(jan=product.jan)
        for hit in hits:
            result = yahoo_offer(category, hit, product, client.affiliate_link)
            if result:
                count, offer = result
                yahoo[count].append(offer)
        diagnostic[product.jan] = {"api_hits": len(hits), "rakuten_sizes": sorted(rakuten),
                                   "yahoo_sizes": sorted(yahoo)}
        for count in sorted(rakuten.keys() & yahoo.keys()):
            products.append((product, count, (cheapest_offer(rakuten[count]), cheapest_offer(yahoo[count]))))
    return products, diagnostic


def yen(amount):
    return f"¥{amount:,}"


def render_offer(category, offer, amount, unit):
    marketplace = {"rakuten": "楽天市場", "yahoo": "Yahoo!ショッピング"}[offer.marketplace]
    shipping = yen(offer.shipping) if offer.shipping is not None else "要確認"
    total = yen(offer.total) if offer.total is not None else "要確認"
    unit_price = f"¥{offer.total * 100 / amount:,.1f} / 100{unit}" if offer.total is not None else "—"
    return (
        f'<div class="marketplace-offer"><h4>{marketplace}</h4>'
        f'<p class="marketplace-shop">{html.escape(offer.shop)}</p>'
        '<dl class="marketplace-figures">'
        f'<div><dt>商品価格</dt><dd>{yen(offer.price)}</dd></div>'
        f'<div><dt>送料</dt><dd>{shipping}</dd></div>'
        f'<div class="marketplace-total"><dt>購入総額</dt><dd>{total}</dd></div>'
        f'<div><dt>送料込み単価</dt><dd>{unit_price}</dd></div></dl>'
        f'<a class="marketplace-buy" data-marketplace="{offer.marketplace}" data-category-id="{category}"'
        f' data-marketplace-item="{html.escape(offer.code)}" href="{html.escape(offer.url)}"'
        f' rel="sponsored nofollow noopener" target="_blank">{marketplace}で確認</a></div>'
    )


def render(category, groups, updated, rakuten_updated):
    entries = []
    japan = timezone(timedelta(hours=9))
    def shown(value):
        return value.astimezone(japan).strftime("%m/%d %H:%M")
    for product, count, (rakuten, yahoo) in groups:
        if rakuten.total is None or yahoo.total is None:
            note = "送料が未確定の候補があります。購入総額はショップで確認してください。"
        elif rakuten.total == yahoo.total:
            note = "掲載候補の購入総額は同じです。"
        else:
            name = "楽天市場" if rakuten.total < yahoo.total else "Yahoo!ショッピング"
            note = f"{name}が安い（差額 {yen(abs(rakuten.total - yahoo.total))}）"
        entries.append(
            f'<article class="marketplace-product" data-jan="{product.jan}" data-pack="{count}"'
            f' data-unit-amount="{product.amount}" data-unit="{product.unit}">'
            f'<h3>{html.escape(product.label)} {product.display_amount} × {count}個</h3>'
            f'<p><strong>{note}</strong></p><div class="marketplace-prices">'
            + "".join(render_offer(category, offer, product.amount * count, product.unit) for offer in (rakuten, yahoo))
            + '</div></article>'
        )
    return (
        f'<section {MARKER} aria-labelledby="marketplace-title">'
        '<h2 id="marketplace-title">楽天市場とYahoo!ショッピングを比較</h2>'
        '<p>容量・個数・商品規格が一致した掲載候補を比較しています。</p>'
        '<div class="marketplace-products">' + "".join(entries) + '</div>'
        '<p class="marketplace-footnote">税込。送料は取得時点の表示です。地域別送料・在庫は購入前にご確認ください。'
        'クーポン・ポイントは計算に含めていません。</p>'
        f'<p class="marketplace-footnote">価格取得（日本時間） 楽天市場 {shown(rakuten_updated)} ／ Yahoo!ショッピング {shown(updated)}。'
        '購入リンクは広告です。</p></section>'
    )


def navigation(entry_point, categories):
    links = []
    for category, name in categories:
        destination = (FRAGMENT if entry_point == "category"
                       else f"/daily-cost-jp/categories/{category}/{FRAGMENT}")
        label = "楽天市場とYahoo!ショッピングを比較する ↓" if entry_point == "category" else name
        links.append(
            f'<a class="marketplace-navigation-link" href="{html.escape(destination)}"'
            f' data-marketplace-entry="{entry_point}" data-category-id="{html.escape(category)}">'
            f'{html.escape(label)}</a>'
        )
    heading = '<h2>楽天市場とYahoo!ショッピングを比較</h2>' if entry_point != "category" else ""
    return (
        f'<nav {NAV_MARKER} aria-label="楽天市場とYahoo!ショッピングの比較">'
        + heading + '<div class="marketplace-navigation-links">' + "".join(links) + '</div></nav>'
    )


def insert_navigation(markup, entry_point, categories):
    if NAV_MARKER in markup:
        return markup
    if markup.count(MAIN) != 1 or markup.count("</head>") != 1:
        raise ValueError("marketplace navigation anchor changed")
    return (markup.replace(MAIN, MAIN + "\n" + navigation(entry_point, categories), 1)
            .replace("</head>", NAV_CSS + "\n</head>", 1))


def apply(site=Path("site"), *, client=None, now=None, include=PRODUCTS):
    now = now or datetime.now(timezone.utc)
    try:
        client = client or YahooShopping(os.getenv("YAHOO_APP_ID", ""), os.getenv("YAHOO_AFFILIATE_ID", ""))
    except YahooUnavailable as error:
        return {"status": str(error), "categories": {}}
    catalog = json.loads((site / "data.json").read_text(encoding="utf-8"))
    catalog_updated = timestamp(catalog.get("updated_at"))
    if not catalog_updated or not timedelta(minutes=-5) <= now - catalog_updated <= timedelta(hours=24):
        return {"status": "rakuten_catalog_not_fresh", "categories": {}}

    sections = {}
    diagnostics = {}
    try:
        for category in include:
            rows = catalog["categories"].get(category, {}).get("items", [])
            groups, candidates = select(category, rows, client, include=include)
            comparable = sum(all(offer.total is not None for offer in offers) for _, _, offers in groups)
            diagnostics[category] = {"pairs": len(groups), "comparable": comparable, "candidates": candidates}
            if comparable:
                sections[category] = render(category, groups, now, catalog_updated)
    except YahooUnavailable as error:
        # Do not apply a partial market snapshot to this build.
        return {"status": str(error), "categories": {}}

    available = [(category, catalog["categories"][category]["name"]) for category in sections]
    pages = {}
    for category, section in sections.items():
        page = site / "categories" / category / "index.html"
        markup = page.read_text(encoding="utf-8")
        if MARKER in markup:
            continue
        # Use the purchase summary as an insertion point and place the required
        # Yahoo credit at the bottom of each page that uses Yahoo data.
        if markup.count('</footer>') != 1 or markup.count('</head>') != 1:
            raise ValueError("marketplace page structure changed")
        anchor = ANCHOR if ANCHOR in markup else f'<section class="category-section" id="{category}">'
        if markup.count(anchor) != 1:
            raise ValueError("marketplace section anchor changed")
        markup = markup.replace(anchor, section + "\n" + anchor, 1)
        markup = markup.replace('</footer>', CREDIT + '\n</footer>', 1)
        markup = markup.replace('</head>', CSS + '\n</head>', 1)
        pages[page] = insert_navigation(markup, "category", [(category, "")])
    if available:
        for path, entry_point in (("index.html", "home"), ("categories/index.html", "directory")):
            page = site / path
            pages[page] = insert_navigation(page.read_text(encoding="utf-8"), entry_point, available)
    for page, markup in pages.items():
        temp = page.with_suffix('.tmp')
        temp.write_text(markup, encoding="utf-8")
        temp.replace(page)
    return {"status": "rendered" if sections else "no_comparable_pair", "categories": diagnostics}


if __name__ == "__main__":
    print("Marketplace comparison:", json.dumps(apply(), ensure_ascii=False, sort_keys=True))
