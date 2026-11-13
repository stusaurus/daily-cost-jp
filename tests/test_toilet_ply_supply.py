import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from toilet_ply_supply import group_toilet_offers, select_toilet_rankings
from comparison_units import comparison_unit


def item(ply, length, price, index):
    return dict(
        name=f"トイレットペーパー {ply} {length}m 12ロール 品番{index}",
        price=price, unit_price=price / 12, metric="roll", confidence=.99,
        postage="送料込み", url=f"https://item.rakuten.co.jp/shop/{index}/",
        item_code=f"shop:{index}", shop="店舗",
    )


def rank(rows):
    return ("roll", sorted(rows, key=lambda r: r["unit_price"])[:12])


class ToiletPlySupplyTests(unittest.TestCase):
    def test_both_ply_types_remain_separate_and_rank_by_10m(self):
        singles = [item("シングル", 100, 1000, 1), item("シングル", 50, 900, 2)]
        doubles = [item("ダブル", 30, 900, 3), item("ダブル", 60, 1100, 4)]
        metric, primary, alternate, family = select_toilet_rankings(
            singles + doubles, rank, lambda cid, rows: rows
        )
        self.assertEqual(metric, "roll")
        self.assertEqual(family, "シングル10m")
        self.assertEqual([r['item_code'] for r in primary], ['shop:2', 'shop:1'])
        self.assertEqual([r["item_code"] for r in alternate], ["shop:4", "shop:3"])
        self.assertTrue(all(comparison_unit("toilet-paper", r)[0] == "ダブル10m" for r in alternate))

    def test_no_invented_double_from_unverified_product(self):
        singles = [item("シングル", 50, 900, 1)]
        unknown = item("ダブル", 50, 900, 2)
        unknown["name"] = "トイレットペーパー ダブル 12ロール 長さ不明"
        result = select_toilet_rankings(
            singles + [unknown], rank, lambda cid, rows: rows
        )
        self.assertEqual(result[2], [])
        self.assertEqual(result[3], "シングル10m")

    def test_double_can_be_primary_when_single_absent(self):
        doubles = [item("ダブル", 30, 900, 3)]
        _, ranked, alternate, family = select_toilet_rankings(
            doubles, rank, lambda cid, rows: rows
        )
        self.assertEqual(ranked, doubles)
        self.assertEqual(alternate, [])
        self.assertEqual(family, "ダブル10m")

    def test_group_validation_rechecks_alternatives(self):
        check = Mock(return_value=[])
        _, _, alternate, _ = select_toilet_rankings(
            [item("シングル", 100, 1000, 1), item("ダブル", 30, 900, 2)],
            rank, check
        )
        check.assert_called_once()
        self.assertEqual(alternate, [])

    def test_html_shows_verified_double_offer_and_real_affiliate_link(self):
        from improve_category_seo import toilet_ply_compare_panel, toilet_ply_availability_note
        single = item("シングル", 100, 1000, 1)
        double = item("ダブル", 60, 1100, 2)
        data = {"categories": {"toilet-paper": {
            "items": [single], "toilet_ply_offers": [double],
        }}}
        page = toilet_ply_compare_panel(data)
        self.assertIn("ダブルの比較候補（1件）", page)
        self.assertIn("¥15.28／ダブル10m", page)
        self.assertIn('href="https://item.rakuten.co.jp/shop/2/"', page)
        self.assertIn("シングルの比較を見る", page)
        self.assertEqual(toilet_ply_availability_note(data), "")

    def test_2x_longer_roll_is_not_two_ply(self):
        item_single = item("シングル", 100, 1000, 1)
        item_single["name"] += " 2倍巻き"
        self.assertEqual(len(group_toilet_offers([item_single])["ダブル10m"]), 0)


if __name__ == "__main__":
    unittest.main()
