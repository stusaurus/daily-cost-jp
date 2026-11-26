import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from product_quality import category_rejection
from sale_quantity import normalize
from yahoo_shopping import YahooShopping, YahooUnavailable
from marketplace_offers import known_shipping
import build_site_entry as rakuten
import os

def pc(row):
    return urlsplit(parse_qs(urlsplit(row['url']).query).get('pc', [''])[0]).path

models = {
 'coffee': [('4901201157592', '職人の珈琲 深いコク スペシャルブレンド 280g'),
            ('4901201157592', 'UCC 280g 職人 スペシャルブレンド 12袋')],
 'mask': [('4967576540155', 'PN-NV65L 65枚 ふつう'),
          ('4901957214853', 'フィッティ 7DAYS プラス 60枚 ふつう'),
          ('4903111951376', '超快適マスク プリーツ ふつう 30枚 4903111951376'),
          ('4903111579709', '超快適マスク プリーツ ふつう 30枚 4903111579709')]
}
for cat, searches in models.items():
    for jan, query in searches:
        try:
            raw=rakuten.fetch_page({'id':cat,'keyword':query,'_supplementary':True},1)
        except HTTPError as e:
            print('Rakuten error',cat,e.code,flush=True)
            continue
        rows=[]
        for entry in raw:
            row=rakuten.core.normalize_item(entry,{'id':cat,'kind':cat if cat=='coffee' else 'count'})
            if not row['item_code']:continue
            if cat=='coffee' and ('280g' not in normalize(row['name']).lower() or 'スペシャル' not in row['name']):continue
            if cat=='mask' and not re.search(r'65|60|30',row['name']):continue
            content=entry.get('Item',entry)
            rows.append([row['item_code'],pc(row),row['price'],row['postage'],row.get('metric'),row.get('sale_quantity_label'),row['name'][:145],known_shipping(content.get('itemCaption','')),category_rejection(cat,row['name'])])
        print('RA',cat,jan,json.dumps(rows[:21],ensure_ascii=False),flush=True)
        time.sleep(1.4)
yahoo=YahooShopping(os.environ['YAHOO_APP_ID'],os.environ['YAHOO_AFFILIATE_ID'])
for cat, searches in models.items():
    for jan in dict(searches):
        try:
            hits=yahoo.search(jan=jan,shipping='free')
        except YahooUnavailable as e:
            print('Yahoo error',cat,e,flush=True)
            continue
        rows=[]
        for hit in hits:
            terms=' '.join(str(hit.get(key) or '') for key in ('name','headLine','description'))
            rows.append([hit['code'],hit['price'],hit.get('janCode')==jan,hit.get('shipping',{}).get('code'),hit.get('priceLabel',{}).get('taxable'),bool(yahoo.affiliate_link(hit)),known_shipping(terms),hit['name'][:145]])
        print('YA',cat,jan,json.dumps(rows[:24],ensure_ascii=False),flush=True)
