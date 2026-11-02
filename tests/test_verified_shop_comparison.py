"""Regression coverage for the same-SKU shop comparison."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts import verified_shop_comparison as c


def product(shop, price, **overrides):
    row = {
        "name": "【6個】さらさ 洗濯洗剤 液体 詰め替え 1490g",
        "sale_quantity_label": "1490g×6個", "category_id": "laundry",
        "postage": "送料込み", "quality_version": 1,
        "sale_quantity_confidence": .99,
        "shop": shop, "price": price,
        "url": "https://hb.afl.rakuten.co.jp/hgc/test/?pc=test",
    }
    return {**row, **overrides}


class VerifiedShopComparisonTests(unittest.TestCase):
    def test_exact_two_shop_comparison(self):
        offers = c.select_offers({"categories": {"laundry": {
            "items": [product("Shop A", 7980), product("Shop B", 8580)]
        }}})
        self.assertEqual([x["price"] for x in offers], [7980, 8580])
        rendered = c.render(offers)
        self.assertIn("¥600", rendered)
        self.assertIn("¥7,980", rendered)
        self.assertIn('rel="nofollow sponsored noopener"', rendered)
        self.assertIn("全店舗の最安値を保証するものではありません", rendered)

    def test_no_fake_shop_differences_or_different_products(self):
        rows = [product("A", 1000), product("A", 900),
                product("B", 800, sale_quantity_label="1590g×6個"),
                product("C", 800, name="さらさ 柔軟剤 1490g"),
                product("D", 800, postage="送料別"),
                product("E", 800, url="https://evil.example/offer"),
                product("F", 800, sale_quantity_confidence=.5)]
        self.assertEqual(c.select_offers({"categories": {"laundry": {"items": rows}}}), [])

    def test_escape_output_and_idempotent_html(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            page = root / "categories/laundry/index.html"
            page.parent.mkdir(parents=True)
            page.write_text('<html><head></head><body><main class="container">'
                            + c.ANCHOR + 'x</section></main></body></html>',
                            encoding="utf-8")
            (root/"data.json").write_text(json.dumps({"categories": {"laundry": {
                "items": [product("<Store>", 1000), product("B", 1200)]
            }}}), encoding="utf-8")
            self.assertEqual(c.apply(root), "rendered")
            self.assertEqual(c.apply(root), "already_exists")
            value = page.read_text(encoding="utf-8")
            self.assertIn("&lt;Store&gt;", value)
            self.assertNotIn("<Store>", value)
            self.assertEqual(value.count(c.MARKER), 1)

    def test_missing_pair_keeps_original_html(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            page = root / "categories/laundry/index.html"
            page.parent.mkdir(parents=True)
            original = '<html><head></head><body><main class="container">' + c.ANCHOR + 'x</section></main></body></html>'
            page.write_text(original, encoding="utf-8")
            (root/"data.json").write_text(json.dumps({"categories": {"laundry": {
                "items": [product("A", 1000)]
            }}}), encoding="utf-8")
            self.assertEqual(c.apply(root), "no_verified_pair")
            self.assertEqual(page.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
