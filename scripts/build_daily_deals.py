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
        image = (
            f'<img src="{html.escape(row["image"], quote=True)}" alt="" loading="lazy">'
            if row["image"] else '<div class="image-placeholder">画像なし</div>'
        )
        cards.append(f'''
<section class="category-section deal-card" id="{html.escape(row['id'])}">
  <div class="deal-rank">{position}</div>
  <div class="deal-image">{image}</div>
  <div class="deal-body">
    <div class="deal-category">{html.escape(row['emoji'])} {html.escape(row['name'])}</div>
    <div class="deal-discount">比較候補の中央値より <strong>{row['discount']:.0f}%安い</strong></div>
    <h2>{html.escape(row['product_name'])}</h2>
    <div class="unit-price">{money(row['unit_price'])} <span>/ {html.escape(row['metric_label'])}</span></div>
    <div class="deal-meta">商品価格 ¥{row['price']:,} ・ {html.escape(row['shop'])}</div>
    <div class="deal-meta">中央値 {money(row['median'])} ・ 送料込み候補 {row['sample']}件で比較</div>
    <div class="deal-actions">
      <a class="buy-button" href="{html.escape(row['url'], quote=True)}" target="_blank" rel="nofollow sponsored noopener">楽天市場で確認する</a>
      <a class="today-category-link" href="../categories/{html.escape(row['id'])}/">カテゴリの安い順を見る</a>
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
:root{{--bg:#fbfaf9;--card:#fff;--text:#252525;--muted:#6b7280;--line:#e8dfda;--accent:#b3261e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}}a{{color:inherit}}.wrap{{width:min(900px,calc(100% - 28px));margin:auto}}header{{padding:27px 0 18px;background:linear-gradient(180deg,#fff8f5,#fbfaf9);border-bottom:1px solid #f0e5df}}.crumb{{font-size:11px;color:var(--muted)}}.eyebrow{{display:inline-block;margin-top:13px;font-size:11px;font-weight:900;color:var(--accent)}}h1{{font-size:clamp(29px,8vw,42px);line-height:1.2;margin:5px 0 9px;letter-spacing:-.03em}}.lead{{max-width:760px;margin:0;color:#5f6368;font-size:13px}}.updated{{margin-top:9px;font-size:10px;color:var(--muted)}}main{{padding:18px 0 38px}}.method{{padding:13px 14px;border:1px solid var(--line);border-radius:14px;background:#fff;font-size:10px;color:#6d645f;margin-bottom:14px}}.deal-card{{position:relative;display:grid;grid-template-columns:90px minmax(0,1fr);gap:13px;margin:10px 0;padding:13px;border:1px solid var(--line);border-radius:17px;background:#fff;box-shadow:0 5px 18px rgba(62,42,32,.04)}}.deal-rank{{position:absolute;left:-6px;top:-6px;width:28px;height:28px;display:grid;place-items:center;border-radius:50%;background:#252525;color:#fff;font-size:12px;font-weight:900}}.deal-image{{width:90px;height:90px;display:grid;place-items:center;overflow:hidden;border:1px solid #eee7e2;border-radius:11px;background:#fff}}.deal-image img{{width:100%;height:100%;object-fit:contain}}.image-placeholder{{font-size:10px;color:#999}}.deal-category{{font-size:11px;font-weight:900;color:#6d625c}}.deal-discount{{font-size:11px;margin-top:1px}}.deal-discount strong{{font-size:18px;color:var(--accent)}}.deal-body h2{{font-size:13px;line-height:1.45;margin:4px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.unit-price{{font-size:18px;font-weight:900}}.unit-price span{{font-size:10px;font-weight:600;color:#666}}.deal-meta{{font-size:9px;color:#777}}.deal-actions{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}}.deal-actions a{{min-height:42px;display:flex;align-items:center;justify-content:center;text-align:center;padding:8px;border-radius:9px;text-decoration:none;font-size:10px;font-weight:900}}.buy-button{{background:var(--accent);color:#fff}}.today-category-link{{border:1px solid var(--line)}}.footnote{{font-size:9px;color:#777;margin-top:15px}}@media(max-width:520px){{.deal-card{{grid-template-columns:76px minmax(0,1fr)}}.deal-image{{width:76px;height:76px}}.deal-actions{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header><div class="wrap"><div class="crumb"><a href="../">日用品コスパ比較</a> › 今日の買い候補</div><span class="eyebrow">毎朝データから自動更新</span><h1>今日の買い候補5選</h1><p class="lead">楽天市場の日用品21カテゴリを送料込み・同一単位で比較し、今日の取得データの中から差が大きい候補だけを自動選出しています。</p><div class="updated">{date_ja} {now:%H:%M} 更新</div></div></header>
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
