"""Decision layer for daily-cost-jp.

Turns the site from a passive unit-price ranking into an in-store decision tool.
After the normal growth build it adds:
- a mobile-first "この値段、買い？" calculator on the home page,
- current Rakuten best/median benchmarks,
- optional monthly/annual savings impact,
- a data-derived "今日の買い目安" section on every category page,
- search-oriented titles around "いくらなら安い" intent.

All thresholds are explicitly based on today's eligible Rakuten listings, not a
claim about the entire retail market.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import build_site_growth as growth

core = growth.core
final = growth.final


INPUT_META = {
    "roll": {"input_unit": "ロール", "factor": 1.0, "placeholder": "例：12"},
    "box": {"input_unit": "箱", "factor": 1.0, "placeholder": "例：5"},
    "pack": {"input_unit": "パック", "factor": 1.0, "placeholder": "例：5"},
    "100g": {"input_unit": "g", "factor": 100.0, "placeholder": "例：1800"},
    "100ml": {"input_unit": "ml", "factor": 100.0, "placeholder": "例：1200"},
    "1L": {"input_unit": "L", "factor": 1.0, "placeholder": "例：2"},
    "sheet": {"input_unit": "枚", "factor": 1.0, "placeholder": "例：100"},
    "piece": {"input_unit": "本", "factor": 1.0, "placeholder": "例：6"},
}


def money(value: float) -> str:
    if value >= 100:
        return f"¥{value:,.0f}"
    if value >= 10:
        return f"¥{value:,.1f}"
    return f"¥{value:,.2f}"


def load_benchmarks():
    payload = json.loads((core.OUTPUT_DIR / "data.json").read_text(encoding="utf-8"))
    categories_data = payload.get("categories", {})
    category_map = {c["id"]: c for c in core.CATEGORIES}
    benchmarks = []

    for category_id, data in categories_data.items():
        category = category_map.get(category_id)
        metric = data.get("metric")
        items = data.get("items") or []
        meta = INPUT_META.get(metric)
        if not category or not metric or not meta or not items:
            continue
        prices = sorted(
            float(item.get("unit_price"))
            for item in items
            if item.get("unit_price") is not None and float(item.get("unit_price")) > 0
        )
        if not prices:
            continue
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
        best = prices[0]
        benchmarks.append({
            "id": category_id,
            "name": category["name"],
            "emoji": category["emoji"],
            "metric": metric,
            "metric_label": final.display_metric_label(items[0], metric),
            "input_unit": meta["input_unit"],
            "factor": meta["factor"],
            "placeholder": meta["placeholder"],
            "best": best,
            "median": median,
            "sample": len(prices),
        })
    return benchmarks


DECISION_CSS = r"""
    .decision-tool {
      margin: 14px 0 22px;
      border: 1px solid #e7d9cf;
      border-radius: 18px;
      background: linear-gradient(180deg,#fffaf6 0%,#fff 100%);
      padding: 16px;
      box-shadow: 0 5px 18px rgba(66,47,35,.06);
    }
    .decision-kicker { font-size: 11px; font-weight: 800; color: #b3261e; letter-spacing: .03em; }
    .decision-tool h2 { margin: 3px 0 5px; font-size: 22px; line-height: 1.25; }
    .decision-tool .decision-lead { margin: 0 0 14px; color: #5f6368; font-size: 12px; line-height: 1.6; }
    .decision-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .decision-field { display: flex; flex-direction: column; gap: 5px; }
    .decision-field.wide { grid-column: 1 / -1; }
    .decision-field label { font-size: 11px; font-weight: 800; }
    .decision-field select,.decision-field input {
      min-height: 44px; border: 1px solid #d9d9d9; border-radius: 11px; background: #fff;
      padding: 9px 10px; font-size: 16px; width: 100%; box-sizing: border-box;
    }
    .decision-helper { color: #777; font-size: 10px; margin-top: 2px; }
    .decision-button {
      grid-column: 1 / -1; min-height: 48px; border: 0; border-radius: 12px;
      background: #b3261e; color: #fff; font-size: 15px; font-weight: 900; cursor: pointer;
    }
    .decision-result { display: none; margin-top: 13px; border-radius: 14px; padding: 14px; background: #f8f7f5; }
    .decision-result.show { display: block; }
    .decision-verdict { font-size: 20px; font-weight: 900; margin-bottom: 7px; }
    .decision-result p { margin: 5px 0; font-size: 12px; line-height: 1.55; }
    .decision-result strong { color: #b3261e; }
    .decision-impact { margin-top: 8px !important; padding-top: 8px; border-top: 1px dashed #d7cec7; }
    .decision-note { color: #777; font-size: 9px !important; }
    .buy-line-box {
      border: 1px solid #eaded5; background: #fffaf6; border-radius: 14px; padding: 14px;
      margin: 0 0 18px;
    }
    .buy-line-box h2 { margin: 0 0 7px; font-size: 18px; }
    .buy-line-number { font-size: 24px; font-weight: 900; color: #b3261e; }
    .buy-line-box p { margin: 5px 0; color: #555; font-size: 12px; line-height: 1.6; }
    @media (max-width: 420px) { .decision-grid { grid-template-columns: 1fr 1fr; } }
"""


def decision_markup(benchmarks):
    options = "".join(
        f'<option value="{html.escape(b["id"])}">{b["emoji"]} {html.escape(b["name"])}</option>'
        for b in benchmarks
    )
    data_json = json.dumps({b["id"]: b for b in benchmarks}, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section class="decision-tool" id="buy-judge" aria-label="店頭価格の買い判定">
  <div class="decision-kicker">店頭で10秒判定</div>
  <h2>この値段、買い？</h2>
  <p class="decision-lead">スーパーやドラッグストアで見つけた価格を、今日の楽天・送料込み候補と同じ単位に直して比較します。</p>
  <div class="decision-grid">
    <div class="decision-field wide">
      <label for="judge-category">商品カテゴリ</label>
      <select id="judge-category">{options}</select>
    </div>
    <div class="decision-field">
      <label for="judge-price">店頭価格</label>
      <input id="judge-price" inputmode="decimal" type="number" min="0" step="1" placeholder="例：498">
    </div>
    <div class="decision-field">
      <label for="judge-quantity">内容量 <span id="judge-unit"></span></label>
      <input id="judge-quantity" inputmode="decimal" type="number" min="0" step="any">
    </div>
    <div class="decision-field wide">
      <label for="judge-monthly">月に使う量（任意） <span id="judge-month-unit"></span></label>
      <input id="judge-monthly" inputmode="decimal" type="number" min="0" step="any" placeholder="年間差額も見たい時だけ入力">
      <span class="decision-helper">入力すると、今日の楽天最安候補との差を月額・年額でも表示します。</span>
    </div>
    <button class="decision-button" id="judge-button" type="button">買いか判定する</button>
  </div>
  <div class="decision-result" id="judge-result" aria-live="polite"></div>
  <p class="decision-note">※「買い／見送り」は当サイトが取得した今日の楽天市場・送料込み比較候補を基準にした目安です。市場全体の最安値を保証するものではありません。</p>
</section>
<script>
(() => {{
  const data = {data_json};
  const cat = document.getElementById('judge-category');
  const price = document.getElementById('judge-price');
  const qty = document.getElementById('judge-quantity');
  const monthly = document.getElementById('judge-monthly');
  const unit = document.getElementById('judge-unit');
  const monthUnit = document.getElementById('judge-month-unit');
  const result = document.getElementById('judge-result');
  const button = document.getElementById('judge-button');
  const yen = (v) => v >= 100 ? '¥' + v.toLocaleString('ja-JP', {{maximumFractionDigits:0}}) :
    v >= 10 ? '¥' + v.toFixed(1) : '¥' + v.toFixed(2);
  function sync() {{
    const d = data[cat.value]; if (!d) return;
    unit.textContent = '（' + d.input_unit + '）';
    monthUnit.textContent = '（' + d.input_unit + '/月）';
    qty.placeholder = d.placeholder;
  }}
  function judge() {{
    const d = data[cat.value];
    const p = Number(price.value), q = Number(qty.value);
    if (!d || !p || !q || p <= 0 || q <= 0) {{
      result.className = 'decision-result show';
      result.innerHTML = '<div class="decision-verdict">価格と内容量を入力してください</div>';
      return;
    }}
    const comparableUnits = q / d.factor;
    const mine = p / comparableUnits;
    let verdict, message;
    if (mine <= d.best * 1.05) {{ verdict = '🔥 かなり買い'; message = '今日の楽天最安候補と同等か、それより安い水準です。'; }}
    else if (mine <= d.median * 0.90) {{ verdict = '◎ 買い'; message = '今日の楽天比較候補の中央値より10%以上安い水準です。'; }}
    else if (mine <= d.median * 1.05) {{ verdict = '○ ほぼ相場'; message = '今日の楽天比較候補の中心価格に近い水準です。'; }}
    else {{ verdict = '△ 急がなければ見送り'; message = '今日の楽天比較候補の中央値より高めです。'; }}
    let impact = '';
    const m = Number(monthly.value);
    if (m > 0) {{
      const monthlyComparable = m / d.factor;
      const diffMonth = (mine - d.best) * monthlyComparable;
      const diffYear = diffMonth * 12;
      if (Math.abs(diffYear) >= 1) {{
        impact = '<p class="decision-impact">月の使用量で換算すると、今日の楽天最安候補より' +
          (diffYear > 0 ? '<strong>年間約' + yen(Math.abs(diffYear)) + '高い</strong>' : '<strong>年間約' + yen(Math.abs(diffYear)) + '安い</strong>') + '計算です。</p>';
      }}
    }}
    result.className = 'decision-result show';
    result.innerHTML = '<div class="decision-verdict">' + verdict + '</div>' +
      '<p>あなたの店頭単価：<strong>' + yen(mine) + ' / ' + d.metric_label + '</strong></p>' +
      '<p>今日の楽天最安候補：' + yen(d.best) + ' ／ 比較候補の中央値：' + yen(d.median) + '</p>' +
      '<p>' + message + '</p>' + impact;
    if (typeof window.gtag === 'function') {{
      window.gtag('event', 'buy_judge', {{category_id:d.id, verdict:verdict, store_unit_price:Number(mine.toFixed(2)), benchmark_best:Number(d.best.toFixed(2))}});
    }}
  }}
  cat.addEventListener('change', sync); button.addEventListener('click', judge); sync();
}})();
</script>
"""


def add_decision_tool(benchmarks):
    path = core.OUTPUT_DIR / "index.html"
    markup = path.read_text(encoding="utf-8")
    if 'id="buy-judge"' in markup:
        return
    markup = markup.replace("</style>", DECISION_CSS + "\n  </style>", 1)
    block = decision_markup(benchmarks)
    marker = '<section class="top-picks"'
    if marker in markup:
        markup = markup.replace(marker, block + "\n" + marker, 1)
    else:
        markup = markup.replace('<main class="container">', '<main class="container">\n' + block, 1)
    path.write_text(markup, encoding="utf-8")


def enhance_category_pages(benchmarks):
    by_id = {b["id"]: b for b in benchmarks}
    for category in core.CATEGORIES:
        b = by_id.get(category["id"])
        if not b:
            continue
        path = core.OUTPUT_DIR / "categories" / category["id"] / "index.html"
        if not path.exists():
            continue
        markup = path.read_text(encoding="utf-8")
        if "buy-line-box" in markup:
            continue
        buy_line = b["median"] * 0.90
        box = f"""
  <section class="buy-line-box">
    <h2>{html.escape(category['name'])}、今日は「いくらなら安い？」</h2>
    <div class="buy-line-number">{money(buy_line)} / {html.escape(b['metric_label'])} 以下が買い目安</div>
    <p>今日取得できた楽天市場の送料込み比較候補では、最安が <strong>{money(b['best'])}</strong>、中央値が <strong>{money(b['median'])}</strong> / {html.escape(b['metric_label'])}。店頭で中央値より約10%以上安ければ、今日の楽天候補と比べても「買い」と判断しやすい水準です。</p>
    <p><a href="../../#buy-judge">店頭価格を入力して買い判定する →</a></p>
    <p style="font-size:9px;color:#777">※当日の楽天掲載候補（{b['sample']}件）を基準にした比較目安で、市場全体の平均価格ではありません。</p>
  </section>
"""
        markup = markup.replace("</style>", DECISION_CSS + "\n  </style>", 1)
        summary = '<div class="category-summary">'
        pos = markup.find(summary)
        if pos >= 0:
            end = markup.find('</div>', pos)
            if end >= 0:
                end += len('</div>')
                markup = markup[:end] + "\n" + box + markup[end:]
        # Search-intent title/description without pretending the threshold is universal.
        title = f"{category['name']}はいくらなら安い？今日の単価・買い目安 | 日用品コスパ比較"
        desc = f"{category['name']}の今日の楽天単価を送料込みで比較。店頭価格が買いか判断できる買い目安と安い順ランキングを毎朝更新。"
        markup = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", markup, count=1)
        markup = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(desc, quote=True)}">', markup, count=1)
        path.write_text(markup, encoding="utf-8")


def main():
    growth.main()
    benchmarks = load_benchmarks()
    add_decision_tool(benchmarks)
    enhance_category_pages(benchmarks)
    print(f"Added buy-decision utility and buy-line content for {len(benchmarks)} categories.")


if __name__ == "__main__":
    main()
