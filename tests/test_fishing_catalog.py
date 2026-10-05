import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "fishing_catalog",
    ROOT/"scripts"/"build_fishing_catalog.py"
)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class FishingCatalogBuilderTest(unittest.TestCase):
    def test_canonical_item_url(self):
        self.assertEqual(
            mod.canonical_item_url("https://item.rakuten.co.jp/shop/item"),
            "https://item.rakuten.co.jp/shop/item/"
        )
        self.assertEqual(mod.canonical_item_url("https://example.com/a"),"")

    def test_identity_groups_and_forbidden_terms(self):
        seed={
            "identityGroups":[["ダイワ","DAIWA"],["240C"]],
            "forbiddenTerms":["中古"],
        }
        self.assertTrue(mod.identity_ok("DAIWA フィッシュホルダー 240C",seed))
        self.assertFalse(mod.identity_ok("DAIWA フィッシュホルダー 240",seed))
        self.assertFalse(mod.identity_ok("中古 DAIWA フィッシュホルダー 240C",seed))

    def test_coverage_detects_complete_core_matrix(self):
        methods=["sabiki","choi_nage"]
        budgets=["low","balanced","long_term"]
        products=[]
        sabiki=["rod_reel","rig","bait","life_jacket_adult","bucket","fish_grip","scissors"]
        choi=["rod_reel","rig","bait","life_jacket_adult","fish_grip","scissors","pliers"]
        for method,cats in [("sabiki",sabiki),("choi_nage",choi)]:
            for category in cats:
                products.append({
                    "methodIds":[method],
                    "budgetTiers":budgets,
                    "coverCategoryIds":[category],
                })
        products.append({
            "methodIds":methods,
            "budgetTiers":budgets,
            "coverCategoryIds":["life_jacket_child"],
        })
        products.append({
            "methodIds":methods,
            "budgetTiers":budgets,
            "coverCategoryIds":["cooler"],
        })
        self.assertEqual(mod.coverage(products),[])

if __name__=="__main__":
    unittest.main()
