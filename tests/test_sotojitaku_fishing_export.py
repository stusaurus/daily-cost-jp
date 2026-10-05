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

if __name__=="__main__":
    unittest.main()
