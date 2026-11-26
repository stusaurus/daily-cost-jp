"""Regression tests for automatic admission and lookup of unregistered packages."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from marketplace_discovery import discover, source_evidence
from marketplace_finder import add_finder
from marketplace_seeds import directory_products, extend_pool
from test_marketplace_comparison import MockYahoo, PRODUCT, RAKUTEN_ITEM, RAKUTEN_URL, YAHOO_URL, rakuten, yahoo
from validate_product_quality import valid_exact_marketplace_link

JAN = PRODUCT.jan
TITLE = "花王 アタックZERO 部屋干し 詰め替え 2000g×3袋"


def listing(**changes):
    return rakuten(name=TITLE, metric="100g", jan=JAN, basis="caption_jan", unit_price=120.0,
                   review_count=5, confidence=.99, **changes)


def source(**changes):
    return dict(itemName=TITLE, itemCaption=f"JANコード：{JAN}", availability=1, postageFlag=0) | changes


def run(hits, rows=None):
    return discover({"laundry": rows or [listing()]}, {"laundry": []}, MockYahoo(hits))


class AutomaticDiscovery(unittest.TestCase):
    def test_source_requires_current_purchase_and_unambiguous_jan(self):
        self.assertEqual(source_evidence(source(), listing()), {"jan": JAN, "basis": "caption_jan"})
        for override in ({"availability": 0}, {"postageFlag": 1}, {"itemCaption": "対象品あり"},
                         {"itemCaption": f"JAN {JAN} 別製品 4901301466235"},
                         {"itemCaption": f"JAN {JAN} 沖縄は別途送料"},
                         {"itemCaption": f"JAN {JAN} 旧商品との混在あり"}):
            self.assertIsNone(source_evidence(source(**override), listing()))
        self.assertIsNone(source_evidence(source(), listing() | {"url": "https://example.test/"}))

    def test_new_pack_is_searchable_and_scoped_to_this_category(self):
        groups, reports = run([yahoo(name=TITLE)])
        rec = reports["laundry"]
        self.assertEqual(rec["outcomes"], {"matched": 1})
        self.assertEqual(rec["matched_pairs"], 1)
        self.assertEqual(groups["laundry"][0][1], 3)
        attrs = {"class": "marketplace-buy", "target": "_blank", "rel": "sponsored nofollow noopener",
                 "data-marketplace": "rakuten", "data-category-id": "laundry",
                 "href": RAKUTEN_URL, "data-marketplace-item": RAKUTEN_ITEM}
        coverage = {"laundry": {"status": "available", "discovery": rec}}
        self.assertTrue(valid_exact_marketplace_link(attrs, "categories/laundry/index.html", coverage))
        self.assertFalse(valid_exact_marketplace_link(attrs, "categories/dish/index.html", coverage))
        self.assertFalse(valid_exact_marketplace_link(attrs | {"href": RAKUTEN_URL + "&other=1"},
                                                     "categories/laundry/index.html", coverage))
        page = '<main><input id="q"><div id="status"></div></main>'
        markup = add_finder(page, groups)
        self.assertIn(f'/categories/laundry/#compare-{JAN}-3', markup)
        self.assertEqual(add_finder(markup, groups), markup)

    def test_variants_pack_counts_and_failed_offers_stay_out(self):
        for differing in (TITLE.replace("3袋", "6袋"), TITLE.replace("2000g", "2000ml"),
                          TITLE.replace("詰め替え", "本体"), TITLE.replace("部屋干し", "ドラム式"),
                          TITLE + " ローズの香り", TITLE + " 旧モデル", TITLE + " 2点"):
            groups, report = run([yahoo(name=differing)])
            self.assertFalse(groups["laundry"], differing)
            self.assertEqual(sum(report["laundry"]["outcomes"].values()), 1)
        for override in ({"inStock": False}, {"shipping": {"code": 3}},
                         {"description": "沖縄は別途送料"}, {"url": YAHOO_URL.replace("pid=200", "pid=300")}):
            self.assertFalse(run([yahoo(name=TITLE, **override)])[0]["laundry"])

    def test_cached_profiles_excluded_and_api_error_is_not_no_match(self):
        _, reports = discover({"laundry": [listing()]}, {"laundry": [PRODUCT]}, MockYahoo())
        self.assertEqual(reports["laundry"]["eligible_jans"], 0)
        _, reports = discover({"laundry": [listing()]}, {"laundry": []}, MockYahoo(fails=True))
        self.assertEqual(reports["laundry"]["api_error"], "http_503")
        self.assertEqual(reports["laundry"]["outcomes"], {})

    def test_real_directory_envelope_and_unknown_schema(self):
        row = {"productCode": JAN, "salesItemCount": 3}
        self.assertEqual(directory_products({"Products": [row]}), [row])
        self.assertEqual(directory_products({"Products": [{"Product": row}]}), [row])
        self.assertEqual(directory_products({"items": [row]}), [row])
        self.assertEqual(directory_products({"Products": []}), [])
        with self.assertRaises(ValueError):
            directory_products({"count": 30})

    def test_directory_never_authorizes_a_search_result_by_query_alone(self):
        master = {"productName": TITLE, "productCode": JAN, "salesItemCount": 7, "reviewCount": 5}
        pool = {}
        current = source()
        current.update(itemCode=RAKUTEN_ITEM)
        stats = extend_pool(pool, {"laundry": []}, directory=lambda *_: [master, master],
                            listings=lambda _: [current | {"itemCaption": "別のJAN 4901301466235"}, current],
                            normalize_item=lambda *_: listing(), categories={"laundry": {}}, pause=lambda _: None)
        self.assertEqual(stats["product_searches"], 1)
        self.assertEqual(stats["item_searches"], 1)
        self.assertEqual(len(pool["laundry"]), 1)
        self.assertEqual(pool["laundry"][0]["master_name"], TITLE)
