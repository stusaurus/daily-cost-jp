"""Regression coverage for exact packs, money, and optional Yahoo failure."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from marketplace_comparison import ANCHOR, PRODUCTS, apply, select
from marketplace_offers import package_quantity, rakuten_offer, yahoo_offer
from yahoo_shopping import YahooShopping, YahooUnavailable, affiliate_config

PRODUCT = PRODUCTS["laundry"][0]
TITLE = f"アタックZERO 部屋干し つめかえ 2000g×3袋 {PRODUCT.jan}"
CREDENTIAL = "https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=100&pid=200&vc_url="
YAHOO_ITEM = "teststore_attack-3"
YAHOO_URL = CREDENTIAL + quote("https://store.shopping.yahoo.co.jp/teststore/attack-3.html", safe="")
RAKUTEN_ITEM = "examplestore:10000001"
RAKUTEN_URL = "https://hb.afl.rakuten.co.jp/hgc/path/?" + urlencode({
    "pc": "https://item.rakuten.co.jp/examplestore/attack-3/",
    "m": "http://m.rakuten.co.jp/examplestore/i/10000001/",
})
NOW = datetime(2026, 11, 25, 6, tzinfo=timezone.utc)


def rakuten(**fields):
    return {"category_id": "laundry", "quality_version": 1, "name": TITLE, "price": 7200,
            "sale_quantity_label": "2000g×3個", "postage": "送料込み",
            "url": RAKUTEN_URL, "item_code": RAKUTEN_ITEM, "shop": '楽天 <店>'} | fields


def yahoo(**fields):
    return {"janCode": PRODUCT.jan, "name": TITLE, "price": 6900, "priceLabel": {"taxable": True},
            "inStock": True, "condition": "new", "code": YAHOO_ITEM, "url": YAHOO_URL,
            "seller": {"name": "Yahoo! 店"}, "shipping": {"code": 2}} | fields


class MockYahoo(YahooShopping):
    def __init__(self, hits=None, fails=False):
        super().__init__("private-app-id", CREDENTIAL)
        self.hits = [yahoo()] if hits is None else hits
        self.fails = fails

    def search(self, *, jan):
        if self.fails:
            raise YahooUnavailable("http_503")
        return self.hits if jan == PRODUCT.jan else []


class MarketplaceTest(unittest.TestCase):
    def test_checks_jan_and_does_not_convert_mass_to_volume(self):
        self.assertEqual(package_quantity("laundry", TITLE, PRODUCT), 3)
        self.assertEqual(package_quantity("laundry", TITLE.replace("2000g", "2kg"), PRODUCT), 3)
        rejected = [
            TITLE.replace("2000g", "2000ml"), TITLE.replace("2000g", "2300g"),
            TITLE.replace("部屋干し", "ドラム式専用"), TITLE + " ドラム式専用",
            TITLE + " サイズが選べる", TITLE + " ×2セット", TITLE + " + 1袋",
            TITLE.replace("2000g×3袋", "2000g まとめ買い"), TITLE + " 1ケース",
        ]
        for title in rejected:
            with self.subTest(title=title):
                self.assertIsNone(package_quantity("laundry", title, PRODUCT))
        self.assertIsNone(rakuten_offer("laundry", rakuten(name=TITLE.replace(PRODUCT.jan, "")), PRODUCT))
        self.assertIsNone(rakuten_offer("laundry", rakuten(sale_quantity_label="2000g×2個"), PRODUCT))
        self.assertIsNone(rakuten_offer("laundry", rakuten(item_code="examplestore:10000009"), PRODUCT))

    def test_yahoo_item_and_affiliate_identity(self):
        client = MockYahoo()
        for data in (yahoo(janCode="4901301466235"), yahoo(inStock=False), yahoo(condition="used"),
                     yahoo(priceLabel=None), yahoo(priceLabel={"taxable": False}), yahoo(price=True),
                     yahoo(url=YAHOO_URL.replace("sid=100", "sid=300")),
                     yahoo(url=YAHOO_URL.replace("attack-3.html", "attack-4.html")),
                     yahoo(url=YAHOO_URL.replace("store.shopping.yahoo.co.jp", "store.shopping.yahoo.co.jp.evil.test")),
                     yahoo(url=YAHOO_URL.replace("https%3A", "http%3A")),
                     yahoo(url=YAHOO_URL + "&vc_url=overwritten"),
                     yahoo(url=YAHOO_URL + "&unexpected=private-app-id")):
            self.assertIsNone(yahoo_offer("laundry", data, PRODUCT, client.affiliate_link))
        self.assertIsNotNone(yahoo_offer("laundry", yahoo(), PRODUCT, client.affiliate_link))
        self.assertEqual(affiliate_config(quote(CREDENTIAL, safe=""))[0], CREDENTIAL)
        self.assertEqual(affiliate_config(CREDENTIAL.removesuffix("&vc_url="))[0], CREDENTIAL)
        with self.assertRaisesRegex(YahooUnavailable, "^affiliate_config_format$"):
            affiliate_config("200")

    def test_rank_by_confirmed_total_without_commission(self):
        uncertain = yahoo(price=3000, affiliateRate=100, shipping={"code": 3})
        regional = yahoo(price=3200, description="北海道・沖縄・離島は別途送料が必要です。")
        for result in (uncertain, regional, yahoo(shipping=None), yahoo(shipping={"code": 1})):
            with self.subTest(result=result["shipping"]):
                self.assertIsNone(yahoo_offer("laundry", result, PRODUCT, MockYahoo().affiliate_link)[1].total)
        groups, _ = select("laundry", [rakuten()], MockYahoo([uncertain, regional, yahoo(affiliateRate=0)]))
        self.assertEqual(groups[0][2][1].price, 6900)
        self.assertEqual(groups[0][2][1].total, 6900)
        groups, _ = select("laundry", [rakuten()], MockYahoo([yahoo(name=TITLE.replace("3袋", "6袋"))]))
        self.assertEqual(groups, [])

    def test_build_keeps_catalog_and_legacy_html_on_outage(self):
        original = "<html><head></head><body>" + ANCHOR + '<h2>楽天の比較</h2></section><footer>既存フッター</footer></body></html>'
        with TemporaryDirectory() as directory:
            site = Path(directory)
            page = site / "categories/laundry/index.html"
            page.parent.mkdir(parents=True)
            page.write_text(original)
            data = site / "data.json"
            data.write_text(json.dumps({"updated_at": NOW.isoformat(),
                                        "categories": {"laundry": {"items": [rakuten()]}}}))
            before = data.read_bytes()
            for client, now, expected in (
                (MockYahoo(fails=True), NOW, "http_503"),
                (MockYahoo(hits=[]), NOW, "no_comparable_pair"),
                (MockYahoo(), NOW + timedelta(hours=25), "rakuten_catalog_not_fresh"),
            ):
                self.assertEqual(apply(site, client=client, now=now)["status"], expected)
                self.assertEqual(page.read_text(), original)
            result = apply(site, client=MockYahoo(), now=NOW)
            self.assertEqual(result["categories"]["laundry"]["comparable"], 1)
            rendered = page.read_text()
            self.assertIn("Yahoo!ショッピングが¥300安い", rendered)
            self.assertIn("¥115.0 / 100g", rendered)
            self.assertIn("楽天 &lt;店&gt;", rendered)
            self.assertIn("Webサービス by Yahoo! JAPAN", rendered.split("<footer>", 1)[1])
            self.assertNotIn("private-app-id", rendered)
            self.assertEqual(data.read_bytes(), before)
            apply(site, client=MockYahoo(), now=NOW)
            self.assertEqual(page.read_text(), rendered)


if __name__ == "__main__":
    unittest.main()
