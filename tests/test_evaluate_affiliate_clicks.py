"""Tests for fail-closed three-day affiliate click evaluation."""
import datetime as dt
import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "evaluate_affiliate_clicks.py"
spec = importlib.util.spec_from_file_location("evaluate_affiliate_clicks", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

TODAY = dt.date(2026, 10, 10)

def row(day, clicks, sessions=20, test=0, complete=True):
    return {"date": day, "affiliate_click": clicks, "sessions": sessions,
            "operator_test_clicks": test, "data_complete": complete}

class EvaluateClicksTests(unittest.TestCase):
    def test_complete_three_day_window_excludes_tests(self):
        report = module.evaluate({"days": [
            row("2026-10-07", 4, 30, 2),
            row("2026-10-08", 3, 40, 1),
            row("2026-10-09", 2, 50, 0),
        ]}, TODAY)
        self.assertEqual(report["qualified_clicks"], 6)
        self.assertEqual(report["sessions"], 120)
        self.assertEqual(report["status"], "OBSERVE")
        self.assertEqual(report["revenue"], "NOT_CHECKED")

    def test_missing_days_not_treated_as_zero(self):
        report = module.evaluate({"days": [
            row("2026-10-08", 1), row("2026-10-09", 1)
        ]}, TODAY)
        self.assertEqual(report["status"], "DATA_UNAVAILABLE")
        self.assertEqual(report["action"], "OBSERVE")
        self.assertNotIn("qualified_clicks", report)

    def test_incomplete_day_not_treated_as_zero(self):
        report = module.evaluate({"days": [
            row("2026-10-07", 1), row("2026-10-08", 1, complete=False), row("2026-10-09", 1)
        ]}, TODAY)
        self.assertEqual(report["status"], "DATA_UNAVAILABLE")

    def test_duplicate_date_fails(self):
        with self.assertRaises(ValueError):
            module.evaluate({"days": [row("2026-10-09", 1), row("2026-10-09", 2)]}, TODAY)

    def test_test_clicks_cannot_exceed_total(self):
        with self.assertRaises(ValueError):
            module.evaluate({"days": [
                row("2026-10-07", 1, test=2), row("2026-10-08", 0), row("2026-10-09", 0)
            ]}, TODAY)

    def test_invalid_numeric_fields_rejected(self):
        with self.assertRaises(ValueError):
            module.evaluate({"days": [
                row("2026-10-07", 1), row("2026-10-08", -1), row("2026-10-09", 2)
            ]}, TODAY)

if __name__ == "__main__":
    unittest.main()
