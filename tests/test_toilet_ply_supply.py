import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from comparison_units import comparison_unit, toilet_ply_length
from toilet_ply_supply import (
    MAX_PER_PLY, build_toilet_ply_groups, group_toilet_offers, supply_diagnostics,
)
from improve_category_seo import toilet_ply_compare_panel


def offer(ply, length, price, index, rolls=12):
    return dict(
        name=f"トイレットペーパー {ply} {length}m {rolls}ロール 商品{index}",
        price=price, unit_price=price / rolls, metric="roll", confidence=.99,
        postage="送料込み", url=f"https://item.rakuten.co.jp/shop/{index}/",
        item_code=f"shop:{index}", image="", shop="店舗",
    )


class PermanentToiletSupplyTests(unittest.TestCase):
    def test_both_types_have_independent_10m_price_ranking(self):
        rows = [
            offer("シングル", 100, 1200, 1),
            offer("ダブル", 30, 1200, 2),
            offer("シングル", 100, 1000, 3),
            offer("ダブル", 60, 1200, 4),
        ]
        result = build_toilet_ply_groups(rows)
        self.assertEqual([x["item_code"] for x in result["single"]], ["shop:3", "shop:1"])
        self.assertEqual([x["item_code"] for x in result["double"]], ["shop:4", "shop:2"])
        self.assertAlmostEqual(comparison_unit("toilet-paper", result["double"][0])[1], 16.6666667)

    def test_full_pool_is_used_not_only_first_twelve(self):
        singles = [offer("シングル", 100, 1000 + i, i) for i in range(12)]
        double = offer("ダブル", 30, 1200, 30)
        result = build_toilet_ply_groups(singles + [double])
        self.assertEqual(len(result["single"]), MAX_PER_PLY)
        self.assertEqual([r["item_code"] for r in result["double"]], [double["item_code"]])

    def test_double_does_not_mean_twice_as_long(self):
        single = offer("シングル", 100, 900, 1)
        single["name"] += " 2倍巻き"
        self.assertEqual(len(group_toilet_offers([single])["double"]), 0)
        ambiguous = offer("ダブル", 30, 1000, 2)
        ambiguous["name"] += " 60mも選択可能"
        self.assertIsNone(toilet_ply_length(ambiguous))
        self.assertIsNone(comparison_unit("toilet-paper", ambiguous))

    def test_ambiguous_and_wrong_shipping_are_not_reinstated(self):
        ambiguous = offer("ダブル", 30, 1000, 1)
        ambiguous["name"] = "トイレットペーパー ダブル 12ロール 長さ未確認"
        postage = offer("ダブル", 30, 1000, 2)
        postage["postage"] = "送料別"
        accessory = offer("ダブル", 30, 1000, 3)
        accessory["name"] += " トイレットペーパーホルダー"
        result = build_toilet_ply_groups([ambiguous, postage, accessory])
        self.assertEqual(result, {"single": [], "double": []})

    def test_duplicate_offer_and_capacity_limit(self):
        entries = [offer("ダブル", 60, 1200 + i, i) for i in range(8)]
        entries.append(entries[0].copy())
        self.assertEqual(len(build_toilet_ply_groups(entries)["double"]), MAX_PER_PLY)
        with self.assertRaises(ValueError):
            build_toilet_ply_groups(entries, limit=20)

    def test_diagnostics_never_claim_market_is_out_of_stock(self):
        states = supply_diagnostics({"single": [offer("シングル", 50, 1000, 1)],
                                    "double": []},
                                   {"requests": [{"query": "トイレットペーパー ダブル 12ロール",
                                                  "error": "HTTPError"}]})
        self.assertEqual(states["families"]["single"]["state"], "VERIFIED")
        self.assertEqual(states["families"]["double"]["state"], "INCOMPLETE_ACQUISITION")
        self.assertEqual(states["families"]["double"]["verified"], 0)

    def test_render_both_buying_paths_and_matching_rakuten_offers(self):
        single = offer("シングル", 100, 1000, 1)
        double = offer("ダブル", 60, 1100, 2)
        payload = {"categories": {"toilet-paper": {
            "toilet_ply_groups": {"single": [single], "double": [double]},
            "toilet_ply_supply": {"families": {}},
        }}}
        page = toilet_ply_compare_panel(payload)
        self.assertIn('id="toilet-single-offers"', page)
        self.assertIn('id="toilet-double-offers"', page)
        self.assertIn("ダブルの比較候補（1件）", page)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page, "html.parser")
        self.assertEqual(
            soup.select_one("#toilet-double-offers .toilet-ply-price").get_text(""),
            "¥15.28／ダブル10m",
        )
        self.assertIn("シングルの比較を見る", page)
        self.assertIn("支払総額 ¥1,100", page)
        self.assertIn("60m／ロール", page)
        self.assertIn('href="https://item.rakuten.co.jp/shop/2/"', page)
        self.assertEqual(page.count('class="toilet-ply-card"'), 2)

    def test_unavailable_family_has_search_not_fake_checkout(self):
        payload = {"categories": {"toilet-paper": {
            "toilet_ply_groups": {"single": [offer("シングル", 50, 900, 1)], "double": []},
            "toilet_ply_supply": {"families": {"double": {
                "state": "NO_VERIFIED_SNAPSHOT_OFFER",
                "search_failed": False,
            }}},
        }}}
        page = toilet_ply_compare_panel(payload)
        self.assertIn("ダブルの比較候補（0件）", page)
        self.assertIn("ダブルを商品名でさらに検索する", page)
        self.assertNotIn("楽天でダブルの商品を確認する", page)
        self.assertEqual(page.count('class="toilet-ply-card"'), 1)


if __name__ == "__main__":
    unittest.main()
