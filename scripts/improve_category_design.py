"""Polish generated category pages without changing ranking or SEO logic."""
from __future__ import annotations

import html
import urllib.parse
from pathlib import Path

SITE_DIR = Path("site/categories")

CATEGORIES = {
    "toilet-paper": "トイレットペーパー",
    "tissue": "ティッシュ",
    "laundry": "洗濯洗剤",
    "dish": "食器用洗剤",
    "water": "水・ミネラルウォーター",
    "coffee": "コーヒー",
    "softener": "柔軟剤",
    "shampoo": "シャンプー",
    "conditioner": "コンディショナー",
    "body-soap": "ボディソープ",
    "hand-soap": "ハンドソープ",
    "bath-cleaner": "お風呂用洗剤",
    "toilet-cleaner": "トイレ用洗剤",
    "laundry-bleach": "衣料用漂白剤",
    "mouthwash": "マウスウォッシュ",
    "paper-towel": "ペーパータオル",
    "garbage-bag-45l": "45Lゴミ袋",
    "mask": "不織布マスク",
    "toothbrush": "歯ブラシ",
    "cotton-swab": "綿棒",
    "floor-sheet": "フローリングシート",
}

CSS = r"""
<style id="category-design-v1">
.category-page-hero{
  padding:22px 0 20px;
  background:linear-gradient(180deg,#faf7f3 0%,#fff 100%);
  border-bottom:1px solid var(--line);
}
.category-page-hero .breadcrumb{margin-bottom:13px}
.category-page-hero h1{margin:7px 0 8px;line-height:1.32;letter-spacing:-.02em}
.category-page-hero .lead{max-width:720px;line-height:1.75}
.category-page-hero .updated{margin-top:9px;font-size:10px;color:var(--muted)}
.category-quick-panel{
  margin:14px 0 16px;
  padding:13px;
  border:1px solid var(--line);
  border-radius:16px;
  background:#fff;
  box-shadow:0 6px 22px rgba(37,37,37,.05);
}
.category-proof-row{
  display:flex;
  gap:6px;
  overflow-x:auto;
  padding:0 0 10px;
  scrollbar-width:none;
}
.category-proof-row::-webkit-scrollbar{display:none}
.category-proof-row span{
  flex:0 0 auto;
  padding:5px 8px;
  border-radius:999px;
  background:#f5f1ed;
  color:#5d514a;
  font-size:10px;
  font-weight:800;
  white-space:nowrap;
}
.category-quick-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.category-quick-actions a{
  display:flex;
  min-height:66px;
  padding:11px 10px;
  border-radius:12px;
  text-decoration:none;
  align-items:flex-start;
  justify-content:center;
  flex-direction:column;
  line-height:1.35;
}
.category-quick-actions strong{font-size:12px;font-weight:900}
.category-quick-actions small{display:block;margin-top:4px;font-size:9px;font-weight:600;opacity:.72}
.category-ranking-jump{background:#252525;color:#fff}
.category-quick-search{border:1px solid #cfc5bd;background:#fff;color:#252525}
.category-summary{
  margin:0 0 14px;
  padding:11px 13px;
  border-radius:12px;
  background:#fafafa;
  font-size:11px;
  line-height:1.7;
}
.category-seo-guide,.category-seo-faq{box-shadow:0 4px 16px rgba(37,37,37,.035)}
.category-seo-guide{margin-top:14px}
.category-seo-guide ul{display:grid;gap:5px}
.category-search-cta{min-height:44px;display:flex;align-items:center;justify-content:center}
.category-section{scroll-margin-top:12px}
.category-section .section-heading{
  margin-top:22px;
  padding-top:4px;
}
.category-section .section-heading h2{font-size:20px;letter-spacing:-.01em}
.related-categories .category-pages-grid{gap:7px}
.related-categories .category-page-link{background:#fafafa}
@media (min-width:760px){
  .category-quick-panel{padding:16px}
  .category-quick-actions a{min-height:72px;padding:13px 16px}
  .category-quick-actions strong{font-size:14px}
  .category-quick-actions small{font-size:10px}
}
</style>
"""


def quick_panel(category_id: str, name: str) -> str:
    query = urllib.parse.quote(name)
    safe_name = html.escape(name)
    return f"""
<section class="category-quick-panel" aria-label="{safe_name}の比較メニュー">
  <div class="category-proof-row" aria-label="比較条件">
    <span>✓ 送料込みを優先</span>
    <span>✓ 単価に換算</span>
    <span>✓ 毎朝更新</span>
  </div>
  <div class="category-quick-actions">
    <a class="category-ranking-jump" href="#{category_id}">
      <strong>今日の安い順を見る</strong>
      <small>単価ランキングへ ↓</small>
    </a>
    <a class="category-search-cta category-quick-search" href="../../products/?q={query}">
      <strong>商品名で今の価格を検索</strong>
      <small>楽天の送料込み候補を見る →</small>
    </a>
  </div>
</section>
"""


def enhance(category_id: str, name: str) -> bool:
    path = SITE_DIR / category_id / "index.html"
    if not path.exists():
        return False
    markup = path.read_text(encoding="utf-8")
    if 'id="category-design-v1"' in markup:
        return False
    if "</head>" not in markup or '<main class="container">' not in markup:
        return False

    markup = markup.replace("</head>", CSS + "\n</head>", 1)
    markup = markup.replace(
        '<main class="container">',
        '<main class="container">\n' + quick_panel(category_id, name),
        1,
    )
    path.write_text(markup, encoding="utf-8")
    return True


def main() -> None:
    changed = sum(1 for category_id, name in CATEGORIES.items() if enhance(category_id, name))
    print(f"Polished category design on {changed}/{len(CATEGORIES)} pages.")


if __name__ == "__main__":
    main()
