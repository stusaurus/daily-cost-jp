import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from improve_category_seo import metric_label, seo_section, faq_section
from comparison_units import comparison_unit


class SeoComparisonUnitsTests(unittest.TestCase):
    def test_tissue_guide_matches_normalized_ranking_not_catalog_box(self):
        payload = {"categories": {"tissue": {"metric": "box"}}}
        label = metric_label("tissue", payload)
        unit = comparison_unit("tissue", {"name": "200組5箱", "metric": "box", "unit_price": 100})
        self.assertEqual(label, unit[0])
        self.assertEqual(label, "100組")
        self.assertIn("100組あたり", faq_section("tissue", "ティッシュ", label))
        self.assertNotIn("<strong>1箱あたり</strong>", seo_section("tissue", "ティッシュ", "ティッシュ", label))

    def test_toilet_guide_keeps_ply_separation_and_normalized_length(self):
        payload = {"categories": {"toilet-paper": {"metric": "roll"}}}
        label = metric_label("toilet-paper", payload)
        self.assertEqual(label, "シングル・ダブル別の10m")
        guide = seo_section("toilet-paper", "トイレットペーパー", "トイレットペーパー", label)
        self.assertIn("シングル・ダブル別の10mあたり", guide)
        self.assertNotIn("<strong>1ロールあたり</strong>", guide)

    def test_other_categories_and_unknown_metrics_are_unchanged(self):
        for metric, expected in (("100g", "100g"), ("100ml", "100ml"), ("unknown", "同じ単位")):
            self.assertEqual(metric_label("laundry", {"categories": {"laundry": {"metric": metric}}}), expected)
