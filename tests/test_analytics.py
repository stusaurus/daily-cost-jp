import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analytics', ROOT / 'scripts/add_analytics.py')
analytics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analytics)


class AnalyticsBuildTests(unittest.TestCase):
    def test_site_validator_accepts_one_approved_config_not_missing_or_duplicate(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from validate_generated_site import has_one_ga4_config
        old = "gtag('config', 'G-GFVSZ8YDQ5')"
        new = "gtag('config', 'G-GFVSZ8YDQ5', window.dailyCostMeasurementContext())"
        for valid in (old, new):
            self.assertTrue(has_one_ga4_config(valid))
        for invalid in ('', old + new, old + old, new + new,
                        "gtag('config', 'G-GFVSZ8YDQ5', {})",
                        "gtag('config', 'G-GFVSZ8YDQ5'"):
            self.assertFalse(has_one_ga4_config(invalid))

    def test_rebuild_keeps_content_and_one_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            content = '<h1>変更禁止SEO見出し</h1><p>変更禁止本文</p><a href="https://hb.afl.rakuten.co.jp/test">楽天</a>'
            path.write_text('<html><head><title>変更禁止タイトル</title></head><body>' + content + '</body></html>')
            for _ in range(2):
                analytics.inject_file(path, 'G-GFVSZ8YDQ5')
                text = path.read_text()
                self.assertIn(content, text)
                self.assertEqual(text.count("gtag('config', 'G-GFVSZ8YDQ5', window.dailyCostMeasurementContext())"), 1)
                self.assertEqual(text.count("function affiliate(event)"), 1)
                self.assertEqual(text.count("gtag/js?id="), 1)
                self.assertLess(text.index('daily_cost_operator_test_v1'), text.index("gtag('config',"))

    def test_malformed_html_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            path.write_text('<h1>incomplete</h1>')
            self.assertFalse(analytics.inject_file(path, 'G-GFVSZ8YDQ5'))
            self.assertEqual(path.read_text(), '<h1>incomplete</h1>')
