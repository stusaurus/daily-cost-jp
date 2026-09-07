import html as html_lib
import re
import urllib.parse
from pathlib import Path

TRENDS = Path("site/trends/index.html")
PRODUCTS = Path("site/products/index.html")


def main():
    if not TRENDS.exists() or not PRODUCTS.exists():
        print("Trend/product pages unavailable; skipping trend label improvement")
        return

    trend_html = TRENDS.read_text(encoding="utf-8")
    product_html = PRODUCTS.read_text(encoding="utf-8")

    # After query validation, the trend page has the final safe search URL while the
    # visible card still contains the original ranked product title. Use that title
    # as the display label on the product-search page too.
    card_pattern = re.compile(
        r'<article class="card">.*?<div class="name">(.*?)</div>.*?'
        r'<a class="search" href="../products/\?q=([^"]+)">',
        re.DOTALL,
    )
    labels = {}
    for match in card_pattern.finditer(trend_html):
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
        query = urllib.parse.unquote(match.group(2))
        if title and query:
            labels.setdefault(query, title)

    grid_pattern = re.compile(
        r'(<a href="\?q=([^"]+)"><strong>.*?</strong><span>)(.*?)(</span></a>)',
        re.DOTALL,
    )

    def replace_label(match):
        query = urllib.parse.unquote(match.group(2))
        title = labels.get(query)
        if not title:
            return match.group(0)
        return match.group(1) + html_lib.escape(title) + match.group(4)

    product_html = grid_pattern.sub(replace_label, product_html)

    # Two lines are enough to identify the product while keeping the mobile grid tidy.
    style = '''<style id="trend-label-improvement">
#trend-searches .trend-grid span{
  display:-webkit-box!important;
  -webkit-line-clamp:2;
  -webkit-box-orient:vertical;
  white-space:normal!important;
  overflow:hidden;
  text-overflow:ellipsis;
  line-height:1.35;
  min-height:2.7em;
}
</style>'''
    if 'id="trend-label-improvement"' not in product_html:
        product_html = product_html.replace("</head>", style + "\n</head>", 1)

    PRODUCTS.write_text(product_html, encoding="utf-8")
    print(f"Restored descriptive labels for {len(labels)} trend searches")


if __name__ == "__main__":
    main()
