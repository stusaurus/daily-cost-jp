"""Aggregate a GA4 event export; keep ambiguous traffic out of production counts.

CSV columns: eventName, pageLocation, operator_test, eventCount.
Require pageLocation because pagePath alone cannot distinguish local development.
"""
import csv
import json
import sys
from collections import Counter
from urllib.parse import urlsplit


def aggregate(rows):
    counts = Counter(production_operator=0, production_non_operator=0,
                     production_unknown=0, development=0, other_site=0, unscoped=0)
    for row in rows:
        if row.get('eventName') != 'affiliate_click':
            continue
        count = int(row['eventCount'])
        if count < 0:
            raise ValueError('Negative eventCount')
        url = urlsplit(row.get('pageLocation', ''))
        if not url.hostname:
            bucket = 'unscoped'
        elif url.hostname in ('localhost', '127.0.0.1', '::1'):
            bucket = 'development'
        elif url.hostname != 'stusaurus.github.io' or not url.path.startswith('/daily-cost-jp/'):
            bucket = 'other_site'
        else:
            flag = row.get('operator_test', '').strip()
            bucket = {'1': 'production_operator', '0': 'production_non_operator'}.get(flag, 'production_unknown')
        counts[bucket] += count
    return dict(counts)


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8-sig', newline='') as source:
        print(json.dumps(aggregate(csv.DictReader(source)), ensure_ascii=False, indent=2))
