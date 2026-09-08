"""Polish the homepage visual hierarchy without changing comparison logic."""
from __future__ import annotations

import re
from pathlib import Path

HOME = Path("site/index.html")

STYLE = r'''
<style id="home-design-polish-style">
  body{background:#fbfaf9}
  header{background:linear-gradient(180deg,#fff8f5 0%,#fbfaf9 100%);border-bottom:1px solid #f0e5df}
  header .container{padding-top:30px;padding-bottom:24px}
  header h1{font-size:clamp(30px,8vw,44px);line-height:1.12;letter-spacing:-.035em;margin:9px 0 10px}
  header .lead{max-width:720px;font-size:14px;line-height:1.75;color:#5f6368}
  .value-props{margin-top:15px}

  #home-start{margin:16px auto 24px}
  #home-start .home-start-label{margin:0 0 8px;font-size:12px;font-weight:900;color:#6b625e}
  #home-start .home-start-grid{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:9px}
  #home-start a{position:relative;display:flex;flex-direction:column;justify-content:center;min-height:94px;padding:15px 16px;border:1px solid #e8dfda;border-radius:17px;background:#fff;color:#252525;text-decoration:none;box-shadow:0 5px 18px rgba(62,42,32,.045);transition:transform .15s ease,box-shadow .15s ease}
  #home-start a:active{transform:scale(.985)}
  #home-start .home-start-primary{background:linear-gradient(145deg,#b3261e,#8f1f19);border-color:#a7241d;color:#fff;box-shadow:0 9px 24px rgba(179,38,30,.18)}
  #home-start .home-start-icon{font-size:23px;line-height:1;margin-bottom:8px}
  #home-start strong{font-size:14px;line-height:1.4;font-weight:900}
  #home-start small{display:block;margin-top:4px;font-size:10px;line-height:1.45;color:#777}
  #home-start .home-start-primary small{color:rgba(255,255,255,.82)}
  #home-start .home-start-arrow{position:absolute;right:13px;bottom:11px;font-size:15px;font-weight:900;opacity:.72}

  main.container{padding-top:2px}
  #buy-judge{border-radius:20px!important;box-shadow:0 8px 24px rgba(66,47,35,.06)!important}
  #buy-judge .decision-kicker{display:inline-flex;align-items:center;min-height:25px;padding:3px 8px;border-radius:999px;background:#fff0ec}
  #buy-judge .decision-button{box-shadow:0 6px 14px rgba(179,38,30,.16)}
  #home-ranking-hero{border-radius:20px!important;box-shadow:0 8px 24px rgba(60,35,25,.055)!important}
  .category-pages-block{padding:17px;border:1px solid #ece4df;border-radius:18px;background:#fff;box-shadow:0 6px 20px rgba(60,35,25,.035)}
  .category-pages-block h2{margin-top:0}
  .category-page-link{transition:transform .12s ease,box-shadow .12s ease}
  .category-page-link:active{transform:scale(.985)}

  @media(max-width:680px){
    header .container{padding-top:24px;padding-bottom:19px}
    header h1{font-size:34px}
    header .lead{font-size:13px;line-height:1.7}
    #home-start{margin-top:12px}
    #home-start .home-start-grid{grid-template-columns:1fr 1fr}
    #home-start .home-start-primary{grid-column:1/-1;min-height:104px}
    #home-start a{min-height:88px;padding:14px}
    #home-start strong{font-size:13px}
  }
</style>
'''

START = r'''
<section id="home-start" class="container" aria-label="まず使う機能">
  <p class="home-start-label">まず、やりたいことを選ぶ</p>
  <div class="home-start-grid">
    <a class="home-start-primary" href="products/">
      <span class="home-start-icon">🔎</span>
      <strong>商品名で今の価格を検索</strong>
      <small>楽天の送料込み購入候補をリアルタイムで確認</small>
      <span class="home-start-arrow">→</span>
    </a>
    <a href="#buy-judge">
      <span class="home-start-icon">🧮</span>
      <strong>この店頭価格、買い？</strong>
      <small>同じ単位に換算して今日の楽天価格と比較</small>
      <span class="home-start-arrow">↓</span>
    </a>
    <a href="categories/">
      <span class="home-start-icon">🛒</span>
      <strong>カテゴリから安い順を見る</strong>
      <small>21カテゴリの単価ランキング</small>
      <span class="home-start-arrow">→</span>
    </a>
  </div>
</section>
'''


def main() -> None:
    if not HOME.exists():
        raise SystemExit("site/index.html not found")

    markup = HOME.read_text(encoding="utf-8")
    markup = re.sub(r'<style id="home-design-polish-style">.*?</style>\s*', '', markup, flags=re.DOTALL)
    markup = re.sub(r'<section id="home-start".*?</section>\s*', '', markup, flags=re.DOTALL)

    if "</head>" in markup:
        markup = markup.replace("</head>", STYLE + "\n</head>", 1)

    if "</header>" in markup:
        markup = markup.replace("</header>", "</header>\n" + START, 1)
    elif '<main class="container">' in markup:
        markup = markup.replace('<main class="container">', START + '\n<main class="container">', 1)

    HOME.write_text(markup, encoding="utf-8")
    print("Polished homepage visual hierarchy and primary actions")


if __name__ == "__main__":
    main()
