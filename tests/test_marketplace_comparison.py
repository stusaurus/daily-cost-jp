"""Regression coverage for exact packs, money, and optional Yahoo failure."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from marketplace_comparison import ANCHOR, MAIN, NAV_MARKER, PRODUCTS, apply, select
from marketplace_offers import package_quantity, price_unit, rakuten_offer, yahoo_offer
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

    def search(self, *, jan, shipping=None):
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

    def test_softener_requires_the_same_pack_and_volume(self):
        product = PRODUCTS["softener"][0]
        name = f"P&G さらさ 柔軟剤 つめかえ用 1350ml×6袋 {product.jan}"
        self.assertEqual(package_quantity("softener", name, product), 6)
        self.assertIsNone(package_quantity("softener", name.replace("1350ml", "1350g"), product))
        self.assertIsNone(package_quantity("softener", name + "×2箱", product))
        self.assertIsNone(package_quantity("softener", name.replace("柔軟剤", "洗濯洗剤"), product))

    def test_dish_refill_requires_the_orange_variant_and_exact_capacity(self):
        product = PRODUCTS["dish"][0]
        title = f"キュキュット 食器用洗剤 オレンジの香り 詰替え用 1380mL×2個 {product.jan}"
        self.assertEqual(package_quantity("dish", title, product), 2)
        self.assertIsNone(package_quantity("dish", title.replace("1380mL", "770mL"), product))
        self.assertIsNone(package_quantity("dish", title.replace("オレンジ", "マスカット"), product))
        self.assertIsNone(package_quantity("dish", title + " マスカットも選べる", product))
        self.assertIsNone(package_quantity("dish", title + " 本体同梱", product))

    def test_toilet_refill_rejects_other_fragrances_and_body_bottle(self):
        product = PRODUCTS["toilet-cleaner"][0]
        title = f"トイレマジックリン 消臭・洗浄スプレー エレガントローズの香り つめかえ用 300mL {product.jan}"
        self.assertEqual(package_quantity("toilet-cleaner", title, product), 1)
        self.assertEqual(package_quantity("toilet-cleaner", title + "×2袋", product), 2)
        self.assertIsNone(package_quantity("toilet-cleaner", title + " 本体（別容量）", product))
        self.assertIsNone(package_quantity("toilet-cleaner", title.replace("ローズ", "シトラス"), product))

    def test_counted_packs_require_total_length_and_matching_sheet_count(self):
        roll = PRODUCTS["toilet-paper"][0]
        title = "スコッティ フラワーパック 3倍長持ち トイレットペーパー ダブル 75m×12ロール"
        self.assertEqual(package_quantity("toilet-paper", title, roll), 1)
        self.assertIsNone(package_quantity("toilet-paper", title.replace("75m", "50m"), roll))
        self.assertIsNone(package_quantity("toilet-paper", title + "×2個×3箱", roll))
        self.assertEqual(price_unit("toilet-paper", roll), (10, 75, "10m"))
        tissue = PRODUCTS["tissue"][0]
        title = "スコッティ ティッシュ 200組 400枚 5箱×12パック 計60箱"
        self.assertEqual(package_quantity("tissue", title, tissue), 12)
        self.assertIsNone(package_quantity("tissue", title.replace("60箱", "48箱"), tissue))
        self.assertIsNone(package_quantity("tissue", title.replace("400枚", "320枚"), tissue))
        self.assertEqual(price_unit("tissue", tissue), (100, 200, "100組"))
        self.assertEqual(price_unit("water", PRODUCTS["water"][0]), (1000, 1, "1L"))

    def test_bottles_inside_cases_and_kitchen_roll_dimensions(self):
        water = PRODUCTS["water"][0]
        title = "温泉水99 天然水 1.9Lペットボトル×2箱（12本）"
        self.assertEqual(package_quantity("water", title, water), 12)
        self.assertEqual(package_quantity("water", title.replace("×2箱（12本）", "×12本"), water), 12)
        self.assertIsNone(package_quantity("water", title.replace("12本", "24本"), water))
        crystal = PRODUCTS["water"][1]
        title = "クリスタルガイザー エコボトル 正規輸入品 500ml×48本"
        self.assertEqual(package_quantity("water", title, crystal), 48)
        self.assertIsNone(package_quantity("water", title.replace("正規輸入品", "並行輸入"), crystal))
        body = PRODUCTS["body-soap"][0]
        title = "花王 ビオレu ボディウォッシュ 業務用 10L"
        self.assertEqual(package_quantity("body-soap", title, body), 1)
        self.assertIsNone(package_quantity("body-soap", title + " 泡タイプ", body))
        kitchen = PRODUCTS["kitchen-paper"][0]
        title = "花王 シェフ キッチンペーパー たっぷり吸収 M 100枚×2ロール×6袋"
        self.assertEqual(package_quantity("kitchen-paper", title, kitchen), 6)
        self.assertEqual(price_unit("kitchen-paper", kitchen), (1, 1, "1枚"))
        self.assertIsNone(package_quantity("kitchen-paper", title.replace("100枚×2", "50枚×4"), kitchen))
        self.assertIsNone(package_quantity("kitchen-paper", title + "×2ケース", kitchen))

    def test_verified_merchant_record_requires_matching_urls_and_independent_quantity(self):
        tissue = PRODUCTS["tissue"][0]
        pc = "https://item.rakuten.co.jp/kyoto23/10001789/"
        mobile = "http://m.rakuten.co.jp/kyoto23/i/10001789/"
        url = "https://hb.afl.rakuten.co.jp/hgc/path/?" + urlencode({"pc": pc, "m": mobile})
        row = rakuten(category_id="tissue", item_code="kyoto23:10001789", url=url,
                      sale_quantity_label="5箱×12パック",
                      name="スコッティ ティッシュ 200組 400枚 5箱×12パック")
        self.assertEqual(rakuten_offer("tissue", row, tissue)[0], 12)
        self.assertIsNone(rakuten_offer("tissue", row | {"url": url.replace("10001789%2F", "10001788%2F", 1)}, tissue))
        self.assertIsNone(rakuten_offer("tissue", row | {"name": row["name"] + " 4901301440815"}, tissue))
        self.assertIsNone(rakuten_offer("tissue", row | {"sale_quantity_label": "5箱×6パック"}, tissue))

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
        original = ("<html><head></head><body>" + MAIN + ANCHOR
                    + '<h2>楽天の比較</h2></section></main><footer>既存フッター</footer></body></html>')
        landing = "<html><head></head><body>" + MAIN + "</main></body></html>"
        with TemporaryDirectory() as directory:
            site = Path(directory)
            page = site / "categories/laundry/index.html"
            page.parent.mkdir(parents=True)
            page.write_text(original)
            home = site / "index.html"
            directory_page = site / "categories/index.html"
            for entry in (home, directory_page):
                entry.write_text(landing)
            data = site / "data.json"
            data.write_text(json.dumps({"updated_at": NOW.isoformat(),
                                        "categories": {
                                            "laundry": {"name": "洗濯洗剤", "items": [rakuten()]},
                                            "dish": {"name": "食器用洗剤", "items": []},
                                        }}))
            before = data.read_bytes()
            for client, now, expected in (
                (MockYahoo(fails=True), NOW, "http_503"),
                (MockYahoo(hits=[]), NOW, "no_comparable_pair"),
                (MockYahoo(), NOW + timedelta(hours=25), "rakuten_catalog_not_fresh"),
            ):
                self.assertEqual(apply(site, client=client, now=now)["status"], expected)
                self.assertEqual(page.read_text(), original)
                self.assertEqual(home.read_text(), landing)
                self.assertEqual(directory_page.read_text(), landing)
            result = apply(site, client=MockYahoo(), now=NOW)
            self.assertEqual(result["categories"]["laundry"]["comparable"], 1)
            published = json.loads((site / "marketplace-coverage.json").read_text())
            self.assertEqual(set(published["categories"]), {"laundry", "dish"})
            self.assertEqual(published["categories"]["laundry"]["yahoo_results"], 1)
            self.assertEqual(published["categories"]["dish"]["status"], "no_rakuten_match")
            rendered = page.read_text()
            self.assertIn("Yahoo!ショッピングが安い（差額 ¥300）", rendered)
            self.assertIn("¥115.0 / 100g", rendered)
            self.assertIn("楽天 &lt;店&gt;", rendered)
            self.assertIn("Webサービス by Yahoo! JAPAN", rendered.split("<footer>", 1)[1])
            self.assertNotIn("private-app-id", rendered)
            self.assertEqual(data.read_bytes(), before)
            self.assertIn('href="#marketplace-comparison" data-marketplace-entry="category"', rendered)
            entry_pages = {}
            for path, entry_point in ((home, "home"), (directory_page, "directory")):
                text = path.read_text()
                entry_pages[path] = text
                self.assertEqual(text.count(NAV_MARKER), 1)
                self.assertIn(f'href="/daily-cost-jp/categories/laundry/#marketplace-comparison" '
                              f'data-marketplace-entry="{entry_point}"', text)
                self.assertNotIn("/categories/dish/", text)
            apply(site, client=MockYahoo(), now=NOW)
            self.assertEqual(page.read_text(), rendered)
            for path, text in entry_pages.items():
                self.assertEqual(path.read_text(), text)


if __name__ == "__main__":
    unittest.main()
