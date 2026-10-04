"""Everyday Art: editorial images are never used as product evidence."""
import hashlib
import shutil
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = '/daily-cost-jp/'
SOURCE = Path('scripts/design/art')
CATEGORY_ART = {'toilet-paper':'paper', 'tissue':'tissue', 'laundry':'wash',
                'shampoo':'care', 'body-soap':'care', 'bath-cleaner':'clean'}
DESCRIPTIONS = {
    'hero':'紙の柱と浮遊するティッシュ、ガラスと布を朝の光で描いた日用品アート',
    'paper':'建築の柱のような紙のロールと、アーチを描く薄い紙',
    'tissue':'空中に彫刻のように流れるティッシュ',
    'wash':'透き通る洗剤容器と、水と布の静物アート',
    'care':'無地のポンプ容器、水面、石とタオルの静物アート',
    'clean':'木のブラシ、布、スポンジとステンレスの静物アート',
}

def fragment(markup): return BeautifulSoup(markup, 'html.parser')

def install_art(site):
    target = site/'assets/art'
    target.mkdir(parents=True, exist_ok=True)
    for source in SOURCE.glob('*.webp'):
        shutil.copy2(source, target/source.name)

def art_picture(key, hero=False):
    widths = (800,1600) if hero else (480,960)
    version = hashlib.sha256((SOURCE/f'{key}-{widths[0]}.webp').read_bytes()).hexdigest()[:10]
    urls = [ROOT+f'assets/art/{key}-{width}.webp?v={version}' for width in widths]
    width = widths[-1]; height = round(width*2/3) if hero else width
    mobile = ''
    if hero:
        mobile_version = hashlib.sha256((SOURCE/'hero-mobile-480.webp').read_bytes()).hexdigest()[:10]
        mobile_urls = [ROOT+f'assets/art/hero-mobile-{w}.webp?v={mobile_version}' for w in (480,960)]
        mobile = (f'<source media="(max-width:600px)" type="image/webp" '
                  f'srcset="{mobile_urls[0]} 480w, {mobile_urls[1]} 960w" sizes="100vw" width="960" height="1440">')
    return (f'<picture class="art-picture" data-editorial-art="{key}">{mobile}<img src="{urls[0]}" '
            f'srcset="{urls[0]} {widths[0]}w, {urls[1]} {widths[1]}w" '
            f'sizes="{"100vw" if hero else "(max-width:600px) 45vw, 320px"}" '
            f'width="{width}" height="{height}" alt="{DESCRIPTIONS[key]}" '
            f'loading="{"eager" if hero else "lazy"}" decoding="async" '
            f'{"fetchpriority=high" if hero else ""}></picture>')

def apply_art(soup, path, site):
    home = path == site/'index.html'
    if home:
        stamp = soup.select_one('.lab-hero .updated').get_text()
        soup.select_one('.lab-hero').replace_with(fragment(
            '<header class="art-cover">'+art_picture('hero',True)+
            '<div class="container art-cover-content"><p class="lab-kicker">日用品を、アートにする。 / DAILY COST</p>'
            '<h1>その日用品、<br>本当に安い？</h1>'
            '<p class="lead">同じものさしで比べれば、わかります。<br>容量も、個数も、送料も。日用品の価格を、同じ単位へ。</p>'
            '<div id="art-cover-search"></div><div class="lab-actions">'
            '<a class="lab-button" href="#lab-categories">カテゴリから比べる ↓</a>'
            '<a class="lab-button secondary" href="'+ROOT+'today/" data-conversion-source="daily_pick">今日の比較候補 ↗</a>'
            '</div><p class="updated"></p></div>'
            '<span class="art-credit">EVERYDAY ART 01 / 紙・布・ガラス</span></header>'))
        soup.select_one('.art-cover .updated').string=stamp
        finder = soup.select_one('#product-finder-home')
        if finder:
            finder['class']=list(finder.get('class',[]))+['art-search']
            soup.select_one('#art-cover-search').replace_with(finder.extract())
        # The real two-product example follows the art immediately, without
        # changing a single price, unit or product image.
        from redesign_laboratory import demo_markup
        import json
        categories=json.loads((site/'data.json').read_text())['categories']
        demo=fragment('<section class="lab-section art-data" id="art-data"><div>'
                      '<p class="lab-kicker">ART × DATA / 本当の価格差</p>'
                      '<h2>美しく眺めて、<br>数字で選ぶ。</h2>'
                      '<p>販売価格だけでは、見えない違い。<br>実際の商品を同じ量にそろえると。</p>'
                      '</div>'+demo_markup(categories)+'</section>')
        soup.main.insert(0,demo)
        method=soup.select_one('#lab-method')
        if method: method.insert(0,fragment('<figure class="art-method">'+art_picture('tissue')+'<figcaption>紙は、形を変える。価格は、単位をそろえる。</figcaption></figure>'))
        closing=fragment('<section class="art-closing container">'+art_picture('clean')+
                         '<div><p class="lab-kicker">暮らしを、丁寧に編集する。</p>'
                         '<h2>いつもの買い物に、<br>新しいものさしを。</h2>'
                         '<a class="lab-button secondary" href="'+ROOT+'categories/">日用品を比べる ↗</a>'
                         '<p class="art-disclosure">アートは日用品をモチーフにした生成ビジュアルです。掲載商品の写真ではありません。</p></div></section>')
        soup.main.append(closing)
    if home or path==site/'categories/index.html':
        for group,key in zip(soup.select('.lab-life-photo'),('wash','tissue','clean','paper')):
            group.clear();group.append(fragment(art_picture(key)))
        for entry in soup.select('.lab-showroom-item'):
            cid=entry['href'].rstrip('/').rsplit('/',1)[-1]
            if cid in CATEGORY_ART:
                photo=entry.select_one('.lab-showroom-photo');photo.clear()
                photo.append(fragment(art_picture(CATEGORY_ART[cid])))
        if path==site/'categories/index.html':
            note=soup.select_one('.category-pages-block .lab-section-head p')
            if note:note.string='日用品アートと商品写真で探す。購入候補はカテゴリ内の実商品で比較できます。'
    cid=path.parent.name if path.parent.parent.name=='categories' else ''
    if cid in CATEGORY_ART or path==site/'today/index.html':
        header=soup.select_one('header')
        if header:
            header['class']=list(header.get('class',[]))+['art-page-header']
            header.append(fragment('<figure class="art-page-visual">'+art_picture(CATEGORY_ART.get(cid,'care'))+'</figure>'))
