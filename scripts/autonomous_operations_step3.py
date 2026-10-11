#!/usr/bin/env python3
"""Evidence-only UI registry and measurement baseline. No generated code execution."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from autonomous_operations_triage import SITE, good_path, read_optional

RECIPE = 'home-ranking-link-tap-v1'
TARGET = 'scripts/design/laboratory.css'
SELECTOR = '#home-ranking-hero .home-rank-all'
BLOCK = '\n/* STEP3 home-ranking-link-tap-v1: restore the existing 44px interaction area. */\n#home-ranking-hero .home-rank-all{display:inline-flex;align-items:center;min-height:44px}\n'
PAGES = ('/', '/categories/laundry/', '/categories/tissue/', '/categories/toilet-paper/', '/products/', '/today/')
WIDTHS = (1440, 390, 320)
HUMAN = {'PRODUCT_PRICE', 'POSTAGE', 'QUANTITY', 'RAKUTEN_LINK', 'SEO_TITLE', 'SAFETY_RULE',
         'PRODUCT_QUALITY_WARNINGS', 'PRODUCT_QUALITY_FAILURE', 'SEO_SNIPPET_RESEARCH',
         'FEATURE_ADDITION', 'DESIGN_REFRESH'}


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def repair(text):
    if (not isinstance(text, str) or len(text) > 200000 or '.home-rank-all' in text or
            'STEP3 home-ranking-link-tap-v1' in text or '.lab-masthead' not in text or '.lab-section-head' not in text):
        return None
    return text + BLOCK


def valid_report(report, css, base_sha, now=None):
    if (not isinstance(report, dict) or report.get('source') != 'daily-cost UI audit v1' or
            report.get('site') != SITE or report.get('read_only') is not True or
            report.get('mode') != 'live' or report.get('status') != 'PASS' or report.get('base_sha') != base_sha):
        return False
    try:
        stamp = dt.datetime.fromisoformat(report['generated_at_utc'].replace('Z', '+00:00'))
        age = ((now or dt.datetime.now(dt.timezone.utc)) - stamp).total_seconds()
        if stamp.tzinfo is None or not -300 <= age <= 21600:
            return False
    except (ValueError, TypeError, KeyError, AttributeError):
        return False
    rows = report.get('observations')
    if not isinstance(rows, list) or len(rows) != 18:
        return False
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        pair = (row.get('path'), row.get('viewport'))
        if (pair not in {(p, w) for p in PAGES for w in WIDTHS} or pair in seen or
                row.get('status') != 'PASS' or row.get('http_status') != 200 or
                row.get('css_hash') != digest(css) or not row.get('screenshot') or
                not isinstance(row.get('issues'), list)):
            return False
        seen.add(pair)
    return True


def ui_decisions(report, css, base_sha):
    authorized = valid_report(report, css, base_sha)
    decisions = []
    if not authorized:
        decisions.append({'code': 'UI_DATA_UNAVAILABLE_OR_UNTRUSTED', 'decision': 'INVESTIGATE', 'path': '/'})
    if isinstance(report, dict) and isinstance(report.get('observations'), list):
        seen = set()
        for row in report['observations'][:18]:
            if not isinstance(row, dict) or row.get('path') not in PAGES:
                continue
            for issue in row.get('issues', [])[:150]:
                if not isinstance(issue, dict):
                    continue
                code = issue.get('code')
                if code not in {'HOME_RANKING_TAP_TARGET', 'SMALL_TAP_TARGET', 'HORIZONTAL_OVERFLOW',
                                'TEXT_CLIPPING_REVIEW', 'CONTRAST_REVIEW', 'TEXT_OVERLAP_REVIEW', 'ACCESSIBLE_NAME_MISSING', 'KEYBOARD_FOCUS_REVIEW'}:
                    continue
                key = (row['path'], code)
                if key in seen:
                    continue
                seen.add(key)
                decisions.append({'code': code, 'path': row['path'], 'decision': 'INVESTIGATE'})
    candidates = []
    if authorized and repair(css):
        home = [r for r in report['observations'] if r['path'] == '/']
        for row in home:
            target = row.get('target') or {}
            rect = target.get('rect') or {}
            width, height = rect.get('width'), rect.get('height')
            if (target.get('count') == 1 and target.get('tag') == 'A' and target.get('href') == 'trends/' and
                    target.get('display') == 'inline' and target.get('minHeight') == '0px' and
                    type(width) in (int, float) and type(height) in (int, float) and
                    math.isfinite(width) and math.isfinite(height) and width >= 44 and 10 <= height < 44):
                candidates.append(row['viewport'])
        if set(candidates) == set(WIDTHS):
            decisions = [d for d in decisions if d['code'] != 'HOME_RANKING_TAP_TARGET']
            decisions.append({'code': 'HOME_RANKING_TAP_TARGET', 'path': '/', 'decision': 'AUTO_FIX',
                              'recipe': RECIPE, 'selector': SELECTOR})
            return {'decisions': decisions[:60], 'recipe': RECIPE, 'candidate': repair(css),
                    'evidence_hash': digest(json.dumps(report, sort_keys=True))}
    return {'decisions': decisions[:60], 'recipe': None, 'candidate': None}


def feature_decisions(step1, joined):
    decisions = []
    for row in (step1 or {}).get('findings', [])[:20]:
        if isinstance(row, dict) and good_path(row.get('path')):
            decisions.append({'code': row.get('code'), 'path': row['path'],
                              'decision': 'HUMAN_ONLY' if row.get('code') in HUMAN else 'INVESTIGATE'})
    if not isinstance(joined, dict) or joined.get('source') != 'GA4 + Search Console read-only page triage':
        decisions.append({'code': 'FUNNEL_DATA_UNAVAILABLE', 'path': '/', 'decision': 'INVESTIGATE'})
    else:
        for row in joined.get('top_investigations', [])[:8]:
            if isinstance(row, dict) and good_path(row.get('path')):
                decisions.append({'code': 'FEATURE_JOURNEY_RESEARCH', 'path': row['path'], 'decision': 'INVESTIGATE'})
    return decisions


def metric(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def baseline(joined):
    """Sources are different populations; no search-to-affiliate conversion claim."""
    valid = isinstance(joined, dict) and joined.get('source') == 'GA4 + Search Console read-only page triage' and joined.get('site') == SITE
    report = {'source': 'daily-cost improvement baseline v1', 'status': 'PROVISIONAL' if valid else 'UNAVAILABLE',
              'revenue': 'NOT_CONNECTED', 'revenue_improvement_verified': False,
              'cross_source_conversion_rate': None, 'pages': [],
              'gsc_period': joined.get('gsc_period_last_28') if valid else None,
              'ga4_period': joined.get('ga4_period_last_28') if valid else None,
              'comparison_save_filter_usage': 'NOT_COLLECTED',
              'evaluation': 'After human-approved publication, compare equal completed 28-day windows within each source, allow reporting latency, exclude known operator tests and retain unknown flags. Low samples are investigation only; no causal/revenue claims.'}
    if valid:
        report['periods_aligned'] = report['gsc_period'] is not None and report['gsc_period'] == report['ga4_period']
        for row in joined.get('page_diagnostics', [])[:12]:
            if not isinstance(row, dict) or not good_path(row.get('path')):
                continue
            g = row.get('gsc_last_28') if joined.get('status') == 'JOINT_PROVISIONAL' else None
            a = row.get('ga4_last_28')
            known = joined.get('ga4_operator_dimension_registered') is True and isinstance(a, dict) and a.get('unknown_operator_clicks') == 0 and joined.get('ga4_source_status') == 'PROVISIONAL'
            clicks = metric(a.get('provisional_non_operator_clicks')) if known else None
            g = {k: metric(g.get(k)) for k in ('impressions', 'clicks', 'ctr', 'position')} if isinstance(g, dict) else None
            report['pages'].append({'path': row['path'], 'search': g, 'ga4_pageviews': metric(a.get('pageviews')) if isinstance(a, dict) else None,
                                    'known_operator_tests': metric(a.get('operator_tests')) if isinstance(a, dict) else None,
                                    'unknown_operator_clicks': metric(a.get('unknown_operator_clicks')) if isinstance(a, dict) else None,
                                    'non_operator_affiliate_clicks': clicks,
                                    'click_evidence': 'UNAVAILABLE' if clicks is None else 'LOW_SAMPLE' if clicks < 20 else 'PROVISIONAL',
                                    'decision': 'INVESTIGATE'})
    return report


def write_candidates():
    root = Path('audit-results')
    from autonomous_operations_step2 import git
    css = Path(TARGET).read_text(encoding='utf-8')
    ui = ui_decisions(read_optional(root / 'step3-ui/report.json'), css, git('rev-parse', 'HEAD'))
    joined = read_optional(root / 'search-affiliate-joint.json')
    report = {'source': 'daily-cost STEP 3 candidates v1', 'ui': {k: v for k, v in ui.items() if k != 'candidate'},
              'features': feature_decisions(read_optional(root / 'autonomous-operations.json'), joined),
              'baseline': baseline(joined), 'automatic_merge': False, 'automatic_deploy': False}
    root.mkdir(exist_ok=True)
    (root / 'step3-candidates.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STEP3 candidates: fixed recipe only; unknown metrics remain unknown')


if __name__ == '__main__':
    write_candidates()
