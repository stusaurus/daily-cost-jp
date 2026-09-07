import html as html_lib
import re
import urllib.parse
from pathlib import Path

PRODUCTS = Path("site/products/index.html")
TRENDS = Path("site/trends/index.html")
HOME = Path("site/index.html")
MAX_CHIPS = 4

TREND_CHIP_STYLE = '''<style id="trend-chip-style">
.examples .trend-chip{flex:0 0 190px;min-height:58px;white-space:normal;text-align:left;display:flex;align-items:flex-start;gap:6px;line-height:1.35;padding:8px 10px}
.trend-chip-rank{flex:0 0 auto;font-weight:900;color:#b3261e}
.trend-chip-name{min-width:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-weight:700}
</style>'''


def strip_tags(value: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def short_label(name: str) -> str:
    text = re.sub(r"\s+", " ", name).strip()
    # Two visible lines are allowed so the user can still identify the product.
    # Keep a generous cap only to prevent unusually long Rakuten titles from
    # producing oversized accessibility/text payloads.
    if len(text) > 58:
        text = text[:58].rstrip() + "…"
    return text


def collect_searchable_trends(markup: str):
    card_pattern = re.compile(r'<article class="card">(.*?)</article>', re.DOTALL)
    rows = []
    seen = set()
    for card_match in card_pattern.finditer(markup):
        card = card_match.group(1)
        rank_match = re.search(r'<div class="rank"><b>(\d+)位</b>', card)
        name_match = re.search(r'<div class="name">(.*?)</div>', card, re.DOTALL)
        search_match = re.search(r'<a class="search" href="../products/\?q=([^"]+)"', card)
        if not (rank_match and name_match and search_match):
            continue
        rank = int(rank_match.group(1))
        query = urllib.parse.unquote(search_match.group(1)).strip()
        name = strip_tags(name_match.group(1))
        key = re.sub(r"\s+", "", query.lower())
        if not query or not name or key in seen:
            continue
        seen.add(key)
        rows.append({"rank": rank, "name": name, "query": query})
    rows.sort(key=lambda row: row["rank"])
    return rows[:MAX_CHIPS]


def replace_product_chips(markup: str, rows):
    if not rows:
        return markup
    buttons = []
    for row in rows:
        q = html_lib.escape(row["query"], quote=True)
        label = html_lib.escape(short_label(row["name"]))
        buttons.append(
            f'<button class="chip trend-chip" data-q="{q}" data-trend-rank="{row["rank"]}">' 
            f'<span class="trend-chip-rank">{row["rank"]}位</span>'
            f'<span class="trend-chip-name">{label}</span></button>'
        )
    block = '<div class="examples" aria-label="今の人気商品">' + ''.join(buttons) + '</div>'
    markup = re.sub(r'<div class="examples">.*?</div>', block, markup, count=1, flags=re.DOTALL)
    markup = re.sub(r'<style id="trend-chip-style">.*?</style>', '', markup, flags=re.DOTALL)
    markup = markup.replace('</head>', TREND_CHIP_STYLE + '\n</head>', 1)
    markup = markup.replace(
        'placeholder="例：おしりセレブ / アリエール / JANコード"',
        'placeholder="今人気の商品名・ブランド・JANコード"',
        1,
    )
    return markup


def clean_home_fixed_examples(markup: str):
    markup = markup.replace(
        '「おしりセレブ」「アリエール」など、欲しい製品そのものを選んで楽天価格ナビの購入可能な最低価格を確認できます。',
        '欲しい商品名やブランド名を入れて、楽天で確認できる送料込み価格を探せます。',
    )
    return markup


def main():
    if not PRODUCTS.exists() or not TRENDS.exists():
        print("Product/trend page unavailable; skipping dynamic trend chips")
        return

    trend_html = TRENDS.read_text(encoding="utf-8")
    rows = collect_searchable_trends(trend_html)
    if not rows:
        print("No validated searchable trend items found; keeping current search chips")
        return

    product_html = PRODUCTS.read_text(encoding="utf-8")
    product_html = replace_product_chips(product_html, rows)
    PRODUCTS.write_text(product_html, encoding="utf-8")

    if HOME.exists():
        home_html = HOME.read_text(encoding="utf-8")
        HOME.write_text(clean_home_fixed_examples(home_html), encoding="utf-8")

    print("Synced product search chips to validated Rakuten trends: " + ", ".join(f"{r['rank']}:{r['query']}" for r in rows))


if __name__ == "__main__":
    main()
