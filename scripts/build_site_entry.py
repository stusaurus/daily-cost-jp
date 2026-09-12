"""Runtime entry point for the 2026-07-01 Rakuten Ichiba API response shape."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import build_site as core
from sale_quantity import purchase_summary


# Rakuten Ichiba Item Search API output semantics (2026-07-01):
# postageFlag=0 means postage included, postageFlag=1 means postage not included.
_original_normalize_item = core.normalize_item


def normalize_item_with_correct_postage(raw, category):
    normalized = _original_normalize_item(raw, category)
    source = raw.get("Item", raw) if isinstance(raw, dict) else {}
    postage_flag = source.get("postageFlag")
    if postage_flag in (0, "0"):
        normalized["postage"] = "送料込み"
    elif postage_flag in (1, "1"):
        normalized["postage"] = "送料別"
    else:
        normalized["postage"] = "送料は商品ページで確認"
    return normalized


core.normalize_item = normalize_item_with_correct_postage


def to_base_amount(amount, unit):
    unit = unit.lower()
    amount = float(amount)
    if unit == "kg":
        return "weight", amount * 1000
    if unit == "g":
        return "weight", amount
    if unit == "l":
        return "volume", amount * 1000
    if unit == "ml":
        return "volume", amount
    return None, None


def result_from_total(kind, total, category_kind, confidence, evidence):
    if not total or total <= 0:
        return None
    if kind == "weight":
        metric = "100g"
        quantity = total / 100
    else:
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total / (1000 if metric == "1L" else 100)

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


def safer_parse_measure_quantity(title, category_kind):
    """Reject variant titles unless all visible capacity evidence agrees."""
    text = core.normalize_text(title)

    explicit_matches = list(re.finditer(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = []
        kinds = []
        for match in explicit_matches:
            kind, base = to_base_amount(match.group(1), match.group(2))
            totals.append(base * int(match.group(3)))
            kinds.append(kind)
        if len(set(kinds)) != 1 or max(totals) - min(totals) > 0.001:
            return None

        chosen = explicit_matches[0]
        chosen_kind = kinds[0]
        chosen_total = totals[0]

        all_measures = re.findall(
            r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
            text,
            flags=re.IGNORECASE,
        )
        visible_bases = []
        for amount, unit in all_measures:
            kind, base = to_base_amount(amount, unit)
            if kind == chosen_kind:
                visible_bases.append(base)
        explicit_base = to_base_amount(chosen.group(1), chosen.group(2))[1]
        if any(abs(base - explicit_base) > 0.001 and abs(base - chosen_total) > 0.001 for base in visible_bases):
            return None

        return result_from_total(
            chosen_kind,
            chosen_total,
            category_kind,
            0.99,
            chosen.group(0),
        )

    all_measures = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
        text,
        flags=re.IGNORECASE,
    )
    if len(all_measures) != 1:
        return None

    amount, unit = all_measures[0]
    kind, base = to_base_amount(amount, unit)
    if not kind or not base:
        return None

    pack_counts = [
        int(value)
        for value, pack_unit in re.findall(
            r"(\d+)\s*(個|袋|本|パック|セット)",
            text,
            flags=re.IGNORECASE,
        )
        if int(value) > 1
    ]
    if len(pack_counts) == 1:
        total = base * pack_counts[0]
        evidence = f"{pack_counts[0]}個相当 × {amount}{unit}"
        confidence = 0.94
    elif len(pack_counts) == 0:
        total = base
        evidence = f"{amount}{unit}"
        confidence = 0.88
    else:
        return None

    return result_from_total(kind, total, category_kind, confidence, evidence)


def safer_parse_count_quantity(title, allowed_units):
    text = core.normalize_text(title)
    units_re = "|".join(re.escape(unit) for unit in allowed_units)

    explicit_matches = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = [float(m.group(1)) * int(m.group(3)) for m in explicit_matches]
        if max(totals) - min(totals) > 0.001:
            return None
        total = totals[0]
        if total > 0 and float(total).is_integer():
            return {
                "metric": allowed_units[explicit_matches[0].group(2)],
                "quantity": total,
                "confidence": 0.99,
                "evidence": explicit_matches[0].group(0),
            }

    singles = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})",
        text,
        flags=re.IGNORECASE,
    ))
    if not singles:
        return None

    values = [float(m.group(1)) for m in singles]
    if len(set(values)) > 1:
        return None

    total = values[0]
    if total > 0 and total.is_integer():
        return {
            "metric": allowed_units[singles[0].group(2)],
            "quantity": total,
            "confidence": 0.88,
            "evidence": singles[0].group(0),
        }
    return None


def category_is_suitable(category_id, title):
    ambiguous_variant_terms = (
        "種類を選べる",
        "タイプを選べる",
        "サイズを選べる",
        "容量を選べる",
        "個数を選べる",
        "カラーを選べる",
    )
    if any(term in title for term in ambiguous_variant_terms):
        return False

    exclusions = {
        "tissue": (
            "ウェット", "ウエット", "おしり", "手口", "除菌シート",
            "ペーパータオル", "キッチンペーパー", "ティッシュケース",
            "ティッシュボックス", "ティッシュカバー", "ティッシュホルダー",
            "シートバック", "収納ポケット", "車用ポケット",
        ),
        "dish": ("ディスペンサー", "ハンドソープ", "ソープディスペンサー", "洗濯用"),
        "water": ("炭酸", "スパークリング", "ウォーターサーバー", "水筒"),
        "coffee": ("コーヒーメーカー", "ドリッパー", "フィルター", "コーヒーミル", "マグカップ"),
    }
    if any(term in title for term in exclusions.get(category_id, ())):
        return False

    if category_id == "tissue":
        tissue_product_terms = (
            "ティッシュペーパー",
            "ボックスティッシュ",
            "箱ティッシュ",
            "ソフトパックティッシュ",
            "パックティッシュ",
            "ポケットティッシュ",
        )
        if not any(term in title for term in tissue_product_terms):
            return False

    if category_id == "dish" and not any(term in title for term in ("食器", "台所", "キッチン", "ジョイ", "キュキュット", "チャーミー", "ヤシノミ")):
        return False

    return True


def fetch_page(category, page):
    params = {
        "applicationId": core.APP_ID,
        "keyword": category["keyword"],
        "NGKeyword": "ふるさと納税",
        "hits": 30,
        "page": page,
        "formatVersion": 2,
        "format": "json",
        "hasReviewFlag": 1,
        "imageFlag": 1,
        "sort": "-reviewCount",
    }
    if core.AFFILIATE_ID:
        params["affiliateId"] = core.AFFILIATE_ID

    url = core.API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "accessKey": core.ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": core.SITE_URL,
            "User-Agent": "daily-cost-jp/0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("Items") or payload.get("items") or []


def fetch_category(category):
    raw_items = fetch_page(category, 1)
    normalized = [core.normalize_item(raw, category) for raw in raw_items]

    excluded = ("ふるさと納税", "返礼品")
    filtered = [
        item
        for item in normalized
        if item.get("price", 0) > 0
        and item.get("url")
        and not any(term in item.get("name", "") for term in excluded)
        and category_is_suitable(category["id"], item.get("name", ""))
    ]

    # Ranking is shipping-inclusive by default, so fetch a second page if the
    # first page does not yield enough safely comparable shipping-inclusive items.
    shipping_items = [item for item in filtered if item.get("postage") == "送料込み"]
    _, ranked = _original_choose_ranked_items(shipping_items)
    if len(ranked) < 5:
        time.sleep(1.1)
        raw_more = fetch_page(category, 2)
        more = [core.normalize_item(raw, category) for raw in raw_more]
        filtered.extend(
            item
            for item in more
            if item.get("price", 0) > 0
            and item.get("url")
            and not any(term in item.get("name", "") for term in excluded)
            and category_is_suitable(category["id"], item.get("name", ""))
        )

    return filtered


core.parse_measure_quantity = safer_parse_measure_quantity
core.parse_count_quantity = safer_parse_count_quantity

_original_choose_ranked_items = core.choose_ranked_items


def choose_ranked_shipping_included(items):
    shipping_included = [item for item in items if item.get("postage") == "送料込み"]
    return _original_choose_ranked_items(shipping_included)


def clean_display_name(name):
    """Remove leading promotional labels for readability; source title is unchanged."""
    text = str(name or "").strip()
    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"^\s*[【\[].{1,60}?[】\]]\s*", "", text)
    text = re.sub(r"^\s*(?:送料無料|送料込|SALE[^ ]*|セール)\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or str(name or "")


def render_product_card_clean(item, rank, metric):
    name = core.html.escape(clean_display_name(item["name"]))
    shop = core.html.escape(item["shop"])
    url = core.html.escape(item["url"], quote=True)
    image = core.html.escape(item["image"], quote=True)
    metric_label = core.METRIC_LABELS[metric]
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
        <div class="unit-price">{core.yen(item["unit_price"])} <span>/ {metric_label}</span></div>
        <div class="purchase-summary">{core.html.escape(purchase_summary(item))}</div>
        <div class="meta-grid">
          <span>{core.html.escape(review)}</span>
          <span>{core.html.escape(point)}</span>
        </div>
        <p class="shop">{shop}</p>
        <a class="buy-button" href="{url}" target="_blank" rel="nofollow sponsored noopener">楽天市場で確認する</a>
      </div>
    </article>
    """


def render_top_picks(category_snapshots):
    cards = []
    for category, metric, ranked in category_snapshots:
        if not ranked or not metric:
            continue
        item = ranked[0]
        label = core.METRIC_LABELS[metric]
        cards.append(f"""
        <a class="top-pick" href="#{core.html.escape(category['id'])}">
          <span class="top-pick-category">{category['emoji']} {core.html.escape(category['name'])}</span>
          <strong>{core.yen(item['unit_price'])}</strong>
          <span class="top-pick-unit">/ {label}</span>
          <small>送料込みの1位を見る →</small>
        </a>
        """)
    if not cards:
        return ""
    return f"""
    <section class="top-picks" aria-label="今日のコスパ1位">
      <div class="top-picks-heading">
        <span>今日のコスパ1位</span>
        <small>送料込み商品から比較</small>
      </div>
      <div class="top-picks-grid">{''.join(cards)}</div>
    </section>
    """


core.choose_ranked_items = choose_ranked_shipping_included
core.render_product_card = render_product_card_clean
core.fetch_category = fetch_category

EXTRA_CSS = r"""
    .purchase-summary { margin-top: 2px; color: #343434; font-size: 13px; font-weight: 800; }
    header { padding: 22px 0 18px; }
    h1 { margin: 10px 0 6px; }
    .lead { font-size: 14px; }
    .updated { margin-top: 8px; }
    main { padding-top: 14px; }
    .top-picks { margin: 0 0 18px; }
    .top-picks-heading {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 10px;
    }
    .top-picks-heading > span { font-size: 20px; font-weight: 800; }
    .top-picks-heading small { color: var(--muted); font-size: 11px; }
    .top-picks-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .top-pick {
      text-decoration: none;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      min-width: 0;
      box-shadow: 0 2px 10px rgba(0,0,0,.025);
    }
    .top-pick-category {
      display: block;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 4px;
    }
    .top-pick strong { color: var(--accent); font-size: 20px; line-height: 1.2; }
    .top-pick-unit { color: var(--muted); font-size: 10px; font-weight: 600; }
    .top-pick small { display: block; color: var(--muted); font-size: 10px; margin-top: 5px; }
    details.info-box { padding: 0; overflow: hidden; }
    details.info-box summary { cursor: pointer; padding: 13px 15px; font-weight: 700; color: var(--text); }
    details.info-box .info-detail { padding: 0 15px 14px; }
    .shipping-chip { color: #176b3a; font-weight: 700; }
    @media (min-width: 760px) {
      .top-picks-grid { grid-template-columns: repeat(3, 1fr); }
    }
"""

IMPROVED_HEAD = core.HTML_HEAD.replace("  </style>", EXTRA_CSS + "\n  </style>")


def build_site_improved():
    core.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    updated_at = datetime.now(ZoneInfo("Asia/Tokyo"))
    category_results = []
    category_snapshots = []
    serializable = {}
    successful_categories = 0

    for index, category in enumerate(core.CATEGORIES):
        error = None
        items = []
        try:
            items = core.fetch_category(category)
            successful_categories += 1
            print(f"{category['name']}: {len(items)} items")
        except Exception as exc:
            error = str(exc)
            print(f"{category['name']}: fetch failed: {exc}", file=sys.stderr)

        metric, ranked = core.choose_ranked_items(items)
        serializable[category["id"]] = {
            "name": category["name"],
            "metric": metric,
            "items": ranked,
            "error": error,
        }
        category_snapshots.append((category, metric, ranked))
        category_results.append(core.render_category(category, items, error=error))

        if index < len(core.CATEGORIES) - 1:
            time.sleep(1.15)

    if successful_categories == 0:
        print("All Rakuten API requests failed; refusing to deploy an empty site.", file=sys.stderr)
        sys.exit(1)

    nav = "".join(
        f'<a href="#{core.html.escape(category["id"])}">{category["emoji"]} {core.html.escape(category["name"])}</a>'
        for category in core.CATEGORIES
    )
    top_picks = render_top_picks(category_snapshots)

    body = f"""
<header>
  <div class="container">
    <span class="eyebrow">毎朝自動更新</span>
    <h1>日用品コスパ比較</h1>
    <p class="lead">楽天市場の日用品を「1個あたり・100gあたり・1Lあたり」で比較。送料込み商品の中から安い順に表示します。</p>
    <p class="updated">最終更新：{updated_at.strftime("%Y年%m月%d日 %H:%M")}（日本時間）</p>
  </div>
</header>
<div class="nav-wrap">
  <nav class="container">{nav}</nav>
</div>
<main class="container">
  {top_picks}
  <details class="info-box">
    <summary>比較方法・注意点</summary>
    <div class="info-detail">
      商品名から数量を高い確度で判定できる商品のみ掲載し、同じ単位に換算しています。ランキングは送料込み商品の商品価格を基準にしています。
      クーポン・一部ポイント還元は単価に含めていません。購入前に楽天市場の商品ページで最新の価格・送料・内容量をご確認ください。
    </div>
  </details>
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
    (core.OUTPUT_DIR / "index.html").write_text(IMPROVED_HEAD + body, encoding="utf-8")

    public_data = {
        "updated_at": updated_at.isoformat(),
        "source": "Rakuten Ichiba API",
        "ranking_basis": "shipping_included_unit_price",
        "categories": serializable,
    }
    (core.OUTPUT_DIR / "data.json").write_text(
        json.dumps(public_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (core.OUTPUT_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + core.SITE_URL + "sitemap.xml\n",
        encoding="utf-8",
    )
    (core.OUTPUT_DIR / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'<url><loc>{core.SITE_URL}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>'
        f'</urlset>\n',
        encoding="utf-8",
    )

    print(f"Built {core.OUTPUT_DIR / 'index.html'}")


core.build_site = build_site_improved

if __name__ == "__main__":
    core.build_site()
