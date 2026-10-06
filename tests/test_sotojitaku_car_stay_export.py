import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "car_stay_export",
    ROOT/"scripts"/"export_sotojitaku_car_stay.py"
)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class CarStayExportTest(unittest.TestCase):
    def setUp(self):
        self.old_env={k:os.environ.get(k) for k in ("RAKUTEN_APPLICATION_ID","RAKUTEN_ACCESS_KEY","RAKUTEN_AFFILIATE_ID")}
        for k in self.old_env:
            os.environ[k]="test"
        self.original_exact=mod.exact_item_candidate
        self.original_search=mod.search_identity
        self.original_fetch=mod.fetch_json

    def tearDown(self):
        mod.exact_item_candidate=self.original_exact
        mod.search_identity=self.original_search
        mod.fetch_json=self.original_fetch
        for k,v in self.old_env.items():
            if v is None:
                os.environ.pop(k,None)
            else:
                os.environ[k]=v

    def seed(self):
        return {
            "productId":"nvan-mat",
            "name":"Levolva N-VAN",
            "brand":"Levolva",
            "itemUrl":"https://item.rakuten.co.jp/auc-sovie-store/mr-11/",
            "gapIds":["floor_step","sleep_surface"],
            "recommendationRole":"beginner_alternative",
            "score":92,
            "identityGroups":[["Levolva"],["N-VAN"],["JJ1","JJ2"]],
            "forbiddenTerms":["N-WGN"],
            "fitCheckedAt":"2026-10-06",
            "fitEvidenceUrl":"https://item.rakuten.co.jp/auc-sovie-store/mr-11/",
            "vehicleFit":[{"vehicleId":"honda-nvan-jj1-jj2","status":"verified"}],
        }

    def candidate(self,url="https://item.rakuten.co.jp/auc-sovie-store/mr-11/"):
        return {
            "name":"Levolva N-VAN JJ1 JJ2 車中泊マット",
            "price":19800,
            "itemUrl":url,
            "affiliateUrl":"https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(url,safe=""),
            "image":"https://example.com/a.jpg",
            "itemCode":"auc-sovie-store:12345",
            "shopCode":"auc-sovie-store",
        }

    def run_one(self,candidate):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"seed.json"
            p.write_text(json.dumps(self.seed(),ensure_ascii=False))
            mod.exact_item_candidate=lambda seed,env:candidate
            mod.search_identity=lambda seed,env:(None,"none")
            return mod.export_catalog(Path(td))

    def test_preserves_car_stay_fit_metadata(self):
        out=self.run_one(self.candidate())
        self.assertEqual(out["verifiedCount"],1)
        p=out["products"][0]
        self.assertEqual(p["gapIds"],["floor_step","sleep_surface"])
        self.assertEqual(p["vehicleFit"][0]["vehicleId"],"honda-nvan-jj1-jj2")
        self.assertEqual(p["audit"]["salesSource"],"daily-cost-jp_github_actions")

    def test_cross_shop_candidate_is_rejected(self):
        out=self.run_one(self.candidate("https://item.rakuten.co.jp/other-shop/mr-11/"))
        self.assertEqual(out["verifiedCount"],0)
        self.assertEqual(out["failures"]["nvan-mat"],"cross_shop_rejected")


    def test_explicit_seed_item_code_resolves_exact_listing(self):
        seed=self.seed()
        seed["rakutenItemCode"]="auc-sovie-store:mr-11"
        url=seed["itemUrl"]
        affiliate="https://hb.afl.rakuten.co.jp/hgc/x/?pc="+__import__("urllib.parse").parse.quote(url,safe="")
        seen=[]
        def fake_fetch(request_url,headers):
            seen.append(request_url)
            return {"items":[{
                "itemName":"Levolva N-VAN JJ1 JJ2 車中泊マット",
                "itemPrice":19800,
                "itemUrl":url,
                "affiliateUrl":affiliate,
                "mediumImageUrls":["https://example.com/a.jpg"],
                "itemCode":"auc-sovie-store:mr-11",
                "shopCode":"auc-sovie-store"
            }]}
        mod.fetch_json=fake_fetch
        candidate=mod.explicit_item_code_candidate(seed,{
            "RAKUTEN_APPLICATION_ID":"app",
            "RAKUTEN_ACCESS_KEY":"key",
            "RAKUTEN_AFFILIATE_ID":"aff",
        })
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["itemUrl"],url)
        self.assertTrue(any("itemCode=auc-sovie-store%3Amr-11" in x for x in seen))

    def test_missing_credentials_fail_before_export(self):
        for k in ("RAKUTEN_APPLICATION_ID","RAKUTEN_ACCESS_KEY","RAKUTEN_AFFILIATE_ID"):
            os.environ.pop(k,None)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,"missing Rakuten credentials"):
                mod.export_catalog(Path(td))

if __name__=="__main__":
    unittest.main()
