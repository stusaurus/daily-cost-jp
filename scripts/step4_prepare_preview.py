"""Bounded first-party production capture for unpublished before/after QA."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlsplit,unquote
import concurrent.futures
import json
import re
from step4_purchase_audit import load_live
BASE='https://stusaurus.github.io/daily-cost-jp/'
PAGES=('index.html','categories/laundry/index.html','categories/tissue/index.html','categories/toilet-paper/index.html','products/index.html','today/index.html')

def fetch(rel,root):
    if '..' in rel or rel.startswith('/'):raise ValueError('Unsafe capture path')
    request=Request(BASE+rel,headers={'User-Agent':'DailyCost-Step4-QA/1.0'})
    with urlopen(request,timeout=25) as response:raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Oversized capture')
    target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return raw

def main(root=Path('audit-results/step4-preview-before')):
    root.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        markup=list(pool.map(lambda rel:fetch(rel,root).decode(),PAGES))
    assets={'assets/comparison-catalog.json','assets/purchase-tools.js','assets/laboratory.css'}
    for page in markup:
        for target in re.findall(r'(?:src|href)=["\']([^"\']+)',page):
            path=urlsplit(target).path
            if path.startswith('/daily-cost-jp/assets/'):assets.add(path[len('/daily-cost-jp/'):])
    if len(assets)>60:raise ValueError('Unexpected asset count')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda rel:fetch(rel,root),sorted(assets)))
    snapshot=load_live();(root/'data.json').write_text(json.dumps(snapshot,ensure_ascii=False))
    print('Captured first-party preview pages and assets:',len(assets))
if __name__=='__main__':main()
