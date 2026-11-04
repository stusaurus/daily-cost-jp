"""Expose price/quantity tradeoffs from already published ranking cards only."""
import html
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from bs4 import BeautifulSoup
from payment_insights import payment_insight

CSS='''.buying-decisions{margin:16px 0;padding:18px;border:1px solid #cfc7b9;border-radius:14px;background:#fff}.buying-decisions h2{font-size:21px;margin:0 0 8px}.buying-decisions p{font-size:14px;line-height:1.7}.buying-decisions table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:14px}.buying-decisions th,.buying-decisions td{padding:10px 5px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}.buying-decisions a{display:inline-flex;align-items:center;min-height:44px;color:#743425;font-weight:bold}.buying-decisions a:focus-visible{outline:3px solid #166f81}@media(max-width:400px){.buying-decisions{padding:12px}.buying-decisions table{font-size:12px}}'''

def render(markup, category, cid):
    doc=BeautifulSoup(markup,'html.parser')
    groups={}
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
    rows=[]
    insights=[]
    e=html.escape
    for unit,items in groups.items():
        finding=payment_insight([{'id':anchor,'unit_key':unit,'checkout_yen':total,'unit_yen':value,'shipping_verified':True} for total,value,anchor,qty in items])
        if finding:
            insights.append('<p class="decision-insight" role="note"><strong>'+e(finding['title'])+'</strong>：今回の支払額は単価最安の候補の方が¥'+f"{finding['checkout_difference_yen']:,.0f}"+'高くなります。必要量・保管場所・商品の適合性を確認してください。</p>')
        for label,pick in [('支払総額を抑える',min(items,key=lambda x:(x[0],x[1],x[2]))),('単価を抑える',min(items,key=lambda x:(x[1],x[0],x[2])))]:
            total,value,anchor,qty=pick
            rows.append(f'<tr data-decision-target="{e(anchor)}"><th scope="row">{label}</th><td>{e(qty)}<br>¥{total:,.0f}</td><td>¥{value:,.2f}{e(unit)}<br><a href="#{e(anchor)}">商品・条件を見る ↓</a></td></tr>')
    if not rows:return ''
    extra='<p><a href="/daily-cost-jp/tools/laundry-cost-per-wash/">濃縮度が違う洗剤は、ラベル使用量で1回費用を比較 →</a></p>' if cid=='laundry' else ''
    return ('<section id="buying-decisions" class="buying-decisions" aria-labelledby="buying-decisions-title"><h2 id="buying-decisions-title">単価と支払総額、どちらを優先する？</h2>'
        '<p>掲載ランキングの商品を、今回払う金額と単価の2通りで比較。必要な量と保管場所も確認してください。</p><table><thead><tr><th>選ぶ基準</th><th>購入する量・送料込総額</th><th>単価・商品詳細</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'+''.join(insights)
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
