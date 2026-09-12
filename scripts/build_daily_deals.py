"""Generate a conservative, fully automatic daily deals landing page.

The page is rebuilt from site/data.json on every scheduled Pages build. It also
emits a small machine-readable social payload so a connected social publisher
can post the same daily data without a human writing copy.
"""
from __future__ import annotations

import html
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from sale_quantity import purchase_summary

SITE = "https://stusaurus.github.io/daily-cost-jp/"
DATA = Path("site/data.json")
HOME = Path("site/index.html")
TODAY_DIR = Path("site/today")
SOCIAL_DIR = Path("site/social")
SITEMAP = Path("site/sitemap.xml")

METRIC_LABELS = {
    "roll": "1ロール",
    "box": "1箱",
    "pack": "1パック",
    "100g": "100g",
    "100ml": "100ml",
    "1L": "1L",
    "sheet": "1枚",
    "piece": "1個",
}


def fnum(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: float) -> str:
    if value >= 100:
        return f"¥{value:,.0f}"
    if value >= 10:
        return f"¥{value:,.1f}"
    return f"¥{value:,.2f}"


def choose_category(category_id: str, category: dict):
    raw_items = category.get("items") or []
    valid = []
    for item in raw_items:
        unit_price = fnum(item.get("unit_price"))
        confidence = fnum(item.get("confidence"))
        metric = str(item.get("metric") or "")
        if unit_price <= 0 or confidence < 0.84:
            continue
        if item.get("postage") != "送料込み":
            continue
        if metric not in METRIC_LABELS:
            continue
        if not str(item.get("url") or "").strip():
            continue
        valid.append(item)

    if len(valid) < 5:
        return None

    metric_counts = Counter(str(item.get("metric") or "") for item in valid)
    metric = metric_counts.most_common(1)[0][0]
    same_metric = [item for item in valid if str(item.get("metric") or "") == metric]
    if len(same_metric) < 5:
        return None

    prices = sorted(fnum(item.get("unit_price")) for item in same_metric)
    median = float(statistics.median(prices))
    if median <= 0:
        return None

    ordered = sorted(same_metric, key=lambda item: fnum(item.get("unit_price")))

    # Very large apparent discounts on unit-price data are usually parsing or
    # pack-size edge cases. Do not turn them into clickbait. Prefer the first
    # candidate that is at least 45% of the category median and is not wildly
    # separated from the next comparable item.
    candidate = None
    filtered_outliers = 0
    for index, item in enumerate(ordered):
        unit_price = fnum(item.get("unit_price"))
        next_price = fnum(ordered[index + 1].get("unit_price")) if index + 1 < len(ordered) else median
        too_low_vs_median = unit_price < median * 0.45
        isolated = next_price > 0 and unit_price < next_price * 0.55
        if too_low_vs_median and isolated:
            filtered_outliers += 1
            continue
        candidate = item
        break

    if not candidate:
        return None

    best = fnum(candidate.get("unit_price"))
    if best <= 0 or best >= median:
        return None
    discount = (median - best) / median * 100

    # Only publish useful but believable differences automatically.
    if discount < 8 or discount > 55:
        return None

    return {
        "id": category_id,
        "name": str(category.get("name") or category_id),
        "emoji": str(category.get("emoji") or "🛒"),
        "metric": metric,
        "metric_label": METRIC_LABELS[metric],
        "unit_price": best,
        "median": median,
        "discount": discount,
        "sample": len(same_metric),
        "filtered_outliers": filtered_outliers,
        "product_name": str(candidate.get("name") or ""),
        "price": int(fnum(candidate.get("price"))),
        "image": str(candidate.get("image") or ""),
        "url": str(candidate.get("url") or ""),
        "shop": str(candidate.get("shop") or "ショップ情報なし"),
        "sale_quantity_label": candidate.get("sale_quantity_label"),
    }


def build_rows(payload: dict):
    rows = []
    for category_id, category in (payload.get("categories") or {}).items():
        row = choose_category(category_id, category or {})
        if row:
            rows.append(row)
    rows.sort(key=lambda row: (-row["discount"], row["unit_price"]))
    return rows[:5]


def render_page(rows: list[dict], now: datetime) -> str:
    date_ja = f"{now.year}年{now.month}月{now.day}日"
    cards = []
    schema_items = []
    for position, row in enumerate(rows, start=1):
        fallback = (
            f'<div class="image-placeholder"><span class="fallback-emoji">{html.escape(row["emoji"])}</span>'
            f'<span>{html.escape(row["name"])}</span></div>'
        )
        if row["image"]:
            image = (
                f'<img src="{html.escape(row["image"], quote=True)}" '
                f'alt="{html.escape(row["product_name"], quote=True)}" loading="lazy" decoding="async" '
                f'onerror="this.hidden=true;this.nextElementSibling.hidden=false">'
                f'<div class="image-placeholder" hidden><span class="fallback-emoji">{html.escape(row["emoji"])}</span>'
                f'<span>{html.escape(row["name"])}</span></div>'
            )
        else:
            image = fallback

        cards.append(f'''
<section class="category-section deal-card" id="{html.escape(row['id'])}">
  <div class="deal-visual">
    <div class="deal-rank">{position}</div>
    <a class="deal-image" href="{html.escape(row['url'], quote=True)}" target="_blank" rel="nofollow sponsored noopener">{image}</a>
  </div>
  <div class="deal-body">
    <div class="deal-topline">
      <span class="category-chip">{html.escape(row['emoji'])} {html.escape(row['name'])}</span>
      <span class="discount-chip"><strong>{row['discount']:.0f}%</strong> 安い</span>
    </div>
    <div class="discount-note">今日取得した比較候補の中央値より</div>
    <h2>{html.escape(row['product_name'])}</h2>
    <div class="price-panel">
      <div class="unit-price">{money(row['unit_price'])} <span>/ {html.escape(row['metric_label'])}</span></div>
      <div class="deal-purchase">{html.escape(purchase_summary(row))}</div>
    </div>
    <div class="deal-details">
      <div><span>ショップ</span><strong>{html.escape(row['shop'])}</strong></div>
      <div><span>比較基準</span><strong>中央値 {money(row['median'])} ・ 送料込み {row['sample']}件</strong></div>
    </div>
    <div class="deal-actions">
      <a class="buy-button" href="{html.escape(row['url'], quote=True)}" target="_blank" rel="nofollow sponsored noopener">楽天市場で価格を見る</a>
      <a class="today-category-link" href="../categories/{html.escape(row['id'])}/">このカテゴリをもっと比較する</a>
    </div>
  </div>
</section>''')
        schema_items.append({
            "@type": "ListItem",
            "position": position,
            "name": f"{row['name']}：{row['product_name']}",
            "url": f"{SITE}categories/{row['id']}/",
        })

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{date_ja} 今日の買い候補",
        "itemListElement": schema_items,
    }, ensure_ascii=False)

    return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>今日の買い候補5選｜楽天送料込み単価比較 {date_ja}</title>
<meta name="description" content="{date_ja}に取得した楽天市場の日用品データから、送料込み・同一単位で比較できる候補を自動分析。極端な外れ値を除き、中央値より安い買い候補を掲載します。">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{SITE}today/">
<meta property="og:title" content="今日の買い候補5選｜{date_ja}">
<meta property="og:description" content="楽天市場の日用品を送料込み・単価換算で毎朝自動比較。">
<meta property="og:url" content="{SITE}today/">
<script type="application/ld+json">{schema}</script>
<style>
:root{{--bg:#f8f6f4;--card:#fff;--text:#252525;--muted:#6b7280;--line:#eadfd9;--accent:#b3261e;--soft:#fff5f2}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.65}}a{{color:inherit}}.wrap{{width:min(960px,calc(100% - 24px));margin:auto}}header{{padding:28px 0 22px;background:linear-gradient(180deg,#fff8f5,#f8f6f4);border-bottom:1px solid #eee1da}}.crumb{{font-size:12px;color:var(--muted)}}.eyebrow{{display:inline-flex;align-items:center;gap:6px;margin-top:15px;padding:5px 9px;border-radius:999px;background:#fff0ec;font-size:11px;font-weight:900;color:var(--accent)}}h1{{font-size:clamp(30px,8vw,44px);line-height:1.18;margin:8px 0 10px;letter-spacing:-.03em}}.lead{{max-width:760px;margin:0;color:#5f6368;font-size:14px}}.updated{{margin-top:9px;font-size:11px;color:var(--muted)}}main{{padding:18px 0 42px}}.method{{padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:#fff;font-size:11px;color:#6d645f;margin-bottom:18px}}.deal-card{{position:relative;margin:18px 0;border:1px solid var(--line);border-radius:22px;background:#fff;box-shadow:0 10px 28px rgba(62,42,32,.07);overflow:hidden}}.deal-visual{{position:relative;padding:14px;background:linear-gradient(180deg,#fff8f5,#fff)}}.deal-rank{{position:absolute;z-index:2;left:24px;top:24px;width:34px;height:34px;display:grid;place-items:center;border-radius:50%;background:#252525;color:#fff;font-size:14px;font-weight:900;box-shadow:0 4px 12px rgba(0,0,0,.15)}}.deal-image{{height:210px;display:flex;align-items:center;justify-content:center;overflow:hidden;border:1px solid #eee5e0;border-radius:16px;background:#fff;text-decoration:none}}.deal-image img{{display:block;width:100%;height:100%;object-fit:contain;padding:10px}}.image-placeholder{{width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:linear-gradient(135deg,#fff8f5,#f7f3f0);color:#7a6c64;font-size:13px;font-weight:800}}.fallback-emoji{{font-size:56px;line-height:1}}.deal-body{{padding:17px 16px 19px}}.deal-topline{{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap}}.category-chip{{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;background:#f5f2f0;font-size:12px;font-weight:900;color:#5f554f}}.discount-chip{{display:inline-flex;align-items:baseline;gap:3px;padding:5px 9px;border-radius:999px;background:#fff0ec;color:var(--accent);font-size:12px;font-weight:900}}.discount-chip strong{{font-size:20px;line-height:1}}.discount-note{{margin-top:7px;font-size:11px;color:#8a7f79}}.deal-body h2{{font-size:18px;line-height:1.45;margin:7px 0 11px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}.price-panel{{padding:13px 14px;border-radius:15px;background:#fff8f5;border:1px solid #f1e1da}}.unit-price{{font-size:30px;line-height:1.2;font-weight:950;letter-spacing:-.03em}}.unit-price span{{font-size:12px;font-weight:700;color:#6c625d}}.deal-purchase{{margin-top:4px;font-size:14px;font-weight:850;color:#343434}}.deal-details{{display:grid;gap:7px;margin-top:12px;padding:12px 13px;border-radius:13px;background:#faf9f8}}.deal-details div{{display:grid;grid-template-columns:72px minmax(0,1fr);gap:8px;align-items:start}}.deal-details span{{font-size:10px;color:#91857f}}.deal-details strong{{font-size:11px;line-height:1.45;font-weight:750;color:#514944;overflow-wrap:anywhere}}.deal-actions{{display:grid;gap:8px;margin-top:14px}}.deal-actions a{{min-height:50px;display:flex;align-items:center;justify-content:center;text-align:center;padding:10px 12px;border-radius:12px;text-decoration:none;font-size:13px;font-weight:900}}.buy-button{{background:var(--accent);color:#fff;box-shadow:0 5px 14px rgba(179,38,30,.18)}}.today-category-link{{border:1px solid var(--line);background:#fff;color:#5d514b}}.footnote{{font-size:10px;color:#777;margin-top:18px}}@media(min-width:760px){{.deal-card{{display:grid;grid-template-columns:minmax(280px,38%) minmax(0,1fr)}}.deal-visual{{padding:18px}}.deal-image{{height:100%;min-height:290px}}.deal-body{{padding:22px 22px 24px}}.deal-body h2{{font-size:20px}}.deal-actions{{grid-template-columns:1.25fr .9fr}}.deal-actions a{{font-size:14px}}}}
</style>
</head>
<body>
<header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 今日の買い候補</div><span class="eyebrow">📅 毎朝データから自動更新</span><h1>今日の買い候補5選</h1><p class="lead">楽天市場の日用品21カテゴリを送料込み・同一単位で比較。今日の取得データから、差が大きく信頼性の高い候補だけを見やすくまとめています。</p><div class="updated">{date_ja} {now:%H:%M} 更新</div></div></header>
<main class="wrap"><div class="method">信頼性優先：単価計算の信頼度が高い商品だけを使い、極端に安すぎる単独データは外れ値として自動除外します。クーポン・ポイントは比較に含めません。</div>{''.join(cards)}<p class="footnote">※「安い」は当サイトが当日取得できた楽天市場の比較候補内での目安です。市場全体の最安値を保証するものではありません。当サイトは楽天アフィリエイトを利用しています。</p></main>
</body></html>'''


def build_social(rows: list[dict], now: datetime):
    date_short = f"{now.month}/{now.day}"
    bullets = []
    for row in rows[:3]:
        bullets.append(f"・{row['name']} 約{row['discount']:.0f}%安い")
    text = (
        f"【{date_short} 今日の日用品買い候補】\n"
        + "\n".join(bullets)
        + f"\n\n送料込み・単価換算で毎朝自動比較。\n{SITE}today/"
        + "\n※当日取得できた比較候補内の目安"
    )
    return {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "url": f"{SITE}today/",
        "text": text,
        "items": rows,
    }


def inject_home(rows: list[dict], now: datetime):
    if not HOME.exists() or not rows:
        return
    markup = HOME.read_text(encoding="utf-8")
    import re
    markup = re.sub(r'<section id="today-deals-entry".*?</section>\s*', '', markup, flags=re.DOTALL)
    top = rows[0]
    block = f'''<section id="today-deals-entry" style="margin:12px 0 20px;padding:15px;border:1px solid #ecd8cf;border-radius:17px;background:linear-gradient(180deg,#fff8f5,#fff)">
  <div style="font-size:10px;font-weight:900;color:#b3261e">📅 {now.month}/{now.day} 毎朝自動更新</div>
  <strong style="display:block;margin-top:2px;font-size:16px">今日の買い候補5選</strong>
  <p style="margin:4px 0 9px;font-size:11px;color:#6b7280">いま最も差が大きいのは {html.escape(top['name'])}。比較候補の中央値より約{top['discount']:.0f}%安い候補があります。</p>
  <a href="today/" style="display:block;padding:10px 12px;border-radius:10px;background:#b3261e;color:#fff;text-align:center;text-decoration:none;font-size:11px;font-weight:900">今日の5選を見る →</a>
</section>'''
    if '<main class="container">' in markup:
        markup = markup.replace('<main class="container">', '<main class="container">\n' + block, 1)
    else:
        markup = markup.replace('</header>', '</header>\n' + block, 1)
    HOME.write_text(markup, encoding="utf-8")


def update_sitemap():
    if not SITEMAP.exists():
        return
    text = SITEMAP.read_text(encoding="utf-8")
    url = f"{SITE}today/"
    if url in text:
        return
    entry = f'<url><loc>{url}</loc></url>'
    text = text.replace('</urlset>', entry + '\n</urlset>')
    SITEMAP.write_text(text, encoding="utf-8")


def main():
    if not DATA.exists():
        raise SystemExit("site/data.json not found")
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    rows = build_rows(payload)
    if not rows:
        print("No conservative daily deals available; keeping site without today page")
        return

    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    TODAY_DIR.mkdir(parents=True, exist_ok=True)
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)
    (TODAY_DIR / "index.html").write_text(render_page(rows, now), encoding="utf-8")
    social = build_social(rows, now)
    (TODAY_DIR / "data.json").write_text(json.dumps(social, ensure_ascii=False, indent=2), encoding="utf-8")
    (SOCIAL_DIR / "latest.json").write_text(json.dumps(social, ensure_ascii=False, indent=2), encoding="utf-8")
    (SOCIAL_DIR / "latest.txt").write_text(social["text"] + "\n", encoding="utf-8")
    inject_home(rows, now)
    update_sitemap()
    print("Generated conservative daily deals:", ", ".join(f"{r['name']}({r['discount']:.0f}%)" for r in rows))


if __name__ == "__main__":
    main()
