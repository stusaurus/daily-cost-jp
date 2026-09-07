import html as html_lib
import re
import urllib.parse
from collections import defaultdict, deque
from pathlib import Path

TRENDS = Path("site/trends/index.html")
PRODUCTS = Path("site/products/index.html")


def main():
    if not TRENDS.exists() or not PRODUCTS.exists():
        print("Trend/product pages unavailable; skipping trend label improvement")
        return

    trend_html = TRENDS.read_text(encoding="utf-8")
    product_html = PRODUCTS.read_text(encoding="utf-8")

    # Keep display text and search text separate.
    # The trend page still has the original ranked product title, while the href may
    # have been shortened to a safer Product API query. Multiple ranked products can
    # legitimately resolve to the same short query (for example, 柔軟剤), so store
    # every title for each query in order instead of collapsing them into one value.
    card_pattern = re.compile(
        r'<article class="card">.*?<div class="name">(.*?)</div>.*?'
        r'<a class="search" href="../products/\?q=([^"]+)">',
        re.DOTALL,
    )

    labels_by_query = defaultdict(deque)
    all_labels = []
    for match in card_pattern.finditer(trend_html):
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()
        query = urllib.parse.unquote(match.group(2))
        if title and query:
            labels_by_query[query].append(title)
            all_labels.append(title)

    grid_pattern = re.compile(
        r'(<a href="\?q=([^"]+)"><strong>.*?</strong><span>)(.*?)(</span></a>)',
        re.DOTALL,
    )

    used = 0

    def replace_label(match):
        nonlocal used
        query = urllib.parse.unquote(match.group(2))
        queue = labels_by_query.get(query)
        if queue:
            title = queue.popleft()
            used += 1
            return match.group(1) + html_lib.escape(title) + match.group(4)
        return match.group(0)

    product_html = grid_pattern.sub(replace_label, product_html)

    # Show enough of the actual ranked product name to identify it. Search queries
    # can stay short internally, but the user-facing label must never degrade to a
    # category-only word such as "柔軟剤" or "洗濯洗剤".
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
    print(f"Restored descriptive labels for {used} trend cards")


if __name__ == "__main__":
    main()
