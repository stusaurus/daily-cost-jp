import sys
import unittest
from hashlib import sha256
from tempfile import TemporaryDirectory
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from toilet_ply_contract import audit_page, audit_published_styles
from improve_category_seo import toilet_ply_compare_panel


def product(ply, idx):
    return {
        "name": f"トイレットペーパー {ply} 50m 12ロール 品番{idx}",
        "price": 1200 + idx,
        "unit_price": (1200 + idx) / 12,
        "confidence": .99,
        "metric": "roll",
        "postage": "送料込み",
        "shop": "店舗",
        "item_code": f"shop:{idx}",
        "url": f"https://item.rakuten.co.jp/shop/{idx}/",
    }


class ToiletPlyContractTests(unittest.TestCase):
    def setUp(self):
        self.category = {
            "toilet_ply_groups": {
                "single": [product("シングル", 1)],
                "double": [product("ダブル", 2)],
            },
            "toilet_ply_supply": {"families": {}},
        }
        self.page = toilet_ply_compare_panel({
            "categories": {"toilet-paper": self.category}
        })

    def test_valid_both_family_cards_pass(self):
        self.assertEqual(audit_page(self.category, self.page), [])

    def test_tampered_affiliate_url_and_payment_are_blocked(self):
        bad_url = self.page.replace(
            "https://item.rakuten.co.jp/shop/2/",
            "https://item.rakuten.co.jp/shop/900/",
        )
        self.assertTrue(any("purchase data" in e for e in
                            audit_page(self.category, bad_url)))
        bad_price = self.page.replace('data-shipping-price="1202"', 'data-shipping-price="1"')
        self.assertTrue(any("purchase data" in e for e in
                            audit_page(self.category, bad_price)))

    def test_removed_single_navigation_fails(self):
        changed = self.page.replace('href="#toilet-single-offers"', 'href="#toilet-paper"')
        self.assertTrue(any("navigation missing" in e for e in
                            audit_page(self.category, changed)))

    def test_final_page_requires_versioned_scoped_css_asset(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            css = b".toilet-ply-compare{}.toilet-ply-card{}.toilet-ply-amount{}" \
                  b".toilet-ply-unit{}.toilet-ply-buy{}@media(max-width:580px){}"
            (root / "assets/toilet-paper.css").write_bytes(css)
            hash_part = sha256(css).hexdigest()[:12]
            html = ('<head><link data-laboratory-design="v1">'
                    '<link data-toilet-ply-design="v1" rel="stylesheet" '
                    f'href="/daily-cost-jp/assets/toilet-paper.css?v={hash_part}"></head>')
            self.assertEqual(audit_published_styles(root, html), [])
            self.assertTrue(audit_published_styles(root, html.replace(hash_part, "stale")))
            self.assertTrue(audit_published_styles(root, html.replace(
                'data-toilet-ply-design="v1"', 'data-toilet-ply-design="old"')))
            (root / "assets/toilet-paper.css").unlink()
            self.assertTrue(audit_published_styles(root, html))

    def test_empty_double_has_search_and_no_fake_purchase(self):
        self.category["toilet_ply_groups"]["double"] = []
        page = toilet_ply_compare_panel({"categories": {"toilet-paper": self.category}})
        self.assertEqual(audit_page(self.category, page), [])


if __name__ == "__main__":
    unittest.main()
