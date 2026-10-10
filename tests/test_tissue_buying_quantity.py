"""Strict quantity-selection tests; never convert 60 boxes into a 5-box offer."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tissue_buying_quantity import safe_box_count, choose_small_tissue_offer, small_offer_snapshot
from candidate_acquisition import acquire, SUPPLEMENTAL_QUERIES
from product_quality import filter_items
from improve_purchase_pages import tissue_size_guide
from validate_product_quality import validate_catalog


def box_offer(index=1, boxes=5, unit=100):
    title = f"ボックスティッシュ 200組 {boxes}箱"
    return {
        "name": title, "price": boxes * unit, "unit_price": unit,
        "metric": "box", "confidence": 0.99, "postage": "送料込み",
        "url": f"https://item.rakuten.co.jp/shop/{index}/",
        "item_code": f"shop:{index}", "shop": "確認済みショップ",
        "review_count": 0, "review_average": 0, "image": "",
        "evidence": f"{boxes}箱",
    }


def bulk_offer(index=1):
    offer = box_offer(index, boxes=60, unit=70 + index)
    offer["name"] = "ボックスティッシュ 200組 5箱×12パック"
    return offer


def rank(rows):
    return "box", sorted(rows, key=lambda x: x["unit_price"])[:12]


class TissueQuantityTests(unittest.TestCase):
    def test_five_box_candidate_is_verified_against_price_and_title(self):
        row = box_offer()
        self.assertEqual(safe_box_count(row), 5)
        selected = choose_small_tissue_offer([row])
        self.assertEqual(selected["url"], row["url"])
        self.assertEqual(selected["price"], row["price"])
        self.assertEqual(selected["category_id"], "tissue")

    def test_bulk_5_times_12_is_not_falsely_treated_as_five_boxes(self):
        self.assertIsNone(safe_box_count(bulk_offer()))
        self.assertIsNone(choose_small_tissue_offer([bulk_offer()]))

    def test_quantity_price_mismatch_not_allowed(self):
        row = box_offer()
        row["price"] = 99
        self.assertIsNone(safe_box_count(row))
        self.assertIsNone(choose_small_tissue_offer([row]))

    def test_shipment_and_selection_ambiguity_are_rejected(self):
        row = box_offer()
        row["postage"] = "送料別"
        self.assertIsNone(safe_box_count(row))
        row = box_offer()
        row["name"] = "ボックスティッシュ 200組 5箱〜60箱から選べる"
        self.assertIsNone(safe_box_count(row))
        row = box_offer()
        row["url"] = "https://bad.example/item"
        self.assertIsNone(safe_box_count(row))

    def test_pack_metric_is_not_treated_as_box_quantity(self):
        row = box_offer()
        row["metric"] = "pack"
        self.assertIsNone(safe_box_count(row))

    def test_selects_verified_lowest_unit_price_not_first_listed(self):
        items = [box_offer(1, 5, 120), box_offer(2, 10, 90), bulk_offer(3)]
        self.assertEqual(choose_small_tissue_offer(items)["item_code"], "shop:2")
        self.assertEqual(small_offer_snapshot(items)["boxes"], 10)

    def test_no_offer_is_explicit_and_never_fabricates_price(self):
        s = small_offer_snapshot([bulk_offer()])
        self.assertEqual(s["status"], "NO_VERIFIED_SMALL_OFFER")
        self.assertIsNone(s["offer"])
        rendered = tissue_size_guide({"small_pack_offer": None})
        self.assertIn("候補がありません", rendered)
        self.assertIn("../../products/?q=", rendered)
        self.assertNotIn("楽天でこの商品の価格・数量を確認", rendered)

    def test_verified_direct_link_is_not_a_fake_marketwide_cheapest_claim(self):
        offer = box_offer()
        rendered = tissue_size_guide({"small_pack_offer": offer})
        self.assertIn("5箱・支払総額 ¥500", rendered)
        self.assertIn("100組", rendered)
        self.assertIn(offer["url"], rendered)
        self.assertIn('data-conversion-source="category"', rendered)
        self.assertIn("最安値は保証しません", rendered)
        self.assertNotIn("5箱・支払総額 ¥3,980", rendered)

    def test_snapshot_cannot_import_unsafe_offer_into_catalog(self):
        other = box_offer(9)
        other["postage"] = "送料別"
        safe = box_offer(2)
        fixture = {"categories": {
            "tissue": {"items": [bulk_offer()], "metric": "box",
                       "small_pack_offer": other, "small_pack_boxes": 5}
        }}
        errors, accepted = validate_catalog(fixture)
        self.assertIn("tissue: unsafe small-pack offer", errors)
        self.assertNotIn(other["url"], accepted["tissue"])
        fixture["categories"]["tissue"]["small_pack_offer"] = safe
        errors, accepted = validate_catalog(fixture)
        self.assertNotIn("tissue: unsafe small-pack offer", errors)
        self.assertIn(safe["url"], accepted["tissue"])

    def test_tissue_triggers_one_optional_small_pack_lookup_if_bulk_sufficient(self):
        bulky = [bulk_offer(n) for n in range(1, 6)]
        small = box_offer(10)
        fetch = Mock(side_effect=[bulky, [small]])
        rows, report = acquire(
            {"id": "tissue", "keyword": "ティッシュ"}, fetch,
            lambda x, category: x, rank, Mock()
        )
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(report["baseline"]["ranked"], 5)
        self.assertEqual(fetch.call_args_list[1].args[0]["keyword"], SUPPLEMENTAL_QUERIES["tissue"][0])
        self.assertEqual(choose_small_tissue_offer(rows)["item_code"], small["item_code"])
        self.assertTrue(report["requests"][-1]["supplementary"])

    def test_tissue_with_existing_small_offer_does_not_spend_another_api_call(self):
        offer = [box_offer(1)] + [bulk_offer(n) for n in range(2, 6)]
        fetch = Mock(return_value=offer)
        rows, report = acquire(
            {"id": "tissue", "keyword": "ティッシュ"}, fetch,
            lambda x, category: x, rank, Mock()
        )
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(report["requests"]), 1)

    def test_optional_small_lookup_failure_keeps_original_safe_bulk(self):
        bulk = [bulk_offer(n) for n in range(1, 6)]
        fetch = Mock(side_effect=[bulk, TimeoutError()])
        rows, report = acquire(
            {"id": "tissue", "keyword": "ティッシュ"}, fetch,
            lambda x, category: x, rank, Mock()
        )
        self.assertEqual(len(rows), 5)
        self.assertEqual(report["requests"][-1]["error"], "TimeoutError")
        self.assertIsNone(choose_small_tissue_offer(rows))


if __name__ == "__main__":
    unittest.main()
