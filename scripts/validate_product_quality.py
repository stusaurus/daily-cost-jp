"""Block deployment if any catalog/recommendation bypasses the shared filter."""
from __future__ import annotations
import json
import math
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from product_quality import REQUIRED, filter_items, item_rejection
from sync_trend_search_chips import checked_suggestions
from product_display import clean_display_name
from build_freshness import freshness_errors
from candidate_acquisition import TARGET, MAX_REQUESTS, SUPPLEMENTAL_QUERIES


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external, self.chips = [], []
        self.display_names, self._name_tag, self._name_parts = [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('h2', 'h3') or (tag == 'span' and 'top-pick-name' in a.get('class', '').split()):
            self._name_tag, self._name_parts = tag, []
        if tag == 'a' and (urlsplit(a.get('href', '')).hostname or '').endswith('.rakuten.co.jp'):
            self.external.append(a['href'])
        if tag == 'button' and 'chip' in a.get('class', '').split():
            self.chips.append(a.get('data-q'))

    def handle_data(self, data):
        if self._name_tag:
            self._name_parts.append(data)

    def handle_endtag(self, tag):
        if tag == self._name_tag:
            self.display_names.append(' '.join(''.join(self._name_parts).split()))
            self._name_tag = None


def validate_acquisition(catalog, report):
    errors = []
    for cid, category in catalog.get('categories', {}).items():
        audit = report.get(cid, {})
        items = category.get('items') or []
        acquisition = audit.get('acquisition', {})
        requests = acquisition.get('requests', [])
        if audit.get('published') != len(items) or [p.get('url') for p in audit.get('published_products', [])] != [p['url'] for p in items]:
            errors.append(f'{cid}: acquisition report differs from catalog')
        if category.get('error') and not items:
            continue  # A failed first request is visible as an empty category.
        if not requests or len(requests) > MAX_REQUESTS:
            errors.append(f'{cid}: missing/unbounded acquisition evidence')
        baseline = acquisition.get('baseline', {}).get('ranked')
        if baseline is None:
            errors.append(f'{cid}: missing baseline count')
        elif baseline < TARGET and not any(r.get('supplementary') and r.get('query') in SUPPLEMENTAL_QUERIES.get(cid, ()) for r in requests):
            errors.append(f'{cid}: supplemental acquisition was skipped')
    return errors


def validate_catalog(payload):
    errors, accepted = [], {}
    categories = payload.get('categories', {})
    if set(categories) != set(REQUIRED):
        errors.append('Expected exactly the 21 configured categories')
    for category_id, category in categories.items():
        items = category.get('items') or []
        safe = filter_items(category_id, items)
        if len(safe) != len(items):
            errors.append(f'{category_id}: unsafe/outlier items reached the published catalog')
        for item in items:
            reason = item_rejection(category_id, item)
            if reason:
                errors.append(f'{category_id}: {reason}: {item.get("name", "")}')
            if item.get('metric') != category.get('metric'):
                errors.append(f'{category_id}: mixed ranking units')
        accepted[category_id] = {p['url']: p for p in safe}
    if not any(accepted.values()):
        errors.append('Refusing to publish a catalog with zero safe products')
    return errors, accepted


def validate_recommendations(payload, accepted):
    errors = []
    seen = set()
    for row in payload.get('items', []):
        category_id = row.get('id')
        source = accepted.get(category_id, {}).get(row.get('url'))
        if not source:
            errors.append(f'Recommendation outside verified catalog: {category_id}')
            continue
        if category_id in seen:
            errors.append(f'Duplicate recommended category: {category_id}')
        seen.add(category_id)
        if row.get('product_name') != source.get('name') or row.get('metric') != source.get('metric'):
            errors.append(f'Recommendation title/unit differs from catalog: {category_id}')
        for key in ('unit_price', 'price'):
            try:
                same = math.isclose(float(row[key]), float(source[key]), rel_tol=.0001)
            except (KeyError, TypeError, ValueError):
                same = False
            if not same:
                errors.append(f'Recommendation {key} differs from catalog: {category_id}')
    if len(payload.get('items', [])) > 5:
        errors.append('Too many daily recommendations')
    if not payload.get('items') and payload.get('text'):
        errors.append('Empty selection must not generate an X post')
    return errors


def validate(root=Path('site'), report_path=Path('quality-report.json')):
    payload = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    errors, accepted = validate_catalog(payload)
    errors.extend(validate_acquisition(payload, json.loads(report_path.read_text(encoding='utf-8'))))
    today = json.loads((root / 'today/data.json').read_text(encoding='utf-8'))
    social = json.loads((root / 'social/latest.json').read_text(encoding='utf-8'))
    errors.extend(validate_recommendations(today, accepted))
    errors.extend(validate_recommendations(social, accepted))
    errors.extend(freshness_errors(today, payload))
    errors.extend(freshness_errors(social, payload))
    if today.get('items') != social.get('items'):
        errors.append('Today and X have different product candidates')
    all_urls = {url for rows in accepted.values() for url in rows}
    today_urls = {row['url'] for row in today.get('items', [])}
    # Includes top picks and product guides; general ranking has its own scope.
    for path in root.rglob('*.html'):
        rel = path.relative_to(root).as_posix()
        if rel in ('trends/index.html', 'products/index.html'):
            continue
        page = Links(); page.feed(path.read_text(encoding='utf-8'))
        if any(clean_display_name(name) != name for name in page.display_names):
            errors.append(f'{rel}: unformatted promotional product title')
        if rel == 'today/index.html':
            allowed = today_urls
        elif rel.startswith('categories/') and rel != 'categories/index.html':
            allowed = set(accepted.get(rel.split('/')[1], {}))
        else:
            allowed = all_urls
        if any(url not in allowed for url in page.external):
            errors.append(f'{rel}: rendered Rakuten link outside verified selection')
    page = Links(); page.feed((root / 'products/index.html').read_text(encoding='utf-8'))
    if page.chips != [query for _, query, _ in checked_suggestions()]:
        errors.append('Search suggestions differ from checked daily-goods examples')
    return errors, {'categories': len(accepted), 'products': sum(map(len, accepted.values())),
                    'today_picks': len(today.get('items', [])), 'search_examples': len(page.chips)}


if __name__ == '__main__':
    errors, stats = validate()
    print(json.dumps(stats))
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Product quality checks passed.')
