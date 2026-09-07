from pathlib import Path
import html
import json
import statistics

PAGE = Path("site/index.html")
DATA = Path("site/data.json")

if not PAGE.exists() or not DATA.exists():
    raise SystemExit("site/index.html or site/data.json not found")

markup = PAGE.read_text(encoding="utf-8")
if 'id="daily-buy-picks"' in markup:
    print("Daily buy picks already present")
    raise SystemExit(0)

payload = json.loads(DATA.read_text(encoding="utf-8"))
categories = payload.get("categories", {})

rows = []
for category_id, category in categories.items():
    items = [
        item for item in (category.get("items") or [])
        if item.get("unit_price") is not None
        and float(item.get("unit_price") or 0) > 0
        and item.get("postage") == "送料込み"
    ]
    if len(items) < 3:
        continue

    prices = sorted(float(item["unit_price"]) for item in items)
    best = prices[0]
    median = float(statistics.median(prices))
    if median <= 0 or best >= median:
        continue

    discount = (median - best) / median * 100
    metric = category.get("metric") or items[0].get("metric") or ""
    rows.append({
        "id": category_id,
        "name": category.get("name") or category_id,
        "best": best,
        "median": median,
        "discount": discount,
        "metric": metric,
        "sample": len(items),
    })

rows.sort(key=lambda row: (-row["discount"], row["best"]))
picks = rows[:3]

if not picks:
    print("No suitable daily buy picks")
    raise SystemExit(0)

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

def money(value: float) -> str:
    if value >= 100:
        return f"¥{value:,.0f}"
    if value >= 10:
        return f"¥{value:,.1f}"
    return f"¥{value:,.2f}"


def badge(discount: float) -> str:
    if discount >= 25:
        return "🔥 かなり安い"
    if discount >= 15:
        return "◎ 買い候補"
    if discount >= 8:
        return "○ やや安い"
    return "△ 差は小さめ"

cards = []
for row in picks:
    label = METRIC_LABELS.get(row["metric"], row["metric"] or "同一単位")
    cards.append(f'''
      <a class="daily-pick-card" href="categories/{html.escape(row['id'])}/" data-daily-pick="{html.escape(row['id'])}" data-discount="{row['discount']:.1f}">
        <div class="daily-pick-top"><span class="daily-pick-category">{html.escape(row['name'])}</span><span class="daily-pick-badge">{badge(row['discount'])}</span></div>
        <div class="daily-pick-discount">比較候補の中央値より <strong>{row['discount']:.0f}%安い</strong></div>
        <div class="daily-pick-price"><strong>{money(row['best'])}</strong> / {html.escape(label)}</div>
        <div class="daily-pick-meta">中央値 {money(row['median'])} ・ 送料込み候補 {row['sample']}件で比較</div>
        <div class="daily-pick-cta">1位の候補を見る →</div>
      </a>''')

css = r'''
.daily-buy-picks{margin:16px 0 22px;padding:16px;border:1px solid #f0d8c4;border-radius:18px;background:linear-gradient(180deg,#fff9f1 0%,#fff 100%);box-shadow:0 5px 18px rgba(86,55,24,.05)}
.daily-buy-picks h2{margin:3px 0 4px;font-size:22px;line-height:1.3}.daily-pick-kicker{font-size:11px;font-weight:900;color:#a14b00;letter-spacing:.03em}.daily-pick-lead{margin:0 0 12px;color:#5f6368;font-size:11px;line-height:1.6}.daily-pick-grid{display:grid;gap:9px}.daily-pick-card{display:block;padding:13px;border:1px solid #eadfD4;border-radius:13px;background:#fff;text-decoration:none;color:inherit}.daily-pick-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.daily-pick-category{font-size:14px;font-weight:900}.daily-pick-badge{font-size:10px;font-weight:900;white-space:nowrap;color:#a14b00;background:#fff4e6;padding:3px 7px;border-radius:999px}.daily-pick-discount{margin-top:7px;font-size:12px}.daily-pick-discount strong{font-size:18px;color:#b3261e}.daily-pick-price{margin-top:3px;font-size:11px;color:#555}.daily-pick-price strong{font-size:18px;color:#252525}.daily-pick-meta{margin-top:3px;font-size:9px;color:#777;line-height:1.5}.daily-pick-cta{margin-top:8px;font-size:11px;font-weight:900;color:#b3261e}.daily-pick-note{margin:9px 0 0;font-size:9px;color:#777;line-height:1.55}@media(min-width:760px){.daily-pick-grid{grid-template-columns:repeat(3,1fr)}}
'''
markup = markup.replace("</style>", css + "\n</style>", 1)

section = f'''
<section class="daily-buy-picks" id="daily-buy-picks" aria-label="今日の買い候補3選">
  <div class="daily-pick-kicker">毎朝データから自動選出</div>
  <h2>今日の買い候補3選</h2>
  <p class="daily-pick-lead">日用品21カテゴリの中から、今日取得できた楽天市場の<strong>送料込み・同一単位で比較できる候補</strong>について、最安値と中央値の差が大きいカテゴリを3つ選んでいます。</p>
  <div class="daily-pick-grid">{''.join(cards)}</div>
  <p class="daily-pick-note">※「安い」は当サイトが本日取得・比較できた候補内での目安です。市場全体の最安値を保証するものではなく、クーポン・ポイントは含みません。</p>
</section>
<script>
(() => {{
  document.addEventListener('click', (e) => {{
    const a = e.target.closest('[data-daily-pick]');
    if (!a || typeof window.gtag !== 'function') return;
    window.gtag('event', 'daily_pick_click', {{
      category_id: a.dataset.dailyPick || '',
      discount_vs_median: Number(a.dataset.discount || 0)
    }});
  }});
}})();
</script>
'''

anchor = '<section class="home-ranking-hero"'
if anchor in markup:
    markup = markup.replace(anchor, section + "\n" + anchor, 1)
else:
    anchor = '<section class="top-picks"'
    if anchor in markup:
        markup = markup.replace(anchor, section + "\n" + anchor, 1)
    else:
        markup = markup.replace('</main>', section + '\n</main>', 1)

PAGE.write_text(markup, encoding="utf-8")
print("Added daily buy picks:", ", ".join(f"{p['name']}({p['discount']:.0f}% off median)" for p in picks))
