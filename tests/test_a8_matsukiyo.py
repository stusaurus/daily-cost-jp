"""A8 official Matsukiyo/Cocokara creative and separation regression tests."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from scripts import add_a8_matsukiyo as a8


class Parsed(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.images = []
        self.ids = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.append(data["id"])
        if tag == "a" and "px.a8.net" in data.get("href", ""):
            self.links.append(data)
        if tag == "img" and "a8.net/0.gif" in data.get("src", ""):
            self.images.append(data)


def basic_page():
    return (
        '<!doctype html><html lang="ja"><head><title>洗濯洗剤の比較</title>'
        '<link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/categories/laundry/">'
        '</head><body><main class="container">'
        '<h1>実際の楽天購入価格を比較</h1>'
        '<section id="ranking"><p>取得済み商品: ¥1,280</p>'
        '<a href="https://hb.afl.rakuten.co.jp/hgc/real">楽天で商品を確認</a>'
        '</section>'
        '<section class="related-categories"><h2>関連カテゴリ</h2></section>'
        '</main></body></html>'
    )


class MatsukiyoA8Tests(unittest.TestCase):
    def test_official_anchor_pixel_and_disclosure_are_exact(self):
        page = a8.inject(basic_page(), "laundry", "洗濯洗剤")
        node = Parsed(page)
        self.assertEqual(node.links, [{
            "href": "https://px.a8.net/svt/ejp?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM",
            "rel": "nofollow",
        }])
        self.assertEqual(node.images, [{
            "border": "0", "width": "1", "height": "1",
            "src": "https://www19.a8.net/0.gif?a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM",
            "alt": "",
        }])
        self.assertEqual(page.count(a8.AD_CREATIVE), 1)
        self.assertEqual(node.ids.count("a8-matsukiyo-option"), 1)
        self.assertEqual(node.ids.count("a8-matsukiyo-click-tracker"), 1)
        self.assertEqual(node.ids.count("a8-matsukiyo-style"), 1)
        self.assertIn("広告｜A8.netアフィリエイト", page)
        self.assertIn("実際に支払う金額", page)
        self.assertIn("クーポンが必ず利用できることは保証しません", page)
        self.assertIn("同じ商品・容量・個数", page)

    def test_existing_rankings_and_metadata_do_not_change(self):
        original = basic_page()
        rendered = a8.inject(original, "laundry", "洗濯洗剤")
        self.assertIn('<h1>実際の楽天購入価格を比較</h1>', rendered)
        self.assertIn('<section id="ranking"><p>取得済み商品: ¥1,280</p>', rendered)
        self.assertIn('<a href="https://hb.afl.rakuten.co.jp/hgc/real">', rendered)
        self.assertEqual(rendered.count('rel="canonical"'), 1)
        self.assertLess(rendered.index('id="ranking"'), rendered.index('id="a8-matsukiyo-option"'))
        self.assertLess(rendered.index('id="a8-matsukiyo-option"'), rendered.index('class="related-categories"'))
        self.assertEqual(rendered.count("<h1>"), 1)

    def test_safe_to_rerun_and_missing_structure_blocks_ad(self):
        original = basic_page()
        once = a8.inject(original, "laundry", "洗濯洗剤")
        self.assertEqual(once, a8.inject(once, "laundry", "洗濯洗剤"))
        with self.assertRaises(ValueError):
            a8.inject(original.replace("</main>", ""), "laundry", "洗濯洗剤")
        with self.assertRaises(ValueError):
            a8.inject(original, "wrong-category", "洗濯洗剤")
        with self.assertRaises(ValueError):
            a8.inject(once.replace("www19.a8.net", "www15.a8.net"), "laundry", "洗濯洗剤")
        with self.assertRaises(ValueError):
            a8.validate(once + a8.AD_CREATIVE, "laundry")

    def test_three_categories_only_and_fail_closed_missing_categories(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            original = basic_page()
            for category in (*a8.CATEGORIES, "dish", "water", "coffee"):
                page = site / "categories" / category / "index.html"
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(original, encoding="utf-8")
            self.assertEqual(a8.apply(site), 3)
            self.assertEqual(a8.apply(site), 0)
            for category in a8.CATEGORIES:
                page = (site / "categories" / category / "index.html").read_text(encoding="utf-8")
                a8.validate(page, category)
            for category in ("dish", "water", "coffee"):
                page = (site / "categories" / category / "index.html").read_text(encoding="utf-8")
                self.assertNotIn(a8.MARKER, page)

    def test_category_data_stays_unchanged_and_tracker_tags_valid(self):
        page = a8.inject(basic_page(), "tissue", "ティッシュ")
        self.assertIn('data-a8-category="tissue"', page)
        self.assertIn("window.gtag('event', 'affiliate_click'", page)
        self.assertIn("affiliate: 'a8'", page)
        self.assertIn("conversion_source: 'category'", page)
        self.assertIn("click_position: 'alternate_online_retailer'", page)
        self.assertEqual(page.count("a8mat=4BGCF1+A1E4Z6+5QFO+5YJRM"), 2)


if __name__ == "__main__":
    unittest.main()
