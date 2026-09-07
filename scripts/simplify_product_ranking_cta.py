import re
from pathlib import Path

PRODUCTS = Path("site/products/index.html")
TRENDS = Path("site/trends/index.html")


def main():
    if not PRODUCTS.exists():
        print("Product page unavailable; skipping ranking CTA cleanup")
        return

    text = PRODUCTS.read_text(encoding="utf-8")

    text = re.sub(
        r'<style>\s*#trend-searches.*?</style>\s*<section id="trend-searches">.*?</section>',
        '',
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'<section id="product-ranking-cta".*?</section>',
        '',
        text,
        flags=re.DOTALL,
    )

    rank11_available = False
    if TRENDS.exists():
        rank11_available = 'id="rank-11"' in TRENDS.read_text(encoding="utf-8")

    if rank11_available:
        description = 'トップページに1位〜10位を掲載中。続きは11位〜50位まで確認できます。'
        href = '../trends/#rank-11'
        label = '11位〜50位を見る →'
    else:
        description = '楽天総合リアルタイムランキングを確認できます。'
        href = '../trends/'
        label = 'ランキングを見る →'

    block = f'''<section id="product-ranking-cta" style="margin:24px 0 8px;padding:14px 16px;border:1px solid #e7e1dc;border-radius:16px;background:#fff">
  <strong style="display:block;font-size:14px;color:#252525">🔥 楽天総合リアルタイムランキング</strong>
  <p style="margin:5px 0 9px;font-size:11px;line-height:1.6;color:#6b7280">{description}</p>
  <a href="{href}" style="font-size:12px;font-weight:800">{label}</a>
</section>'''

    text = text.replace('</main>', block + '\n</main>', 1)
    PRODUCTS.write_text(text, encoding="utf-8")
    print(f"Product ranking CTA configured; rank11_available={rank11_available}")


if __name__ == "__main__":
    main()
