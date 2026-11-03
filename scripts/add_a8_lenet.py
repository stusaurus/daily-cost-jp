"""Place the user's unmodified A8 Lenet creative on the laundry comparison page.

A separate service recommendation: never enter product price rankings or imply
that a cleaning service is an alternative detergent price quote. Run after
category rendering and before GA4 injection.
"""
from pathlib import Path

SITE = Path("site")
TARGET = Path("categories/laundry/index.html")
MARKER = "<!-- a8-lenet-laundry-service-v1 -->"
LINK = "https://px.a8.net/svt/ejp?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA"
PIXEL = "https://www10.a8.net/0.gif?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA"

# Preserve the advertiser's supplied HTML, including the original 1x1 pixel.
AD_CREATIVE = '''<a href="https://px.a8.net/svt/ejp?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA" rel="nofollow">子育てママに大人気！家まで届けてくれる宅配クリーニング「リネット」</a>
<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4BGCF1+ATDIEQ+2W7Y+67JUA" alt="">'''

CSS = """<style id="a8-lenet-style">
.a8-lenet-option{margin:24px 0;padding:clamp(16px,3.5vw,24px);border:1px solid #cfdbe4;border-radius:18px;background:#f4f8fc;color:#223747;overflow-wrap:anywhere}
.a8-lenet-option .a8-lenet-label{display:inline-block;margin:0 0 9px;font-size:12px;font-weight:800;color:#425a70}
.a8-lenet-option h2{font-size:clamp(19px,2.8vw,24px);line-height:1.45;margin:0 0 9px}
.a8-lenet-option p{font-size:14px;line-height:1.7;margin:8px 0}
.a8-lenet-option .a8-lenet-creative{margin:15px 0 10px}
.a8-lenet-option .a8-lenet-creative a{display:block;max-width:760px;min-height:48px;padding:14px 16px;border-radius:11px;background:#245c86;color:#fff;font-size:15px;font-weight:800;line-height:1.65;text-decoration:none}
.a8-lenet-option .a8-lenet-creative a:hover{background:#184969}
.a8-lenet-option .a8-lenet-creative a:focus-visible{outline:3px solid #7baed5;outline-offset:3px}
.a8-lenet-option .a8-lenet-note{font-size:12px;color:#506476}
@media(max-width:600px){.a8-lenet-option{margin:18px 0;padding:15px}.a8-lenet-option .a8-lenet-creative a{font-size:14px;padding:13px 14px}}
</style>"""

CLICK_TRACKER = """<script id="a8-lenet-click-tracker">
(() => {
  document.addEventListener('click', event => {
    const target = event.target?.closest ? event.target : event.target?.parentElement;
    const link = target?.closest('#a8-lenet-option a[href^="https://px.a8.net/svt/ejp?"]');
    if (!link || typeof window.gtag !== 'function') return;
    window.gtag('event', 'affiliate_click', {
      affiliate: 'a8',
      merchant: 'lenet',
      program: 'lenet_delivery_cleaning',
      category_id: 'laundry',
      conversion_source: 'category',
      click_position: 'cleaning_service_alternative',
      ad_placement: 'a8_lenet_laundry_card'
    });
  });
})();
</script>"""


def card():
    return (
        MARKER
        + '<section id="a8-lenet-option" class="a8-lenet-option" aria-labelledby="a8-lenet-title">'
        + '<p class="a8-lenet-label">広告｜A8.netアフィリエイト</p>'
        + '<h2 id="a8-lenet-title">自宅では洗いにくい衣類は宅配クリーニングも</h2>'
        + '<p>洗濯洗剤の単価比較とは別に、クリーニングを利用したい衣類がある場合の'
          'サービス案内です。料金・対応品目・配送条件などはリンク先でご確認ください。</p>'
        + '<div class="a8-lenet-creative">' + AD_CREATIVE + '</div>'
        + '<p class="a8-lenet-note">※宅配クリーニングサービスの広告です。'
          '楽天の商品ランキング・単価計算には含めていません。'
          'リンク先の申込みなどにより当サイトに成果報酬が発生する場合があります。</p>'
        + '</section>'
    )


def validate(page):
    required = (
        MARKER,
        AD_CREATIVE,
        'id="a8-lenet-option"',
        'id="a8-lenet-title"',
        'id="a8-lenet-style"',
        'id="a8-lenet-click-tracker"',
        '広告｜A8.netアフィリエイト',
    )
    for part in required:
        if page.count(part) != 1:
            raise ValueError("missing/duplicate A8 Lenet component: " + part[:80])
    if page.count(LINK) != 1 or page.count(PIXEL) != 1:
        raise ValueError("A8 Lenet tracking URLs must occur exactly once each")
    if page.count('<section class="related-categories">') != 1:
        raise ValueError("missing/duplicate category closing section")


def inject(page):
    if MARKER in page:
        validate(page)
        return page
    if (page.count('<main class="container">') != 1
            or page.count("</main>") != 1
            or page.count("</head>") != 1
            or page.count("</body>") != 1
            or page.count('<section class="related-categories">') != 1):
        raise ValueError("unexpected laundry comparison page structure")
    page = page.replace('<section class="related-categories">', card() + '\n<section class="related-categories">', 1)
    page = page.replace("</head>", CSS + "\n</head>", 1)
    page = page.replace("</body>", CLICK_TRACKER + "\n</body>", 1)
    validate(page)
    return page


def apply(site=SITE):
    page = site / TARGET
    if not page.is_file():
        raise FileNotFoundError(f"Missing laundry category: {page}")
    original = page.read_text(encoding="utf-8")
    updated = inject(original)
    if updated != original:
        page.write_text(updated, encoding="utf-8")
    for category in ("tissue", "toilet-paper", "dish"):
        other = site / "categories" / category / "index.html"
        if other.is_file() and MARKER in other.read_text(encoding="utf-8"):
            raise ValueError("Lenet ad leaked into another category")
    return int(updated != original)


if __name__ == "__main__":
    print(f"Inserted A8 Lenet laundry advertisement: {apply()} page(s).")
