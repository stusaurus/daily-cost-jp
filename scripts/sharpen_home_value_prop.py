import re
from pathlib import Path

HOME = Path("site/index.html")

STYLE = r'''
<style id="home-value-prop-style">
  .value-props{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
  .value-prop{display:inline-flex;align-items:center;min-height:30px;padding:5px 9px;border:1px solid #ead9d4;border-radius:999px;background:#fff;color:#4b5563;font-size:11px;font-weight:800;line-height:1.35}
  @media(max-width:480px){.value-props{gap:6px}.value-prop{font-size:10px;padding:5px 8px}}
</style>
'''


def main():
    if not HOME.exists():
        raise SystemExit("site/index.html not found")

    html = HOME.read_text(encoding="utf-8")

    html = re.sub(r'<style id="home-value-prop-style">.*?</style>\s*', '', html, flags=re.DOTALL)
    if '</head>' in html:
        html = html.replace('</head>', STYLE + '\n</head>', 1)

    header_pattern = re.compile(
        r'(<header>\s*<div class="container">).*?(</div>\s*</header>)',
        re.DOTALL,
    )
    match = header_pattern.search(html)
    if not match:
        raise SystemExit("homepage header not found")

    existing = match.group(0)
    updated_match = re.search(r'<p class="updated">.*?</p>', existing, re.DOTALL)
    updated = updated_match.group(0) if updated_match else ''

    replacement = f'''<header>
  <div class="container">
    <span class="eyebrow">無料・登録不要｜毎朝自動更新</span>
    <h1>その日用品、本当に安い？</h1>
    <p class="lead">店頭価格を1個・1ロール・100mlなど同じ単位に換算して、今日の楽天・送料込み候補と比較。欲しい商品名から送料込み価格も探せます。</p>
    <div class="value-props" aria-label="このサイトの特徴">
      <span class="value-prop">送料込み候補で比較</span>
      <span class="value-prop">同じ単位に自動換算</span>
      <span class="value-prop">不確かな価格は出さない</span>
    </div>
    {updated}
  </div>
</header>'''

    html = header_pattern.sub(replacement, html, count=1)
    HOME.write_text(html, encoding="utf-8")
    print("Sharpened homepage value proposition")


if __name__ == '__main__':
    main()
