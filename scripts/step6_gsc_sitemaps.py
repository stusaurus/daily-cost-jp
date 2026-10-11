"""Sitemap registration/download evidence using existing readonly credentials."""
from urllib.parse import quote
from gsc_readonly_pilot import SITE, API_ROOT


def collect_sitemaps(session):
    try:
        response = session.get(API_ROOT + '/sites/' + quote(SITE, safe='') + '/sitemaps', timeout=30)
        if response.status_code != 200:
            return {'status': 'UNAVAILABLE', 'http_status': response.status_code,
                    'page_index_status': 'UNCONFIRMED'}
        rows = response.json().get('sitemap', [])
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('Invalid sitemap list')
        result = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Invalid sitemap row')
            if row.get('path') in (SITE+'sitemap.xml', SITE+'sitemap-test.xml'):
                result.append({k: row.get(k) for k in ('path', 'lastSubmitted', 'lastDownloaded',
                                                       'isPending', 'errors', 'warnings')})
        return {'status': 'OBSERVED' if result else 'NO_MATCHING_REGISTRATION_REPORTED',
                'sitemaps': result, 'page_index_status': 'UNCONFIRMED', 'read_only': True}
    except Exception:
        # Do not log credential/request/remote exception strings.
        return {'status': 'UNAVAILABLE', 'page_index_status': 'UNCONFIRMED'}
