"""STEP 4-A fail-closed purchase-fit audit regressions (no network / no writes)."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import step4_purchase_audit as a


NOW = dt.datetime(2026, 10, 11, 5, tzinfo=dt.timezone.utc)


def offer(category="tissue", qty=5, metric="box", unit_price=100, suffix="1", title=None):
    if title is None:
        title = f"ボックスティッシュ 200組 {qty}箱" if category == "tissue" else (
            f"トイレットペーパー {qty}ロール" if category == "toilet-paper"
            else f"洗濯洗剤 {qty*100}ml")
    return {
        "name": title, "price": qty * unit_price, "unit_price": unit_price,
        "metric": metric, "confidence": .99, "postage": "送料込み",
        "url": f"https://item.rakuten.co.jp/shop/{suffix}/",
        "item_code": f"shop:{suffix}",
    }


def snapshot(categories):
    return {"source": "Rakuten Ichiba API", "ranking_basis": "shipping_included_unit_price",
            "updated_at": "2026-10-11T12:00:00+09:00", "categories": categories}


class PurchaseFitTests(unittest.TestCase):
    def test_5_boxes_times_12_is_60_not_five(self):
        bulk = offer(qty=60, unit_price=70, suffix="bulk",
                     title="ボックスティッシュ 200組 5箱×12パック")
        r = a.inspect_category("tissue", {"items": [bulk]})
        p = r["offers"][0]
        self.assertEqual(p["status"], "VERIFIED")
        self.assertEqual(p["quantity"], 60)
        self.assertEqual(p["size_band"], "BULK")
        self.assertIn("NO_VERIFIED_HOUSEHOLD_SIZE_IN_SNAPSHOT", r["codes"])

    def test_bulk_unit_ranking_untouched_small_separate(self):
        bulk = offer(qty=60, unit_price=70, suffix="bulk",
                     title="ボックスティッシュ 200組 5箱×12パック")
        small = offer(qty=5, unit_price=100, suffix="small")
        original = {"items": [bulk], "small_pack_offer": small, "metric": "box"}
        before = copy.deepcopy(original)
        r = a.inspect_category("tissue", original)
        self.assertEqual(original, before)
        self.assertEqual(r["offers"][0]["size_band"], "BULK")
        self.assertEqual(r["offers"][1]["size_band"], "SMALL")
        self.assertEqual(r["offers"][1]["source"], "TISSUE_SMALL_SUPPLEMENT")
        self.assertEqual(r["coverage"]["small"], 1)
        self.assertEqual(r["recommendation_action"], "READ_ONLY_INVESTIGATE")

    def test_detergent_six_pack_cannot_fill_small(self):
        six = offer("laundry", qty=30, metric="100ml", suffix="6",
                    title="洗濯洗剤 500ml×6本")
        r = a.inspect_category("laundry", {"items": [six]})
        self.assertEqual(r["offers"][0]["quantity"], 30)
        self.assertNotEqual(r["offers"][0]["size_band"], "SMALL")
        self.assertEqual(r["coverage"]["small"], 0)
        self.assertIn("NO_VERIFIED_SMALL_SIZE_IN_SNAPSHOT", r["codes"])

    def test_duplicate_offer_cannot_masquerade_as_three_choices(self):
        row = offer()
        r = a.inspect_category("tissue", {"items": [row, dict(row), dict(row)]})
        self.assertEqual(r["coverage"]["verified_offers"], 1)
        self.assertEqual(r["coverage"]["distinct_item_codes"], 1)
        self.assertEqual(sum("DUPLICATE_OFFER_ID" in p["codes"] for p in r["offers"]), 2)

    def test_shipping_variant_quantity_metric_id_and_price_fail_closed(self):
        base = offer()
        bad = []
        for field, value in (
            ("postage", "送料別"),
            ("postage", "送料は商品ページで確認"),
            ("metric", "pack"),
            ("url", "https://bad.example/buy"),
            ("price", 1),
            ("unit_price", 0),
            ("confidence", 0.5),
        ):
            item = dict(base)
            item[field] = value
            item["item_code"] = "shop:" + field + str(value)
            bad.append(item)
        for name in ("ボックスティッシュ 5箱〜60箱から選べる",
                     "ボックスティッシュ 5箱 10ロール",
                     "ボックスティッシュ 容量不明"):
            item = dict(base)
            item["name"] = name
            item["item_code"] = "shop:" + name
            bad.append(item)
        for item in bad:
            with self.subTest(item=item):
                r = a.inspect_category("tissue", {"items": [item]})
                self.assertEqual(r["coverage"]["verified_offers"], 0)
                self.assertEqual(r["offers"][0]["status"], "REJECTED")

    def test_no_candidates_do_not_invent_offers_or_price(self):
        empty = a.inspect_category("tissue", {"items": []})
        self.assertEqual(empty["status"], "NO_VERIFIED_OFFERS")
        self.assertEqual(empty["coverage"]["verified_offers"], 0)
        self.assertEqual(empty["offers"], [])
        unknown = a.inspect_category("tissue", {"items": [], "error": "API error"})
        self.assertEqual(unknown["status"], "UNAVAILABLE")
        self.assertIsNone(unknown["coverage"])
        self.assertIsNone(unknown["reject_reasons"])

    def test_missing_malformed_and_expired_snapshots_are_not_zero(self):
        for value in (None, {}, {"source": "Unknown", "categories": {}},
                      {**snapshot({}), "updated_at": "2020-01-01T00:00:00+00:00"},
                      {**snapshot({}), "updated_at": "2050-01-01T00:00:00+00:00"}):
            with self.subTest(value=value):
                r = a.inspect(value, now=NOW)
                self.assertNotEqual(r["status"], "TRUSTED_RECENT")
                self.assertEqual(r["categories"], {})
                self.assertEqual(r["recommendation_changes"], "NONE")

    def test_missing_category_is_partial_not_healthy(self):
        r = a.inspect(snapshot({"tissue": {"items": [offer()]}}), now=NOW)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(r["categories"]["tissue"]["coverage"]["small"], 1)
        self.assertIsNone(r["categories"]["laundry"]["coverage"])

    def test_wrong_source_and_purchase_claims_remain_unavailable(self):
        r = a.inspect(snapshot({}), now=NOW)
        self.assertEqual(r["real_user_conversion_status"], "NOT_EVALUATED")
        self.assertEqual(r["affiliate_sales_status"], "NOT_CONNECTED")
        self.assertEqual(r["search_price_failure_breakdown"], "NOT_IN_PUBLISHED_SNAPSHOT")
        self.assertEqual(r["brand_request_match"], "NOT_EVALUATED_WITHOUT_EXPLICIT_BRAND_REQUEST")
        self.assertFalse(r["published_changes"])
        self.assertNotIn("実売上: ¥", a.markdown(r))

    def test_report_never_includes_raw_product_name_or_affiliate_url(self):
        r = a.inspect(snapshot({"tissue": {"items": [offer()]}}), now=NOW)
        raw = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("ボックスティッシュ 200組", raw)
        self.assertNotIn("https://item.rakuten.co.jp/shop/1/", raw)
        self.assertIn("price_total_yen", raw)

    def test_no_band_guess_for_other_categories(self):
        self.assertEqual(a.band_for("dish", "100ml", 2), "UNKNOWN")
        self.assertEqual(a.band_for("tissue", "pack", 5), "UNKNOWN")
        self.assertEqual(a.band_for("tissue", "box", None), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
