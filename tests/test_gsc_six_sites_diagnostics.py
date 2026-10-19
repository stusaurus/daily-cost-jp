import datetime as dt
import unittest
from unittest.mock import patch
from io import BytesIO
from urllib.parse import unquote

from scripts import gsc_six_sites_diagnostics as g


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload if payload is not None else {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        if "index:inspect" in url:
            return Response(payload={"inspectionResult": {"indexStatusResult": {
                "verdict": "PASS", "coverageState": "Submitted and indexed",
                "lastCrawlTime": "2026-10-11T00:00:00Z",
                "googleCanonical": json["inspectionUrl"],
            }}})
        dimension = json.get("dimensions")
        key = "2026-10-10" if dimension == ["date"] else "紙おむつ 価格 比較"
        return Response(payload={"rows": [{
            "keys": ([key, unquote(url.split("/sites/")[1].split("/searchAnalytics")[0])] if dimension == ["query", "page"] else [key]), "clicks": 0, "impressions": 2, "ctr": 0.0, "position": 21.0,
        }]})


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        public = patch.object(g, "public_state", return_value={"status": "PUBLIC_HTML", "http_status": 200})
        public.start()
        self.addCleanup(public.stop)
        self.first_name, self.first_site = g.base.SITES[0]
        self.windows = g.base.date_windows(dt.date(2026, 10, 18))

    def test_exact_six_site_targets(self):
        self.assertEqual(set(g.TARGET_PATHS), {name for name, _ in g.base.SITES})
        for paths in g.TARGET_PATHS.values():
            self.assertEqual(len(set(paths)), len(paths))
            self.assertTrue(all(path.startswith("/") and not path.startswith("//") for path in paths))

    def test_non_exhaustive_query_rows_sorted_by_impressions(self):
        rows = {"rows": [
            {"keys": ["a"], "clicks": 1, "impressions": 4, "ctr": 0.25, "position": 2},
            {"keys": ["b"], "clicks": 0, "impressions": 20, "ctr": 0, "position": 10},
        ]}
        result = g.analytics_rows(rows, "query")
        self.assertEqual([r["key"] for r in result["rows"]], ["b", "a"])
        self.assertNotIn("total_impressions", result)

    def test_empty_rows_not_a_zero_metric(self):
        self.assertEqual(g.analytics_rows({}, "query")["status"], "NO_ROWS")
        with self.assertRaises(ValueError):
            g.analytics_rows({"rows": [{"keys": ["x"], "impressions": 3}]}, "query")
        self.assertEqual(g.make_report(dt.date(2026, 10, 18), auth_problem="MISSING")["status"], "UNAVAILABLE")

    def test_inspection_exact_site_and_no_external_paths(self):
        session = FakeSession()
        result = g.inspect_url(session, self.first_site, "/categories/tissue/")
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(session.calls[0][1]["siteUrl"], self.first_site)
        self.assertEqual(session.calls[0][1]["inspectionUrl"], self.first_site + "categories/tissue/")
        for path in ("//evil.org", "/hello?modify=1"):
            with self.assertRaises(ValueError):
                g.inspect_url(session, self.first_site, path)

    def test_failed_inspection_does_not_claim_indexed(self):
        class Forbidden(FakeSession):
            def post(self, url, json=None, timeout=None):
                return Response(403)
        result = g.inspect_url(Forbidden(), self.first_site, "/")
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertNotIn("verdict", result)

    def test_missing_index_status_is_unavailable(self):
        class Missing(FakeSession):
            def post(self, url, json=None, timeout=None):
                return Response(payload={"inspectionResult": {}})
        self.assertEqual(g.inspect_url(Missing(), self.first_site, "/")["status"], "UNAVAILABLE")

    def test_one_site_access_keeps_other_five_unknown(self):
        session = FakeSession()
        result = g.make_report(dt.date(2026, 10, 18), session, {self.first_site: "siteRestrictedUser"})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["sites"][0]["status"], "OBSERVED")
        self.assertEqual(result["sites"][1]["status"], "NOT_CONNECTED")
        self.assertEqual(len(session.calls), 4 + len(g.TARGET_PATHS[self.first_name]))
        self.assertTrue(all(call[1].get("dataState") == "final" for call in session.calls[:4]))

    def test_all_six_return_report(self):
        session = FakeSession()
        permissions = {site: "siteRestrictedUser" for _, site in g.base.SITES}
        result = g.make_report(dt.date(2026, 10, 18), session, permissions)
        self.assertEqual(result["status"], "READY")
        self.assertIn("ボードゲーム", g.markdown(result))
        self.assertIn("SOTOJITAKU", g.markdown(result))

    def test_failed_query_is_partial_and_keeps_index_evidence(self):
        class Broken(FakeSession):
            def post(self, url, json=None, timeout=None):
                if json.get("dimensions") == ["query"]:
                    return Response(503)
                return super().post(url, json=json, timeout=timeout)
        result = g.site_diagnostics(Broken(), self.first_name, self.first_site,
                                    self.windows, {self.first_site: "siteRestrictedUser"})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["analytics"]["queries_28d"]["status"], "UNAVAILABLE")
        self.assertEqual(result["inspection"][0]["status"], "OBSERVED_SNAPSHOT")

    def test_date_validation_does_not_invent_missing_days(self):
        self.assertEqual(g.analytics_rows({"rows": []}, "date")["status"], "NO_ROWS")
        with self.assertRaises(ValueError):
            g.analytics_rows({"rows": [{
                "keys": ["bad"], "clicks": 0, "impressions": 2, "ctr": 0, "position": 9,
            }]}, "date")

    def test_markdown_escapes_search_query_markup(self):
        site = {"name": "日用品", "status": "OBSERVED", "analytics": {
            "queries_28d": {"status": "OBSERVED_ROWS", "rows": [{
                "key": "<a>|bad", "impressions": 3, "clicks": 0, "position": 5,
            }]},
            "queries_7d": {"status": "NO_ROWS", "rows": []},
            "daily_28d": {"status": "NO_ROWS", "rows": []}}, "inspection": []}
        report = {"status": "READY", "as_of_pacific": "2026-10-18",
                  "date_windows": self.windows, "sites": [site]}
        rendered = g.markdown(report)
        self.assertIn("&lt;a&gt;\\|bad", rendered)
        self.assertNotIn("<a>", rendered)


if __name__ == "__main__":
    unittest.main()


class PairAndPublicTests(unittest.TestCase):
    def row(self, page):
        return {"rows": [{"keys": ["ティッシュ | <安い>", page], "clicks": 1,
                          "impressions": 50, "ctr": 0.02, "position": 12}]}

    def test_pair_is_exact_property_and_has_no_totals(self):
        site = g.base.SITES[0][1]
        data = g.analytics_rows(self.row(site + "categories/tissue/"), "query_page", property_url=site)
        self.assertEqual(data["rows"][0]["path"], "/categories/tissue/")
        self.assertNotIn("total_impressions", data)
        for page in (g.base.SITES[1][1], site + "../baby-cost-jp/", site.rstrip("/") + "-evil/"):
            with self.assertRaises(ValueError):
                g.analytics_rows(self.row(page), "query_page", property_url=site)

    def test_pair_limit_missing_and_malformed(self):
        site = g.base.SITES[0][1]
        row = self.row(site)["rows"][0]
        self.assertEqual(g.analytics_rows({"rows": [row] * 1000}, "query_page", property_url=site)["status"], "TOP_ROWS_LIMIT_POSSIBLE")
        self.assertEqual(g.analytics_rows({}, "query_page", property_url=site)["status"], "NO_ROWS")
        for keys in (["a"], ["a", None], ["a", site, "extra"]):
            with self.assertRaises(ValueError):
                g.analytics_rows({"rows": [{**row, "keys": keys}]}, "query_page", property_url=site)

    def test_dead_target_skips_google_inspection_and_stays_partial(self):
        name, site = g.base.SITES[0]
        session = FakeSession()
        with patch.object(g, "public_state", return_value={"status": "PUBLIC_CHECK_UNAVAILABLE"}):
            result = g.site_diagnostics(session, name, site, g.base.date_windows(dt.date(2026, 10, 18)), {site: "siteRestrictedUser"})
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(len(session.calls), 4)
        self.assertTrue(all(r["status"] == "UNAVAILABLE" and "verdict" not in r for r in result["inspection"]))

    def test_public_probe_is_anonymous_bounded_and_rejects_redirect(self):
        site = g.base.SITES[0][1]
        class Page(BytesIO):
            status = 200
            url = site
            headers = {"Content-Type": "text/html"}
        with patch.object(g, "urlopen", return_value=Page(b'<link rel="canonical" href="self"><meta name="robots" content="index,follow">')) as opened:
            result = g.public_state(site)
            self.assertEqual(result["canonical"], ["self"])
            self.assertEqual(opened.call_args.args, (site,))
        page = Page(b"ok")
        page.url = g.base.SITES[1][1]
        with patch.object(g, "urlopen", return_value=page):
            self.assertEqual(g.public_state(site)["status"], "INVALID_PUBLIC_TARGET")

    def test_canonical_and_reason_are_visible_in_summary(self):
        report = g.make_report(dt.date(2026, 10, 18), auth_problem="MISSING")
        report["sites"][0]["inspection"] = [{"path": "/", "status": "UNAVAILABLE", "reason": "INSPECTION_HTTP_403", "google_canonical": "https://example.org/"}]
        summary = g.markdown(report)
        self.assertIn("https://example.org/", summary)
        self.assertIn("INSPECTION_HTTP_403", summary)


class FailureDistinctionTests(unittest.TestCase):
    def test_api_error_and_unindexed_snapshot_remain_distinct(self):
        name, site = g.base.SITES[0]
        class Denied(FakeSession):
            def post(self, url, json=None, timeout=None):
                if "index:inspect" in url:
                    return Response(payload={"inspectionResult": {"indexStatusResult": {"verdict": "FAIL", "coverageState": "Crawled - currently not indexed", "indexingState": "INDEXING_ALLOWED"}}})
                return Response(429)
        with patch.object(g, "public_state", return_value={"status": "PUBLIC_HTML"}):
            result = g.site_diagnostics(Denied(), name, site, g.base.date_windows(dt.date(2026, 10, 18)), {site: "siteRestrictedUser"})
        self.assertEqual(result["analytics"]["query_pages_28d"]["reason"], "SEARCH_ANALYTICS_HTTP_429")
        self.assertEqual(result["inspection"][0]["status"], "OBSERVED_SNAPSHOT")
        self.assertEqual(result["inspection"][0]["verdict"], "FAIL")
        self.assertEqual(result["status"], "PARTIAL")
