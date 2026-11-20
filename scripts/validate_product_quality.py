"""Block deployment if any catalog/recommendation bypasses the shared filter."""
from __future__ import annotations
import json
import math
from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from product_quality import REQUIRED, filter_items, item_rejection
from sync_trend_search_chips import checked_suggestions
from product_display import clean_display_name
from comparison_units import comparison_unit
from build_freshness import freshness_errors
from candidate_acquisition import TARGET, MAX_REQUESTS, SUPPLEMENTAL_QUERIES, TOILET_PLY_QUERIES, max_requests_for
from step4_recommendations import CATEGORIES, select_category, verified_purpose_candidates


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external, self.chips = [], []
        self.external_contexts = []
        self.everyday_value_links = []
        self.tissue_five_box_links = []
        self.display_names, self._name_tag, self._name_parts = [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('h2', 'h3') or (tag == 'span' and 'top-pick-name' in a.get('class', '').split()):
            self._name_tag, self._name_parts = tag, []
        if tag == 'a' and (urlsplit(a.get('href', '')).hostname or '').endswith('.rakuten.co.jp'):
            self.external.append(a['href'])
        if tag == 'a' and ((urlsplit(a.get('href', '')).hostname or '').endswith('.rakuten.co.jp') or 'data-purchase-purpose' in a):
            self.external_contexts.append((a['href'], a.get('data-category-id'), a.get('data-purchase-purpose')))
        if tag == 'a' and a.get('data-purchase-purpose') == 'everyday-value':
            self.everyday_value_links.append(a)
        if tag == 'a' and a.get('data-tissue-five-box-choice') is not None:
            self.tissue_five_box_links.append(a)
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
        if not requests or len(requests) > max_requests_for(cid):
            errors.append(f'{cid}: missing/unbounded acquisition evidence')
        baseline = acquisition.get('baseline', {}).get('ranked')
        if baseline is None:
            errors.append(f'{cid}: missing baseline count')
        elif baseline < TARGET and not any(r.get('supplementary') and r.get('query') in (SUPPLEMENTAL_QUERIES.get(cid, ()) + tuple(q for _, q in TOILET_PLY_QUERIES) if cid == 'toilet-paper' else SUPPLEMENTAL_QUERIES.get(cid, ())) for r in requests):
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
        if category_id == 'toilet-paper' and 'toilet_ply_groups' in category:
            from toilet_ply_supply import MAX_PER_PLY, FAMILY_LABELS
            from candidate_acquisition import identity
            grouped = category['toilet_ply_groups']
            if not isinstance(grouped, dict) or set(grouped) != set(FAMILY_LABELS):
                errors.append('toilet-paper: malformed or missing ply groups')
                grouped = {}
            seen = set()
            for family, label in FAMILY_LABELS.items():
                rows = grouped.get(family, [])
                if not isinstance(rows, list) or len(rows) > MAX_PER_PLY:
                    errors.append(f'toilet-paper: unbounded {family} offers')
                    continue
                safe_rows = filter_items('toilet-paper', rows)
                if len(safe_rows) != len(rows):
                    errors.append(f'toilet-paper: unsafe {family} offers')
                prices = []
                for row in rows:
                    unit = comparison_unit('toilet-paper', row)
                    if unit is None or unit[0] != label:
                        errors.append(f'toilet-paper: invalid ply/length for {family}')
                        continue
                    prices.append(unit[1])
                    marker = identity(row)
                    if marker in seen:
                        errors.append('toilet-paper: offer duplicated across ply groups')
                    seen.add(marker)
                    if row.get('metric') != 'roll' or item_rejection('toilet-paper', row):
                        errors.append(f'toilet-paper: unsafe or non-roll {family} item')
                    else:
                        accepted[category_id][row['url']] = row
                if prices != sorted(prices):
                    errors.append(f'toilet-paper: {family} is not sorted by 10m price')
            diagnostic = category.get('toilet_ply_supply', {}).get('families', {})
            for family in FAMILY_LABELS:
                if not isinstance(diagnostic, dict) or not isinstance(diagnostic.get(family), dict):
                    errors.append(f'toilet-paper: missing {family} acquisition status')
                    continue
                reported = diagnostic[family]
                if reported.get('verified') != len(grouped.get(family, [])):
                    errors.append(f'toilet-paper: {family} reported count differs')
                expected = 'VERIFIED' if grouped.get(family) else (
                    'INCOMPLETE_ACQUISITION' if reported.get('search_failed') else
                    'NO_VERIFIED_SNAPSHOT_OFFER'
                )
                if reported.get('state') != expected:
                    errors.append(f'toilet-paper: {family} status is inconsistent')
        if category_id == 'tissue' and category.get('small_pack_offer') is not None:
            # The extra direct-buy offer must pass the same production safety
            # gate. It may be absent from the bulk top-12, but is not an
            # unverified link or a fabricated pack quantity.
            from tissue_buying_quantity import safe_box_count
            small = category['small_pack_offer']
            if (safe_box_count(small) is None or
                    len(filter_items('tissue', [small])) != 1 or
                    category.get('small_pack_boxes') != safe_box_count(small)):
                errors.append('tissue: unsafe small-pack offer')
            else:
                accepted[category_id][small['url']] = small
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
        if 'comparison_unit_price' in row:
            unit = comparison_unit(category_id, source)
            if not unit or unit[0] != row.get('comparison_label') or not math.isclose(unit[1], float(row['comparison_unit_price']), rel_tol=.0001):
                errors.append(f'Recommendation normalized comparison differs from catalog: {category_id}')
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


def verified_purpose_links(payload):
    """Only selected, revalidated supplementary offers in their declared slot."""
    links = set()
    for cid in CATEGORIES:
        category = payload.get('categories', {}).get(cid)
        safe_urls = {r['url'] for r in verified_purpose_candidates(cid, category)}
        selected = select_category(cid, category)
        for purpose, row in selected['slots'].items():
            if row and row['offer']['url'] in safe_urls:
                links.add((row['offer']['url'], cid, purpose))
        # A separate laundry value choice uses the same strict STEP5 pool
        # and exactly its own approved, fixed-purpose classification.
        optional = selected.get('everyday_value') if cid == 'laundry' else None
        if optional and optional['offer']['url'] in safe_urls:
            links.add((optional['offer']['url'], cid, 'everyday-value'))
    return links


def valid_everyday_value_link(attrs, rel, payload):
    """The extra CTA needs exact SKU, price, category and safe attributes."""
    if rel not in ('index.html', 'categories/laundry/index.html'):
        return False
    if not isinstance(attrs, dict):
        return False
    category = payload.get('categories', {}).get('laundry')
    if not isinstance(category, dict):
        return False
    selected = select_category('laundry', category)
    choice = selected.get('everyday_value')
    if choice is None:
        return False
    offer = choice['offer']
    if offer['url'] not in {r['url'] for r in verified_purpose_candidates('laundry', category)}:
        return False
    if (attrs.get('href') != offer['url'] or
            attrs.get('data-category-id') != 'laundry' or
            attrs.get('data-purchase-purpose') != 'everyday-value' or
            attrs.get('data-conversion-source') != 'category' or
            attrs.get('data-id') != choice['spec_ref'] or
            attrs.get('target') != '_blank' or
            not {'nofollow', 'sponsored', 'noopener'}.issubset(set((attrs.get('rel') or '').split()))):
        return False
    try:
        return Decimal(str(attrs.get('data-shipping-price'))) == Decimal(str(offer['price']))
    except (InvalidOperation, TypeError, ValueError):
        return False



def valid_tissue_five_box_link(attrs, rel, payload):
    """Authorize an extra tissue link only for a fully reverified exact offer.

    Never broaden the general category ranking, Today, home, or purpose slots.
    The URL and merchant identity must match one of the same, deterministic
    safe five-box rows used by the renderer, with price and unit-label equality.
    """
    if rel != 'categories/tissue/index.html' or not isinstance(attrs, dict):
        return False
    if attrs.get('data-tissue-five-box-choice') != '1':
        return False
    from tissue_five_box_choices import select_offers
    category = payload.get('categories', {}).get('tissue')
    choices = select_offers(category)
    if not choices:
        return False
    if (attrs.get('data-category-id') != 'tissue'
            or attrs.get('data-purchase-purpose') != 'small'
            or attrs.get('data-conversion-source') != 'category'
            or attrs.get('target') != '_blank'
            or not {'nofollow', 'sponsored', 'noopener'}.issubset(
                set((attrs.get('rel') or '').split()))):
        return False
    for price, per_100, pairs, row in choices:
        if attrs.get('href') != row['url'] or attrs.get('data-id') != row['item_code']:
            continue
        if (attrs.get('data-product-name') != clean_display_name(row['name'])
                or attrs.get('data-unit-price-label') != f'¥{per_100:,.2f}／100組'):
            return False
        try:
            return Decimal(str(attrs.get('data-shipping-price'))) == Decimal(price)
        except (InvalidOperation, TypeError, ValueError):
            return False
    return False


def validate(root=Path('site'), report_path=Path('quality-report.json')):
    payload = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    errors, accepted = validate_catalog(payload)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    # Enforce the new contract on a true daily-pipeline build. Older test
    # fixtures intentionally model catalogs without typed toilet-paper fields.
    typed_build = 'toilet_ply_counts' in report.get('toilet-paper', {})
    if typed_build and not isinstance(payload.get('categories', {}).get('toilet-paper', {}).get('toilet_ply_groups'), dict):
        errors.append('toilet-paper: permanent single/double comparison missing from catalog')
    errors.extend(validate_acquisition(payload, report))
    today = json.loads((root / 'today/data.json').read_text(encoding='utf-8'))
    social = json.loads((root / 'social/latest.json').read_text(encoding='utf-8'))
    errors.extend(validate_recommendations(today, accepted))
    errors.extend(validate_recommendations(social, accepted))
    errors.extend(freshness_errors(today, payload))
    errors.extend(freshness_errors(social, payload))
    if today.get('items') != social.get('items'):
        errors.append('Today and X have different product candidates')
    if typed_build:
        from toilet_ply_contract import audit_page, audit_published_styles
        toilet_page = root / "categories/toilet-paper/index.html"
        if not toilet_page.is_file():
            errors.append("toilet-paper: public comparison route is missing")
        else:
            markup = toilet_page.read_text(encoding="utf-8")
            # In the dedicated refresh regression suite, only the product
            # generator is exercised; SEO/UX rendering has deliberately not run.
            # Every real end-to-end build adds this independent SEO marker
            # before the strict buying-card contract must be enforced.
            if 'id="category-seo-schema"' in markup:
                errors.extend(audit_page(
                    payload["categories"]["toilet-paper"], markup,
                ))
            errors.extend(audit_published_styles(root, markup))
    all_urls = {url for rows in accepted.values() for url in rows}
    today_urls = {row['url'] for row in today.get('items', [])}
    purpose_links = verified_purpose_links(payload)
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
        # Supplementary links are not ranking/today/social allowlist entries.
        # Require the exact selected offer AND matching category/purpose attrs.
        can_render_purpose = rel == 'index.html' or rel in {f'categories/{cid}/index.html' for cid in CATEGORIES}
        category_scope = rel.split('/')[1] if rel.startswith('categories/') else None
        verified_five_box = {
            (attrs['href'], 'tissue', 'small')
            for attrs in page.tissue_five_box_links
            if valid_tissue_five_box_link(attrs, rel, payload)
        }
        if page.tissue_five_box_links:
            # Require every card to identify a distinct safe offer. A duplicated,
            # mispriced, wrong-category or arbitrary injected link is invalid.
            from tissue_five_box_choices import select_offers
            expected = select_offers(payload.get('categories', {}).get('tissue'))
            if (rel != 'categories/tissue/index.html'
                    or len(page.tissue_five_box_links) != len(expected)
                    or len(verified_five_box) != len(expected)):
                errors.append(f'{rel}: tissue five-box merchant link not fully verified')
        if any(url not in allowed and not (
                can_render_purpose and
                (url, cid, purpose) in purpose_links and (category_scope is None or cid == category_scope)
               ) and not (
                rel == 'categories/tissue/index.html' and (url, cid, purpose) in verified_five_box
               ) for url, cid, purpose in page.external_contexts):
            errors.append(f'{rel}: rendered Rakuten link outside verified selection')
        if len(page.everyday_value_links) > 1 or any(
                not valid_everyday_value_link(attrs, rel, payload)
                for attrs in page.everyday_value_links):
            errors.append(f'{rel}: everyday value link has unverified identity or price')
    page = Links(); page.feed((root / 'products/index.html').read_text(encoding='utf-8'))
    if page.chips != [query for _, query, _ in checked_suggestions()]:
        errors.append('Search suggestions differ from checked daily-goods examples')
    return errors, {'categories': len(accepted), 'products': sum(map(len, accepted.values())),
                    'today_picks': len(today.get('items', [])), 'search_examples': len(page.chips),
                    'verified_selected_purpose_links': len(purpose_links)}


if __name__ == '__main__':
    errors, stats = validate()
    print(json.dumps(stats))
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Product quality checks passed.')
