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

    def test_exact_page_info_extracts_item_id_and_price(self):
        original=mod.fetch_text
        try:
            mod.fetch_text=lambda _url: 'x "itemInfoSku":{"itemId":12345,"sellType":"NORMAL","purchaseInfo":{"purchaseBySellType":{"purchaseCondition":"enabled","normalPurchase":{"price":{"minPrice":6789}}}}} y'
            info=mod.exact_page_info("https://item.rakuten.co.jp/shop-a/item/")
            self.assertEqual(info,{"itemId":12345,"price":6789})
        finally:
            mod.fetch_text=original

    def test_exact_seed_item_uses_item_code_and_identity_gate(self):
        seed={**self.seed,"itemUrl":"https://item.rakuten.co.jp/shop-a/old-item/"}
        original_page=mod.exact_page_info
        original_json=mod.fetch_json
        try:
            mod.exact_page_info=lambda _url: {"itemId":2468,"price":3000}
            def fake_json(url,headers):
                self.assertIn("itemCode=shop-a%3A2468",url)
                return {"items":[{
                    "itemName":"DAIWA フィッシュホルダー 240C",
                    "itemPrice":3000,
                    "itemUrl":"https://item.rakuten.co.jp/shop-a/old-item/",
                    "affiliateUrl":"https://hb.afl.rakuten.co.jp/hgc/x/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fshop-a%2Fold-item%2F",
                    "mediumImageUrls":["https://example.com/a.jpg"],
                    "itemCode":"shop-a:2468",
                    "shopCode":"shop-a"
                }]}
            mod.fetch_json=fake_json
            env={"RAKUTEN_APPLICATION_ID":"a","RAKUTEN_ACCESS_KEY":"b","RAKUTEN_AFFILIATE_ID":"c"}
            item=mod.fetch_exact_seed_item(seed,env)
            self.assertEqual(item["itemCode"],"shop-a:2468")
        finally:
            mod.exact_page_info=original_page
            mod.fetch_json=original_json

if __name__=="__main__":
    unittest.main()
