"""Offline, credential-free regression tests for read-only URL Inspection."""
import unittest
from scripts.gsc_url_inspection import API, SITE, URLS, collect, extract, markdown


class Response:
    def __init__(self, status, data=None):
        self.status_code = status
        self.data = data or {}

    def json(self):
        return self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return next(self.responses)


class InspectionTests(unittest.TestCase):
    def test_only_exact_three_pages_in_readonly_scope(self):
        s = Session([Response(403), Response(429), Response(503)])
        report = collect(s)
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(len(s.calls), 3)
        for i, call in enumerate(s.calls):
            self.assertEqual(call[0], API)
            self.assertEqual(call[1], {"inspectionUrl": URLS[i], "siteUrl": SITE})
            self.assertEqual(call[2], 35)
        self.assertEqual([r["status"] for r in report["urls"]],
                         ["API_HTTP_403", "API_HTTP_429", "API_HTTP_503"])

    def test_extract_index_evidence_and_canonical_mismatch(self):
        payload = {"inspectionResult": {"indexStatusResult": {
            "verdict": "PASS", "googleCanonical": URLS[1],
            "userCanonical": URLS[0], "lastCrawlTime": "2026-10-01T00:00:00Z",
            "indexingState": "INDEXING_ALLOWED", "robotsTxtState": "ALLOWED",
        }}}
        r = extract(URLS[0], payload)
        self.assertEqual(r["status"], "RETURNED")
        self.assertTrue(r["canonical_mismatch"])
        self.assertEqual(r["lastCrawlTime"], "2026-10-01T00:00:00Z")
        self.assertIsNone(r["pageFetchState"])
        self.assertRaises(ValueError, extract, SITE + "categories/fake/", payload)

    def test_missing_google_canonical_is_unknown_not_mismatch(self):
        r = extract(URLS[0], {"inspectionResult": {"indexStatusResult": {
            "verdict": "NEUTRAL", "coverageState": "Discovered - currently not indexed"
        }}})
        self.assertIsNone(r["canonical_mismatch"])
        self.assertIsNone(r["googleCanonical"])

    def test_partial_results_and_safe_report(self):
        s = Session([
            Response(200, {"inspectionResult": {"indexStatusResult": {
                "verdict": "PASS", "googleCanonical": URLS[0]}}}),
            Response(403),
            Response(200, {"inspectionResult": {}}),
        ])
        report = collect(s)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["urls"][1]["status"], "API_HTTP_403")
        self.assertEqual(report["urls"][2]["status"], "INDEX_STATUS_UNAVAILABLE")
        md = markdown(report)
        self.assertIn("未確認", md)
        self.assertIn("categories/laundry", md)

    def test_full_result(self):
        r = collect(Session([Response(200, {"inspectionResult": {
            "indexStatusResult": {"verdict": "PASS"}}}) for _ in URLS]))
        self.assertEqual(r["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
