import json, os, time
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit,parse_qs
from urllib.request import Request
from marketplace_offers import known_shipping
from rakuten_request import fetch_json
import build_site_entry as r

codes = {
 'coffee': ['drink-market:10097409','misono-support:10009266','nozomi-market:10005123'],
 'mask': ['kurasio-en:10000600','kurasio-en:10000602','kzstore:10000862','megadrug:10042504',
          'tsuruha:10094980','tsuruha:10094981','denchiya-bekkan:10260570']
}
for cat, entries in codes.items():
 for code in entries:
  params={"applicationId":r.core.APP_ID,"affiliateId":r.core.AFFILIATE_ID,
          "itemCode":code,"availability":1,"hits":1,"formatVersion":2}
  req=Request(r.core.API_URL+"?"+urlencode(params),headers={"accessKey":r.core.ACCESS_KEY,"Origin":"https://stusaurus.github.io","Referer":r.core.SITE_URL})
  try: answer=fetch_json(req)
  except HTTPError as error:
   print('EX HTTP',cat,code,error.code,flush=True);continue
  for raw in answer.get('Items',answer.get('items',[])):
   item=raw.get('Item',raw)
   caption=item.get('itemCaption','')
   pc=urlsplit(parse_qs(urlsplit(item.get('affiliateUrl','')).query).get('pc',[''])[0])
   mobile=urlsplit(parse_qs(urlsplit(item.get('affiliateUrl','')).query).get('m',[''])[0])
   print('EX',cat,json.dumps([code,pc.path,mobile.path,item.get('itemPrice'),item.get('postageFlag'),
      item.get('availability'),known_shipping(caption),item.get('itemName',''), len(caption)],ensure_ascii=False),flush=True)
  time.sleep(1.3)
