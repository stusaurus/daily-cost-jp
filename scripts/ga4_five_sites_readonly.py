"""Bounded manual GA4 reads. No credentials, individual rows, or external writes."""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

HOST = 'stusaurus.github.io'
SITES = ('baby-cost-jp', 'pet-cost-jp', 'food-cost-jp', 'kyo-bodo-jp', 'sotojitaku')
ADMIN = 'https://analyticsadmin.googleapis.com/v1beta/'
DATA = 'https://analyticsdata.googleapis.com/v1beta/'
# Existing deployments and dated analytics audits correlate these IDs/properties.
# kyo-bodo-jp/docs/seo-pilot-20261012/AUDIT.md and
# sotojitaku/docs/growth-phase1/REPORT.md contain the prior official mapping.
# Admin verification is reported separately; this is not a discovered stream ID.
EXISTING_MAPPING = {'G-GFVSZ8YDQ5': '552907444', 'G-Q1N14V276G': '556462193', 'G-6STQ5HXRDH': '558239521'}
LIMIT = 1000


def windows(today):
    end = today - dt.timedelta(days=2)
    return {str(n): [(end-dt.timedelta(days=n-1)).isoformat(), end.isoformat()] for n in (7, 28)}


def api(session, method, url, payload=None):
    """Only constant Google API origins; no retry and no raw error disclosure."""
    allowed = ((method == 'get' and (url == ADMIN+'accountSummaries?pageSize=200'
                or re.fullmatch(re.escape(ADMIN)+r'properties/[0-9]+/dataStreams\?pageSize=200', url)
                or re.fullmatch(re.escape(DATA)+r'properties/[0-9]+/metadata', url)))
               or (method == 'post' and re.fullmatch(re.escape(DATA)+r'properties/[0-9]+:runReport', url)))
    if not allowed:
        raise ValueError('Unapproved read endpoint')
    try:
        response = getattr(session, method)(url, **({'json': payload} if payload is not None else {}), timeout=40)
        if response.status_code != 200:
            reason = 'HTTP_' + str(response.status_code)
            try:
                details = response.json().get('error', {}).get('details', [])
                codes = {d.get('reason') for d in details if isinstance(d, dict)}
                if 'SERVICE_DISABLED' in codes:
                    reason = 'SERVICE_DISABLED'
                elif response.status_code == 403:
                    reason = 'PERMISSION_DENIED'
                elif response.status_code == 429:
                    reason = 'RATE_LIMITED_STOP'
            except (ValueError, AttributeError):
                pass
            return {'status': 'UNAVAILABLE', 'http_status': response.status_code, 'reason': reason}
        data = response.json()
        return {'status': 'OBSERVED', 'data': data} if isinstance(data, dict) else {'status': 'UNAVAILABLE', 'reason': 'INVALID_RESPONSE'}
    except Exception:
        return {'status': 'UNAVAILABLE', 'reason': 'REQUEST_FAILED'}


def published_measurement(site):
    if site not in SITES:
        raise ValueError('Unknown site')
    url = 'https://' + HOST + '/' + site + '/'
    try:
        with urlopen(url, timeout=25) as response:
            if response.status != 200 or response.url != url:
                return {'status': 'UNAVAILABLE'}
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {'status': 'UNAVAILABLE'}
        ids = sorted(set(re.findall(r'G-[A-Z0-9]{6,20}', raw.decode('utf-8'))))
        return {'status': 'OBSERVED', 'measurement_ids': ids, 'source': url}
    except Exception:
        return {'status': 'UNAVAILABLE'}


def safe_default_uri(value):
    try:
        u = urlsplit(value)
        if (u.scheme == 'https' and u.hostname == HOST and not u.username and not u.password
                and u.port is None and not u.query and not u.fragment
                and u.path in ['/'+s+'/' for s in (*SITES, 'daily-cost-jp')]):
            return value
    except (ValueError, TypeError):
        pass
    return 'OTHER_OR_UNREPORTED_DEFAULT_URI'


def discover(session, allowed_ids):
    result = api(session, 'get', ADMIN + 'accountSummaries?pageSize=200')
    properties = set(EXISTING_MAPPING.values())
    if result.get('http_status') == 429:
        return result, {}
    if result['status'] == 'OBSERVED':
        data = result['data']
        for account in data.get('accountSummaries', []):
            for prop in account.get('propertySummaries', []):
                value = prop.get('property', '')
                if re.fullmatch(r'properties/[0-9]+', value):
                    properties.add(value.split('/')[1])
        result = {'status': 'OBSERVED', 'has_more': bool(data.get('nextPageToken'))}
    # Bounded discovery, never guess other property IDs or output account names.
    found = {}
    result['property_scan_limit_reached'] = len(properties) > 20
    for prop in sorted(properties)[:20]:
        streams = api(session, 'get', ADMIN + 'properties/' + prop + '/dataStreams?pageSize=200')
        if streams['status'] == 'OBSERVED':
            streams = {'status': 'OBSERVED', 'has_more': bool(streams['data'].get('nextPageToken')), 'streams': [
                {'name': s.get('name'), 'measurement_id': s.get('webStreamData', {}).get('measurementId'),
                 'default_uri': safe_default_uri(s.get('webStreamData', {}).get('defaultUri'))}
                for s in streams['data'].get('dataStreams', []) if s.get('type') == 'WEB_DATA_STREAM'
                and s.get('webStreamData', {}).get('measurementId') in allowed_ids]}
        if prop in EXISTING_MAPPING.values() or streams.get('streams'):
            found[prop] = streams
        if streams.get('http_status') == 429:
            result.update(status='UNAVAILABLE', http_status=429, reason='RATE_LIMITED_STOP')
            break
    return result, found


def mappings(ids, streams):
    matched = []
    for prop, evidence in streams.items():
        for stream in evidence.get('streams', []):
            name = stream.get('name', '')
            if stream.get('measurement_id') in ids and re.fullmatch(r'properties/[0-9]+/dataStreams/[0-9]+', name):
                matched.append({'property_id': prop, 'stream_id': name.split('/')[-1],
                                'measurement_id': stream['measurement_id'], 'basis': 'ADMIN_STREAM_MATCH'})
    if not matched:
        matched = [{'property_id': EXISTING_MAPPING[i], 'stream_id': None, 'measurement_id': i,
                    'basis': 'EXISTING_CONFIG_CORRELATION_STREAM_UNVERIFIED'} for i in ids if i in EXISTING_MAPPING]
    return matched


def filters(site, stream=None, flag=None):
    if site not in SITES:
        raise ValueError('Unknown site')
    def exact(field, value, match='EXACT'):
        return {'filter': {'fieldName': field, 'stringFilter': {'matchType': match, 'value': value, 'caseSensitive': True}}}
    expr = [exact('hostName', HOST), exact('pagePath', '/'+site+'/', 'BEGINS_WITH'),
            exact('pageLocation', 'https://'+HOST+'/'+site+'/', 'BEGINS_WITH')]
    if stream:
        if not str(stream).isdigit():
            raise ValueError('Invalid stream')
        expr.append(exact('streamId', str(stream)))
    if flag is not None:
        if flag not in ('0', '1'):
            raise ValueError('Invalid operator flag')
        expr.append(exact('customEvent:operator_test', flag))
    return {'andGroup': {'expressions': expr}}


def parse_report(data, dimensions, metric):
    rows = data.get('rows', [])
    meta = data.get('metadata', {})
    quality = {k: meta.get(k) for k in ('subjectToThresholding', 'dataLossFromOtherRow', 'samplingMetadatas', 'timeZone')}
    if (data.get('rowCount', 0) != len(rows) or len(rows) > LIMIT or meta.get('subjectToThresholding')
            or meta.get('dataLossFromOtherRow') or meta.get('samplingMetadatas')):
        return {'status': 'WITHHELD_DATA_QUALITY', 'quality': quality}
    if meta.get('timeZone') != 'Asia/Tokyo':
        return {'status': 'WITHHELD_PROPERTY_TIMEZONE', 'quality': quality}
    if ([h.get('name') for h in data.get('dimensionHeaders', [])] != dimensions
            or [h.get('name') for h in data.get('metricHeaders', [])] != [metric]):
        return {'status': 'INVALID_HEADERS'}
    parsed = []
    for row in rows:
        keys = [x.get('value') for x in row.get('dimensionValues', [])]
        vals = row.get('metricValues', [])
        if len(keys) != len(dimensions) or len(vals) != 1 or not re.fullmatch(r'[0-9]+', vals[0].get('value', '')):
            return {'status': 'INVALID_ROWS'}
        # Dimension values are channel groups, standard event names, and test flags only.
        if any(not isinstance(k, str) or len(k) > 80 for k in keys):
            return {'status': 'INVALID_ROWS'}
        if dimensions[0] == 'eventName' and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', keys[0]):
            return {'status': 'INVALID_ROWS'}
        parsed.append({'dimensions': keys, 'count': int(vals[0]['value'])})
    return {'status': 'OBSERVED_ROWS' if rows else 'NO_REPORTED_ROWS', 'quality': quality, 'rows': parsed}


def report(session, mapping, site, period, kind, operator_registered):
    event = kind == 'events'
    dims = ['eventName'] + (['customEvent:operator_test'] if operator_registered else []) if event else ['sessionDefaultChannelGroup']
    metric = 'eventCount' if event else 'sessions'
    flag = {'sessions_marked_non_operator': '0', 'sessions_marked_operator': '1'}.get(kind)
    payload = {'dateRanges': [{'startDate': period[0], 'endDate': period[1]}],
               'dimensions': [{'name': d} for d in dims], 'metrics': [{'name': metric}],
               'dimensionFilter': filters(site, mapping['stream_id'], flag), 'limit': LIMIT}
    raw = api(session, 'post', DATA+'properties/'+mapping['property_id']+':runReport', payload)
    if raw['status'] != 'OBSERVED':
        return raw
    return parse_report(raw['data'], dims, metric)


def collect(session, today, public_reader=published_measurement):
    public_sites = {site: public_reader(site) for site in SITES}
    allowed_ids = {i for p in public_sites.values() for i in p.get('measurement_ids', [])}
    account_status, streams = discover(session, allowed_ids)
    if account_status.get('http_status') == 429 or any(v.get('http_status') == 429 for v in streams.values()):
        return {'periods': windows(today), 'sites': [], 'discovery': account_status,
                'stream_access': streams, 'status': 'RATE_LIMITED_STOP'}
    metadata = {}
    sites = []
    periods = windows(today)
    for site in SITES:
        public = public_sites[site]
        candidates = mappings(public.get('measurement_ids', []), streams)
        entry = {'site': site, 'published_tracking': public, 'mappings': candidates, 'periods': {}}
        sites.append(entry)
        if len(public.get('measurement_ids', [])) != 1:
            entry['status'] = 'PUBLISHED_MEASUREMENT_UNAVAILABLE_OR_AMBIGUOUS'
            continue
        if len(candidates) != 1:
            entry['status'] = 'PROPERTY_UNKNOWN' if not candidates else 'AMBIGUOUS_STREAM_MAPPING'
            continue
        mapping = candidates[0]
        prop = mapping['property_id']
        if prop not in metadata:
            raw = api(session, 'get', DATA+'properties/'+prop+'/metadata')
            metadata[prop] = ({'status': 'OBSERVED', 'operator_registered': any(
                d.get('apiName') == 'customEvent:operator_test' for d in raw['data'].get('dimensions', []))}
                if raw['status'] == 'OBSERVED' else raw)
        if metadata[prop].get('http_status') == 429:
            entry['status'] = 'RATE_LIMITED_STOP'
            return {'periods': periods, 'sites': sites, 'discovery': account_status,
                    'stream_access': streams, 'status': 'RATE_LIMITED_STOP'}
        entry['data_api_metadata'] = metadata[prop]
        if metadata[prop]['status'] != 'OBSERVED':
            entry['status'] = 'DATA_API_UNAVAILABLE'
            continue
        registered = metadata[prop]['operator_registered']
        entry['status'] = 'QUERIED'
        for n, period in periods.items():
            results = {}
            for kind in ('sessions_all_scopes', 'sessions_marked_non_operator', 'sessions_marked_operator', 'events'):
                results[kind] = (report(session, mapping, site, period, kind, registered)
                                 if registered or kind in ('sessions_all_scopes', 'events') else {'status': 'OPERATOR_DIMENSION_MISSING'})
                if results[kind].get('http_status') == 429:
                    entry['status'] = 'RATE_LIMITED_STOP'
                    return {'periods': periods, 'sites': sites, 'discovery': account_status, 'stream_access': streams,
                            'status': 'RATE_LIMITED_STOP'}
            entry['periods'][n] = results
    return {'source': 'GA4 Data API / read-only Admin API', 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'periods': periods, 'sites': sites, 'discovery': account_status, 'stream_access': streams,
            'limitations': ['Property calendar must be Asia/Tokyo; two-day latency allowance is not a guarantee of finality.',
                'Sessions across operator flags can overlap; never add those buckets or subtract them to infer real users.',
                'Marked non-operator is provisional, not proof of a real customer. All-scopes includes tests.',
                'Events are counts, not users, purchases, or commissions. Missing or withheld reports are not zeros.',
                'This manual read does not change Google settings, schedules, pages, products, or credentials.']}


def markdown(data):
    lines = ['# 5サイト GA4 手動読み取り', '', '期間: '+json.dumps(data.get('periods'), ensure_ascii=False), '',
             '運営者区分ごとのセッションは重複し得ます。合算・差引で実人数を計算しません。', '',
             '|サイト|取得状態|7日 / 28日レポート|', '|---|---|---|']
    for site in data.get('sites', []):
        states = [site.get('periods', {}).get(n, {}).get('sessions_all_scopes', {}).get('status', '未取得') for n in ('7','28')]
        lines.append('|'+site['site']+'|'+site['status']+'|'+' / '.join(states)+'|')
    lines += ['', '数値・権限・ストリーム照合・テスト区分は同じ成果物のJSONで確認。',
              '楽天確定成果は未接続。実利用者・成果報酬への換算は行いません。']
    return '\n'.join(lines)


def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    data = collect(AuthorizedSession(credentials), dt.datetime.now(ZoneInfo('Asia/Tokyo')).date())
    root = Path('audit-results'); root.mkdir(exist_ok=True)
    (root/'ga4-five-sites.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (root/'ga4-five-sites.md').write_text(markdown(data), encoding='utf-8')
    print('Manual five-site GA4 read stored; missing access is not zero traffic.')
