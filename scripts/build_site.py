import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sale_quantity import sale_quantity_for_item

API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
SITE_URL = "https://stusaurus.github.io/daily-cost-jp/"
OUTPUT_DIR = Path("site")

APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

if not APP_ID or not ACCESS_KEY:
    print("Missing required Rakuten secrets.", file=sys.stderr)
    sys.exit(2)

CATEGORIES = [
    {
        "id": "toilet-paper",
        "name": "トイレットペーパー",
        "emoji": "🧻",
        "keyword": "トイレットペーパー",
        "kind": "count",
        "allowed_units": {"ロール": "roll", "巻": "roll"},
    },
    {
        "id": "tissue",
        "name": "ティッシュ",
        "emoji": "📦",
        "keyword": "ティッシュ",
        "kind": "count",
        "allowed_units": {"箱": "box", "パック": "pack", "個": "pack"},
    },
    {
        "id": "laundry",
        "name": "洗濯洗剤",
        "emoji": "🧴",
        "keyword": "洗濯洗剤 詰め替え",
        "kind": "measure",
    },
    {
        "id": "dish",
        "name": "食器用洗剤",
        "emoji": "🍽️",
        "keyword": "食器用洗剤 詰め替え",
        "kind": "measure",
    },
    {
        "id": "water",
        "name": "水・ミネラルウォーター",
        "emoji": "💧",
        "keyword": "ミネラルウォーター",
        "kind": "water",
    },
    {
        "id": "coffee",
        "name": "コーヒー",
        "emoji": "☕",
        "keyword": "コーヒー 豆 粉",
        "kind": "coffee",
    },
]

METRIC_LABELS = {
    "roll": "1ロール",
    "box": "1箱",
    "pack": "1パック",
    "100g": "100g",
    "100ml": "100ml",
    "1L": "1L",
}


def normalize_text(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("×", "x").replace("Ｘ", "x").replace("X", "x")
    value = value.replace(",", "")
    return value


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_count_quantity(title, allowed_units):
    text = normalize_text(title)
    units_re = "|".join(re.escape(unit) for unit in allowed_units)

    explicit = re.search(
        rf"(\d+(?:\.\d+)?)\s*({units_re})\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if explicit:
        base = float(explicit.group(1))
        raw_unit = explicit.group(2)
        multiplier = int(explicit.group(3))
        total = base * multiplier
        if total > 0 and total.is_integer():
            return {
                "metric": allowed_units[raw_unit],
                "quantity": total,
                "confidence": 0.98,
                "evidence": explicit.group(0),
            }

    single = re.search(
        rf"(\d+(?:\.\d+)?)\s*({units_re})",
        text,
        flags=re.IGNORECASE,
    )
    if single:
        total = float(single.group(1))
        raw_unit = single.group(2)
        if total > 0 and total.is_integer():
            return {
                "metric": allowed_units[raw_unit],
                "quantity": total,
                "confidence": 0.86,
                "evidence": single.group(0),
            }

    return None


def parse_measure_quantity(title, category_kind):
    text = normalize_text(title)

    explicit = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if explicit:
        amount = float(explicit.group(1))
        unit = explicit.group(2).lower()
        multiplier = int(explicit.group(3))
        confidence = 0.98
        evidence = explicit.group(0)
    else:
        single = re.search(
            r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
            text,
            flags=re.IGNORECASE,
        )
        if not single:
            return None
        amount = float(single.group(1))
        unit = single.group(2).lower()
        multiplier = 1
        confidence = 0.84
        evidence = single.group(0)

    if amount <= 0 or multiplier <= 0:
        return None

    if unit == "kg":
        total_g = amount * 1000 * multiplier
        metric = "100g"
        quantity = total_g / 100
    elif unit == "g":
        total_g = amount * multiplier
        metric = "100g"
        quantity = total_g / 100
    elif unit == "l":
        total_ml = amount * 1000 * multiplier
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total_ml / (1000 if metric == "1L" else 100)
    else:
        total_ml = amount * multiplier
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total_ml / (1000 if metric == "1L" else 100)

    if category_kind == "coffee" and metric != "100g":
        return None

    if quantity <= 0:
        return None

    return {
        "metric": metric,
        "quantity": quantity,
        "confidence": confidence,
        "evidence": evidence,
    }


def parse_quantity(title, category):
    if category["kind"] == "count":
        return parse_count_quantity(title, category["allowed_units"])
    return parse_measure_quantity(title, category["kind"])


def first_image(item):
    for key in ("mediumImageUrls", "smallImageUrls"):
        value = item.get(key)
        if not value:
            continue
        if isinstance(value, list):
            first = value[0] if value else None
        else:
            first = value
        if isinstance(first, dict):
            first = first.get("imageUrl") or first.get("url")
        if first:
            return str(first).replace("http://", "https://")
    return ""


def normalize_item(raw, category):
    item = raw.get("Item", raw) if isinstance(raw, dict) else {}
    title = item.get("itemName", "")
    price = safe_int(item.get("itemPrice"))
    parsed = parse_quantity(title, category)

    unit_price = None
    metric = None
    confidence = 0.0
    evidence = ""
    if parsed and price > 0:
        unit_price = price / parsed["quantity"]
        metric = parsed["metric"]
        confidence = parsed["confidence"]
        evidence = parsed["evidence"]

    sale_quantity = sale_quantity_for_item(title, price, unit_price, metric)

    affiliate_url = item.get("affiliateUrl") or item.get("itemUrl") or ""
    postage_flag = item.get("postageFlag")
    if postage_flag in (1, "1"):
        postage = "送料込み"
    elif postage_flag in (0, "0"):
        postage = "送料別"
    else:
        postage = "送料は商品ページで確認"

    normalized = {
        "name": title,
        "price": price,
        "image": first_image(item),
        "url": affiliate_url,
        "shop": item.get("shopName", ""),
        "review_average": safe_float(item.get("reviewAverage")),
        "review_count": safe_int(item.get("reviewCount")),
        "point_rate": safe_int(item.get("pointRate"), 1),
        "postage": postage,
        "metric": metric,
        "unit_price": unit_price,
        "confidence": confidence,
        "evidence": evidence,
    }
    if sale_quantity:
        normalized.update(sale_quantity)
    return normalized


def fetch_category(category):
    params = {
        "applicationId": APP_ID,
        "keyword": category["keyword"],
        "hits": 30,
        "formatVersion": 2,
    }
    if AFFILIATE_ID:
        params["affiliateId"] = AFFILIATE_ID

    url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "accessKey": ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": SITE_URL,
            "User-Agent": "daily-cost-jp/0.2",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_items = payload.get("items", [])
    return [normalize_item(raw, category) for raw in raw_items]


def choose_ranked_items(items):
    comparable = [
        item
        for item in items
        if item["unit_price"] is not None
        and item["confidence"] >= 0.84
        and item["metric"] in METRIC_LABELS
    ]
    if not comparable:
        return None, []

    metric_counts = Counter(item["metric"] for item in comparable)
    dominant_metric = metric_counts.most_common(1)[0][0]

    same_metric = [
        item for item in comparable if item["metric"] == dominant_metric
    ]
    same_metric.sort(
        key=lambda item: (
            item["unit_price"],
            -item["review_count"],
            -item["review_average"],
        )
    )

    seen = set()
    ranked = []
    for item in same_metric:
        key = normalize_text(item["name"]).lower()
        if key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) >= 5:
            break

    return dominant_metric, ranked


def yen(value):
    if value is None:
        return "-"
    if value < 100:
        return f"¥{value:.1f}"
    return f"¥{value:,.0f}"


def render_product_card(item, rank, metric):
    name = html.escape(item["name"])
    shop = html.escape(item["shop"])
    url = html.escape(item["url"], quote=True)
    image = html.escape(item["image"], quote=True)
    metric_label = METRIC_LABELS[metric]
    review = (
        f"★ {item['review_average']:.2f}（{item['review_count']:,}件）"
        if item["review_count"] > 0
        else "レビュー情報なし"
    )
    point = (
        f"ポイント {item['point_rate']}倍"
        if item["point_rate"] > 1
        else "通常ポイント"
    )
    image_html = (
        f'<img src="{image}" alt="" loading="lazy">'
        if image
        else '<div class="image-placeholder">画像なし</div>'
    )

    return f"""
    <article class="product-card">
      <div class="rank-badge">{rank}</div>
      <div class="product-image">{image_html}</div>
      <div class="product-body">
        <h3>{name}</h3>
        <div class="unit-price">{yen(item["unit_price"])} <span>/ {metric_label}</span></div>
        <div class="meta-grid">
          <span>商品価格 <strong>¥{item["price"]:,}</strong></span>
          <span>{html.escape(item["postage"])}</span>
          <span>{html.escape(review)}</span>
          <span>{html.escape(point)}</span>
        </div>
        <p class="shop">{shop}</p>
        <a class="buy-button" href="{url}" target="_blank" rel="nofollow sponsored noopener">楽天市場で確認する</a>
      </div>
    </article>
    """


def render_category(category, items, error=None):
    anchor = html.escape(category["id"])
    heading = f'{category["emoji"]} {html.escape(category["name"])}'
    if error:
        return f"""
        <section id="{anchor}" class="category-section">
          <div class="section-heading"><h2>{heading}</h2></div>
          <div class="notice">現在データを取得できませんでした。次回の自動更新で再試行します。</div>
        </section>
        """

    metric, ranked = choose_ranked_items(items)
    if not ranked:
        return f"""
        <section id="{anchor}" class="category-section">
          <div class="section-heading"><h2>{heading}</h2></div>
          <div class="notice">単価を安全に計算できる商品が不足しています。推測値は表示していません。</div>
        </section>
        """

    metric_label = METRIC_LABELS[metric]
    cards = "\n".join(
        render_product_card(item, index, metric)
        for index, item in enumerate(ranked, start=1)
    )
    return f"""
    <section id="{anchor}" class="category-section">
      <div class="section-heading">
        <h2>{heading}</h2>
        <p>取得商品のうち、同じ単位（{metric_label}）で比較できる商品を商品価格ベースで表示</p>
      </div>
      <div class="product-list">{cards}</div>
    </section>
    """


HTML_HEAD = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>日用品コスパ比較 | 楽天市場の単価を自動計算</title>
  <meta name="description" content="トイレットペーパー、ティッシュ、洗剤、水、コーヒーなどの日用品を、楽天市場の商品情報から単価換算して比較します。">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/">
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --card: #ffffff;
      --text: #17191c;
      --muted: #6b7280;
      --line: #e5e7eb;
      --accent: #b3261e;
      --accent-dark: #8f1d17;
      --soft: #fff4f2;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans",
                   "Noto Sans JP", "Yu Gothic", sans-serif;
      color: var(--text);
      background: var(--bg);
      line-height: 1.65;
    }
    a { color: inherit; }
    .container { width: min(1040px, calc(100% - 28px)); margin: 0 auto; }
    header {
      background: linear-gradient(135deg, #ffffff, #fff5f3);
      border-bottom: 1px solid var(--line);
      padding: 34px 0 26px;
    }
    .eyebrow {
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      color: var(--accent);
      background: #fff;
      border: 1px solid #f0cbc7;
      border-radius: 999px;
      padding: 5px 10px;
    }
    h1 { font-size: clamp(28px, 7vw, 46px); line-height: 1.2; margin: 14px 0 10px; }
    .lead { color: #4b5563; margin: 0; max-width: 760px; }
    .updated { margin-top: 14px; font-size: 13px; color: var(--muted); }
    .nav-wrap {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(255,255,255,.94);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
    }
    nav {
      display: flex;
      overflow-x: auto;
      gap: 8px;
      padding: 10px 0;
      scrollbar-width: none;
    }
    nav::-webkit-scrollbar { display: none; }
    nav a {
      white-space: nowrap;
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 12px;
      background: #fff;
      font-size: 13px;
    }
    main { padding: 22px 0 40px; }
    .info-box {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 22px;
      font-size: 13px;
      color: #4b5563;
    }
    .category-section { scroll-margin-top: 64px; margin: 34px 0 44px; }
    .section-heading { margin-bottom: 14px; }
    .section-heading h2 { margin: 0; font-size: 24px; }
    .section-heading p { margin: 5px 0 0; color: var(--muted); font-size: 13px; }
    .product-list { display: grid; gap: 12px; }
    .product-card {
      position: relative;
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 14px;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      box-shadow: 0 3px 16px rgba(0,0,0,.035);
    }
    .rank-badge {
      position: absolute;
      top: -7px;
      left: -7px;
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--text);
      color: #fff;
      font-weight: 800;
      font-size: 13px;
    }
    .product-image {
      width: 92px;
      height: 92px;
      border: 1px solid var(--line);
      border-radius: 12px;
      display: grid;
      place-items: center;
      overflow: hidden;
      background: #fff;
    }
    .product-image img { width: 100%; height: 100%; object-fit: contain; }
    .image-placeholder { color: var(--muted); font-size: 11px; }
    .product-body h3 {
      margin: 0 0 6px;
      font-size: 15px;
      line-height: 1.45;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .unit-price {
      color: var(--accent);
      font-size: 24px;
      font-weight: 800;
      line-height: 1.25;
      margin: 6px 0 9px;
    }
    .unit-price span { color: var(--muted); font-size: 12px; font-weight: 600; }
    .meta-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 5px 12px;
      color: #4b5563;
      font-size: 12px;
    }
    .shop { margin: 8px 0 10px; color: var(--muted); font-size: 12px; }
    .buy-button {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      min-height: 42px;
      width: 100%;
      border-radius: 11px;
      background: var(--accent);
      color: #fff;
      text-decoration: none;
      font-weight: 700;
      font-size: 14px;
    }
    .buy-button:hover { background: var(--accent-dark); }
    .notice {
      padding: 18px;
      border: 1px dashed #cbd5e1;
      background: #fff;
      border-radius: 14px;
      color: var(--muted);
      font-size: 13px;
    }
    footer {
      border-top: 1px solid var(--line);
      background: #fff;
      padding: 30px 0 44px;
      color: var(--muted);
      font-size: 12px;
    }
    footer strong { color: var(--text); }
    @media (min-width: 760px) {
      .product-list { grid-template-columns: 1fr 1fr; }
      .product-card { grid-template-columns: 110px 1fr; }
      .product-image { width: 110px; height: 110px; }
    }
  </style>
</head>
<body>
"""


def build_site():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(ZoneInfo("Asia/Tokyo"))
    category_results = []
    serializable = {}
    successful_categories = 0

    for index, category in enumerate(CATEGORIES):
        error = None
        items = []
        try:
            items = fetch_category(category)
            successful_categories += 1
            print(f"{category['name']}: {len(items)} items")
        except Exception as exc:
            error = str(exc)
            print(f"{category['name']}: fetch failed: {exc}", file=sys.stderr)

        metric, ranked = choose_ranked_items(items)
        serializable[category["id"]] = {
            "name": category["name"],
            "metric": metric,
            "items": ranked,
            "error": error,
        }
        category_results.append(render_category(category, items, error=error))

        if index < len(CATEGORIES) - 1:
            time.sleep(1.15)

    if successful_categories == 0:
        print("All Rakuten API requests failed; refusing to deploy an empty site.", file=sys.stderr)
        sys.exit(1)

    nav = "".join(
        f'<a href="#{html.escape(category["id"])}">{category["emoji"]} {html.escape(category["name"])}</a>'
        for category in CATEGORIES
    )
    body = f"""
<header>
  <div class="container">
    <span class="eyebrow">毎朝自動更新</span>
    <h1>日用品コスパ比較</h1>
    <p class="lead">楽天市場の商品名から容量・個数を読み取り、計算に自信が持てる商品だけを同じ単位に換算して比較します。</p>
    <p class="updated">最終更新：{updated_at.strftime("%Y年%m月%d日 %H:%M")}（日本時間）</p>
  </div>
</header>
<div class="nav-wrap">
  <nav class="container">{nav}</nav>
</div>
<main class="container">
  <div class="info-box">
    <strong>比較方法について：</strong>
    表示順位は、楽天市場APIで取得した商品のうち、商品名から数量を高い確度で判定でき、同じ単位に換算できる商品の商品価格を基準にしています。
    送料・クーポン・一部ポイント還元は単価に含めていません。購入前に必ず楽天市場の商品ページで最新の価格・送料・内容量をご確認ください。
  </div>
  {"".join(category_results)}
</main>
<footer>
  <div class="container">
    <p><strong>広告について</strong><br>当サイトは楽天アフィリエイトを利用しています。掲載リンクを経由した購入により、運営者に報酬が発生する場合があります。</p>
    <p>商品情報・価格・レビュー等は取得時点の情報です。当サイトは楽天市場の商品を独自に単価換算して表示するもので、楽天グループ株式会社が運営するサイトではありません。</p>
    <p>© {updated_at.year} 日用品コスパ比較</p>
  </div>
</footer>
</body>
</html>
"""
    (OUTPUT_DIR / "index.html").write_text(HTML_HEAD + body, encoding="utf-8")

    public_data = {
        "updated_at": updated_at.isoformat(),
        "source": "Rakuten Ichiba API",
        "categories": serializable,
    }
    (OUTPUT_DIR / "data.json").write_text(
        json.dumps(public_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + SITE_URL + "sitemap.xml\n",
        encoding="utf-8",
    )
    (OUTPUT_DIR / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'<url><loc>{SITE_URL}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>'
        f'</urlset>\n',
        encoding="utf-8",
    )

    print(f"Built {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    build_site()
