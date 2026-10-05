import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "fishing_export",
    ROOT/"scripts"/"export_sotojitaku_fishing.py"
)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class FishingExportTest(unittest.TestCase):
    def setUp(self):
        self.seed={
            "itemUrl":"https://item.rakuten.co.jp/shop-a/old-item/",
            "identityGroups":[["ダイワ","DAIWA"],["240C"]],
            "forbiddenTerms":["中古"],
        }

    def test_identity_requires_every_group(self):
        self.assertTrue(mod.identity_ok("DAIWA フィッシュホルダー 240C",self.seed))
        self.assertFalse(mod.identity_ok("DAIWA フィッシュホルダー",self.seed))

    def test_forbidden_term_rejects_candidate(self):
        self.assertFalse(mod.identity_ok("中古 DAIWA フィッシュホルダー 240C",self.seed))

    def test_canonical_affiliate_target(self):
        item="https://item.rakuten.co.jp/shop-a/new-item/"
        aff="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(item,safe="")
        self.assertTrue(mod.safe_affiliate(aff,item))

    def test_other_shop_target_is_rejected(self):
        item="https://item.rakuten.co.jp/shop-a/new-item/"
        other="https://item.rakuten.co.jp/shop-b/new-item/"
        aff="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(other,safe="")
        self.assertFalse(mod.safe_affiliate(aff,item))

    def test_shop_parser(self):
        self.assertEqual(mod.rakuten_shop("https://item.rakuten.co.jp/shop-a/item/"),"shop-a")

    def test_numeric_term_does_not_match_larger_number(self):
        self.assertTrue(mod.term_matches("ホリデークール 60 6L","6L"))
        self.assertFalse(mod.term_matches("ホリデークール 260 26L","6L"))
        self.assertFalse(mod.term_matches("ホリデークール 260 26L","60"))

    def test_model_token_requires_ascii_boundary(self):
        self.assertTrue(mod.term_matches("BSJ-201ARS トカラウ","BSJ-201ARS"))
        self.assertFalse(mod.term_matches("XBSJ-201ARS2","BSJ-201ARS"))

    def test_extract_item_info_json(self):
        html='<script>window.x={"itemInfoSku":{"itemId":12345,"purchaseInfo":{"purchaseBySellType":{"purchaseCondition":"enabled"}}}}</script>'
        info=mod.extract_json_object(html,'"itemInfoSku":')
        self.assertEqual(info["itemId"],12345)

    def test_exact_item_id_reads_enabled_listing(self):
        original=mod.fetch_text
        try:
            mod.fetch_text=lambda _url: '<script>{"itemInfoSku":{"itemId":98765,"purchaseInfo":{"purchaseBySellType":{"purchaseCondition":"enabled"}}}}</script>'
            seed={"itemUrl":"https://item.rakuten.co.jp/shop-a/item/"}
            self.assertEqual(mod.exact_item_id(seed),98765)
        finally:
            mod.fetch_text=original

    def test_global_fallback_accepts_other_shop_only_with_full_identity(self):
        seed={**self.seed,"searchQueries":["DAIWA 240C"]}
        original=mod.fetch_json
        try:
            def fake_json(_url,_headers):
                item="https://item.rakuten.co.jp/shop-b/new-item/"
                aff="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(item,safe="")
                return {"items":[{
                    "itemName":"DAIWA フィッシュホルダー 240C",
                    "itemPrice":3200,
                    "itemUrl":item,
                    "affiliateUrl":aff,
                    "mediumImageUrls":["https://example.com/a.jpg"],
                    "itemCode":"shop-b:123",
                    "shopCode":"shop-b"
                }]}
            mod.fetch_json=fake_json
            env={"RAKUTEN_APPLICATION_ID":"a","RAKUTEN_ACCESS_KEY":"b","RAKUTEN_AFFILIATE_ID":"c"}
            item=mod.search_global(seed,env)
            self.assertEqual(item["shopCode"],"shop-b")
        finally:
            mod.fetch_json=original

    def test_global_fallback_rejects_partial_identity(self):
        seed={**self.seed,"searchQueries":["DAIWA 240C"]}
        original=mod.fetch_json
        try:
            def fake_json(_url,_headers):
                item="https://item.rakuten.co.jp/shop-b/new-item/"
                aff="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(item,safe="")
                return {"items":[{
                    "itemName":"DAIWA フィッシュホルダー 240",
                    "itemPrice":3000,
                    "itemUrl":item,
                    "affiliateUrl":aff,
                    "mediumImageUrls":["https://example.com/a.jpg"],
                    "itemCode":"shop-b:124",
                    "shopCode":"shop-b"
                }]}
            mod.fetch_json=fake_json
            env={"RAKUTEN_APPLICATION_ID":"a","RAKUTEN_ACCESS_KEY":"b","RAKUTEN_AFFILIATE_ID":"c"}
            self.assertIsNone(mod.search_global(seed,env))
        finally:
            mod.fetch_json=original

if __name__=="__main__":
    unittest.main()
