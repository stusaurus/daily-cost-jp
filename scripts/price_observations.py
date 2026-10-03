"""Carry observed prices through Pages rebuilds, keyed by product and specification.

Reads only public first-party data, bounded by size and timeout. Missing history
is never reconstructed or described as historical evidence.
"""
import hashlib
import json
import math
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from zoneinfo import ZoneInfo

BASE = 'https://stusaurus.github.io/daily-cost-jp/'
CACHE = Path('.previous-observations.json')
JST = ZoneInfo('Asia/Tokyo')


def identity(cid, item):
    target = parse_qs(urlsplit(item.get('url', '')).query).get('pc', [item.get('url', '')])[0]
    # A changed title/capacity starts a new series even at the same shop URL.
    specification = [cid, target, item.get('name'), item.get('metric'), item.get('evidence')]
    return hashlib.sha256(json.dumps(specification, ensure_ascii=False).encode()).hexdigest()[:24]


def fetch_public(path):
    req = urllib.request.Request(BASE + path, headers={'User-Agent':'daily-cost-quality-audit/1.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(3_000_001)
    if len(raw) > 3_000_000: raise ValueError('Previous observation file too large')
    return json.loads(raw)


def prepare():
    previous = {'version':1,'products':{},'selections':[]}
    for path, key in [('price-observations.json','history'), ('data.json','catalog'), ('today/data.json','today')]:
        try: previous[key] = fetch_public(path)
        except (OSError, ValueError) as exc: print(f'Previous {key} unavailable ({type(exc).__name__}); no history inferred.')
    CACHE.write_text(json.dumps(previous, ensure_ascii=False), encoding='utf-8')


def previous():
    try: return json.loads(CACHE.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def update(payload, prior, now=None):
    now = now or datetime.now(JST)
    cutoff = (now - timedelta(days=60)).isoformat()
    history = prior.get('history', {})
    products = history.get('products', {})
    result = {'version':1,'products':{},'selections':history.get('selections', [])[-120:]}
    # Keep temporarily absent products, but only for the stated retention window.
    for key, rows in products.items():
        safe = []
        for row in rows if isinstance(rows, list) else []:
            try:
                at = datetime.fromisoformat(row['at'])
                price = float(row['price'])
                if at.tzinfo and now-timedelta(days=60) <= at <= now and math.isfinite(price) and price > 0:
                    safe.append({'at':row['at'],'price':price})
            except (KeyError, ValueError, TypeError): pass
        if safe: result['products'][key] = sorted(safe, key=lambda r:r['at'])[-120:]
    for cid, cat in payload['categories'].items():
        for item in cat['items']:
            key = identity(cid, item)
            rows = result['products'].setdefault(key, [])
            at = payload['updated_at']
            if not any(r['at'] == at for r in rows): rows.append({'at':at,'price':item['price']})
            result['products'][key] = rows[-120:]
    return result


def stats(cid, item, history):
    rows = history.get('products', {}).get(identity(cid, item), [])
    days = {r['at'][:10] for r in rows}
    # Different days are needed; morning/evening alone is not a trend.
    if len(days) < 2: return None
    old = [r for r in rows if r['at'][:10] != rows[-1]['at'][:10]]
    before = old[-1]['price']
    current = float(item['price'])
    return {'days':len(days),'previous':before,'minimum':min(r['price'] for r in rows),
            'drop_percent':(before-current)/before*100,'first':rows[0]['at'],'last':rows[-1]['at']}


if __name__ == '__main__': prepare()
