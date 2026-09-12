import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from sale_quantity import parse_sale_quantity, sale_quantity_for_item


class SaleQuantityTests(unittest.TestCase):
    def label(self, title):
        parsed = parse_sale_quantity(title)
        return parsed and parsed["label"]

    def test_representative_labels(self):
        cases = {
            "水 500ml×24本": "500ml×24本",
            "天然水 2L X 6本": "2L×6本",
            "ペーパー 12ロール": "12ロール入り",
            "ペーパー 12ロール×2パック": "12ロール×2パック",
            "ティッシュ 180組×5箱": "180組×5箱",
            "食品 500g×2袋": "500g×2袋",
            "お菓子 24個": "24個入り",
            "シート 100枚": "100枚入り",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(self.label(title), expected)

    def test_does_not_treat_unqualified_numbers_as_quantity(self):
        for title in ("ABC-123 新型", "2026年モデル", "発売30周年", "No.12 限定版"):
            with self.subTest(title=title):
                self.assertIsNone(parse_sale_quantity(title))

    def test_unit_price_consistency_is_required(self):
        self.assertIsNotNone(sale_quantity_for_item("水 500ml×24本", 1200, 10, "100ml"))
        self.assertIsNone(sale_quantity_for_item("水 500ml×24本", 1200, 20, "100ml"))


if __name__ == "__main__":
    unittest.main()
