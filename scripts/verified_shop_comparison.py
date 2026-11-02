"""Show a verified, same-pack Rakuten shop comparison on the laundry page.

Only eligible offers from the existing published, quality-gated catalogue.
Never claim that the entire marketplace was searched.
"""
import html
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

MARKER = '<!-- verified-same-sku-shop-comparison-v1 -->'
ANCHOR = '<section class="purchase-answer lab-answer" id="buying-answer">'
CSS = """<style id="same-sku-shop-css">
.same-sku-shop{margin:20px 0;padding:22px;border:1px solid #d6e4d9;border-radius:18px;background:#f5faf6}
.same-sku-shop h2{font-size:clamp(19px,2.2vw,25px);line-height:1.4;margin:0 0 10px;color:#1e3930}
.same-sku-shop p{font-size:14px;line-height:1.75;margin:8px 0}
.same-sku-shop table{width:100%;border-collapse:collapse;background:#fff;font-size:14px}
.same-sku-shop th,.same-sku-shop td{padding:12px 10px;border-bottom:1px solid #e5eae6;text-align:left;overflow-wrap:anywhere}
.same-sku-shop a{color:#105c3a;font-weight:700;text-underline-offset:3px}
.same-sku-shop .price{font-weight:900;white-space:nowrap}
@media(max-width:600px){.same-sku-shop{padding:14px 10px}.same-sku-shop th,.same-sku-shop td{font-size:12px;padding:10px 5px}}
</style>"""


def normalized(value):
    return unicodedata.normalize("NFKC", str(value or "")).replace(" ", "").replace("　", "").replace("×", "x").lower()


def verified_offer(row):
    if not isinstance(row, dict):
        return False
    name = normalized(row.get("name"))
    size = normalized(row.get("sale_quantity_label"))
    url = row.get("url")
    if not isinstance(url, str):
        return False
    address = urlsplit(url)
    price = row.get("price")
    return (
        row.get("category_id") == "laundry"
        and all(word in name for word in ("さらさ", "洗濯洗剤", "液体"))
        and ("詰め替え" in name or "詰替" in name)
        and re.fullmatch(r"1490g[x]6個", size) is not None
        and row.get("postage") == "送料込み"
        and row.get("quality_version") == 1
        and row.get("sale_quantity_confidence", 0) >= 0.9
        and type(price) is int and price > 0
        and isinstance(row.get("shop"), str) and 0 < len(row["shop"].strip()) <= 90
        and address.scheme == "https" and address.hostname in
        {"hb.afl.rakuten.co.jp", "item.rakuten.co.jp"}
        and not address.username and not address.password
        and not any(c in url for c in '<>"\r\n')
    )


def select_offers(catalog):
    category = catalog.get("categories", {}).get("laundry", {})
    listings = category.get("items", [])
    if not isinstance(listings, list):
        return []
    shops = {}
    for row in listings:
        if verified_offer(row):
            shop = row["shop"].strip()
            if shop not in shops or row["price"] < shops[shop]["price"]:
                shops[shop] = row
    if len(shops) < 2:
        return []
    return sorted(shops.values(), key=lambda r: (r["price"], r["shop"]))[:5]


def render(offers):
    if len(offers) < 2:
        return ""
    cheapest = offers[0]
    diff = offers[1]["price"] - cheapest["price"]
    escape = html.escape
    rows = "".join(
        '<tr><th scope="row">' + escape(row["shop"]) + '</th><td class="price">¥'
        + format(row["price"], ",") + '</td><td><a href="'
        + escape(row["url"], quote=True)
        + '" target="_blank" rel="nofollow sponsored noopener">楽天で条件を確認</a></td></tr>'
        for row in offers
    )
    return (
        MARKER + '<section id="verified-same-sku-shops" class="same-sku-shop" aria-labelledby="same-sku-title">'
        '<h2 id="same-sku-title">さらさ 1490g×6個はどの楽天ショップが安い？</h2>'
        f'<p>現在の掲載候補では{len(offers)}店舗を比較できます。'
        'いずれも液体洗剤・詰め替え1490g×6個の送料込み表示価格です。</p>'
        '<p>掲載候補では<strong>' + escape(cheapest["shop"]) + 'の¥'
        + format(cheapest["price"], ",") + 'が最も安く</strong>、'
        '2番目の候補より<strong>¥' + format(diff, ",") + '</strong>低い価格です。</p>'
        '<table><caption>同じ商品規格の掲載ショップ価格比較</caption>'
        '<thead><tr><th scope="col">ショップ</th><th scope="col">送料込み価格</th>'
        '<th scope="col">商品の確認</th></tr></thead><tbody>'
        + rows + '</tbody></table>'
        '<p>※楽天市場の全店舗の最安値を保証するものではありません。'
        '地域別送料・在庫・クーポン・ポイントは購入前に各商品ページで確認してください。</p>'
        '</section>'
    )


def apply(site=Path("site")):
    page = site / "categories/laundry/index.html"
    text = page.read_text(encoding="utf-8")
    if MARKER in text:
        return "already_exists"
    if text.count(ANCHOR) != 1 or text.count("</head>") != 1 or text.count("<main ") != 1:
        raise ValueError("unexpected laundry page structure")
    offers = select_offers(json.loads((site / "data.json").read_text(encoding="utf-8")))
    if not offers:
        return "no_verified_pair"
    page.write_text(text.replace(ANCHOR, render(offers) + "\n" + ANCHOR, 1)
                    .replace("</head>", CSS + "\n</head>", 1), encoding="utf-8")
    return "rendered"


if __name__ == "__main__":
    print("Verified shop comparison:", apply())
