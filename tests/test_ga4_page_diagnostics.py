"""Offline synthetic tests for read-only page diagnostics."""
import datetime as dt
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("ga4_page_diagnostics", SCRIPTS / "ga4_page_diagnostics.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TODAY = dt.date(2026, 10, 10)
DATES = module.dates_for(TODAY)
SITE = "https://stusaurus.github.io/daily-cost-jp/"
TISSUE = SITE + "categories/tissue/"
PATH = "/daily-cost-jp/categories/tissue/"


def view_records(days=28, per_day=3):
    selection = DATES[-days:]
    return [(d.strftime("%Y%m%d"), PATH, per_day) for d in selection]


def click(date, url=TISSUE, flag="0", count=1):
    return (date.strftime("%Y%m%d"), url, flag, count)


class DiagnosticsTests(unittest.TestCase):
    def test_exact_dates_allow_two_day_reporting_delay(self):
        self.assertEqual(DATES[-1], dt.date(2026, 10, 8))
        self.assertEqual(DATES[-28], dt.date(2026, 9, 11))
        self.assertEqual(len(DATES), 56)

    def test_only_trusted_https_site_url_is_accepted(self):
        self.assertEqual(module.path_from_location(TISSUE + "?q=safe"), "/categories/tissue/")
        self.assertIsNone(module.path_from_location("https://evil.example/daily-cost-jp/categories/tissue/"))
        self.assertIsNone(module.path_from_location("http://stusaurus.github.io/daily-cost-jp/categories/tissue/"))
        self.assertIsNone(module.path_from_location("https://stusaurus.github.io.evil/daily-cost-jp/"))
        self.assertIsNone(module.path_from_location("https://stusaurus.github.io:999/daily-cost-jp/"))
        self.assertIsNone(module.path_from_location("https://stusaurus.github.io/daily-cost-jp-malicious/"))

    def test_operator_exclusion_and_query_normalization(self):
        clicks = [
            click(DATES[-2], TISSUE + "?utm_source=a", "1", 2),
            click(DATES[-2], TISSUE + "?utm_source=b", "0", 3),
            click(DATES[-1], TISSUE, "(not set)", 4),
            click(DATES[-1], "http://localhost:8000/daily-cost-jp/categories/tissue/", "0", 8),
        ]
        report = module.make_report(clicks, view_records(), TODAY, True)
        page = report["pages"][0]
        stats = page["periods"]["last_28"]
        self.assertEqual(stats["pageviews"], 84)
        self.assertEqual(stats["clicks"]["production_operator"], 2)
        self.assertEqual(stats["clicks"]["production_non_operator"], 3)
        self.assertEqual(stats["clicks"]["production_unknown"], 4)
        self.assertEqual(report["excluded_clicks"]["development"], 8)
        self.assertEqual(page["action_code"], "CHECK_UNKNOWN_TEST_EVENTS")
        self.assertIsNone(page["provisional_clicks_per_100_pageviews"])

    def test_7_and_28_windows_do_not_double_count(self):
        views = view_records(56, 2)
        clicks = [click(DATES[-1], count=2), click(DATES[-12], count=3),
                  click(DATES[-31], count=5)]
        page = module.make_report(clicks, views, TODAY, True)["pages"][0]
        periods = page["periods"]
        self.assertEqual(periods["last_7"]["pageviews"], 14)
        self.assertEqual(periods["last_28"]["pageviews"], 56)
        self.assertEqual(periods["prior_28"]["pageviews"], 56)
        self.assertEqual(periods["last_7"]["clicks"]["production_non_operator"], 2)
        self.assertEqual(periods["last_28"]["clicks"]["production_non_operator"], 5)
        self.assertEqual(periods["prior_28"]["clicks"]["production_non_operator"], 5)

    def test_cta_audit_is_only_a_hypothesis_with_enough_exposure(self):
        report = module.make_report([], view_records(28, 4), TODAY, True)
        page = report["pages"][0]
        self.assertEqual(report["status"], "PROVISIONAL")
        self.assertEqual(page["action_code"], "AUDIT_CTA_AND_LINKS")
        self.assertEqual(page["priority"], 2)
        self.assertEqual(page["periods"]["last_28"]["pageviews"], 112)

    def test_low_traffic_yields_observe(self):
        report = module.make_report([], view_records(28, 1), TODAY, True)
        self.assertEqual(report["pages"][0]["action_code"], "OBSERVE_LOW_TRAFFIC")

    def test_missing_days_block_cta_conclusion(self):
        report = module.make_report([], view_records(27, 20), TODAY, True)
        self.assertEqual(report["status"], "COVERAGE_UNCERTAIN")
        self.assertEqual(report["pageview_dates_observed_in_last_28"], 27)
        self.assertEqual(report["pages"][0]["action_code"], "CHECK_DATA_COVERAGE")
        self.assertIsNone(report["pages"][0]["provisional_clicks_per_100_pageviews"])

    def test_unregistered_dimension_prevents_clean_click_claim(self):
        report = module.make_report([click(DATES[-1], flag="0", count=5)],
                                    view_records(), TODAY, False)
        c = report["pages"][0]["periods"]["last_28"]["clicks"]
        self.assertEqual(report["status"], "OPERATOR_DIMENSION_UNAVAILABLE")
        self.assertEqual(c["production_unknown"], 5)
        self.assertEqual(c["production_non_operator"], 0)
        self.assertEqual(report["pages"][0]["action_code"], "CHECK_OPERATOR_DIMENSION")

    def test_pageview_drop_proposed_not_assumed_seo(self):
        previous = [(d.strftime("%Y%m%d"), PATH, 10) for d in DATES[-14:-7]]
        current = [(d.strftime("%Y%m%d"), PATH, 3) for d in DATES[-7:]]
        earlier = [(d.strftime("%Y%m%d"), PATH, 2) for d in DATES[-28:-14]]
        report = module.make_report([], previous + current + earlier, TODAY, True)
        self.assertEqual(report["pages"][0]["action_code"], "INVESTIGATE_PAGEVIEW_DROP")

    def test_duplicate_view_rows_rejected(self):
        bad = [view_records(1)[0], view_records(1)[0]]
        with self.assertRaises(ValueError):
            module.make_report([], bad, TODAY, True)

    def test_invalid_or_out_of_range_data_rejected(self):
        with self.assertRaises(ValueError):
            module.make_report([click(DATES[-1], count=-1)], view_records(), TODAY, True)
        with self.assertRaises(ValueError):
            module.make_report([], [("20251008", PATH, 2)], TODAY, True)
        with self.assertRaises(ValueError):
            module.make_report([], [("20261008", "/other-project/", 1)], TODAY, True)

    def test_zero_pageview_rows_do_not_invent_traffic(self):
        report = module.make_report([], [], TODAY, True)
        self.assertEqual(report["status"], "NO_PAGEVIEWS")
        self.assertEqual(report["pages"], [])
        self.assertIn("売上", module.markdown_report(report))

    def test_markdown_disclaims_sales_and_automated_changes(self):
        report = module.make_report([], view_records(), TODAY, True)
        markdown = module.markdown_report(report)
        self.assertIn("楽天", markdown)
        self.assertIn("購入", markdown)
        self.assertIn("自動変更しません", markdown)


if __name__ == "__main__":
    unittest.main()
