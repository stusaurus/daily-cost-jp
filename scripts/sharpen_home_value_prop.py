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
    <h1>日用品は、単価も支払額も見て選ぶ。</h1>
    <p class="lead">いつも買う日用品を、1枚・1ロール・100mlなど同じ単位で比較。単価だけでなく、セットで払う金額と数量も確かめてから選べます。</p>
    <div class="value-props" aria-label="このサイトの特徴">
      <span class="value-prop">確認できた送料込み候補</span>
      <span class="value-prop">数量・単価・支払額を分けて表示</span>
      <span class="value-prop">数量不明の商品は順位に入れない</span>
    </div>
    {updated}
  </div>
</header>'''

    html = header_pattern.sub(replacement, html, count=1)
    HOME.write_text(html, encoding="utf-8")
    print("Sharpened homepage value proposition")


if __name__ == '__main__':
    main()
