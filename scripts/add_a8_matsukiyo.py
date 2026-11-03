"""Add a fully disclosed, source-owned A8 retail alternative to selected daily categories.

Never insert the retailer into verified Rakuten product rankings, compare
unobserved offers, change A8's link/pixel, or promise coupon eligibility.
Run after category ranking/decision scripts, before GA4 injection.
"""
from pathlib import Path
from html.parser import HTMLParser

SITE = Path("site")
CATEGORIES = {
    "laundry": "洗濯洗剤",
    "tissue": "ティッシュ",
    "toilet-paper": "トイレットペーパー",
}
MARKER = "<!-- a8-matsukiyo-cocokara-online-v1 -->"
AD_CREATIVE = '''<a href="https://px.a8.net/svt/ejp?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM" rel="nofollow">クーポン使用可能！かさばる・重たいなど、お店で買いづらいものをオンラインストアでお得に。【マツキヨココカラオンラインストア】</a>
<img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM" alt="">'''

CSS = """<style id="a8-matsukiyo-style">
.a8-retail-option{margin:28px 0 20px;padding:clamp(16px,3.5vw,25px);background:#f3f7f3;border:2px solid #c4d8cc;border-radius:18px;overflow-wrap:anywhere;color:#273c33}
.a8-retail-option .a8-disclosure{display:inline-block;margin:0 0 9px;font-size:12px;font-weight:800;color:#41584d}
.a8-retail-option h2{font-size:clamp(19px,2.8vw,25px);line-height:1.4;margin:0 0 10px}
.a8-retail-option p{margin:9px 0;line-height:1.75;font-size:14px}
.a8-retail-option .a8-merchant-creative{margin:17px 0 12px}
.a8-retail-option .a8-merchant-creative a{display:block;max-width:760px;padding:14px 18px;min-height:48px;border-radius:11px;background:#276044;color:#fff;text-decoration:none;font-size:15px;font-weight:800;line-height:1.65;text-align:left;overflow-wrap:anywhere}
.a8-retail-option .a8-merchant-creative a:hover{background:#1f4e38}
.a8-retail-option .a8-merchant-creative a:focus-visible{outline:3px solid #88b396;outline-offset:3px}
.a8-retail-option .a8-footnote{font-size:12px;color:#56685b}
@media(max-width:600px){.a8-retail-option{margin:18px 0;padding:15px}.a8-retail-option .a8-merchant-creative a{font-size:14px;padding:13px 14px}}
</style>"""

CLICK_TRACKER = """<script id="a8-matsukiyo-click-tracker">
(() => {
  document.addEventListener('click', event => {
    if (event.type === 'auxclick' && event.button !== 1) return;
    const target = event.target?.closest ? event.target : event.target?.parentElement;
    const link = target?.closest('#a8-matsukiyo-option a[href^="https://px.a8.net/svt/ejp?"]');
    if (!link || typeof window.gtag !== 'function') return;
    const category = document.getElementById('a8-matsukiyo-option')?.dataset.a8Category || '';
    window.gtag('event', 'affiliate_click', {
      affiliate: 'a8',
      merchant: 'matsukiyococokara',
      program: 'matsukiyococokara_online',
      category_id: category,
      conversion_source: 'category',
      click_position: 'alternate_online_retailer',
      ad_placement: 'a8_matsukiyo_category_card'
    });
  });
})();
</script>"""


def card(category: str, name: str) -> str:
    if category not in CATEGORIES or name != CATEGORIES[category]:
        raise ValueError("unrecognized target category")
    return (
        MARKER
        + f'<section id="a8-matsukiyo-option" class="a8-retail-option" data-a8-category="{category}" '
          'aria-labelledby="a8-matsukiyo-title">'
        + '<p class="a8-disclosure">広告｜A8.netアフィリエイト</p>'
        + f'<h2 id="a8-matsukiyo-title">{name}を買うお店も比較する</h2>'
        + '<p>上の単価・商品情報は楽天市場で確認できた商品を対象にしています。'
          'マツキヨココカラオンラインストアも購入先の候補として確認できます。'
          '同じ商品・容量・個数を選び、送料や使えるクーポンの条件を確かめてから'
          '<strong>実際に支払う金額</strong>で判断してください。</p>'
        + '<div class="a8-merchant-creative">' + AD_CREATIVE + '</div>'
        + '<p class="a8-footnote">※広告のリンク先はオンラインストアの案内です。'
          '当サイトではこのストアの実売価格・在庫・送料・クーポン適用条件を自動取得していません。'
          '楽天と同一商品の価格差や、クーポンが必ず利用できることは保証しません。'
          'この広告は楽天の商品ランキングと価格計算に影響しません。'
          'リンク先で購入すると当サイトに成果報酬が発生する場合があります。</p>'
        + '</section>'
    )


def validate(page: str, category: str) -> None:
    if page.count(MARKER) != 1 or page.count(AD_CREATIVE) != 1:
        raise ValueError("missing/duplicated A8 creative or section marker")
    for tag in (
        'href="https://px.a8.net/svt/ejp?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM" rel="nofollow"',
        'src="https://www19.a8.net/0.gif?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM"',
        '広告｜A8.netアフィリエイト',
        f'data-a8-category="{category}"',
        'id="a8-matsukiyo-click-tracker"',
    ):
        if page.count(tag) != 1:
            raise ValueError("missing/duplicated original A8 content: " + tag)
    if page.count('id="a8-matsukiyo-style"') != 1:
        raise ValueError("missing or duplicate ad style")
    if page.count('id="a8-matsukiyo-option"') != 1:
        raise ValueError("missing or duplicate ad container")


def inject(page: str, category: str, name: str) -> str:
    """Locate the current comparison page and add a separated merchant choice."""
    if MARKER in page:
        validate(page, category)
        return page
    if (page.count("<main ") != 1 or page.count("</main>") != 1
            or page.count("</head>") != 1 or page.count("</body>") != 1):
        raise ValueError("unexpected category page structure")
    # Put after purchase/comparison advice where possible, before related SEO links.
    anchor = '<section class="related-categories">'
    if page.count(anchor) == 1:
        page = page.replace(anchor, card(category, name) + "\n" + anchor, 1)
    else:
        page = page.replace("</main>", card(category, name) + "\n</main>", 1)
    page = page.replace("</head>", CSS + "\n</head>", 1)
    page = page.replace("</body>", CLICK_TRACKER + "\n</body>", 1)
    validate(page, category)
    return page


def apply(site: Path = SITE) -> int:
    count = 0
    for category, name in CATEGORIES.items():
        page = site / "categories" / category / "index.html"
        if not page.is_file():
            raise FileNotFoundError(f"Expected existing category page: {page}")
        before = page.read_text(encoding="utf-8")
        after = inject(before, category, name)
        if after != before:
            page.write_text(after, encoding="utf-8")
            count += 1
    # Fail if our retailer mysteriously appears in a non-target ranking.
    for other in ("dish", "water", "coffee"):
        other_page = site / "categories" / other / "index.html"
        if other_page.exists() and MARKER in other_page.read_text(encoding="utf-8"):
            raise ValueError("A8 creative leaked to an untargeted category")
    return count


if __name__ == "__main__":
    print(f"Added Matsukiyo/Cocokara A8 retailer choice to {apply()} categories.")
