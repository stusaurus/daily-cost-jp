"""Regression checks for query-intent guidance without invented store rankings."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import improve_purchase_pages as pages


class StoreComparisonIntentTests(unittest.TestCase):
    def test_laundry_explains_how_to_compare_without_store_rank(self):
        with patch.object(pages, "filter_items", return_value=[]):
            result = pages.price_answer("laundry", {"items": []})
        self.assertIn("store-comparison-method", result)
        self.assertIn("店頭では税込価格", result)
        self.assertIn("店頭価格や在庫は取得していません", result)
        self.assertIn("店舗別の最安順位は表示できません", result)
        self.assertNotIn("実店舗ランキング1位", result)

    def test_other_categories_do_not_get_laundry_guidance(self):
        with patch.object(pages, "filter_items", return_value=[]):
            result = pages.price_answer("tissue", {"items": []})
        self.assertNotIn("store-comparison-method", result)


if __name__ == "__main__":
    unittest.main()
