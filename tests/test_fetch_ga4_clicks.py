"""Offline checks: GA4 raw export must not be mistaken for qualified clicks."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_ga4_clicks", ROOT / "scripts" / "fetch_ga4_clicks.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Ga4ExportTests(unittest.TestCase):
    def test_only_affiliate_events(self):
        rows = [("20261008", "affiliate_click", "2"), ("20261008", "page_view", "80"),
                ("20261008", "affiliate_click", "3")]
        self.assertEqual(module.normalize(rows), [{"date": "2026-10-08", "affiliate_click_raw": 5}])

    def test_missing_days_not_fabricated(self):
        self.assertEqual(module.normalize([]), [])

    def test_negative_values_rejected(self):
        with self.assertRaises(ValueError):
            module.normalize([("20261008", "affiliate_click", "-1")])

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            module.normalize([("bad-date", "affiliate_click", "1")])

if __name__ == "__main__":
    unittest.main()
