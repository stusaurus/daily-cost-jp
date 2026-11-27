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

    def test_unmatched_jan_diagnostics_are_bounded_and_do_not_reuse_offers(self):
        wrong = yahoo(name=TITLE + " ローズの香り")
        groups, reports = run([wrong])
        report = reports["laundry"]
        self.assertFalse(groups["laundry"])
        self.assertEqual(report["unmatched_jans"], [{
            "jan": JAN, "outcome": "needs_review", "rakuten_rows": 1,
            "yahoo_hits": 1, "reasons": {"variant_needs_review": 1},
        }])
        self.assertEqual(report["outcomes"], {"needs_review": 1})
        _, missing = run([])
        self.assertEqual(missing["laundry"]["unmatched_jans"], [{
            "jan": JAN, "outcome": "no_yahoo_hits", "rakuten_rows": 1,
            "yahoo_hits": 0, "reasons": {"no_yahoo_hits": 1},
        }])
        _, matched = run([yahoo(name=TITLE)])
        self.assertEqual(matched["laundry"]["unmatched_jans"], [])
        _, failed = discover({"laundry": [listing()]}, {"laundry": []}, MockYahoo(fails=True))
        self.assertEqual(failed["laundry"]["unmatched_jans"], [])
        _, bounded = discover({"laundry": [listing()]}, {"laundry": []}, MockYahoo([]), budget=0)
        self.assertEqual(bounded["laundry"]["unmatched_jans"], [])

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

    def test_rakuten_limit_suppresses_further_exact_fetches_and_directory_queries(self):
        from datetime import datetime, timezone
        import json
        import tempfile
        from unittest.mock import Mock, patch
        from marketplace_comparison import apply, EXACT_RAKUTEN_CATEGORIES
        keys = sorted(EXACT_RAKUTEN_CATEGORIES)[:2]
        now = datetime.now(timezone.utc)
        catalog = {"updated_at": now.isoformat(), "categories": {k: {"items": []} for k in keys}}
        fetch = Mock(return_value=([], "http_429"))
        with tempfile.TemporaryDirectory() as work:
            site = Path(work) / "site"
            site.mkdir()
            (site / "data.json").write_text(json.dumps(catalog))
            (site.parent / "marketplace-discovery-input.json").write_text(json.dumps(catalog | {
                "categories": {k: [] for k in keys}}))
            with patch.dict("os.environ", dict.fromkeys(
                    ["RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID"], "test")), \
                    patch("marketplace_seeds.extend_current") as extra, \
                    patch("price_observations.fetch_public") as prior:
                from zoneinfo import ZoneInfo
                day = now.astimezone(ZoneInfo("Asia/Tokyo")).date().toordinal()
                prior.return_value = {
                    "catalog_updated_at": now.isoformat(),
                    "categories": {k: {"discovery": {"sources": [{"jan": JAN}]}} for k in keys},
                    "api": {"directory": {"categories": {k: {"lookup_days": {JAN: day}} for k in keys}}},
                }
                result = apply(site, now=now, include={k: [] for k in keys}, exact_refresh=fetch, client=MockYahoo([]))
                prior.assert_called_once_with("marketplace-coverage.json")
                for key in keys:
                    retained = result["api"]["directory"]["categories"][key]
                    self.assertEqual(retained["lookup_days"], {JAN: day})
                    self.assertEqual(retained["prior_match_days"], {JAN: day})
                    self.assertEqual(retained["status"], "not_processed")
                    self.assertEqual(retained["verified_rows"], 0)
        fetch.assert_called_once()
        extra.assert_not_called()
        self.assertEqual(result["api"]["rakuten_limit"], "http_429")
        self.assertTrue(all(r["rakuten_exact_status"] == "http_429" for r in result["categories"].values()))

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

    def test_structured_jan_field_requires_one_current_catalog_number(self):
        caption = f"<table><tr><th>JANコード</th><td>{JAN}</td></tr></table>"
        self.assertEqual(source_evidence(source(itemCaption=caption), listing())["jan"], JAN)
        for invalid in [caption.replace("JANコード", "店舗管理番号"),
                        caption.replace("</th>", "</th><td>別製品</td>"),
                        caption + " JAN：4901301466235"]:
            self.assertIsNone(source_evidence(source(itemCaption=invalid), listing()))

    def test_master_maker_can_accompany_a_full_product_name_but_never_mask_a_variant(self):
        master = "テストシリーズ 部屋干し 詰替 2000g"
        retail = "花王 " + master + " 衣料用洗剤 ×3袋"
        other = "衣料用洗剤 テストシリーズ 部屋干し リフィル 2000g×3袋"
        row = listing() | {"name": retail, "master_name": master, "master_maker": "花王"}
        groups, _ = run([yahoo(name=other)], [row])
        self.assertEqual(len(groups["laundry"]), 1)
        for wrong in [other.replace("部屋干し", "無香料"), other + " ローズ", other.replace("3袋", "2袋"),
                      other.replace("リフィル", "本体"), other + " 他社製", other.replace("衣料用洗剤", "台所用洗剤")]:
            self.assertFalse(run([yahoo(name=wrong)], [row])[0]["laundry"], wrong)

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

    def test_lookup_history_prioritizes_winners_and_previously_unsearched_jans(self):
        other = "4901301466235"
        seeds = [{"jan": jan, "name": "商品", "brand": ""} for jan in [JAN, other, "next1", "next2", "next3"]]
        selected = select_seeds(seeds, {JAN}, 4, 0, {other: 1, JAN: 1})
        self.assertEqual([seed["jan"] for seed in selected], [JAN, "next1", "next2", "next3"])

    def test_underserved_category_extra_query_and_bounded_history(self):
        from unittest.mock import Mock
        directory = Mock(side_effect=[[], [{"productCode": JAN, "productName": TITLE, "salesItemCount": 7}]])
        result = extend_pool({}, {"laundry": []}, directory=directory, listings=lambda _: [],
                             normalize_item=lambda *_: {}, categories={"laundry": {"name": "洗濯洗剤"}},
                             pause=lambda _: None, day=10, coverage={"laundry": 2},
                             history={"laundry": {"4901301466235": 6}})
        self.assertEqual(result["product_searches"], 2)
        self.assertEqual(result["item_searches"], 1)
        self.assertEqual(result["categories"]["laundry"]["lookup_days"], {JAN: 10})
        self.assertNotEqual(directory.call_args_list[0], directory.call_args_list[1])

    def test_previously_missing_product_must_be_reacquired_and_old_history_expires(self):
        from unittest.mock import Mock
        search = Mock(return_value=[])
        pool = {}
        stats = extend_pool(pool, {"laundry": []}, directory=lambda *_: [], listings=search,
                            categories={"laundry": {}}, normalize_item=lambda *_: listing(), pause=lambda _: None,
                            confirmed={"laundry": {JAN: 9, "4901301466235": 1}}, day=10)
        self.assertEqual(stats["categories"]["laundry"]["prior_match_days"], {JAN: 9})
        self.assertEqual(stats["categories"]["laundry"]["recovery_lookups"], 1)
        search.assert_called_once_with(JAN)
        self.assertEqual(pool["laundry"], [])
        search.reset_mock()
        extend_pool(pool, {"laundry": []}, directory=lambda *_: [], listings=search,
                    categories={"laundry": {}}, normalize_item=lambda *_: listing(), pause=lambda _: None,
                    confirmed={"laundry": {JAN: 9}}, history={"laundry": {JAN: 10}}, day=10)
        search.assert_not_called()

    def test_rate_limit_preserves_unprocessed_category_history_without_offers(self):
        from urllib.error import HTTPError
        from unittest.mock import Mock
        directory = Mock(side_effect=HTTPError("https://example.test", 429, "limit", {}, None))
        listings = Mock()
        pool = {}
        info = extend_pool(pool, {"laundry": [], "dish": []}, directory=directory,
                           listings=listings, normalize_item=lambda *_: listing(),
                           categories={"laundry": {}, "dish": {}}, pause=lambda _: None,
                           day=10, history={"dish": {JAN: 9, "4901301466235": 7}},
                           confirmed={"dish": {JAN: 6, "4901301466235": 3}})
        self.assertEqual(info["stopped"], "http_429")
        directory.assert_called_once()
        listings.assert_not_called()
        skipped = info["categories"]["dish"]
        self.assertEqual(skipped["status"], "not_processed")
        self.assertEqual(skipped["lookup_days"], {JAN: 9})
        self.assertEqual(skipped["prior_match_days"], {JAN: 6})
        self.assertEqual(skipped["verified_rows"], 0)
        self.assertNotIn("dish", pool)

    def test_priority_retail_search_replaces_speculation_and_binds_each_item_to_its_jan(self):
        from unittest.mock import Mock
        other = "4901301466235"
        directory = Mock(return_value=[{"productCode": other, "productName": "ティシュー", "salesItemCount": 4}])
        listings = Mock(return_value=[])
        name = "日本製紙クレシア スコッティ ティシュー 200組 5箱パック"
        jan = "4901750417352"
        retail = Mock(return_value=[source(itemName=name, itemCaption=f"JANコード：{jan}")])
        row = listing() | {"name": name, "metric": "box", "price": 1500, "unit_price": 300}
        pool = {}
        result = extend_pool(pool, {"tissue": []}, directory=directory, listings=listings, retail=retail,
                             normalize_item=lambda *_: row, categories={"tissue": {"name": "ティッシュ"}},
                             previous={"tissue": {JAN}}, coverage={"tissue": 1}, pause=lambda _: None)
        self.assertEqual(result["item_searches"], 2)
        self.assertEqual(directory.call_args_list[0].args[0]["name"], "箱 ティシュー")
        self.assertEqual(directory.call_args_list[1].args[0]["name"], "スコッティ ティシュー")
        listings.assert_called_once_with(JAN)
        retail.assert_called_once_with("ティシュー 5箱 200組")
        self.assertEqual(result["categories"]["tissue"]["retail_keyword_verified"], 1)
        self.assertEqual(pool["tissue"][0]["jan"], jan)
        self.assertEqual(pool["tissue"][0]["master_name"], "")

    def test_verified_spelling_keeps_physical_and_variant_evidence(self):
        from marketplace_discovery import comparable_names
        from marketplace_offers import package_quantity
        from product_quality import category_rejection, parsed_quantity
        tissue = "スコッティ ティシュー 400枚 (200組) 5箱パック"
        profile = package_profile("tissue", listing() | {"name": tissue, "metric": "box"})
        self.assertEqual(package_quantity("tissue", tissue.replace("ティシュー", "ティッシュ"), profile), 1)
        self.assertIsNone(package_quantity("tissue", tissue.replace("400枚", "300枚"), profile))
        self.assertIsNone(package_quantity("tissue", tissue.replace("5箱", "3箱"), profile))
        self.assertFalse(comparable_names("4列 歯ブラシ 1本 ふつう", "3列 ハブラシ 1本 ふつう", JAN, "", "toothbrush"))
        self.assertTrue(comparable_names("4列 歯ブラシ 1本 ふつう", "4列 ハブラシ 1本 ふつう", JAN, "", "toothbrush"))
        coffee = "レギュラーコーヒー 中細挽き 280g"
        self.assertIsNone(category_rejection("coffee", coffee))
        self.assertIsNotNone(category_rejection("coffee", coffee + " ドリップバッグ"))

        sink = "ケース販売 水切りネット ブルー 排水口用 2000枚(50枚×40冊) 台所"
        profile = package_profile("sink-net", listing() | {"name": sink, "metric": "sheet"})
        self.assertEqual(package_quantity("sink-net", sink.replace("冊", "袋"), profile), 40)
        self.assertIsNone(package_quantity("sink-net", sink.replace("2000枚", "2400枚"), profile))
        self.assertIsNotNone(category_rejection("sink-net", sink + " ホルダー付き"))

        paper = "エリエール キッチンタオル 無漂白 50カット 48ロール（2ロール×24パック）"
        profile = package_profile("kitchen-paper", listing() | {"name": paper, "metric": "sheet"})
        self.assertEqual(parsed_quantity("kitchen-paper", paper)["quantity"], 2400)
        self.assertEqual(package_quantity("kitchen-paper", paper, profile), 24)
        self.assertIsNone(package_quantity("kitchen-paper", paper.replace("48ロール", "40ロール"), profile))
        self.assertIsNone(package_quantity("kitchen-paper", paper + " 2ケース", profile))
        self.assertIsNone(package_quantity("kitchen-paper", paper.replace("2ロール×24", "4ロール×12"), profile))
        self.assertFalse(comparable_names(paper + " 1枚重ね", paper + " 2枚重ね", JAN, "", "kitchen-paper"))

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
