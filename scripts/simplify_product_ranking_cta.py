import re
from pathlib import Path

PRODUCTS = Path("site/products/index.html")


def main():
    if not PRODUCTS.exists():
        print("Product page unavailable; skipping ranking CTA cleanup")
        return

    text = PRODUCTS.read_text(encoding="utf-8")

    # Remove the embedded ranking card grid from the product-search page.
    # After query validation it can become a confusing partial ranking (for example,
    # only rank 2 remaining), so keep product search focused on the searched item.
    text = re.sub(
        r'<style>\s*#trend-searches.*?</style>\s*<section id="trend-searches">.*?</section>',
        '',
        text,
        flags=re.DOTALL,
    )

    # Also remove a prior compact block if this script is run more than once.
    text = re.sub(
        r'<section id="product-ranking-cta".*?</section>',
        '',
        text,
        flags=re.DOTALL,
    )

    block = '''<section id="product-ranking-cta" style="margin:24px 0 8px;padding:14px 16px;border:1px solid #e7e1dc;border-radius:16px;background:#fff">
  <strong style="display:block;font-size:14px;color:#252525">🔥 楽天総合リアルタイムランキング</strong>
  <p style="margin:5px 0 9px;font-size:11px;line-height:1.6;color:#6b7280">トップページに1位〜10位を掲載中。続きは11位〜50位まで確認できます。</p>
  <a href="../trends/#rank-11" style="font-size:12px;font-weight:800">11位〜50位を見る →</a>
</section>'''

    text = text.replace('</main>', block + '\n</main>', 1)
    PRODUCTS.write_text(text, encoding="utf-8")
    print("Replaced partial product-page ranking grid with a compact continuation link")


if __name__ == "__main__":
    main()
