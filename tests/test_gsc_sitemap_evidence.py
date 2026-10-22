import unittest
from urllib.parse import unquote
from scripts import gsc_six_sites_diagnostics as g


class Response:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class Session:
    def __init__(self, row): self.row, self.urls = row, []
    def get(self, url, timeout):
        self.urls.append(url)
        return Response({'sitemap': [self.row]} if url.endswith('/sitemaps') else self.row)


class SitemapEvidenceTests(unittest.TestCase):
    def test_pending_and_missing_fields_are_not_success_or_zero(self):
        site = g.base.SITES[3][1]
        session = Session({'path': site+'sitemap.xml', 'isPending': True})
        result = g.sitemap_evidence(session, site)
        self.assertEqual(result['processing_state'], 'PENDING')
        self.assertIsNone(result['get']['row']['lastDownloaded'])
        self.assertIsNone(result['get']['row']['errors'])
        self.assertEqual(len(session.urls), 2)
        self.assertTrue(all(unquote(url).startswith(g.base.ROOT+'/sites/'+site+'/sitemaps') for url in session.urls))

    def test_download_and_reported_errors_are_separate(self):
        site = g.base.SITES[0][1]
        row = dict(path=site+'sitemap.xml', isPending=False, type='sitemap', errors='0',
                   lastDownloaded='2026-10-22T00:00:00Z', contents=[dict(type='web', submitted='30')])
        self.assertEqual(g.sitemap_evidence(Session(row), site)['processing_state'], 'DOWNLOADED_AND_PROCESSED')
        row['errors'] = '1'
        self.assertEqual(g.sitemap_evidence(Session(row), site)['processing_state'], 'REPORTED_ERRORS')
        row.pop('errors')
        self.assertEqual(g.sitemap_evidence(Session(row), site)['processing_state'], 'PROCESSING_NOT_CONFIRMED')

    def test_http_failure_and_wrong_property_do_not_leak_or_retry(self):
        site = g.base.SITES[0][1]
        session = Session({'path': 'https://example.com/sitemap.xml'})
        result = g.sitemap_evidence(session, site)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['processing_state'], 'PROCESSING_NOT_CONFIRMED')
        self.assertNotIn('example.com', str(result))
        self.assertEqual(len(session.urls), 2)
        with self.assertRaises(ValueError): g.sitemap_evidence(session, 'https://example.com/')


if __name__ == '__main__': unittest.main()
