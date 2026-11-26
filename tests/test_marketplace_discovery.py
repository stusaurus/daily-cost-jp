"""Regression tests for automatic admission and lookup of unregistered packages."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from marketplace_discovery import discover, package_profile, source_evidence
from marketplace_finder import add_finder
from marketplace_seeds import collect_yahoo_leads, directory_products, extend_pool, select_seeds, yahoo_leads
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

    def test_yahoo_keyword_leads_require_both_stores_and_exact_package(self):
        client = MockYahoo([])
        hit = yahoo(name=TITLE)
        invalid = [hit | override for override in ({"janCode": "0000000000000"}, {"price": 0},
                   {"name": "柔軟剤 2000g"}, {"shipping": {"code": 3}}, {"description": "北海道は別途送料"},
                   {"inStock": False}, {"url": YAHOO_URL.replace("pid=200", "pid=300")})]
        self.assertEqual(yahoo_leads("laundry", invalid, client.affiliate_link), {})
        leads = {"laundry": yahoo_leads("laundry", [hit], client.affiliate_link)}
        pool = {}
        stats = extend_pool(pool, {"laundry": []}, directory=lambda *_: [], listings=lambda _: [source()],
                            normalize_item=lambda *_: listing(), categories={"laundry": {}}, pause=lambda _: None,
                            keyword_hits=leads)
        self.assertEqual(stats["categories"]["laundry"]["yahoo_only_lookups"], 1)
        self.assertEqual(pool["laundry"][0]["master_name"], "")
        groups, _ = discover(pool, {"laundry": []}, client, keyword_hits=leads)
        self.assertEqual(groups["laundry"][0][1], 3)
        self.assertFalse(discover({}, {"laundry": []}, client, keyword_hits=leads)[0]["laundry"])
        changed = MockYahoo([hit | {"inStock": False}])
        self.assertFalse(discover(pool, {"laundry": []}, changed, keyword_hits=leads)[0]["laundry"])
        wrong_pack = {"laundry": {JAN: [hit | {"name": TITLE.replace("3袋", "6袋")}]}}
        self.assertFalse(discover(pool, {"laundry": []}, client, keyword_hits=wrong_pack)[0]["laundry"])

    def test_category_keyword_budget_and_provider_failure(self):
        class Limited(MockYahoo):
            def search(self, **params):
                from yahoo_shopping import YahooUnavailable
                self.requests += 1
                if self.requests == 2:
                    raise YahooUnavailable("http_429")
                return [yahoo(name=TITLE)]
        leads, stats = collect_yahoo_leads({k: {"keyword": k} for k in ["laundry", "dish", "mask"]}, Limited(), 0)
        self.assertIn(JAN, leads["laundry"])
        self.assertEqual(stats["requests"], 2)
        self.assertEqual(stats["categories"]["dish"], {"error": "http_429"})

    def test_counted_consumables_retain_dimensions(self):
        from marketplace_offers import package_quantity
        def profile(category, title):
            return package_profile(category, listing() | {"name": title, "metric": "sheet"})
        bag = "ポリ袋 ごみ袋 45L 半透明 65x80cm 10枚x10冊"
        exact = profile("garbage-bag-45l", bag)
        self.assertEqual((exact.amount, package_quantity("garbage-bag-45l", bag, exact)), (10, 10))
        self.assertIsNone(profile("garbage-bag-45l", bag + " 70L"))
        paper = "キッチンペーパー 100枚×2ロール×8袋"
        exact = profile("kitchen-paper", paper)
        self.assertEqual((exact.amount, exact.kitchen_rolls, package_quantity("kitchen-paper", paper, exact)), (200, 2, 8))
        self.assertIsNone(package_quantity("kitchen-paper", paper.replace("100枚×2", "50枚×4"), exact))
        self.assertIsNone(package_profile("dish", listing() | {
            "name": "ペット用食器洗剤 詰め替え用 400ml", "metric": "100ml"}))

    def test_real_directory_envelope_and_unknown_schema(self):
        row = {"productCode": JAN, "salesItemCount": 3}
        self.assertEqual(directory_products({"Products": [row]}), [row])
        self.assertEqual(directory_products({"Products": [{"Product": row}]}), [row])
        self.assertEqual(directory_products({"items": [row]}), [row])
        self.assertEqual(directory_products({"Products": []}), [])
        self.assertEqual(directory_products({"count": 0}), [])
        with self.assertRaises(ValueError):
            directory_products({"count": 30})

    def test_rotates_new_candidates_without_reusing_a_prior_offer(self):
        seeds = [{"jan": str(i), "name": str(i), "brand": ""} for i in range(15)]
        first = select_seeds(seeds, {JAN}, 6, 0)
        second = select_seeds(seeds, {JAN}, 6, 1)
        self.assertEqual(first[0], {"jan": JAN, "name": "", "brand": ""})
        self.assertEqual(len(first), 6)
        self.assertNotEqual(first, second)
        self.assertEqual(first[:3], second[:3])

    def test_category_schema_error_preserves_other_categories(self):
        def directory(config, page):
            if config == "first":
                raise ValueError("product_directory_schema")
            return []
        result = extend_pool({}, {"laundry": [], "dish": []}, directory=directory,
                             listings=lambda _: [], normalize_item=lambda *_: {},
                             categories={"laundry": "first", "dish": "second"}, pause=lambda _: None)
        self.assertEqual(result["categories"]["laundry"]["error"], "ValueError")
        self.assertIn("dish", result["categories"])
        self.assertNotIn("stopped", result)

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
