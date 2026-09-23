"""Growth layer for daily-cost-jp.

Expands repeat-purchase categories while keeping the conservative parsing and
shipping-inclusive ranking rules from build_site_final.py. It also generates a
crawlable category hub plus one static SEO page per category, and expands the
sitemap automatically on every daily build.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import build_site_final as final
from product_quality import filter_items

app = final.app
core = final.core


ADDITIONAL_CATEGORIES = [
    {
        "id": "softener",
        "name": "柔軟剤",
        "emoji": "🌸",
        "keyword": "柔軟剤 詰め替え",
        "kind": "measure",
    },
    {
        "id": "shampoo",
        "name": "シャンプー",
        "emoji": "🧴",
        "keyword": "シャンプー 詰め替え",
        "kind": "measure",
    },
    {
        "id": "conditioner",
        "name": "コンディショナー",
        "emoji": "🫧",
        "keyword": "コンディショナー 詰め替え",
        "kind": "measure",
    },
    {
        "id": "body-soap",
        "name": "ボディソープ",
        "emoji": "🛁",
        "keyword": "ボディソープ 詰め替え",
        "kind": "measure",
    },
    {
        "id": "hand-soap",
        "name": "ハンドソープ",
        "emoji": "🧼",
        "keyword": "ハンドソープ 詰め替え",
        "kind": "measure",
    },
    {
        "id": "bath-cleaner",
        "name": "お風呂用洗剤",
        "emoji": "🛀",
        "keyword": "お風呂用洗剤 詰め替え",
        "kind": "measure",
    },
    {
        "id": "toilet-cleaner",
        "name": "トイレ用洗剤",
        "emoji": "🚽",
        "keyword": "トイレ用洗剤 詰め替え",
        "kind": "measure",
    },
    {
        "id": "laundry-bleach",
        "name": "衣料用漂白剤",
        "emoji": "✨",
        "keyword": "衣料用漂白剤",
        "kind": "measure",
    },
    {
        "id": "mouthwash",
        "name": "マウスウォッシュ",
        "emoji": "🦷",
        "keyword": "マウスウォッシュ",
        "kind": "measure",
    },
    {
        "id": "paper-towel",
        "name": "ペーパータオル",
        "emoji": "🧻",
        "keyword": "ペーパータオル",
        "kind": "count",
        "allowed_units": {"枚": "sheet"},
    },
    {
        "id": "garbage-bag-45l",
        "name": "45Lゴミ袋",
        "emoji": "🗑️",
        "keyword": "ゴミ袋 45L",
        "kind": "count",
        "allowed_units": {"枚": "sheet"},
    },
    {
        "id": "mask",
        "name": "不織布マスク",
        "emoji": "😷",
        "keyword": "不織布マスク",
        "kind": "count",
        "allowed_units": {"枚": "sheet"},
    },
    {
        "id": "toothbrush",
        "name": "歯ブラシ",
        "emoji": "🪥",
        "keyword": "歯ブラシ セット",
        "kind": "count",
        "allowed_units": {"本": "piece"},
    },
    {
        "id": "cotton-swab",
        "name": "綿棒",
        "emoji": "◽",
        "keyword": "綿棒",
        "kind": "count",
        "allowed_units": {"本": "piece"},
    },
    {
        "id": "floor-sheet",
        "name": "フローリングシート",
        "emoji": "🧹",
        "keyword": "フローリングシート",
        "kind": "count",
        "allowed_units": {"枚": "sheet"},
    },
]

existing_ids = {category["id"] for category in core.CATEGORIES}
core.CATEGORIES.extend(
    category for category in ADDITIONAL_CATEGORIES if category["id"] not in existing_ids
)
core.METRIC_LABELS.update({"sheet": "1枚", "piece": "1本"})


# All 21 category rules live in product_quality.py. No downstream override.

GROWTH_CSS = r"""
    .category-pages-block { margin: 18px 0 24px; }
    .category-pages-block h2 { font-size: 19px; margin: 0 0 10px; }
    .category-pages-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .category-page-link {
      display: block;
      padding: 10px 11px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
    }
    .category-page-link small {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 9px;
      font-weight: 500;
    }
    .category-page-hero { padding: 24px 0 18px; }
    .breadcrumb { font-size: 12px; color: var(--muted); margin-bottom: 10px; }
    .breadcrumb a { color: var(--muted); }
    .category-summary {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin: 0 0 18px;
      color: #4b5563;
      font-size: 13px;
    }
    .related-categories { margin: 28px 0 8px; }
    .related-categories h2 { font-size: 18px; }
    @media (min-width: 760px) {
      .category-pages-grid { grid-template-columns: repeat(4, 1fr); }
    }
"""


def category_links_markup(prefix="categories/"):
    links = []
    for category in core.CATEGORIES:
        links.append(
            f'<a class="category-page-link" href="{prefix}{category["id"]}/">'
            f'{category["emoji"]} {core.html.escape(category["name"])}'
            '<small>単価ランキングを見る →</small></a>'
        )
    return "".join(links)


def add_category_links_to_home():
    path = core.OUTPUT_DIR / "index.html"
    markup = path.read_text(encoding="utf-8")
    if "category-pages-block" in markup:
        return
    block = f"""
  <section class="category-pages-block" aria-label="カテゴリ別比較ページ">
    <h2>カテゴリ別に詳しく比較</h2>
    <div class="category-pages-grid">{category_links_markup()}</div>
  </section>
"""
    markup = markup.replace("</style>", GROWTH_CSS + "\n  </style>", 1)
    marker = '<details class="info-box">'
    if marker in markup:
        markup = markup.replace(marker, block + "\n  " + marker, 1)
    else:
        markup = markup.replace("</main>", block + "\n</main>", 1)
    path.write_text(markup, encoding="utf-8")


def customize_head(name, description, canonical):
    head = app.IMPROVED_HEAD
    head = re.sub(
        r"<title>.*?</title>",
        f"<title>{core.html.escape(name)}のコスパ比較 | 日用品コスパ比較</title>",
        head,
        count=1,
    )
    head = re.sub(
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{core.html.escape(description, quote=True)}">',
        head,
        count=1,
    )
    head = re.sub(
        r'<link rel="canonical" href="[^"]+">',
        f'<link rel="canonical" href="{core.html.escape(canonical, quote=True)}">',
        head,
        count=1,
    )
    return head.replace("</style>", GROWTH_CSS + "\n  </style>", 1)


def generate_category_hub(updated_at):
    directory = core.OUTPUT_DIR / "categories"
    directory.mkdir(parents=True, exist_ok=True)
    canonical = core.SITE_URL + "categories/"
    head = customize_head(
        "カテゴリ一覧",
        "楽天市場の日用品を単価換算して比較できるカテゴリ一覧。送料込み商品の中から安い順に毎朝自動更新します。",
        canonical,
    )
    body = f"""
<header class="category-page-hero">
  <div class="container">
    <div class="breadcrumb"><a href="../">日用品コスパ比較</a> › カテゴリ一覧</div>
    <span class="eyebrow">毎朝自動更新</span>
    <h1>カテゴリ一覧</h1>
    <p class="lead">繰り返し買う日用品を、商品ごとに比較しやすい単位へ換算して一覧化しています。</p>
  </div>
</header>
<main class="container">
  <section class="category-pages-block">
    <h2>比較できる日用品</h2>
    <div class="category-pages-grid">{category_links_markup("")}</div>
  </section>
</main>
<footer><div class="container"><p>最終更新：{updated_at.strftime('%Y年%m月%d日 %H:%M')}（日本時間）</p><p><a href="../">トップへ戻る</a></p></div></footer>
</body></html>
"""
    (directory / "index.html").write_text(head + body, encoding="utf-8")


def generate_category_pages(updated_at):
    data_path = core.OUTPUT_DIR / "data.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    categories_data = payload.get("categories", {})

    for category in core.CATEGORIES:
        category_data = categories_data.get(category["id"], {})
        metric = category_data.get("metric")
        items = filter_items(category["id"], category_data.get("items") or [])
        directory = core.OUTPUT_DIR / "categories" / category["id"]
        directory.mkdir(parents=True, exist_ok=True)
        canonical = core.SITE_URL + f"categories/{category['id']}/"
        description = (
            f"{category['name']}を楽天市場の商品情報から単価換算。送料込み商品の中から安い順に比較し、毎朝自動更新します。"
        )
        head = customize_head(category["name"], description, canonical)

        if metric and items:
            label = final.display_metric_label(items[0], metric)
            cards = "\n".join(
                final.render_product_card_final(item, rank, metric, f"{category['id']}-rank-{rank}")
                for rank, item in enumerate(items, start=1)
            )
            ranking = f"""
<section id="{category['id']}" class="category-section">
  <div class="section-heading">
    <h2>今日の安い順ランキング</h2>
    <p>送料込み商品のうち、同じ単位（{core.html.escape(label)}）で比較できる商品を表示</p>
  </div>
  <div class="product-list">{cards}</div>
</section>
"""
        else:
            ranking = f'<div id="{category["id"]}" class="notice">現在、安全に単価比較できる商品が不足しています。次回の自動更新で再試行します。</div>'

        related = "".join(
            f'<a class="category-page-link" href="../{other["id"]}/">{other["emoji"]} {core.html.escape(other["name"])}</a>'
            for other in core.CATEGORIES
            if other["id"] != category["id"]
        )
        body = f"""
<header class="category-page-hero">
  <div class="container">
    <div class="breadcrumb"><a href="../../">日用品コスパ比較</a> › <a href="../">カテゴリ一覧</a> › {core.html.escape(category['name'])}</div>
    <span class="eyebrow">毎朝自動更新</span>
    <h1>{category['emoji']} {core.html.escape(category['name'])}のコスパ比較</h1>
    <p class="lead">楽天市場の{core.html.escape(category['name'])}を、比較しやすい単位へ換算して送料込み商品の中から安い順に表示します。</p>
    <p class="updated">最終更新：{updated_at.strftime('%Y年%m月%d日 %H:%M')}（日本時間）</p>
  </div>
</header>
<main class="container">
  <div class="category-summary">用途・数量・送料込み価格を確認できる商品のみ掲載しています。空容器や周辺用品、容量・個数が選択式で確定できない商品は除外するため、5件未満になる場合があります。クーポン・一部ポイント還元は単価に含めていません。購入前に楽天市場の商品ページで最新情報をご確認ください。</div>
  {ranking}
  <section class="related-categories">
    <h2>ほかの日用品も比較</h2>
    <div class="category-pages-grid">{related}</div>
  </section>
</main>
<footer>
  <div class="container">
    <p><strong>広告について</strong><br>当サイトは楽天アフィリエイトを利用しています。掲載リンクを経由した購入により、運営者に報酬が発生する場合があります。</p>
    <p><a href="../../">日用品コスパ比較トップへ戻る</a></p>
  </div>
</footer>
</body></html>
"""
        (directory / "index.html").write_text(head + body, encoding="utf-8")


def rewrite_sitemap(updated_at):
    urls = [core.SITE_URL, core.SITE_URL + "categories/"]
    urls.extend(core.SITE_URL + f"categories/{category['id']}/" for category in core.CATEGORIES)
    entries = "".join(
        f"<url><loc>{url}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>"
        for url in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries
        + '</urlset>\n'
    )
    (core.OUTPUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")


def main():
    # The final layer builds the home page/data with all categories added above.
    core.build_site()
    updated_at = datetime.now(ZoneInfo("Asia/Tokyo"))
    add_category_links_to_home()
    generate_category_hub(updated_at)
    generate_category_pages(updated_at)
    rewrite_sitemap(updated_at)
    print(f"Generated {len(core.CATEGORIES)} category rankings plus SEO pages.")


if __name__ == "__main__":
    main()
