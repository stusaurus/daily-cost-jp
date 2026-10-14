"""Offline Search Console pilot: property scoping, no fabricated zero and evidence-based SEO hints."""
import datetime as dt
import importlib.util
import pathlib
import unittest
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("gsc_readonly_pilot", SCRIPTS / "gsc_readonly_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

TODAY = dt.date(2026, 10, 10)
DOMAIN = "https://stusaurus.github.io/daily-cost-jp/"
LAUNDRY = DOMAIN + "categories/laundry/"
TISSUE = DOMAIN + "categories/tissue/"

def row(key, clicks, impressions, position=12):
    return {"keys": [key], "clicks": clicks, "impressions": impressions,
            "ctr": clicks / impressions if impressions else 0, "position": position}

def agg(clicks, impressions):
    return {"rows": [{"clicks": clicks, "impressions": impressions,
                      "ctr": clicks / impressions if impressions else 0,
                      "position": 10.0}]}

def pages():
    return {"rows": [row(LAUNDRY, 4, 200, 9), row(TISSUE, 3, 50, 15)]}

class GscTests(unittest.TestCase):
    def test_time_windows_wait_for_final_gsc_data(self):
        ranges = pilot.periods(TODAY)
        self.assertEqual(ranges["last_7"], ["2026-10-01", "2026-10-07"])
        self.assertEqual(ranges["last_28"], ["2026-09-10", "2026-10-07"])
        self.assertEqual(ranges["prior_28"], ["2026-08-13", "2026-09-09"])
        self.assertEqual(ranges["prior_7"], ["2026-09-24", "2026-09-30"])

    def test_exact_site_prefix_url_allowlist(self):
        self.assertEqual(pilot.normalize_path(LAUNDRY), "/categories/laundry/")
        self.assertEqual(pilot.normalize_path(LAUNDRY + "?q=test"), "/categories/laundry/")
        self.assertIsNone(pilot.normalize_path("https://stusaurus.github.io/sotojitaku/"))
        self.assertIsNone(pilot.normalize_path("https://evil.example/daily-cost-jp/"))
        self.assertIsNone(pilot.normalize_path("http://stusaurus.github.io/daily-cost-jp/"))
        self.assertIsNone(pilot.normalize_path("https://stusaurus.github.io.evil/daily-cost-jp/"))
        self.assertIsNone(pilot.normalize_path("https://stusaurus.github.io:8888/daily-cost-jp/"))
        self.assertIsNone(pilot.normalize_path("https://stusaurus.github.io/daily-cost-jp-evil/"))

    def test_valid_GSC_metrics_and_invalid_data(self):
        self.assertEqual(pilot.metrics(row(LAUNDRY, 4, 200, 8.7))["impressions"], 200)
        for value in [
            row(LAUNDRY, -1, 200),
            row(LAUNDRY, 1, -2),
            {"clicks": 1, "impressions": 10, "ctr": 2, "position": 5},
            {"clicks": 1, "impressions": 10, "ctr": .1, "position": -2},
            {"clicks": "1", "impressions": 10, "ctr": .1, "position": 2},
            {"clicks": .5, "impressions": 10, "ctr": .05, "position": 2},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                pilot.metrics(value)

    def test_no_rows_cannot_be_confidently_reported_as_zero(self):
        self.assertIsNone(pilot.aggregate_response({})["metrics"])
        self.assertIsNone(pilot.aggregate_response({"rows": []})["metrics"])
        self.assertEqual(pilot.aggregate_response({"rows": []})["status"], "NO_ROWS")

    def test_only_selected_site_pages_are_saved(self):
        report = pilot.page_response({"rows": [row(LAUNDRY, 4, 200),
            row("https://stusaurus.github.io/sotojitaku/", 2, 100)]})
        self.assertEqual(set(report["pages"]), {"/categories/laundry/"})
        self.assertEqual(report["discarded_out_of_scope"], 1)
        self.assertEqual(report["status"], "OBSERVED_TOP_ROWS")

    def test_duplicate_page_keys_rejected(self):
        with self.assertRaises(ValueError):
            pilot.page_response({"rows": [row(LAUNDRY, 1, 20), row(LAUNDRY, 2, 20)]})

    def test_short_tail_queries_are_not_in_public_report(self):
        data = {"rows": [
            {"keys": [LAUNDRY, "アリエール 安い"], "clicks": 3,
             "impressions": 180, "ctr": 3 / 180, "position": 8},
            {"keys": [LAUNDRY, "rare query"], "clicks": 1,
             "impressions": 3, "ctr": 1/3, "position": 12},
            {"keys": ["https://other.example/", "another query"], "clicks": 2,
             "impressions": 300, "ctr": 2 / 300, "position": 8},
        ]}
        output = pilot.query_response(data)
        self.assertEqual(len(output["queries"]), 1)
        self.assertEqual(output["queries"][0]["query"], "アリエール 安い")

    def test_rank_and_ctr_are_independent_of_affiliate_clicks(self):
        low_ctr = pilot.page_response({"rows": [row(LAUNDRY, 1, 300, 10)]})
        self.assertEqual(pilot.decide(low_ctr["pages"]["/categories/laundry/"],
                                      low_ctr["pages"]["/categories/laundry/"])[0],
                         "CHECK_SEARCH_RESULT_SNIPPET")
        small = {"clicks": 0, "impressions": 10, "ctr": 0, "position": 20}
        self.assertEqual(pilot.decide(small, small)[0], "CHECK_SEARCH_VISIBILITY")
        self.assertEqual(pilot.decide(None, None)[0], "OBSERVE")

    def test_integrated_report_never_claims_sales_or_organic_cause(self):
        aggregates = {label: pilot.aggregate_response(agg(4, 200))
                      for label in pilot.periods(TODAY)}
        per_page = {label: pilot.page_response(pages())
                    for label in pilot.periods(TODAY)}
        queries = pilot.query_response({"rows": []})
        report = pilot.build_report(TODAY, aggregates, per_page, queries)
        self.assertEqual(report["status"], "PROVISIONAL")
        self.assertEqual(report["site_property"], DOMAIN)
        self.assertTrue(report["priority_pages"])
        self.assertIn("Search", report["source"])
        self.assertIn("楽天", pilot.markdown(report))
        self.assertIn("変更していません", pilot.markdown(report))
        self.assertIn("/categories/toilet-paper/", {p["path"] for p in report["pages"]})

    def test_fail_closed_missing_property_access(self):
        item = pilot.not_connected("PROPERTY_ACCESS_MISSING")
        self.assertEqual(item["status"], "NOT_CONNECTED")
        self.assertIsNone(item.get("site_aggregates", {}).get("last_7"))
        self.assertIn("0件という意味ではありません", pilot.markdown(item))
        self.assertEqual(pilot.api_error_reason(403), "SEARCH_CONSOLE_API_DISABLED_OR_FORBIDDEN")

    def test_aggregate_malformed_data_rejected(self):
        with self.assertRaises(ValueError):
            pilot.aggregate_response({"rows": [row(LAUNDRY, 3, 100)]})
        with self.assertRaises(ValueError):
            pilot.aggregate_response({"rows": [{}, {}]})
        with self.assertRaises(ValueError):
            pilot.query_response({"rows": [{"keys": [LAUNDRY], "clicks": 1,
                                             "impressions": 20, "ctr": .05, "position": 1}]})

if __name__ == "__main__":
    unittest.main()
