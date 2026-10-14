import datetime as dt
import unittest

from scripts import gsc_six_sites as g


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
        if json.get("dimensions") == ["page"]:
            return Response(payload={"rows": [{
                "keys": [g.SITES[0][1] + "categories/tissue/"],
                "clicks": 2, "impressions": 40, "ctr": 0.05, "position": 12,
            }]})
        return Response(payload={"rows": [{
            "clicks": 1, "impressions": 30, "ctr": 1 / 30, "position": 10,
        }]})


class SixSiteReportTests(unittest.TestCase):
    def test_exact_sites_are_configured(self):
        self.assertEqual(len(g.SITES), 6)
        self.assertEqual(len(set(url for _, url in g.SITES)), 6)

    def test_lagged_non_overlapping_windows(self):
        windows = g.date_windows(dt.date(2026, 10, 14))
        self.assertEqual(windows["last_7"], ["2026-10-05", "2026-10-11"])
        self.assertEqual(windows["prior_7"], ["2026-09-28", "2026-10-04"])
        self.assertEqual(windows["last_28"], ["2026-09-14", "2026-10-11"])
        self.assertEqual(windows["prior_28"], ["2026-08-17", "2026-09-13"])

    def test_no_rows_is_not_reported_as_zero(self):
        data = g.aggregate({})
        self.assertEqual(data["status"], "NO_ROWS")
        self.assertIsNone(data["metrics"])

    def test_invalid_metrics_rejected(self):
        for item in (
            {"clicks": 2, "impressions": 1, "ctr": .5, "position": 5},
            {"clicks": 1, "impressions": 10, "ctr": -1, "position": 5},
            {"clicks": 0, "impressions": 10, "ctr": 0, "position": "8"},
            {"clicks": 0, "impressions": 10, "ctr": 0, "position": float('nan')},
            {"clicks": 0, "impressions": 10, "ctr": 0, "position": float('inf')},
        ):
            with self.assertRaises(ValueError):
                g.safe_metrics(item)

    def test_strict_prefix_blocks_other_sites(self):
        site = g.SITES[0][1]
        self.assertIsNone(g.safe_page("https://stusaurus.github.io/baby-cost-jp/", site))
        self.assertIsNone(g.safe_page("https://stusaurus.github.io/daily-cost-jp-other/", site))
        self.assertIsNone(g.safe_page("http://stusaurus.github.io/daily-cost-jp/", site))
        self.assertEqual(g.safe_page(site + "categories/tissue/", site), "/categories/tissue/")

    def test_missing_permission_does_not_trigger_api_query(self):
        session = FakeSession()
        report = g.make_report(dt.date(2026, 10, 14), session, {})
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(len(session.calls), 0)
        self.assertEqual(report["sites"][0]["reason"], "PROPERTY_ACCESS_MISSING")
        self.assertIn("不明", g.markdown(report))
        self.assertNotIn("| 日用品 | 0 |", g.markdown(report))

    def test_partial_access_does_not_fake_remaining_five_sites(self):
        session = FakeSession()
        first = g.SITES[0][1]
        report = g.make_report(dt.date(2026, 10, 14), session, {first: "siteRestrictedUser"})
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["sites"][0]["status"], "OBSERVED")
        self.assertEqual(report["sites"][0]["top_pages"][0]["path"], "/categories/tissue/")
        self.assertEqual(report["sites"][1]["status"], "NOT_CONNECTED")
        self.assertEqual(len(session.calls), 5)
        self.assertTrue(all(call[1]["dataState"] == "final" for call in session.calls))

    def test_weekly_decline_flagged_with_sufficient_sample(self):
        earlier = {"impressions": 100}
        later = {"impressions": 30}
        self.assertEqual(g.change(later, earlier)["status"], "OBSERVED_DECLINE")
        self.assertEqual(g.change(later, None)["status"], "UNKNOWN")
        self.assertEqual(g.change({"impressions": 2}, {"impressions": 4})["status"], "LOW_SAMPLE")

    def test_markdown_contains_both_comparison_windows_and_status(self):
        session = FakeSession()
        report = g.make_report(dt.date(2026, 10, 14), session,
                               {site: "siteRestrictedUser" for _, site in g.SITES})
        rendered = g.markdown(report)
        self.assertEqual(report['data_timezone'], 'America/Los_Angeles')
        self.assertIn('| 日用品 | 7日 | 30 / 1 | 30 / 1 | 0 (0.0%) | 0 | OBSERVE |', rendered)
        self.assertIn('| 日用品 | 28日 |', rendered)
        self.assertIn('前28日：2026-08-17〜2026-09-13', rendered)


if __name__ == "__main__":
    unittest.main()
