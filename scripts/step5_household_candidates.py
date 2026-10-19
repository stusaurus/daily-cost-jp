"""Bounded independent household acquisition; no ranking or safety changes."""
from collections import Counter
import copy
import json
import re
from pathlib import Path

from product_quality import filter_items, parsed_quantity
from comparison_units import comparison_unit
from step4_recommendations import destination_matches, sale_band, select_category, specialized_household_use, payment_tradeoffs
from step4_purchase_audit import hashed_id

QUERIES = {
    'tissue': {'small': ('ボックスティッシュ 5箱', 'ボックスティッシュ 10箱'),
               'everyday': ('ボックスティッシュ 15箱', 'ボックスティッシュ 20箱')},
    'toilet-paper': {'small': ('トイレットペーパー シングル 12ロール', 'トイレットペーパー シングル 6ロール'),
                     'everyday': ('トイレットペーパー シングル 24ロール', 'トイレットペーパー シングル 36ロール')},
    'laundry': {'small': ('洗濯洗剤 詰め替え 400g', '洗濯洗剤 詰め替え 900g'),
                'everyday': ('アタック 洗濯洗剤 詰め替え', 'アリエール 洗濯洗剤 詰め替え')},
}
MAX_REQUESTS = 4
MAX_CANDIDATES = 30


def acquire_household(category, ranked, fetch_page, normalize_item, sleep, *, payment_followup=True):
    """Queries are fixed, not user searches. API failure never invents zero supply."""
    cid = category['id']
    report = {'version': 'household-acquisition-v1', 'status': 'NO_VERIFIED_CANDIDATES',
              'ranking_changed': False, 'requests': [], 'eligible_by_purpose': {},
              'reasons': {}, 'distinct_sku_count': None, 'payment_followup_enabled': bool(payment_followup)}
    if cid not in QUERIES:
        return [], report
    families = {u[0] for r in filter_items(cid, ranked) if (u := comparison_unit(cid, r))}
    if len(families) != 1:
        report['status'] = 'RANKING_COMPARISON_FAMILY_UNCONFIRMED'
        return [], report
    family = next(iter(families))
    pool, seen, reasons, attempted = [], set(), Counter(), set()

    def request(purpose, index, phase):
        if len(report['requests']) >= MAX_REQUESTS or (purpose,index) in attempted:
            return [], None
        attempted.add((purpose,index))
        sleep(1.15)
        record = {'purpose': purpose, 'query_index':index, 'phase':phase,
                  'received': None, 'eligible': 0, 'status': 'API_FETCH_FAILURE'}
        report['requests'].append(record)
        try:
            query=QUERIES[cid][purpose][index]
            raw = fetch_page({**category, 'keyword': query, '_supplementary': True, '_household': True}, 1)
            if not isinstance(raw, list) or len(raw) > 30 or any(not isinstance(x, dict) for x in raw):
                raise ValueError('Malformed API list')
            rows = [normalize_item(x, category) for x in raw]
            quality = {}
            safe = filter_items(cid, rows, quality)
            reasons.update(quality[cid]['reasons'])
            record.update(received=len(raw), status='API_RESPONSE_ZERO' if not raw else 'RECEIVED')
        except Exception:
            reasons['api_fetch_failure'] += 1
            return [], record
        accepted, codes = [], set(seen)
        for row in safe:
            qty, unit = parsed_quantity(cid, row['name']), comparison_unit(cid, row)
            specialized = specialized_household_use(cid, row['name'])
            reason = ('specialized_household_use_unconfirmed' if specialized else
                      'item_identity_unconfirmed' if not destination_matches(row) else
                      'comparison_unit_unconfirmed' if not unit else
                      'incompatible_comparison_family' if unit[0] != family else
                      'requested_purpose_mismatch' if not qty or sale_band(cid, row, qty['quantity']) != purpose else None)
            if reason:
                reasons[reason] += 1
                continue
            if row['item_code'] in codes:
                reasons['duplicate_offer'] += 1
                continue
            codes.add(row['item_code']); accepted.append(copy.deepcopy(row)); record['eligible'] += 1
        return accepted, record

    def bounded(rows):
        safe=filter_items(cid,rows)
        return sorted(safe,key=lambda r:(r['price'],r['unit_price'],r['item_code']))[:MAX_CANDIDATES]

    def slots(rows):
        return select_category(cid,{'items':ranked,'purpose_candidates':rows})['slots']

    for purpose, queries in QUERIES[cid].items():
        for index in range(len(queries)):
            accepted,record=request(purpose,index,'INITIAL')
            pool.extend(accepted);seen.update(row['item_code'] for row in accepted)
            if accepted:
                break
    # Keep the original whole-pool gate and 30-offer bound before comparing.
    final_quality = {}
    pool = filter_items(cid, pool, final_quality)
    reasons.update(final_quality[cid]['reasons'])
    pool.sort(key=lambda r: (r['price'], r['unit_price'], r['item_code']))
    pool = pool[:MAX_CANDIDATES]
    if payment_followup:
        for purpose, queries in QUERIES[cid].items():
            before=slots(pool)
            if purpose not in {r['smaller_purpose'] for r in payment_tradeoffs(before)}:
                continue
            for index in range(len(queries)):
                if (purpose,index) in attempted or len(report['requests'])>=MAX_REQUESTS:
                    continue
                accepted,record=request(purpose,index,'PAYMENT_FOLLOWUP')
                trial=bounded(pool+accepted);after=slots(trial)
                a,b=before[purpose],after[purpose]
                improves=(a is not None and b is not None and a['offer']['metric']==b['offer']['metric']
                          and a['unit'][0]==b['unit'][0] and b['offer']['price']<a['offer']['price']
                          and all(after[p]==row for p,row in before.items() if p!=purpose))
                record['decision']='LOWER_CHECKOUT_TOTAL_SELECTED' if improves else 'KEEP_EXISTING_SELECTION'
                if improves:
                    pool=trial;seen.update(row['item_code'] for row in accepted)
                break
    for purpose in ('small', 'everyday', 'bulk'):
        report['eligible_by_purpose'][purpose] = sum(sale_band(cid, r, parsed_quantity(cid, r['name'])['quantity']) == purpose for r in pool)
    report['reasons'] = dict(sorted(reasons.items()))
    report['status'] = ('VERIFIED_CANDIDATES' if pool else 'ACQUISITION_UNAVAILABLE' if
                        report['requests'] and all(r['status'] == 'API_FETCH_FAILURE' for r in report['requests']) else 'NO_VERIFIED_CANDIDATES')
    return pool, report


def attach(category_data, candidates, report):
    before = copy.deepcopy(category_data.get('items'))
    category_data['purpose_candidates'] = candidates
    category_data['household_acquisition'] = report
    assert category_data.get('items') == before


def selection_evidence(cid, ranked, pool):
    result=select_category(cid,{'items':ranked,'purpose_candidates':pool})
    return {'status':result['status'],'slots':{p:({'quantity':r['quantity'],'metric':r['offer']['metric'],
        'total_yen':r['offer']['price'],'comparison_unit':r['unit'][0],
        'offer_ref':hashed_id(r['offer'])[0]} if r else None) for p,r in result['slots'].items()}}


def audit_acquisition(category, ranked, fetch_page, normalize_item, sleep):
    """One real acquisition; replay its exact responses for the legacy baseline.

    Raw responses exist only in memory. The receipt is anonymous; no baseline
    API requests, second credentials, deployments or affiliate clicks occur.
    """
    captured={}
    def recording_fetch(cat,page):
        key=(cat['keyword'],page)
        if key in captured:raise ValueError('Duplicate acquisition request')
        captured[key]=None
        response=fetch_page(cat,page)
        captured[key]=copy.deepcopy(response)
        return response
    pool,report=acquire_household(category,ranked,recording_fetch,normalize_item,sleep)
    missing=[]
    def replay(cat,page):
        key=(cat['keyword'],page)
        if key not in captured:
            missing.append(key)
            raise ValueError('Baseline response missing')
        if captured[key] is None:raise RuntimeError('Recorded API failure')
        return copy.deepcopy(captured[key])
    baseline,base_report=acquire_household(category,ranked,replay,normalize_item,lambda n:None,payment_followup=False)
    if missing:raise ValueError('Baseline could not use the exact captured responses')
    cid=category['id'];before=selection_evidence(cid,ranked,baseline);after=selection_evidence(cid,ranked,pool)
    report['comparison']={'mode':'SAME_RESPONSES_LEGACY_REPLAY','baseline':before,'candidate':after,
        'baseline_request_count':len(base_report['requests']),'candidate_request_count':len(report['requests']),
        'baseline_extra_api_requests':0,'same_product_savings_claim':False,
        'lower_total_purposes':[p for p,a in before['slots'].items() if a and (b:=after['slots'][p])
            and a['metric']==b['metric'] and a['comparison_unit']==b['comparison_unit'] and b['total_yen']<a['total_yen']]}
    return pool,report


def main():
    import argparse
    import time
    import build_site_entry as entry
    parser = argparse.ArgumentParser(); parser.add_argument('site', type=Path)
    parser.add_argument('--audit-followup',action='store_true')
    args = parser.parse_args(); snapshot = json.loads((args.site/'data.json').read_text())
    for category in entry.core.CATEGORIES:
        cid = category['id']
        if cid not in QUERIES:
            continue
        data = snapshot['categories'][cid]
        acquire=audit_acquisition if args.audit_followup else acquire_household
        pool, report = acquire(category, data['items'], entry.fetch_page, entry.core.normalize_item, time.sleep)
        attach(data, pool, report)
        print(cid, report['status'], report['eligible_by_purpose'])
    (args.site/'data.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
