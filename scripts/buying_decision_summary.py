"""Compare checkout choices across the offers actually published on the page.

The purpose layer retains its own approval, freshness and pause gates. Merely
being present in the acquisition pool never makes an offer eligible here.
"""
import html
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from bs4 import BeautifulSoup
from payment_insights import payment_insight
from comparison_units import quantity_label
from product_display import clean_display_name
from step4_recommendations import select_category

CSS='''.buying-decisions{margin:16px 0;padding:18px;border:1px solid #cfc7b9;border-radius:14px;background:#fff}.buying-decisions h2{font-size:21px;margin:0 0 8px}.buying-decisions p{font-size:14px;line-height:1.7}.buying-decisions table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:14px}.buying-decisions th,.buying-decisions td{padding:10px 5px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}.buying-decisions th:first-child{width:22%}.decision-product,.decision-shop{display:block;line-height:1.6;margin-bottom:5px}.decision-shop{font-size:12px;color:#5f5650}.buying-decisions a{display:inline-flex;align-items:center;min-height:44px;color:#743425;font-weight:bold}.buying-decisions a:focus-visible{outline:3px solid #166f81}@media(max-width:400px){.buying-decisions{padding:12px}.buying-decisions table{font-size:12px}}'''


def published_purpose_offers(doc, category, cid):
    """Require the strict selector AND the exact rendered, approved offer.

    Reuse selection without widening its product/quantity/shipping criteria.
    No purpose section (disabled, stale or paused) means no extra choices.
    """
    section = doc.select_one(f'.step4-recommendations[data-step4-category="{cid}"]')
    if section is None:
        return []
    selected = select_category(cid, category)
    result = []
    for purpose, row in selected['slots'].items():
        if row is None:
            continue
        anchor = f'{cid}-purpose-{purpose}'
        card = section.select_one(f'article.step4-purpose[id="{anchor}"][data-purpose="{purpose}"]')
        link = card.select_one('a.buy-button') if card else None
        offer = row['offer']
        if (link is None or offer.get('postage') != '送料込み' or
                link.get('href') != offer['url'] or
                link.get('data-id') != row['spec_ref'] or
                link.get('data-category-id') != cid or
                link.get('data-purchase-purpose') != purpose):
            continue
        try:
            total = Decimal(str(offer['price']))
            value = Decimal(str(row['unit'][1]))
            if (Decimal(link.get('data-shipping-price', 'NaN')) != total or
                    not total.is_finite() or total <= 0 or
                    not value.is_finite() or value <= 0):
                continue
        except (InvalidOperation, ValueError, TypeError):
            continue
        result.append(('／' + row['unit'][0],
                       (total, value, anchor, quantity_label(offer)), offer))
    return result

def render(markup, category, cid):
    doc=BeautifulSoup(markup,'html.parser')
    groups={}
    details={}
    published_urls=set()
    offers={x.get('url'):x for x in category.get('items',[]) if isinstance(x,dict)}
    for card in doc.select(f'article.product-card[id^="{cid}-rank-"]'):
        link=card.select_one('a.buy-button');price=card.select_one('.lab-price-value');unit=card.select_one('.lab-price-unit');quantity=card.select_one('.purchase-summary')
        if not all([link,price,unit,quantity]):continue
        offer=offers.get(link.get('href'))
        if not offer or offer.get('postage')!='送料込み':continue
        try:
            total=Decimal(link['data-shipping-price']);value=Decimal(re.sub(r'[^0-9.]','',price.get_text()))
            if total!=Decimal(str(offer['price'])) or total<=0 or not total.is_finite() or value<=0 or not value.is_finite():continue
        except (KeyError,InvalidOperation):continue
        groups.setdefault(unit.get_text(' ',strip=True),[]).append((total,value,card['id'],quantity.get_text(' ',strip=True)))
        details[card['id']]=offer
        published_urls.add(offer['url'])
    purpose_count=0
    for unit,record,offer in published_purpose_offers(doc,category,cid):
        if offer['url'] in published_urls:
            continue
        groups.setdefault(unit,[]).append(record)
        details[record[2]]=offer
        published_urls.add(offer['url'])
        purpose_count+=1
    rows=[]
    insights=[]
    e=html.escape
    for unit,items in groups.items():
        finding=payment_insight([{'id':anchor,'unit_key':unit,'checkout_yen':total,'unit_yen':value,'shipping_verified':True} for total,value,anchor,qty in items])
        if finding:
            insights.append('<p class="decision-insight" role="note"><strong>'+e(finding['title'])+'</strong>：今回の支払額は単価最安の候補の方が¥'+f"{finding['checkout_difference_yen']:,.0f}"+'高くなります。必要量・保管場所・商品の適合性を確認してください。</p>')
        for label,pick in [('支払総額を抑える',min(items,key=lambda x:(x[0],x[1],x[2]))),('単価を抑える',min(items,key=lambda x:(x[1],x[0],x[2])))]:
            total,value,anchor,qty=pick
            offer=details[anchor]
            name=clean_display_name(str(offer.get('name','')))
            short=name if len(name)<=36 else name[:36]+'…'
            product=(f'<span class="decision-product" title="{e(name,quote=True)}">{e(short)}</span>' if name else '')
            shop=(f'<span class="decision-shop">{e(str(offer["shop"]))}</span>' if offer.get('shop') else '')
            rows.append(f'<tr data-decision-target="{e(anchor)}"><th scope="row">{label}</th><td>{product}{shop}{e(qty)}<br>¥{total:,.0f}</td><td><span class="decision-unit">¥{value:,.2f}{e(unit)}</span><br><a href="#{e(anchor)}">商品・条件を見る ↓</a></td></tr>')
    if not rows:return ''
    extra='<p><a href="/daily-cost-jp/tools/laundry-cost-per-wash/">濃縮度が違う洗剤は、ラベル使用量で1回費用を比較 →</a></p>' if cid=='laundry' else ''
    scope=('掲載ランキングと、表示中の「買う量から選ぶ」の商品を' if purpose_count else '掲載ランキングの商品を')
    return ('<section id="buying-decisions" class="buying-decisions" aria-labelledby="buying-decisions-title"><h2 id="buying-decisions-title">単価と支払総額、どちらを優先する？</h2>'
        '<p>'+scope+'、1セット購入時の金額と単価の2通りで比較。必要な量と保管場所も確認してください。</p><table><thead><tr><th>選ぶ基準</th><th>商品・販売数量・送料込価格</th><th>単価・商品詳細</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'+''.join(insights)+
        '<p>同じ商品が両方に入る場合があります。異なる銘柄・数量の価格差は、同一商品の値引き額ではありません。重ね数・比較単位が違う商品同士は順位付けしません。</p>'+extra+'</section>')

def build(site=Path('site')):
    catalog=json.loads((site/'data.json').read_text())
    for cid in ('laundry','tissue','toilet-paper'):
        path=site/'categories'/cid/'index.html';raw=path.read_text()
        if 'id="buying-decisions"' in raw:continue
        block=render(raw,catalog['categories'].get(cid,{}),cid)
        main=re.search(r'<main\b[^>]*>',raw)
        if block and main:
            raw=raw[:main.end()]+block+raw[main.end():]
            raw=raw.replace('</head>','<style id="buying-decisions-css">'+CSS+'</style></head>',1)
            path.write_text(raw)
if __name__=='__main__':build()
