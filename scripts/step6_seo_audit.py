"""Bounded first-party SEO/GSC audit. GET only; no submissions or copy execution."""
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from autonomous_operations_triage import SITE, good_path, read_optional
from step6_seo_content import REGISTRY, TARGET, policy, recipe, repair

SOURCE = 'daily-cost STEP6 SEO audit v1'
MAX_URLS = 100
MAX_BYTES = 2_000_000
NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def safe_url(url):
    if not isinstance(url, str) or len(url) > 500:
        return False
    try:
        u, root = urlsplit(url), urlsplit(SITE)
        return (u.scheme == 'https' and u.netloc == root.netloc and
                u.path.startswith(root.path) and not u.query and not u.fragment and
                not any(v in unquote(u.path) for v in ('..', '\\', '\x00', '\r', '\n')))
    except ValueError:
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    if not safe_url(url):
        raise ValueError('Out-of-scope audit URL')
    try:
        with build_opener(NoRedirect()).open(Request(url, headers={
                'User-Agent': 'DailyCost-ReadOnlySEO/1.0'}), timeout=15) as r:
            raw = r.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return {'status': 'OVERSIZE', 'http_status': r.status}
            return {'status': 'OBSERVED', 'http_status': r.status,
                    'text': raw.decode('utf-8'), 'x_robots_tag': r.headers.get('X-Robots-Tag', '')}
    except HTTPError as exc:
        return {'status': 'REDIRECT' if 300 <= exc.code < 400 else 'HTTP_FAILURE',
                'http_status': exc.code, 'redirect_in_scope': safe_url(urljoin(url, exc.headers.get('Location', '')))}
    except (OSError, ValueError, UnicodeError):
        return {'status': 'UNAVAILABLE', 'http_status': None}


def sitemap_urls(text):
    if len(text.encode()) > MAX_BYTES or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('Unsafe sitemap XML')
    root = ET.fromstring(text)
    if root.tag != NS + 'urlset' or any(n.tag != NS + 'url' for n in root):
        raise ValueError('Expected sitemap URL set')
    urls = []
    for node in root:
        loc = node.findall(NS + 'loc')
        if len(loc) != 1 or not safe_url(loc[0].text):
            raise ValueError('Unsafe sitemap destination')
        urls.append(loc[0].text)
    if not urls or len(urls) > MAX_URLS or len(set(urls)) != len(urls):
        raise ValueError('Empty, duplicate or oversized sitemap')
    return urls


def inspect_page(url, response, robots):
    path = '/' + url[len(SITE):]
    row = {'path': path, 'http_status': response.get('http_status'),
           'status': response.get('status'), 'issues': [], 'internal_links': [],
           'index_status': 'UNCONFIRMED'}
    if response.get('status') != 'OBSERVED' or response.get('http_status') != 200:
        row['issues'] = ['PAGE_HTTP_UNAVAILABLE_OR_REDIRECT']
        return row
    text = response['text']
    soup = BeautifulSoup(text, 'html.parser')
    row['html_hash'] = digest(text)
    row['title'] = soup.title.get_text(' ', strip=True)[:200] if soup.title else ''
    descriptions = soup.select('meta[name=description]')
    row['description'] = descriptions[0].get('content', '')[:500] if len(descriptions) == 1 else ''
    row['headings'] = [h.get_text(' ', strip=True)[:120] for h in soup.select('h1,h2')][:25]
    row['has_comparison_help'] = bool(soup.select('#step6-comparison-help'))
    cid = next((c for c in REGISTRY if path == f'/categories/{c}/'), None)
    labels = {'laundry': ('100g','100ml'), 'tissue': ('100組',), 'toilet-paper': ('10m',)}
    row['comparison_context_verified'] = bool(cid and any(v in soup.get_text() for v in labels[cid]) and soup.select('#'+cid))
    faq = soup.select_one('#category-faq')
    row['existing_faq_present'] = bool(faq)
    faq_links = [a.get('href','') for a in faq.select('a[href]')] if faq else []
    row['faq_navigation_complete'] = bool(cid and any(REGISTRY[cid][2] in h for h in faq_links) and
                                          any('products/' in h for h in faq_links) and '#'+cid in faq_links)
    row['ids'] = sorted({e['id'] for e in soup.select('[id]')})[:600]
    canon = [e.get('href') for e in soup.select('link[rel=canonical]')]
    if canon != [url]:
        row['issues'].append('CANONICAL_MISMATCH_OR_DUPLICATE')
    tags = ' '.join(e.get('content', '') for e in soup.select('meta[name=robots],meta[name=googlebot]'))
    if 'noindex' in (tags + ' ' + response.get('x_robots_tag', '')).lower():
        row['issues'].append('UNEXPECTED_NOINDEX')
    if not robots.can_fetch('Googlebot', url):
        row['issues'].append('ROBOTS_BLOCKED')
    if not row['title'] or not row['description']:
        row['issues'].append('MISSING_TITLE_OR_DESCRIPTION')
    if len(soup.select('h1')) != 1:
        row['issues'].append('H1_COUNT')
    viewport = soup.select('meta[name=viewport]')
    if len(viewport) != 1 or 'width=device-width' not in viewport[0].get('content', ''):
        row['issues'].append('MOBILE_VIEWPORT_MISSING')
    links = []
    for a in soup.select('a[href]'):
        u = urlsplit(urljoin(url, a['href']))
        if u.netloc != urlsplit(SITE).netloc:
            continue  # No affiliate/outbound GETs or navigation.
        clean = u._replace(query='', fragment='').geturl()
        if not safe_url(clean):
            row['issues'].append('INTERNAL_LINK_OUTSIDE_SITE')
            continue
        links.append({'url': clean, 'fragment': unquote(u.fragment)})
    row['internal_links'] = list({(v['url'], v['fragment']): v for v in links}.values())
    row['status'] = 'PASS' if not row['issues'] else 'REVIEW'
    return row


def audit(get=fetch):
    discovery = {n: get(SITE + n) for n in ('sitemap.xml', 'robots.txt')}
    errors = []
    urls = []
    try:
        if any(r.get('status') != 'OBSERVED' or r.get('http_status') != 200 for r in discovery.values()):
            raise ValueError('Discovery HTTP failure')
        urls = sitemap_urls(discovery['sitemap.xml']['text'])
    except (ValueError, KeyError, ET.ParseError):
        errors.append('SITEMAP_OR_ROBOTS_UNAVAILABLE_OR_INVALID')
    robots = RobotFileParser()
    robots.parse(discovery['robots.txt'].get('text', '').splitlines())
    if 'Sitemap: ' + SITE + 'sitemap.xml' not in discovery['robots.txt'].get('text', '').splitlines():
        errors.append('ROBOTS_SITEMAP_MISMATCH')
    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = list(pool.map(lambda u: inspect_page(u, get(u), robots), urls))
    by_url = {SITE + p['path'][1:]: p for p in pages}
    # Internal destinations absent from the sitemap are independently fetched.
    extra = sorted({l['url'] for p in pages for l in p['internal_links']} - set(urls))
    links_complete = len(extra) <= MAX_URLS
    if not links_complete:
        errors.append('INTERNAL_LINK_AUDIT_LIMIT_REACHED')
    targets = dict(by_url)
    with ThreadPoolExecutor(max_workers=6) as pool:
        targets.update(zip(extra[:MAX_URLS], pool.map(lambda u: inspect_page(u, get(u), robots), extra[:MAX_URLS])))
    for p in pages:
        for link in p['internal_links']:
            dest = targets.get(link['url'])
            if dest is None or dest.get('http_status') != 200 or dest.get('status') in ('REDIRECT', 'UNAVAILABLE', 'HTTP_FAILURE'):
                p['issues'].append('INTERNAL_LINK_HTTP_UNAVAILABLE_OR_REDIRECT')
            elif link['fragment'] and link['fragment'] not in dest.get('ids', []):
                p['issues'].append('INTERNAL_ANCHOR_MISSING')
            if link['url'] not in urls:
                p['issues'].append('LINKED_PAGE_ABSENT_FROM_SITEMAP')
        p['issues'] = sorted(set(p['issues']))
        p['status'] = 'PASS' if not p['issues'] else 'REVIEW'
    for key in ('title', 'description'):
        groups = defaultdict(list)
        for p in pages:
            if p.get(key):
                groups[p[key]].append(p)
        for group in groups.values():
            if len(group) > 1:
                for p in group:
                    p['issues'].append('DUPLICATE_' + key.upper())
                    p['status'] = 'REVIEW'
    return {'status': 'PASS' if pages and not errors and all(p['status'] == 'PASS' for p in pages) else 'REVIEW_OR_UNKNOWN',
            'discovery': {n: {k: r.get(k) for k in ('status', 'http_status')} for n, r in discovery.items()},
            'sitemap_urls': len(urls), 'issues': errors, 'pages': pages,
            'lastmod_policy': 'OMIT_WITHOUT_VERIFIED_SIGNIFICANT_CHANGE_HISTORY',
            'published_lastmod_present': '<lastmod>' in discovery['sitemap.xml'].get('text', ''),
            'page_index_status': 'UNCONFIRMED', 'mobile_visual_status': 'SEPARATE_BROWSER_QA_REQUIRED',
            'sitemap_presence_is_not_indexing': True}


def validated_gsc(gsc, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if (not isinstance(gsc, dict) or gsc.get('source') != 'Search Console Search Analytics API' or
            gsc.get('site_property') != SITE or gsc.get('status') != 'PROVISIONAL'):
        return False
    try:
        stamp = dt.datetime.fromisoformat(gsc['generated_at_utc'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or not -300 <= (now-stamp).total_seconds() <= 21600:
            return False
        windows = gsc['windows']
        for length in (7, 28):
            a, b = [dt.date.fromisoformat(v) for v in windows['last_' + str(length)]]
            c, d = [dt.date.fromisoformat(v) for v in windows['prior_' + str(length)]]
            if (b-a).days != length-1 or (d-c).days != length-1 or d+dt.timedelta(days=1) != a:
                return False
            if b > now.date()-dt.timedelta(days=2):
                return False
        if windows['last_7'][1] != windows['last_28'][1]:
            return False
        if not isinstance(gsc['pages'], list) or len(gsc['pages']) > 100:
            return False
        seen = set()
        for row in gsc['pages']:
            if not good_path(row['path']) or row['path'] in seen:
                return False
            seen.add(row['path'])
            for key in ('last_7', 'prior_7', 'last_28', 'prior_28'):
                m = row.get(key)
                if m is None:
                    continue
                if (type(m['impressions']) is not int or type(m['clicks']) is not int or
                        not 0 <= m['clicks'] <= m['impressions'] or
                        any(type(m[k]) not in (int, float) or not math.isfinite(m[k]) for k in ('ctr', 'position')) or
                        not 0 <= m['ctr'] <= 1 or m['position'] < 1 or
                        (m['impressions'] and abs(m['ctr']-m['clicks']/m['impressions']) > .00001)):
                    return False
        return True
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def analyze(technical, gsc, config_text, base_sha, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    valid = validated_gsc(gsc, now)
    cfg = policy(config_text)
    candidates = []
    public = {p['path']: p for p in technical.get('pages', [])}
    for row in (gsc.get('pages', []) if valid else []):
        path = row['path']
        m = row.get('last_28')
        current_page = public.get(path, {})
        cid = next((c for c in REGISTRY if path == f'/categories/{c}/'), None)
        eligible = bool(m and m['impressions'] >= 50 and 5 <= m['position'] <= 20)
        reason = ('VISIBLE_POSITION_5_20' if eligible else 'LOW_SAMPLE_OR_OUTSIDE_FOCUS_RANGE')
        evidence = {k: row.get(k) for k in ('last_7', 'prior_7', 'last_28', 'prior_28')}
        change = {str(n): ({k: evidence['last_'+str(n)][k]-evidence['prior_'+str(n)][k] for k in ('impressions', 'clicks')}
                         if evidence['last_'+str(n)] and evidence['prior_'+str(n)] else None) for n in (7, 28)}
        fixed = (eligible and cid is not None and not cfg['pages'][cid] and
                 technical.get('status') == 'PASS' and current_page.get('status') == 'PASS' and
                 not current_page.get('has_comparison_help') and
                 REGISTRY[cid][0] in current_page.get('title', '') and
                 current_page.get('comparison_context_verified') is True and
                 current_page.get('existing_faq_present') is True and
                 current_page.get('faq_navigation_complete') is False)
        proposals = []
        if fixed:
            proposals = [{'type': 'H2_FAQ_AND_INTERNAL_LINKS', 'recipe': recipe(cid),
                          'hypothesis': 'FAQ読了後にランキング・比較単位の説明・商品検索への導線があると比較を再開しやすくなる可能性',
                          'benefit': '単価だけで大量商品を選ばず、規格・購入量を確認し、説明と商品検索へ進める',
                          'risk': '説明の追加でページが長くなる。検索・クリック改善は未実証',
                          'source_target': TARGET, 'preview': __import__('step6_seo_content').markup(cid),
                          'classification': 'HUMAN_ONLY', 'publication_authorized': False}]
        candidates.append({'path': path, 'priority': 'P1' if eligible and cid else 'P2' if eligible else 'P3',
                           'reason': reason, 'metrics': evidence, 'descriptive_change': change,
                           'low_ctr_hypothesis': bool(m and m['impressions'] >= 50 and m['ctr'] < .02),
                           'page_position_is_not_keyword_rank': True,
                           'query_intent': 'UNCONFIRMED',
                           'title_meta_h1_proposals': 'DEFERRED_WITHOUT_VERIFIED_QUERY_INTENT',
                           'proposals': proposals, 'evaluation': '評価保留'})
    candidates.sort(key=lambda r: (r['priority'], r['path'] not in [f'/categories/{c}/' for c in REGISTRY],
                                   -(r['metrics']['last_28'] or {}).get('impressions', 0), r['path']))
    return {'source': SOURCE, 'site': SITE, 'generated_at_utc': now.isoformat(), 'base_sha': base_sha,
            'status': 'GROUNDED_HYPOTHESES' if valid else 'GSC_UNKNOWN_OR_STALE',
            'policy_hash': digest(config_text), 'technical': technical,
            'windows': gsc.get('windows') if valid else None,
            'site_aggregates': gsc.get('site_aggregates') if valid else None,
            'page_row_coverage': gsc.get('page_row_coverage', {'status':'UNKNOWN'}) if valid else None,
            'query_coverage': 'PRIVACY_FILTERED_OR_UNAVAILABLE_NOT_ZERO',
            'daily_coverage': {'observed_site_days': gsc.get('daily_series', {}).get('site_dates_observed'),
                               'absent_days_are_unknown': True} if valid else None,
            'gsc_sitemaps': gsc.get('sitemaps', {'status': 'NOT_COLLECTED'}) if valid else {'status': 'UNCONFIRMED'},
            'seo_effects': gsc.get('seo_effects', {'status':'NO_CONFIRMED_PUBLICATION','evaluation':'評価保留'}) if valid else {'status':'GSC_UNKNOWN','evaluation':'評価保留'},
            'candidates': candidates[:20], 'query_evidence': 'UNCONFIRMED_NO_RAW_QUERIES_EXPORTED',
            'publisher': 'EXISTING_STEP2_ONLY', 'maximum_draft_prs_per_cycle': 1,
            'automatic_merge': False, 'automatic_deploy': False, 'sales_status': 'NOT_CONNECTED',
            'cross_source_user_join': False, 'effect_evaluation': '評価保留'}


def candidate(report, text, sha, now=None):
    if not isinstance(report, dict):
        return None
    try:
        stamp = dt.datetime.fromisoformat(report['generated_at_utc'])
        age = ((now or dt.datetime.now(dt.timezone.utc))-stamp).total_seconds()
        if (stamp.tzinfo is None or not -300 <= age <= 21600 or report.get('source') != SOURCE or
                report.get('site') != SITE or report.get('base_sha') != sha or
                report.get('policy_hash') != digest(text) or report.get('status') != 'GROUNDED_HYPOTHESES'):
            return None
        # Recalculate from normalized numeric evidence; report recipe flags cannot authorize.
        reconstructed = {'source': 'Search Console Search Analytics API', 'site_property': SITE,
                         'status': 'PROVISIONAL', 'generated_at_utc': report['generated_at_utc'],
                         'windows': report['windows'], 'pages': [dict(path=r['path'], **r['metrics']) for r in report['candidates']]}
        recalculated = analyze(report['technical'], reconstructed, text, sha, now)
        for row in recalculated['candidates']:
            for proposal in row['proposals']:
                changed = repair(text, proposal['recipe'])
                if changed:
                    return {'recipe': proposal['recipe'], 'target': TARGET, 'path': row['path'],
                            'candidate': changed, 'evidence_hash': digest(json.dumps(report, sort_keys=True))}
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return None


def markdown(report):
    lines = ['# STEP6 自動SEO監査・改善候補', '', '- 状態: ' + report['status'],
             '- ページ単位のインデックス: 未確認。サイトマップの存在は登録完了の証拠ではありません。',
             '- SEO・売上効果: 評価保留。楽天確定成果は未接続。',
             '- 期間: ' + json.dumps(report['windows'], ensure_ascii=False),
             '- 技術監査: ' + report['technical']['status'], '',
             '| ページ | 優先 | 28日表示 | 検索クリック | CTR | 平均順位 | 提案 |',
             '|---|---|---:|---:|---:|---:|---|']
    for row in report['candidates']:
        m = row['metrics']['last_28'] or {}
        lines.append('| ' + ' | '.join([row['path'], row['priority'], *[str(m.get(k, '不明')) for k in ('impressions','clicks','ctr','position')],
                                       '比較説明・FAQ・内部リンクのDraft候補' if row['proposals'] else '観察継続']) + ' |')
    lines += ['', '- 検索意図が未確認のためtitle/meta/H1の文章変更は保留。平均順位は固定キーワード順位ではありません。',
              '- Google検索クリックとGA4楽天クリックは別集計。低サンプルで成功・失敗を断定しません。',
              '- STEP2_ENABLE_PR_WRITESを維持。既存publisherだけが最大1件のDraftを発行し、人間承認を待ちます。']
    for row in report['candidates']:
        for p in row['proposals']:
            lines += ['', '## ' + row['path'], p['hypothesis'], '利用者メリット: ' + p['benefit'], 'リスク: ' + p['risk']]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gsc', type=Path, default=Path('audit-results/gsc-search-pilot.json'))
    args = parser.parse_args()
    from autonomous_operations_step2 import git
    report = analyze(audit(), read_optional(args.gsc), Path(TARGET).read_text(), git('rev-parse', 'HEAD'))
    out = Path('audit-results'); out.mkdir(exist_ok=True)
    (out/'step6-seo.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out/'step6-seo.md').write_text(markdown(report))
    # Append fixed findings to the same bounded rolling issue, never a new issue.
    operations=read_optional(out/'autonomous-operations.json')
    if operations and operations.get('source')=='daily-cost autonomous operations triage v1':
        # Reuse bounded queue/fingerprint semantics directly, without changing
        # STEP4's content authorization or constructing executable commands.
        from autonomous_operations_triage import new_finding, markdown as ops_markdown
        findings=list(operations['findings'])
        if report['technical']['status']!='PASS':
            findings.append(new_finding('P1','SEO_TECHNICAL_REVIEW','/','SEO技術監査に問題または未確認項目','STEP6証拠を確認。自動公開しない'))
        elif report['status']!='GROUNDED_HYPOTHESES':
            findings.append(new_finding('P2','SEO_EVIDENCE_UNKNOWN','/','最新のGSC根拠を確認できない','再取得まで提案を保留'))
        else:
            for row in report['candidates']:
                if row['proposals']:
                    findings.append(new_finding('P2','SEO_COMPARISON_HELP_REVIEW',row['path'],'FAQ読了後の比較導線に改善仮説','固定のDraft候補を検証し人間がレビュー',evidence='28日表示='+str(row['metrics']['last_28']['impressions'])))
        operations['findings']=sorted({f['id']:f for f in findings}.values(),key=lambda f:(f['severity'],f['path'],f['code']))[:20]
        operations['summary']={p:sum(f['severity']==p for f in operations['findings']) for p in ('P0','P1','P2','P3')}
        operations['fingerprint']=digest('\n'.join(f"{f['severity']}:{f['id']}" for f in operations['findings'] if f['severity'] in ('P0','P1','P2')))[:20]
        operations['status']='URGENT_REVIEW' if operations['summary']['P0'] else 'REVIEW_REQUIRED' if any(operations['summary'][p] for p in ('P1','P2')) else 'NO_ACTIONABLE_FINDINGS'
        (out/'autonomous-operations.json').write_text(json.dumps(operations,ensure_ascii=False,indent=2))
        (out/'autonomous-operations.md').write_text(ops_markdown(operations))
    print('STEP6:', report['status'], 'technical=', report['technical']['status'])


if __name__ == '__main__':
    main()
