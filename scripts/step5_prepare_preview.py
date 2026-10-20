"""Real API purpose pool over a faithful unpublished production capture."""
import json
import copy
import re
import shutil
from pathlib import Path
from step4_prepare_candidate import main as apply_current

ROOT=Path('audit-results')


def acquire_preview(snapshot, categories, fetch, normalize, sleep,
                    comparison_category='laundry', baseline_queries=None, baseline_tissue_reviews=False):
    """CI only: compare one query plan using bounded, shared responses."""
    import step5_household_candidates as h
    if comparison_category!='laundry' and baseline_queries is None:
        raise ValueError('Explicit baseline queries required for this category')
    revised=copy.deepcopy(snapshot)
    comparison=None
    for category in categories:
        cid=category['id']
        if cid not in h.QUERIES:continue
        data=revised['categories'][cid]
        cache={}
        query_evidence=[]
        in_baseline=False
        def cached_fetch(query_category,page):
            legacy=bool(in_baseline and baseline_tissue_reviews and cid=='tissue' and
                        query_category.get('_household_purpose')=='everyday')
            query_category={**query_category,'_household_require_reviews':legacy}
            review_flag=int(not (cid=='tissue' and query_category.get('_household') is True and
                                 query_category.get('_household_purpose')=='everyday' and not legacy))
            key=(query_category['keyword'],page,review_flag)
            if key not in cache:
                if len(cache)>=5:raise ValueError('Preview query budget exceeded')
                try:
                    cache[key]=fetch(query_category,page)
                except Exception:
                    cache[key]=RuntimeError('Preview acquisition unavailable')
                    if cid==comparison_category:
                        query_evidence.append({'keyword':key[0],'page':page,'has_review_flag':review_flag,'status':'UNAVAILABLE','items':None})
                else:
                    if cid==comparison_category:
                        try:
                            evidence=public_query_evidence(query_category,page,cache[key],normalize)
                            evidence['has_review_flag']=review_flag
                            query_evidence.append(evidence)
                        except Exception:
                            query_evidence.append({'keyword':key[0],'page':page,'has_review_flag':review_flag,'status':'EVIDENCE_UNAVAILABLE','items':None})
            value=cache[key]
            if isinstance(value,Exception):raise value
            return copy.deepcopy(value)
        pool,report=h.acquire_household(category,data['items'],cached_fetch,normalize,sleep)
        h.attach(data,pool,report)
        if cid!=comparison_category:continue
        candidate=h.select_category(cid,data)
        plan=copy.deepcopy(h.QUERIES)
        try:
            old_queries=baseline_queries or {'small':('洗濯洗剤 詰め替え 400g','洗濯洗剤 詰め替え 900g')}
            h.QUERIES[cid].update(old_queries)
            in_baseline=True
            old_pool,old_report=h.acquire_household(category,data['items'],cached_fetch,normalize,sleep)
        finally:
            in_baseline=False
            h.QUERIES.clear();h.QUERIES.update(plan)
        old_data=copy.deepcopy(snapshot['categories'][cid])
        h.attach(old_data,old_pool,old_report)
        baseline=h.select_category(cid,old_data)
        def receipt(selection):
            result={}
            for purpose,row in selection['slots'].items():
                record=None if row is None else {
                    'quantity':row['quantity'],'price_total_yen':row['offer']['price'],
                    'comparison_unit':row['unit'],'spec_ref':row['spec_ref']}
                if row and cid=='tissue':
                    from sale_quantity import normalize as normalize_title
                    title=normalize_title(row['offer']['name'])
                    groups={int(n) for n in re.findall(r'(\d+)\s*組',title)}
                    sheets={int(n) for n in re.findall(r'(\d+)\s*枚',title)}
                    pairs=next(iter(groups)) if len(groups)==1 else None
                    sheet_count=next(iter(sheets)) if len(sheets)==1 else None
                    record['tissue_specification']={'boxes':row['quantity'],
                        'pairs_per_box':pairs,'total_pairs':pairs*row['quantity'] if pairs else None,
                        'sheets_per_box':sheet_count,
                        'sheets_per_pair':sheet_count//pairs if pairs and sheet_count and sheet_count%pairs==0 else None}
                result[purpose]=record
            return result
        before,after=receipt(baseline),receipt(candidate)
        comparable=bool(report['requests'] and old_report['requests']) and all(r['status'] in ('RECEIVED','API_RESPONSE_ZERO')
                       for r in report['requests']+old_report['requests'])
        comparison={'status':'OBSERVED' if comparable else 'UNKNOWN',
            'query_evidence':query_evidence,
            'baseline':before,'candidate':after,'baseline_acquisition':old_report,
            'unique_api_queries':len(cache),'maximum_unique_queries':5,
            'small_payment_lower':bool(comparable and before['small'] and after['small'] and
                after['small']['price_total_yen']<before['small']['price_total_yen']),
            'other_slots_unchanged':all(before[p]==after[p] for p in ('everyday','bulk')),
            'payment_lower_purposes':[p for p in before if comparable and before[p] and after[p]
                and after[p]['price_total_yen']<before[p]['price_total_yen']],
            'unchanged_purposes':[p for p in before if before[p]==after[p]],
            'interpretation':'Different products/specifications; not same-product savings or revenue proof'}
    return revised,comparison


def public_query_evidence(category,page,raw,normalize):
    """Unpublished fixed product-query evidence; explicit allowlist, no error bodies."""
    from product_quality import item_rejection, parsed_quantity
    if not isinstance(raw,list) or len(raw)>30 or any(not isinstance(x,dict) for x in raw):
        return {'keyword':category['keyword'],'page':page,'status':'MALFORMED','items':None}
    items=[]
    for row in raw:
        source=row.get('Item',row)
        if not isinstance(source,dict):
            continue
        public={key:source[key] for key in ('itemName','itemCode','itemPrice','postageFlag','itemUrl','shopName','reviewCount')
                if key in source and isinstance(source[key],(str,int,float)) and not isinstance(source[key],bool)}
        public={key:value[:1000] if isinstance(value,str) else value for key,value in public.items()}
        normalized=normalize(row,category)
        public['individual_gate_reason']=item_rejection(category['id'],normalized)
        public['parsed_quantity']=parsed_quantity(category['id'],normalized['name'])
        items.append(public)
    return {'keyword':category['keyword'],'page':page,'status':'RECEIVED' if raw else 'API_RESPONSE_ZERO',
            'scope':'INDIVIDUAL_GATE_BEFORE_POOL_OUTLIER_AND_PURPOSE_GATES','items':items}


def main():
    before=ROOT/'step4-preview-before';after=ROOT/'step4-preview-after'
    shutil.copytree(before,after)
    # Remove only the independent existing purpose layer; all ranking bytes stay.
    for path in after.rglob('index.html'):
        text=path.read_text()
        text=re.sub(r'<details class="step4-home-purpose">.*?</details>','',text,flags=re.S)
        text=re.sub(r'<section\b[^>]*data-step4-category=[^>]*>.*?</section>','',text,flags=re.S)
        text=re.sub(r'<style id="step4-purpose-style">.*?</style>','',text,flags=re.S)
        path.write_text(text)
    original=json.loads((before/'data.json').read_text())
    import build_site_entry as entry
    import time
    revised,comparison=acquire_preview(original,entry.core.CATEGORIES,entry.fetch_page,
        entry.core.normalize_item,time.sleep,comparison_category='tissue',
        baseline_queries={'everyday':('ボックスティッシュ 15箱','ボックスティッシュ 20箱')},
        baseline_tissue_reviews=True)
    (after/'data.json').write_text(json.dumps(revised,ensure_ascii=False,indent=2))
    protected=json.loads(json.dumps(revised))
    for cid in ('tissue','laundry','toilet-paper'):
        for key in ('purpose_candidates','household_acquisition'):protected['categories'][cid].pop(key,None)
    expected=json.loads(json.dumps(original))
    for cid in ('tissue','laundry','toilet-paper'):
        for key in ('purpose_candidates','household_acquisition'):expected['categories'][cid].pop(key,None)
    assert protected==expected, 'Original ranking/source changed'
    apply_current(after)
    (ROOT/'step5-acquisition-verification.json').write_text(json.dumps({
        'source':'real API unpublished household preview', 'ranking_unchanged':True,
        'categories':{c:revised['categories'][c]['household_acquisition'] for c in ('tissue','laundry','toilet-paper')},
        'tissue_query_comparison':comparison,
        'sales_status':'NOT_CONNECTED'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
