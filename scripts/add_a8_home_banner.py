"""Add one isolated A8 banner to the bottom of the daily-cost home page.

The advertiser has not been identified from the supplied creative. Never
insert this banner into product rankings or claim it represents a verified
product, price, discount or alternative shop. Keep A8 tracking URLs intact.
"""
from pathlib import Path

SITE = Path('site')
MARKER = '<!-- a8-home-banner-4NJ4-v1 -->'
LINK_URL = 'https://px.a8.net/svt/ejp?a8mat=4BGCF2+6HZHDM+4NJ4+609HT'
IMAGE_URL = ('https://www22.a8.net/svt/bgt?aid=261103070393'
             '&wid=006&eno=01&mid=s00000021712001009000&mc=1')
PIXEL_URL = 'https://www14.a8.net/0.gif?a8mat=4BGCF2+6HZHDM+4NJ4+609HT'

SECTION = f'''{MARKER}
<section id="a8-sponsored-banner" class="a8-sponsored-banner" aria-label="スポンサー広告">
  <p class="a8-sponsored-label">広告｜A8.netアフィリエイト</p>
  <div class="a8-sponsored-creative">
    <a href="{LINK_URL}" rel="nofollow sponsored" aria-label="スポンサーの広告主サイトを開く">
      <img border="0" width="300" height="250" alt="スポンサー広告バナー" src="{IMAGE_URL}">
    </a>
    <img border="0" width="1" height="1" src="{PIXEL_URL}" alt="">
  </div>
  <p class="a8-sponsored-note">この枠は外部広告です。掲載商品の単価比較・ランキングには影響しません。リンク先で申し込み・購入をすると運営者に報酬が発生する場合があります。</p>
</section>'''

CSS = '''<style id="a8-home-banner-style">
.a8-sponsored-banner{box-sizing:border-box;max-width:660px;margin:36px auto 20px;padding:20px;border:1px solid #d7dedc;border-radius:16px;background:#fafbfa;text-align:center;color:#36443f}
.a8-sponsored-label{font-size:12px;font-weight:700;letter-spacing:.04em;margin:0 0 14px}
.a8-sponsored-creative{max-width:300px;margin:0 auto}
.a8-sponsored-creative a{display:block;line-height:0}
.a8-sponsored-creative a:focus-visible{outline:3px solid #2b6951;outline-offset:4px}
.a8-sponsored-creative a img{display:block;width:100%;max-width:300px;height:auto;aspect-ratio:6 / 5;object-fit:contain}
.a8-sponsored-creative>img[width="1"]{position:absolute;width:1px;height:1px}
.a8-sponsored-note{font-size:12px;line-height:1.65;margin:14px 0 0;text-align:left}
@media(max-width:420px){.a8-sponsored-banner{padding:14px;margin:26px auto 14px}}
</style>'''

TRACKER = '''<script id="a8-home-banner-tracker">
(() => {
  const record = event => {
    if (event.type === 'auxclick' && event.button !== 1) return;
    const target = event.target?.closest ? event.target : event.target?.parentElement;
    const link = target?.closest('#a8-sponsored-banner a[href^="https://px.a8.net/"]');
    if (!link || typeof window.gtag !== 'function') return;
    window.gtag('event', 'affiliate_click', {
      affiliate: 'a8',
      program: '4NJ4',
      conversion_source: 'other',
      click_position: 'home_footer_banner',
      ad_placement: 'a8_home_banner_4NJ4',
      transport_type: 'beacon'
    });
  };
  document.addEventListener('click', record);
  document.addEventListener('auxclick', record);
})();
</script>'''


def validate(markup: str) -> None:
    if any(markup.count(value) != 1 for value in (
        MARKER, 'id="a8-sponsored-banner"',
        'id="a8-home-banner-style"', 'id="a8-home-banner-tracker"',
        f'href="{LINK_URL}"', f'src="{IMAGE_URL}"', f'src="{PIXEL_URL}"',
        '広告｜A8.netアフィリエイト',
    )):
        raise ValueError('Missing or duplicate A8 banner, style, tracker or creative')


def inject(markup: str) -> str:
    if MARKER in markup:
        validate(markup)
        return markup
    if any(markup.count(tag) != 1 for tag in ('</head>', '</main>', '</body>')):
        raise ValueError('Unexpected home page HTML structure')
    markup = markup.replace('</main>', SECTION + '\n</main>', 1)
    markup = markup.replace('</head>', CSS + '\n</head>', 1)
    markup = markup.replace('</body>', TRACKER + '\n</body>', 1)
    validate(markup)
    return markup


def apply(site: Path = SITE) -> bool:
    page = site / 'index.html'
    if not page.is_file():
        raise FileNotFoundError(f'Missing generated homepage: {page}')
    before = page.read_text(encoding='utf-8')
    after = inject(before)
    if after != before:
        page.write_text(after, encoding='utf-8')
        return True
    return False


if __name__ == '__main__':
    print(f'Injected A8 home banner: {apply()}')
