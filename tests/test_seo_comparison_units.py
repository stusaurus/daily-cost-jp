import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from improve_category_seo import metric_label, seo_section, faq_section, render_search_copy, SEARCH_TARGETS, toilet_ply_availability_note
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

    def test_laundry_search_copy_matches_actual_unit_and_does_not_claim_cost_per_wash(self):
        target = SEARCH_TARGETS["laundry"]
        for unit in ("100g", "100ml"):
            for field in ("lead", "description", "intent_note"):
                copy = render_search_copy(target[field], unit)
                self.assertIn(f"{unit}あたり", copy)
                self.assertNotIn("{comparison_unit}", copy)
                self.assertNotIn("100g・100ml", copy)
                self.assertNotIn("1回あたりコストまで確認", copy)
            guide = seo_section("laundry", "洗濯洗剤", "洗濯洗剤", unit)
            self.assertIn(f"{unit}あたり", guide)
            self.assertNotIn("{comparison_unit}", guide)

    def test_ply_availability_note_matches_verified_single_only(self):
        item = {"name": "シングル 170m 48ロール", "metric": "roll", "unit_price": 110}
        note = toilet_ply_availability_note({"categories": {"toilet-paper": {"items": [item]}}})
        self.assertIn("比較可能な候補はシングルのみ", note)
        self.assertIn("ダブルの10m単価を確認できた候補", note)
        self.assertIn("ダブルを商品名で検索", note)
        self.assertIn("../../products/?q=", note)
        self.assertNotIn("ダブルの商品がないという意味です", note)

    def test_ply_availability_note_matches_verified_double_only(self):
        item = {"name": "ダブル 30m 12ロール", "metric": "roll", "unit_price": 80}
        note = toilet_ply_availability_note({"categories": {"toilet-paper": {"items": [item]}}})
        self.assertIn("比較可能な候補はダブルのみ", note)
        self.assertIn("シングルの10m単価を確認できた候補", note)

    def test_ply_availability_note_avoids_claims_for_both_or_unverified(self):
        single = {"name": "シングル 170m 48ロール", "metric": "roll", "unit_price": 110}
        double = {"name": "ダブル 30m 12ロール", "metric": "roll", "unit_price": 80}
        uncertain = {"name": "トイレットペーパー 12ロール", "metric": "roll", "unit_price": 80}
        for rows in ([], [single, double], [uncertain], [None], [{"name": "シングル 170m 48ロール", "metric": "roll"}]):
            self.assertEqual(toilet_ply_availability_note({"categories": {"toilet-paper": {"items": rows}}}), "")
        self.assertEqual(toilet_ply_availability_note({"categories": {}}), "")

    def test_other_categories_and_unknown_metrics_are_unchanged(self):
        for metric, expected in (("100g", "100g"), ("100ml", "100ml"), ("unknown", "同じ単位")):
            self.assertEqual(metric_label("laundry", {"categories": {"laundry": {"metric": metric}}}), expected)
