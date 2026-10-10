"""Offline, synthetic tests for production-scoped GA4 reporting."""
import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("ga4_three_day_report", SCRIPTS / "ga4_three_day_report.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

DAYS = [dt.date(2026, 10, 5) + dt.timedelta(days=i) for i in range(3)]
SITE = "https://stusaurus.github.io/daily-cost-jp/categories/tissue/"


class ThreeDayReportTests(unittest.TestCase):
    def test_window_allows_ga4_reporting_delay(self):
        self.assertEqual(module.window(dt.date(2026, 10, 10)), DAYS)

    def test_scopes_events_and_excludes_operator_tests(self):
        report = module.make_report(
            [
                ("20261005", SITE, "1", 2),
                ("20261005", SITE, "0", 3),
                ("20261005", "http://localhost:8000/daily-cost-jp/", "0", 7),
                ("20261006", "https://other.example/daily-cost-jp/", "0", 11),
                ("20261007", SITE, "0", 4),
            ],
            [("20261005", 20), ("20261006", 10), ("20261007", 30)],
            DAYS,
            True,
        )
        summary = report["summary"]
        self.assertEqual(summary["status"], "OBSERVE")
        self.assertEqual(summary["production_raw_clicks"], 9)
        self.assertEqual(summary["known_operator_test_clicks"], 2)
        self.assertEqual(summary["provisional_non_operator_clicks"], 7)
        self.assertEqual(summary["out_of_scope_events"], 18)
        self.assertEqual(summary["sessions"], 60)
        self.assertEqual(summary["clicks_per_session"], round(7 / 60, 4))
        self.assertEqual(summary["revenue"], "NOT_CHECKED")

    def test_unregistered_custom_dimension_does_not_infer_clean_clicks(self):
        report = module.make_report(
            [("20261005", SITE, "", 3)],
            [("20261005", 10), ("20261006", 12), ("20261007", 10)],
            DAYS,
            False,
        )
        summary = report["summary"]
        self.assertEqual(summary["production_raw_clicks"], 3)
        self.assertIsNone(summary["provisional_non_operator_clicks"])
        self.assertEqual(summary["unknown_operator_clicks"], 3)
        self.assertEqual(summary["status"], "DATA_LIMITED")

    def test_missing_session_day_is_unknown_not_zero(self):
        report = module.make_report(
            [("20261005", SITE, "0", 1)],
            [("20261005", 10), ("20261006", 12)],
            DAYS,
            True,
        )
        self.assertIsNone(report["days"][2]["site_sessions"])
        self.assertEqual(report["summary"]["status"], "DATA_LIMITED")
        self.assertIsNone(report["summary"]["sessions"])

    def test_unknown_operator_flag_blocks_decision(self):
        report = module.make_report(
            [("20261005", SITE, "(not set)", 4)],
            [("20261005", 10), ("20261006", 10), ("20261007", 10)],
            DAYS,
            True,
        )
        self.assertEqual(report["summary"]["status"], "DATA_LIMITED")
        self.assertEqual(report["summary"]["unknown_operator_clicks"], 4)

    def test_zero_events_requires_measured_sessions(self):
        report = module.make_report(
            [], [("20261005", 10), ("20261006", 10), ("20261007", 10)],
            DAYS, True)
        self.assertEqual(report["summary"]["production_raw_clicks"], 0)
        self.assertEqual(report["summary"]["recommended_action"], "CHECK_MEASUREMENT_AND_TRAFFIC")
        self.assertEqual(report["summary"]["status"], "NEEDS_ATTENTION")

    def test_duplicate_sessions_date_is_rejected(self):
        with self.assertRaises(ValueError):
            module.accumulate_sessions([("20261005", 5), ("20261005", 10)], DAYS)

    def test_out_of_range_or_negative_clicks_are_rejected(self):
        with self.assertRaises(ValueError):
            module.accumulate_clicks([("20261004", SITE, "0", 1)], DAYS, True)
        with self.assertRaises(ValueError):
            module.accumulate_clicks([("20261005", SITE, "0", -1)], DAYS, True)

    def test_truncated_result_rejected(self):
        class Response:
            row_count = 12
            rows = [None] * 10
            metadata = None
        with self.assertRaises(ValueError):
            module.check_response(Response())


if __name__ == "__main__":
    unittest.main()
