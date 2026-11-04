"""Protect fast purchase-entry paths independently of the full Rakuten build."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import polish_home_design as design
import sharpen_home_value_prop as value


class ConversionFirstHomeTests(unittest.TestCase):
    def test_fast_categories_are_direct_links_and_not_form_gates(self):
        block = design.START
        self.assertIn('aria-label="買う商品が決まっている方の近道"', block)
        for route in ("laundry", "tissue", "toilet-paper"):
            self.assertIn('href="categories/' + route + '/"', block)
        self.assertNotIn('<form', block)
        self.assertNotIn('login', block.lower())

    def test_main_purchase_paths_stay_available(self):
        block = design.START
        self.assertIn('href="products/"', block)
        self.assertIn('href="categories/"', block)
        self.assertIn('href="#buy-judge"', block)

    def test_value_proposition_distinguishes_unit_and_checkout(self):
        source = Path(value.__file__).read_text(encoding="utf-8")
        self.assertIn("数量・単価・支払額を分けて表示", source)
        self.assertIn("数量不明の商品は順位に入れない", source)


if __name__ == "__main__":
    unittest.main()
