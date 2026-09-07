"""Strengthen SEO for all generated category pages without changing ranking logic."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path

SITE_DIR = Path("site")
DATA_PATH = SITE_DIR / "data.json"
BASE_URL = "https://stusaurus.github.io/daily-cost-jp/"

CATEGORIES = {
    "toilet-paper": ("トイレットペーパー", "🧻", "トイレットペーパー"),
    "tissue": ("ティッシュ", "📦", "ティッシュペーパー"),
    "laundry": ("洗濯洗剤", "🧴", "洗濯洗剤"),
    "dish": ("食器用洗剤", "🍽️", "食器用洗剤"),
    "water": ("水・ミネラルウォーター", "💧", "ミネラルウォーター"),
    "coffee": ("コーヒー", "☕", "コーヒー"),
    "softener": ("柔軟剤", "🌸", "柔軟剤"),
    "shampoo": ("シャンプー", "🧴", "シャンプー"),
    "conditioner": ("コンディショナー", "🫧", "コンディショナー・リンス"),
    "body-soap": ("ボディソープ", "🛁", "ボディソープ"),
    "hand-soap": ("ハンドソープ", "🧼", "ハンドソープ"),
    "bath-cleaner": ("お風呂用洗剤", "🛀", "お風呂用洗剤・バスクリーナー"),
    "toilet-cleaner": ("トイレ用洗剤", "🚽", "トイレ用洗剤"),
    "laundry-bleach": ("衣料用漂白剤", "✨", "衣料用漂白剤"),
    "mouthwash": ("マウスウォッシュ", "🦷", "マウスウォッシュ・洗口液"),
    "paper-towel": ("ペーパータオル", "🧻", "ペーパータオル"),
    "garbage-bag-45l": ("45Lゴミ袋", "🗑️", "45Lゴミ袋・ごみ袋"),
    "mask": ("不織布マスク", "😷", "不織布マスク"),
    "toothbrush": ("歯ブラシ", "🪥", "歯ブラシ"),
    "cotton-swab": ("綿棒", "◽", "綿棒"),
    "floor-sheet": ("フローリングシート", "🧹", "フローリングシート"),
}

METRIC_LABELS = {
    "roll": "1ロール",
    "box": "1箱",
    "pack": "1パック",
    "100g": "100g",
    "100ml": "100ml",
    "1L": "1L",
    "sheet": "1枚",
    "piece": "1本",
}


def replace_once(text: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)


def metric_label(category_id: str, payload: dict) -> str:
    data = payload.get("categories", {}).get(category_id, {})
    return METRIC_LABELS.get(data.get("metric"), "同じ単位")


def schema_markup(name: str, category_id: str, description: str) -> str:
    canonical = BASE_URL + f"categories/{category_id}/"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "日用品コスパ比較", "item": BASE_URL},
                    {"@type": "ListItem", "position": 2, "name": "カテゴリ一覧", "item": BASE_URL + "categories/"},
                    {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
                ],
            },
            {
                "@type": "CollectionPage",
                "name": f"{name}の安い順・単価ランキング",
                "description": description,
                "url": canonical,
                "isPartOf": {"@type": "WebSite", "name": "日用品コスパ比較", "url": BASE_URL},
            },
        ],
    }
    return '<script id="category-seo-schema" type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def seo_section(name: str, alias: str, label: str) -> str:
    q = urllib.parse.quote(name)
    safe_name = html.escape(name)
    safe_alias = html.escape(alias)
    safe_label = html.escape(label)
    return f"""
<section class="category-seo-guide" id="compare-guide">
  <h2>{safe_name}はどこが安い？比較するときのポイント</h2>
  <p>{safe_alias}は、商品価格だけでは容量や個数の違いで安さを判断しにくいため、このページでは楽天市場で送料込みと確認できた商品を<strong>{safe_label}あたり</strong>にそろえて比較しています。</p>
  <ul>
    <li><strong>単価で比較：</strong>容量違い・まとめ買いでも{safe_label}あたりに換算</li>
    <li><strong>送料込みを優先：</strong>表示価格だけ安く見える送料別商品を避けて比較</li>
    <li><strong>毎朝更新：</strong>取得できた楽天市場の商品情報をもとにランキングを更新</li>
  </ul>
  <a class="category-search-cta" href="../../products/?q={q}">商品名を指定して楽天の送料込み価格を検索 →</a>
</section>
"""


def faq_section(name: str, label: str) -> str:
    safe_name = html.escape(name)
    safe_label = html.escape(label)
    return f"""
<section class="category-seo-faq" id="category-faq">
  <h2>{safe_name}の価格比較FAQ</h2>
  <details>
    <summary>{safe_name}は何を基準に安い順にしていますか？</summary>
    <p>楽天市場で送料込みと確認でき、商品名から容量や個数を高い確度で読み取れた商品を、{safe_label}あたりの単価に換算して比較しています。</p>
  </details>
  <details>
    <summary>送料はランキング価格に含まれていますか？</summary>
    <p>送料込みの商品を対象に比較しています。クーポンや一部のポイント還元は単価に含めていないため、購入前に楽天市場の商品ページで最終価格をご確認ください。</p>
  </details>
  <details>
    <summary>価格はいつ更新されますか？</summary>
    <p>カテゴリランキングは毎朝自動更新します。特定の商品を今すぐ確認したい場合は、商品名検索からリアルタイムの送料込み購入候補を探せます。</p>
  </details>
</section>
"""


CSS = """
<style id="category-seo-style">
.category-seo-guide,.category-seo-faq{margin:18px 0;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff}
.category-seo-guide h2,.category-seo-faq h2{font-size:18px;line-height:1.4;margin:0 0 9px}
.category-seo-guide p,.category-seo-guide li,.category-seo-faq p{font-size:12px;line-height:1.75;color:#4b5563}
.category-seo-guide ul{margin:10px 0 14px;padding-left:20px}
.category-search-cta{display:block;padding:12px 14px;border-radius:11px;background:#252525;color:#fff;text-decoration:none;text-align:center;font-size:12px;font-weight:900}
.category-seo-faq details{border-top:1px solid var(--line);padding:10px 0}
.category-seo-faq details:first-of-type{border-top:0}
.category-seo-faq summary{cursor:pointer;font-size:12px;font-weight:800;line-height:1.55}
.category-seo-faq p{margin:7px 0 0}
</style>
"""


def enhance_page(category_id: str, name: str, emoji: str, alias: str, payload: dict) -> bool:
    path = SITE_DIR / "categories" / category_id / "index.html"
    if not path.exists():
        return False

    markup = path.read_text(encoding="utf-8")
    label = metric_label(category_id, payload)
    title = f"{name}の安い順比較｜{label}単価・楽天送料込みランキング | 日用品コスパ比較"
    description = (
        f"{alias}を楽天市場の送料込み価格で{label}あたりに換算し、安い順に比較。"
        "毎朝更新の単価ランキングと、商品名から探せるリアルタイム価格検索で買い時を確認できます。"
    )

    markup = replace_once(markup, r"<title>.*?</title>", f"<title>{html.escape(title)}</title>")
    markup = replace_once(
        markup,
        r'<meta name="description" content="[^"]*">',
        f'<meta name="description" content="{html.escape(description, quote=True)}">',
    )
    markup = replace_once(
        markup,
        r"<h1>.*?</h1>",
        f"<h1>{emoji} {html.escape(name)}の安い順・単価ランキング</h1>",
    )
    markup = replace_once(
        markup,
        r'<p class="lead">.*?</p>',
        f'<p class="lead">楽天市場の{html.escape(name)}を送料込み価格で{html.escape(label)}あたりに換算し、今日の安い順に比較します。</p>',
    )

    if 'id="category-seo-style"' not in markup:
        markup = markup.replace("</head>", CSS + "\n" + schema_markup(name, category_id, description) + "\n</head>", 1)

    if 'id="compare-guide"' not in markup:
        summary_end = markup.find("</div>", markup.find('class="category-summary"'))
        if summary_end != -1:
            insert_at = summary_end + len("</div>")
            markup = markup[:insert_at] + "\n" + seo_section(name, alias, label) + markup[insert_at:]
        else:
            markup = markup.replace('<main class="container">', '<main class="container">\n' + seo_section(name, alias, label), 1)

    if 'id="category-faq"' not in markup:
        marker = '<section class="related-categories">'
        if marker in markup:
            markup = markup.replace(marker, faq_section(name, label) + "\n" + marker, 1)
        else:
            markup = markup.replace("</main>", faq_section(name, label) + "\n</main>", 1)

    path.write_text(markup, encoding="utf-8")
    return True


def main() -> None:
    if not DATA_PATH.exists():
        raise SystemExit("site/data.json not found")
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    changed = 0
    for category_id, (name, emoji, alias) in CATEGORIES.items():
        if enhance_page(category_id, name, emoji, alias, payload):
            changed += 1

    print(f"Strengthened category SEO on {changed}/{len(CATEGORIES)} pages.")


if __name__ == "__main__":
    main()
