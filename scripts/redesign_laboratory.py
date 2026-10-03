"""A generated, data-backed visual system. Run after content, before GA4/SEO gates.

This layer changes presentation only: IDs, affiliate URLs, prices, evidence,
JSON-LD and feature scripts are retained. No live product is hard coded here.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from comparison_units import comparison_unit, quantity_label, LABELS
from product_display import clean_display_name

SITE = Path('site')
ROOT = '/daily-cost-jp/'
LIFE = (
    ('01', '洗う', ('laundry','dish','shampoo','body-soap','hand-soap')),
    ('02', '拭く', ('tissue','paper-towel','floor-sheet')),
    ('03', '整える', ('bath-cleaner','toilet-cleaner','garbage-bag-45l','laundry-bleach')),
    ('04', 'ストックする', ('toilet-paper','softener','mask','toothbrush','cotton-swab')),
)

def esc(value): return html.escape(str(value), quote=True)
def money(value): return f'¥{value:,.2f}' if value < 100 else f'¥{value:,.1f}'
def price_markup(value, label):
    # Keep the actual number and unit together in the accessible text.
    return f'<span class="lab-price-value"><small>¥</small>{money(value)[1:]}</span><span class="lab-price-unit">／{esc(label)}</span>'
def fragment(markup): return BeautifulSoup(markup, 'html.parser')
def clean_emoji(text): return re.sub(r'^[^\w\u3040-\u30ff\u3400-\u9fff]+\s*', '', text)

def photo_url(url, size=420):
    """Only request a larger rendering from Rakuten's existing thumbnail host."""
    if not url: return ''
    p = urlsplit(url)
    if p.hostname != 'thumbnail.image.rakuten.co.jp': return url
    query = dict(parse_qsl(p.query, keep_blank_values=True))
    query['_ex'] = f'{size}x{size}'
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(query),p.fragment))

def image_markup(item, eager=False):
    image = photo_url(item.get('image',''))
    if not image: return '<div class="image-placeholder">商品画像なし</div>'
    return f'<img src="{esc(image)}" alt="{esc(clean_display_name(item["name"]))}" width="420" height="420" loading="{"eager" if eager else "lazy"}" decoding="async" srcset="{esc(photo_url(item.get("image",""),240))} 240w, {esc(image)} 420w" sizes="(max-width:600px) {"170" if eager else "120"}px, 350px">'

def category_metric(cid,item):
    if cid=="tissue":return "100組"
    if cid=="toilet-paper":return "重ね数別10m"
    return LABELS.get(item["metric"],item["metric"])

def category_links(categories):
    return ''.join(f'<a class="lab-category-link category-page-link" href="{ROOT}categories/{esc(cid)}/" data-conversion-source="category"><span>{esc(c["name"])}</span><small>{esc(category_metric(cid,c["items"][0]))}で比較 ↗</small></a>' for cid,c in categories.items() if c['items'])

def life_markup(categories):
    sections=[]
    for n,name,ids in LIFE:
        available=[cid for cid in ids if cid in categories and categories[cid]['items']]
        if not available: continue
        cid=available[0]
        photo=f'<a class="lab-life-photo" href="{ROOT}categories/{cid}/" aria-label="{esc(categories[cid]["name"])}を比較">{image_markup(categories[cid]["items"][0])}</a>'
        links=''.join(f'<a class="category-page-link" data-conversion-source="category" href="{ROOT}categories/{c}/">{esc(categories[c]["name"])}</a>' for c in available)
        sections.append(f'<div class="lab-life">{photo}<div class="lab-life-label"><span>{n}</span><h3>{name}</h3></div>{links}</div>')
    return ''.join(sections)

def category_showroom(categories):
    cards=[]
    for cid,c in categories.items():
        if not c['items']:continue
        cards.append(f'<a class="lab-showroom-item category-page-link" href="{ROOT}categories/{cid}/" data-conversion-source="category"><div class="lab-showroom-photo">{image_markup(c["items"][0])}</div><div><h3>{esc(c["name"])}</h3><p>{esc(category_metric(cid,c["items"][0]))}で比較 <span aria-hidden="true">↗</span></p></div></a>')
    return '<div class="lab-showroom-grid">'+''.join(cards)+'</div>'

def sample_pair(categories):
    """Prefer a genuine total-price/unit-price inversion, same known unit only."""
    for cid in ('tissue','toilet-paper','laundry'):
        rows = categories.get(cid,{}).get('items',[])
        for a in sorted(rows,key=lambda x:x['price']):
            ua = comparison_unit(cid,a)
            if not ua: continue
            for b in rows:
                ub = comparison_unit(cid,b)
                if ub and ua[0] == ub[0] and a['price'] < b['price'] and ua[1] > ub[1]:
                    return cid, [(a,ua),(b,ub)], True
    for cid,c in categories.items():
        rows = [(p,comparison_unit(cid,p)) for p in c['items'] if comparison_unit(cid,p)]
        if len(rows)>1:
            same = [r for r in rows if r[1][0]==rows[0][1][0]]
            if len(same)>1: return cid,same[:2],False
    return '',[],False

def demo_markup(categories):
    cid, rows, inversion = sample_pair(categories)
    if not rows: return '<div class="lab-demo"><p>条件を確認できる商品だけを、同じ単位で比較します。</p></div>'
    best = min(u[1] for _,u in rows)
    cards = ''.join(f'<div class="lab-sample {"best" if u[1]==best else ""}"><div class="lab-sample-photo">{image_markup(p,True)}</div><p class="lab-sample-name" title="{esc(clean_display_name(p["name"]))}">{esc(clean_display_name(p["name"]))}</p><div class="lab-sample-total">{esc(quantity_label(p))} · 送料込み<br>支払総額 <b>¥{p["price"]:,}</b></div><div class="lab-sample-unit"><span class="lab-transform">↓ 同じ量にそろえる</span>{price_markup(u[1],u[0])}<span class="lab-choice">{"比較した2商品の低い単価" if u[1]==best else "比較単価"}</span></div></div>' for p,u in rows)
    note = '支払総額が高い方でも、同じ量で比べると単価は低くなる。' if inversion else '内容量が違っても、同じ量までそろえると比べられる。'
    difference=max(u[1] for _,u in rows)-best
    return f'<div class="lab-demo" aria-label="実商品による単価比較の見本"><div class="lab-demo-caption"><span>{esc(categories[cid]["name"])} / 同じものさしで比較</span><span>実際の取得データ</span></div><div class="lab-demo-grid">{cards}</div><p class="lab-demo-note"><strong>同じ{esc(rows[0][1][0])}で、{difference:.2f}円の差。</strong>{note}<br>素材・用途も確認して選びましょう。<a href="{ROOT}categories/{cid}/" data-conversion-source="category">この比較を見る ↗</a></p></div>'

def card_markup(cid, category, item, rank, anchor, reason='送料込み'):
    unit = comparison_unit(cid,item)
    label, value = unit if unit else (LABELS.get(item['metric'],item['metric']),item['unit_price'])
    normalized_note = ''
    if not unit:
        normalized_note = '<p class="lab-base-price">組数・長さ・重ね数は未確認。同じ条件での順位比較対象外。</p>'
    elif cid in ('tissue','toilet-paper'):
        normalized_note = f'<p class="lab-base-price">参考：{money(item["unit_price"])}／{esc(LABELS[item["metric"]])}</p>'
    return f'''<article id="{esc(anchor)}" class="product-card product-card-anchor"><div class="rank-badge">{rank:02d}</div><div class="product-image">{image_markup(item)}</div><div class="product-body"><div class="lab-reason"><span>{esc(category['name'])}</span><span>{esc(reason)}</span></div><h3 title="{esc(clean_display_name(item['name']))}">{esc(clean_display_name(item['name']))}</h3><div class="unit-price">{price_markup(value,label)}</div>{normalized_note}<p class="purchase-summary">{esc(quantity_label(item))}</p><p class="purchase-summary">支払総額 <strong>¥{item['price']:,}</strong> · 送料込み</p><p class="shop">{esc(item.get('shop',''))}</p><a class="buy-button" href="{esc(item['url'])}" target="_blank" rel="nofollow sponsored noopener" data-category-id="{esc(cid)}" data-rank="{rank}" data-shipping-price="{item['price']}" data-product-name="{esc(clean_display_name(item['name']))}">楽天で商品を確認する <span aria-hidden="true">↗</span></a><p class="purchase-note">価格・在庫・地域別送料は楽天で最終確認</p></div></article>'''

def masthead():
    return f'<a class="lab-skip" href="#lab-content">本文へ移動</a><div class="lab-masthead"><div class="lab-masthead-inner"><a class="lab-brand" href="{ROOT}"><span class="lab-mark" aria-hidden="true">日</span><span>日用品コスパ比較<small>DAILY COST / 暮らしの価格研究所</small></span></a><nav class="lab-nav" aria-label="メインナビゲーション"><a href="{ROOT}categories/">カテゴリから探す</a><a href="{ROOT}today/">今日の比較候補</a><a href="{ROOT}products/">商品名で探す ↗</a></nav></div></div>'

def footer():
    return f'<footer class="lab-footer"><div class="lab-footer-brand">同じものさしで、暮らしの値段を。</div><p>日用品コスパ比較 / 暮らしの価格研究所</p><nav aria-label="フッターナビゲーション"><a href="{ROOT}categories/">21カテゴリの比較</a><a href="{ROOT}today/">今日の比較候補</a><a href="{ROOT}products/">商品名から探す</a><a href="{ROOT}guides/tissue-price-per-box/">単価の計算方法</a><a href="{ROOT}trends/">楽天総合ランキング</a></nav><p>当サイトは楽天アフィリエイトを利用しています。リンク経由の購入により運営者に報酬が発生する場合があります。楽天グループ株式会社が運営するサイトではありません。掲載時点の取得データに基づく比較です。価格・在庫・地域別送料は楽天の商品ページで確認してください。</p></footer>'

def redesign_home(soup,payload,today):
    categories=payload['categories']; main=soup.main
    soup.body['class']=['lab-home']
    header=soup.header
    updated=header.select_one('.updated')
    stamp=updated.get_text() if updated else payload['updated_at']
    header.replace_with(fragment(f'<header class="lab-hero"><div class="container lab-hero-grid"><div><div class="lab-kicker">暮らしの価格研究所 / 同じものさしで比べる</div><h1>上質な暮らしを、<br>数字で賢く選ぶ。</h1><p class="lead">箱数も、容量も、セット数も。<br>同じ単位にそろえると、本当の価格差が見えてくる。</p><div class="lab-actions"><a class="lab-button" href="#lab-categories">日用品を比べる <span aria-hidden="true">↓</span></a><a class="lab-button secondary" href="{ROOT}today/" data-conversion-source="daily_pick">今日の比較候補 ↗</a></div><p class="updated">{esc(stamp)}</p></div>{demo_markup(categories)}</div></header>'))
    for selector in ['#home-start','.nav-wrap','#priority-categories','#today-deals-entry','.top-picks','.category-pages-block']:
        for el in soup.select(selector): el.decompose()
    life=life_markup(categories)
    intro=fragment(f'<section class="lab-section" id="lab-life"><div class="lab-section-head"><div><span class="lab-kicker">01 / FIND YOUR EVERYDAY</span><h2>暮らしから探す</h2></div><p>いつもの日用品に、<br>新しい選び方を。</p></div><div class="lab-life-grid">{life}</div></section><section class="lab-section" id="lab-categories"><div class="lab-section-head"><div><span class="lab-kicker">02 / SAME UNIT, FAIR COMPARISON</span><h2>比べたいものは、何ですか。</h2></div><p>21カテゴリ・送料込みで比較</p></div><div class="lab-category-grid">{category_links(categories)}</div></section>')
    main.insert(0,intro)
    picks=[]
    for index,deal in enumerate(today.get('items',[]),1):
        cid=deal['id'];c=categories[cid]
        found=next(((rank,p) for rank,p in enumerate(c['items'],1) if p['url']==deal['url']),None)
        if found:
            rank,p=found;markup=card_markup(cid,c,p,rank,f'lab-today-{cid}','同じ単位の候補と比較')
            el=fragment(markup).article
            el.select_one('.buy-button')['data-conversion-source']='daily_pick'
            picks.append(str(el))
    block=fragment('<section class="lab-section" id="today-deals-entry"><div class="lab-section-head"><div><span class="lab-kicker">03 / TODAY’S OBSERVATIONS</span><h2>今日、比べてみたい日用品。</h2></div><a href="'+ROOT+'today/" data-conversion-source="daily_pick">5つの候補を詳しく ↗</a></div><p class="lab-demo-note">今日取得した同じ単位の候補を比較して選定。価格の安さだけでなく、用途・置き場所も合わせて確認してください。</p><div class="lab-today-grid">'+''.join(picks)+'</div></section>')
    main.select_one('#lab-categories').insert_after(block)
    method=fragment('<section class="lab-section lab-method" id="lab-method"><div><span class="lab-kicker">THE METHOD</span><h2>価格の見方を、<br>少し変える。</h2><p>安さをあおるより、<br>選ぶ理由がわかる比較を。</p></div><ol><li><div><b>内容量を確かめる</b>容量・個数・セット数を解析。曖昧な商品は無理に比較しません。</div></li><li><div><b>送料を含め、同じ単位へ</b>ティッシュは100組。トイレットペーパーは重ね数別の10m。単位をそろえて違いを見ます。</div></li><li><div><b>比べて、保存して、納得して選ぶ</b>単価だけでなく総額や用途も確認。購入前に楽天で最新条件を確かめましょう。</div></li></ol></section>')
    method = method.section
    main.select_one('#today-deals-entry').insert_after(method)
    toolbar=main.select_one('#purchase-tools')
    if toolbar:method.insert_after(toolbar.extract())
    tools=soup.new_tag('div',attrs={'class':'lab-tools-grid'})
    for selector in ['#product-finder-home','#exact-store-compare','#buy-judge']:
        el=main.select_one(selector)
        if el:tools.append(el.extract())
    toolbar.insert_after(tools)
    # Keep old IDs/links and full ranking data, but stop duplicating every category
    # as 200 cards in the primary discovery experience.
    details=soup.new_tag('details',attrs={'class':'lab-all-rankings'})
    summary=soup.new_tag('summary');summary.string='全カテゴリの商品データ・単価一覧を見る';details.append(summary)
    for el in list(main.select('.category-section')):
        cid=el.get('id');c=categories.get(cid)
        if not c:continue
        # Retain every old deep anchor and actual unit, without hydrating hundreds
        # of duplicate purchase widgets on the homepage.
        archive=soup.new_tag('section',attrs={'id':cid,'class':'lab-archive-category'})
        heading=soup.new_tag('h2');heading.string=c['name'];archive.append(heading)
        for rank,item in enumerate(c['items'],1):
            unit=comparison_unit(cid,item)
            label,value=unit if unit else (LABELS.get(item['metric'],item['metric']),item['unit_price'])
            row=fragment(f'<div class="lab-archive-row" id="{cid}-rank-{rank}"><a class="category-page-link" href="{ROOT}categories/{cid}/#{cid}-rank-{rank}">{esc(clean_display_name(item["name"]))}</a><strong>{money(value)} <small>／{esc(label)}</small></strong></div>').div
            archive.append(row)
        details.append(archive);el.decompose()
    main.append(details)
    ranking=main.select_one('#home-ranking-hero')
    if ranking:main.append(ranking.extract())


def group_normalized_cards(soup,categories):
    """Display comparable paper cards together; retain source ranks in data/IDs."""
    for section in soup.select('section.category-section'):
        cid=section.get('id')
        if cid not in ('tissue','toilet-paper'):continue
        old=section.select_one('.product-list')
        if not old:continue
        groups={}
        for card in list(old.select('.product-card')):
            rank=int(card['id'].rsplit('-',1)[1]);item=categories[cid]['items'][rank-1]
            unit=comparison_unit(cid,item)
            label=unit[0] if unit else '条件が未確認の商品'
            groups.setdefault(label,[]).append((unit[1] if unit else float('inf'),card))
        wrapper=soup.new_tag('div',attrs={'class':'lab-unit-groups'})
        for label,rows in sorted(groups.items(),key=lambda x:x[0]=='条件が未確認の商品'):
            group=soup.new_tag('div',attrs={'class':'lab-unit-group'})
            heading=soup.new_tag('h3');heading.string=label+'で比較' if label!='条件が未確認の商品' else label
            group.append(heading);grid=soup.new_tag('div',attrs={'class':'product-list'})
            for _,card in sorted(rows,key=lambda x:x[0]):grid.append(card.extract())
            group.append(grid);wrapper.append(group)
        old.replace_with(wrapper)
        heading=section.select_one('.section-heading h2')
        if heading:heading.string=categories[cid]['name']+'の比較候補'
        note=section.select_one('.section-heading p')
        if note:note.string='同じ条件ごとに単価の低い順。素材・用途と購入する量も確認してください。'

def main(site=SITE):
    payload=json.loads((site/'data.json').read_text())
    today=json.loads((site/'today/data.json').read_text())
    (site/'assets').mkdir(exist_ok=True)
    (site/'assets/laboratory.css').write_text(Path('scripts/design/laboratory.css').read_text(),encoding='utf-8')
    (site/'assets/favicon.svg').write_text(Path('scripts/design/favicon.svg').read_text(),encoding='utf-8')
    for path in site.rglob('*.html'):
        if path.name.startswith('google'):continue
        soup=BeautifulSoup(path.read_text(),'html.parser')
        if not soup.head or not soup.body or not soup.main:continue
        if soup.select_one('[data-laboratory-design]'):continue
        # The old presentation is removed instead of accumulating CSS overrides.
        for style in soup.find_all('style'):style.decompose()
        for el in soup.find_all(style=True):del el['style']
        css=soup.new_tag('link',rel='stylesheet',href=ROOT+'assets/laboratory.css')
        css['data-laboratory-design']='v1';soup.head.append(css)
        if not soup.select_one('link[rel=icon]'):soup.head.append(soup.new_tag('link',rel='icon',type='image/svg+xml',href=ROOT+'assets/favicon.svg'))
        soup.body.insert(0,fragment(masthead()))
        soup.main['id']='lab-content'
        ishome=path==site/'index.html'
        if ishome:redesign_home(soup,payload,today)
        if path==site/'categories/index.html':
            block=soup.select_one('.category-pages-block')
            if block:
                block.clear()
                block.append(fragment('<div class="lab-section-head"><div><span class="lab-kicker">暮らしの売場</span><h2>いつもの日用品を、賢く選ぶ。</h2></div><p>写真は掲載商品の一例です。<br>カテゴリ内で容量・用途も比べられます。</p></div><div class="lab-life-grid">'+life_markup(payload['categories'])+'</div>'))
                block.append(fragment('<h2 class="lab-showroom-heading">すべての日用品</h2>'+category_showroom(payload['categories'])))
        if path==site/'today/index.html':
            soup.body['class']=['lab-daily']
            h=soup.select_one('h1')
            if h:h.string='今日、比べておきたい日用品'
            k=soup.select_one('.eyebrow')
            if k:k.string='今日の比較セレクション / 毎朝更新'

        for el in list(soup.select('.product-card')):
            anchor=el.get('id','');match=re.fullmatch(r'(.+)-rank-(\d+)',anchor)
            if not match:continue
            cid,rank=match[1],int(match[2]);c=payload['categories'].get(cid)
            if not c or rank>len(c['items']):continue
            el.replace_with(fragment(card_markup(cid,c,c['items'][rank-1],rank,anchor)))
        for field in soup.select('input:not([aria-label]):not([id])'):
            if field.get('placeholder'):field['aria-label']=field['placeholder']
        group_normalized_cards(soup,payload['categories'])
        answer=soup.select_one('#buying-answer')
        if answer:
            picked=answer.select_one('.answer-pick a[href]')
            match=re.fullmatch(r'#(.+)-rank-(\d+)',picked['href']) if picked else None
            if match and match[1] in payload['categories']:
                rows=payload['categories'][match[1]]['items'];rank=int(match[2])
                if 0<rank<=len(rows):
                    answer['class']=list(answer.get('class',[]))+['lab-answer']
                    content=soup.new_tag('div',attrs={'class':'lab-answer-body'})
                    for child in list(answer.contents):content.append(child.extract())
                    photo=fragment('<div class="lab-answer-photo">'+image_markup(rows[rank-1],True)+'</div>').div
                    context=soup.new_tag('details',attrs={'class':'lab-answer-context'})
                    summary=soup.new_tag('summary');summary.string='価格の目安・比較条件';context.append(summary)
                    for child in list(content.find_all('p',recursive=False)):context.append(child.extract())
                    picked_block=content.select_one('.answer-pick')
                    if picked_block:picked_block.insert_after(context)
                    answer.append(photo);answer.append(content)
        # Secondary units become the main number; the actual catalog remains intact.
        for image in soup.select('.deal-image img'):
            original=image.get('src','');image['src']=photo_url(original);image['width']='420';image['height']='420'
            image['srcset']=photo_url(original,240)+' 240w, '+photo_url(original,420)+' 420w';image['sizes']='(max-width:600px) 110px, 280px'
        # Give existing daily units the same number/unit hierarchy, without
        # changing the displayed value or interpreting product data again.
        for unit in soup.select('.deal-card .unit-price'):
            text=unit.get_text(' ',strip=True)
            match=re.fullmatch(r'¥([\d,.]+)\s*[/／]\s*(.+)',text)
            if match:
                unit.clear()
                unit.append(fragment('<span class="lab-price-value"><small>¥</small>'+esc(match[1])+'</span><span class="lab-price-unit">／'+esc(match[2])+'</span>'))
        for link in soup.select('a.buy-button'):

            link.clear();link.append('楽天で商品を確認する ↗')
        for el in soup.select('.deal-topline .category-chip,.eyebrow,h1,.section-heading h2'):
            if not el.find(True):el.string=clean_emoji(el.get_text())
        for el in soup.select('.related-categories a,.category-page-link,option'):
            for child in list(el.children):
                if isinstance(child,str):child.replace_with(clean_emoji(str(child)))
        # Keep the whole normalized table and its anchors; offer it as an explicit
        # detail after the product experience rather than a huge first-screen wall.
        normalized=soup.select_one('#normalized-comparison')
        if normalized:
            d=soup.new_tag('details',attrs={'class':'lab-table-details'})
            summary=soup.new_tag('summary');summary.string='全商品の単価を比較表で見る';d.append(summary)
            for child in list(normalized.contents):d.append(child.extract())
            normalized.append(d)
            product_section=soup.select_one('section.category-section')
            if product_section:product_section.insert_after(normalized.extract())
        for footer_el in soup.find_all('footer'):footer_el.decompose()
        soup.body.append(fragment(footer()))
        if soup.select_one('#purchase-tools'):
            mobile=fragment(f'<nav class="lab-mobile-nav" aria-label="スマートフォン用ナビゲーション"><a href="{ROOT}categories/">カテゴリ</a><a href="{ROOT}today/">今日の候補</a><a href="#purchase-tools">保存・比較</a></nav>')
        else:mobile=fragment(f'<nav class="lab-mobile-nav" aria-label="スマートフォン用ナビゲーション"><a href="{ROOT}">ホーム</a><a href="{ROOT}categories/">カテゴリ</a><a href="{ROOT}today/">今日の候補</a></nav>')
        soup.body.append(mobile)
        path.write_text(str(soup),encoding='utf-8')
    print('Rebuilt the editorial laboratory design from the verified live catalog.')

if __name__=='__main__':main()
