"""Safe alternative for everyday laundry: stronger unit price without bulk spend."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_step4_purchase_audit import offer, snapshot
from step4_recommendations import select_category, block, apply
from buying_decision_summary import render
from validate_product_quality import Links, verified_purpose_links, valid_everyday_value_link


def catalog():
    bulk = offer("laundry", 89.4, "100g", unit_price=7980 / 89.4,
                 suffix="bulk", title="さらさ 洗濯洗剤 1490g×6袋")
    bulk["price"] = 7980
    small = offer("laundry", 8.5, "100g", unit_price=897 / 8.5,
                  suffix="small", title="アタック 洗濯洗剤 850g")
    small["price"] = 897
    everyday = offer("laundry", 15.9, "100g", unit_price=1528 / 15.9,
                     suffix="everyday", title="アタック 洗濯洗剤 1590g")
    everyday["price"] = 1528
    alternative = offer("laundry", 27.7, "100g", unit_price=2100 / 27.7,
                        suffix="value", title="アタック 洗濯洗剤 2770g")
    alternative["price"] = 2100
    for item in (bulk, small, everyday, alternative):
        item["shop"] = "テスト販売店"
    return {"items": [bulk], "purpose_candidates": [small, everyday, alternative]}


def ranked_html(category):
    item = category["items"][0]
    return (
        '<article class="product-card" id="laundry-rank-1">'
        f'<span class="lab-price-value">¥{item["unit_price"]:.2f}</span>'
        '<span class="lab-price-unit">／100g</span>'
        '<p class="purchase-summary">6袋</p>'
        f'<a class="buy-button" href="{item["url"]}" '
        f'data-shipping-price="{item["price"]}">購入条件</a></article>'
    )


class LaundryEverydayValueChoiceTests(unittest.TestCase):
    def test_existing_three_choices_remain_and_value_choice_is_valid(self):
        source = catalog()
        before = copy.deepcopy(source)
        result = select_category("laundry", source)
        self.assertEqual(source, before)
        self.assertEqual(set(result["slots"]), {"small", "everyday", "bulk"})
        self.assertEqual(result["slots"]["small"]["offer"]["price"], 897)
        self.assertEqual(result["slots"]["everyday"]["offer"]["price"], 1528)
        self.assertEqual(result["slots"]["bulk"]["offer"]["price"], 7980)
        value = result["everyday_value"]
        self.assertEqual(value["offer"]["price"], 2100)
        self.assertEqual(value["unit"][0], "100g")
        self.assertLess(value["unit"][1], result["slots"]["bulk"]["unit"][1])

        html = block("laundry", result, "洗濯洗剤")
        doc = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(doc.select("article.step4-purpose")), 3)
        entry = doc.select_one("#laundry-purpose-everyday-value")
        self.assertIsNotNone(entry)
        link = entry.select_one("a.buy-button")
        self.assertEqual(link["href"], value["offer"]["url"])
        self.assertEqual(link["data-shipping-price"], "2100")
        self.assertEqual(link["data-id"], value["spec_ref"])
        self.assertEqual(link["data-purchase-purpose"], "everyday-value")
        self.assertIn("¥2,100", entry.get_text())

        decision = BeautifulSoup(render(ranked_html(source) + html, source, "laundry"), "html.parser")
        targets = [x["data-decision-target"] for x in decision.select("tbody tr")]
        self.assertEqual(targets, ["laundry-purpose-small", "laundry-purpose-everyday-value"])
        self.assertIn("¥75.81", decision.get_text())

    def test_no_promotion_of_untrusted_or_not_materially_better_candidate(self):
        changes = (
            {"postage": "送料不明"},
            {"url": "https://example.com/fake"},
            {"unit_price": 94.0},
            {"price": 2600},
            {"name": "業務用 洗濯洗剤 2770g"},
            {"metric": "100ml"},
        )
        for edit in changes:
            with self.subTest(edit=edit):
                source = catalog()
                source["purpose_candidates"][2].update(edit)
                result = select_category("laundry", source)
                self.assertIsNone(result.get("everyday_value"))
                rendered = block("laundry", result, "洗濯洗剤")
                self.assertNotIn("laundry-purpose-everyday-value", rendered)

    def test_rank_only_low_unit_offer_cannot_be_unverified_extra_cta(self):
        source = catalog()
        ranked_extra = offer("laundry", 25.5, "100g", unit_price=60.0,
                             suffix="rank_only", title="アタック 洗濯洗剤 2550g")
        ranked_extra["price"] = 1530
        ranked_extra["shop"] = "テスト販売店"
        source["items"].append(ranked_extra)
        result = select_category("laundry", source)
        # The ranked-only offer can be seen in the regular ranking but is not
        # automatically authorized as an extra STEP5 acquisition link.
        self.assertEqual(result["everyday_value"]["offer"]["item_code"], "shop:value")
        source["purpose_candidates"] = source["purpose_candidates"][:2]
        result_without_pool = select_category("laundry", source)
        self.assertNotIn("everyday_value", result_without_pool)

    def test_no_candidate_from_unpublished_markup_enters_decision(self):
        source = catalog()
        html = ranked_html(source)
        self.assertNotIn("everyday-value", render(html, source, "laundry"))
        rendered = block("laundry", select_category("laundry", source), "洗濯洗剤")
        # An altered URL does not receive approval merely by appearing in HTML.
        bad = rendered.replace("https://item.rakuten.co.jp/shop/value/",
                               "https://example.com/mismatched/")
        decision = BeautifulSoup(render(html + bad, source, "laundry"), "html.parser")
        self.assertNotIn("laundry-purpose-everyday-value",
                         [x["data-decision-target"] for x in decision.select("tbody tr")])

    def test_public_anonymous_report_never_contains_extra_raw_offer(self):
        source = catalog()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data.json").write_text(
                json.dumps(snapshot({"laundry": source}), ensure_ascii=False), encoding="utf-8"
            )
            with patch("step4_recommendations.verify_snapshot", return_value="TRUSTED_RECENT"):
                apply(root, enabled=False)
            public = (root / "purchase-recommendations.json").read_text(encoding="utf-8")
            parsed = json.loads(public)
            self.assertEqual(parsed["categories"]["laundry"]["everyday_value"]["price_total_yen"], 2100)
            self.assertNotIn("item.rakuten.co.jp", public)
            self.assertNotIn("shop:value", public)
            self.assertNotIn("アタック 洗濯洗剤", public)

    def test_step5_publish_allowlist_checks_exact_extra_link_and_forgery(self):
        source = catalog()
        payload = {"categories": {"laundry": source}}
        choice = select_category("laundry", source)["everyday_value"]
        self.assertIn(
            (choice["offer"]["url"], "laundry", "everyday-value"),
            verified_purpose_links(payload)
        )
        parsed = Links()
        parsed.feed(block("laundry", select_category("laundry", source), "洗濯洗剤"))
        self.assertEqual(len(parsed.everyday_value_links), 1)
        attrs = parsed.everyday_value_links[0]
        self.assertTrue(valid_everyday_value_link(attrs, "index.html", payload))
        self.assertTrue(valid_everyday_value_link(attrs, "categories/laundry/index.html", payload))
        self.assertFalse(valid_everyday_value_link(attrs, "categories/tissue/index.html", payload))
        for key, bad in (
            ("href", "https://item.rakuten.co.jp/shop/wrong/"),
            ("data-category-id", "tissue"),
            ("data-id", "wrong-spec"),
            ("data-shipping-price", "1"),
            ("data-conversion-source", "other"),
            ("rel", "noopener"),
            ("target", "_self"),
        ):
            with self.subTest(key=key):
                self.assertFalse(valid_everyday_value_link({**attrs, key: bad}, "index.html", payload))
        self.assertFalse(valid_everyday_value_link(attrs, "index.html", {"categories": {"laundry": {"items": []}}}))

    def test_volume_metric_never_mislabels_100ml_as_100g(self):
        source = catalog()
        for row in source["items"] + source["purpose_candidates"]:
            row["metric"] = "100ml"
            row["name"] = row["name"].replace("g×", "ml×").replace("g", "ml")
        result = select_category("laundry", source)
        self.assertEqual(result["everyday_value"]["unit"][0], "100ml")
        html = block("laundry", result, "洗濯洗剤")
        entry = BeautifulSoup(html, "html.parser").select_one("#laundry-purpose-everyday-value")
        self.assertIn("100mlあたり", entry.get_text())
        self.assertNotIn("100gあたり", entry.get_text())

    def test_non_laundry_categories_keep_three_purpose_slots_only(self):
        tissue = {"items": [offer("tissue", 60, "box", 70, "bulk",
                                 title="ボックスティッシュ 200組 5箱×12パック")]}
        result = select_category("tissue", tissue)
        self.assertEqual(set(result["slots"]), {"small", "everyday", "bulk"})
        self.assertNotIn("everyday_value", result)
        self.assertNotIn("everyday-value", block("tissue", result, "ティッシュ"))


if __name__ == "__main__":
    unittest.main()
