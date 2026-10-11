"""Bounded independent household acquisition; no ranking or safety changes."""
from collections import Counter
import copy
import json
import re
from pathlib import Path

from product_quality import filter_items, parsed_quantity
from comparison_units import comparison_unit
from step4_recommendations import destination_matches, sale_band, select_category

QUERIES = {
    'tissue': {'small': ('ボックスティッシュ 200組 5箱', 'ボックスティッシュ 200組 10箱'),
               'everyday': ('ボックスティッシュ 200組 15箱', 'ボックスティッシュ 200組 20箱')},
    'toilet-paper': {'small': ('トイレットペーパー シングル 12ロール', 'トイレットペーパー シングル 6ロール'),
                     'everyday': ('トイレットペーパー シングル 24ロール', 'トイレットペーパー シングル 36ロール')},
    'laundry': {'small': ('洗濯洗剤 詰め替え 400g', '洗濯洗剤 詰め替え 900g'),
                'everyday': ('アタック 洗濯洗剤 詰め替え', 'アリエール 洗濯洗剤 詰め替え')},
}
MAX_REQUESTS = 4
MAX_CANDIDATES = 30


def acquire_household(category, ranked, fetch_page, normalize_item, sleep):
    """Queries are fixed, not user searches. API failure never invents zero supply."""
    cid = category['id']
    report = {'version': 'household-acquisition-v1', 'status': 'NO_VERIFIED_CANDIDATES',
              'ranking_changed': False, 'requests': [], 'eligible_by_purpose': {},
              'reasons': {}, 'distinct_sku_count': None}
    if cid not in QUERIES:
        return [], report
    families = {u[0] for r in filter_items(cid, ranked) if (u := comparison_unit(cid, r))}
    if len(families) != 1:
        report['status'] = 'RANKING_COMPARISON_FAMILY_UNCONFIRMED'
        return [], report
    family = next(iter(families))
    pool, seen, reasons = [], set(), Counter()
    for purpose, queries in QUERIES[cid].items():
        for query in queries:
            if len(report['requests']) >= MAX_REQUESTS:
                break
            sleep(1.15)
            record = {'purpose': purpose, 'received': None, 'eligible': 0, 'status': 'API_FETCH_FAILURE'}
            report['requests'].append(record)
            try:
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
                continue
            for row in safe:
                qty, unit = parsed_quantity(cid, row['name']), comparison_unit(cid, row)
                reason = ('specialized_household_use_unconfirmed' if re.search(r'作業着|作業服|作業衣|ユニフォーム|業務用|工業用|医療用|施設用', row['name']) else
                          'item_identity_unconfirmed' if not destination_matches(row) else
                          'comparison_unit_unconfirmed' if not unit else
                          'incompatible_comparison_family' if unit[0] != family else
                          'requested_purpose_mismatch' if not qty or sale_band(cid, row, qty['quantity']) != purpose else None)
                if reason:
                    reasons[reason] += 1
                    continue
                # Item-code identifies an offer, not a claim of distinct SKU.
                if row['item_code'] in seen:
                    reasons['duplicate_offer'] += 1
                    continue
                seen.add(row['item_code']); pool.append(copy.deepcopy(row)); record['eligible'] += 1
            if record['eligible']:
                break
    # Reapply the whole-pool outlier gate; per-query acceptance is insufficient.
    final_quality = {}
    pool = filter_items(cid, pool, final_quality)
    reasons.update(final_quality[cid]['reasons'])
    pool.sort(key=lambda r: (r['price'], r['unit_price'], r['item_code']))
    pool = pool[:MAX_CANDIDATES]
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


def main():
    import argparse
    import time
    import build_site_entry as entry
    parser = argparse.ArgumentParser(); parser.add_argument('site', type=Path)
    args = parser.parse_args(); snapshot = json.loads((args.site/'data.json').read_text())
    for category in entry.core.CATEGORIES:
        cid = category['id']
        if cid not in QUERIES:
            continue
        data = snapshot['categories'][cid]
        pool, report = acquire_household(category, data['items'], entry.fetch_page, entry.core.normalize_item, time.sleep)
        attach(data, pool, report)
        print(cid, report['status'], report['eligible_by_purpose'])
    (args.site/'data.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
