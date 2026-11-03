"""Tests for exact A8 Lenet placement, structure, and build idempotence."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from scripts import add_a8_lenet as a8


class Parsed(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.links, self.images, self.ids = [], [], []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if "id" in fields:
            self.ids.append(fields["id"])
        if tag == "a" and "px.a8.net" in fields.get("href", ""):
            self.links.append(fields)
        if tag == "img" and "a8.net/0.gif" in fields.get("src", ""):
            self.images.append(fields)


def fixture():
    return (
        '<!doctype html><html lang="ja"><head><title>洗濯洗剤</title>'
        '<link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/categories/laundry/">'
        '</head><body><main class="container">'
        '<h1>洗濯洗剤の比較</h1><section id="ranking">'
        '<a href="https://hb.afl.rakuten.co.jp/test">楽天市場</a>'
        '<span>送料込み1,300円</span></section>'
        '<section class="related-categories"><h2>ほかのカテゴリ</h2></section>'
        '</main></body></html>'
    )


class LenetA8Tests(unittest.TestCase):
    def test_exact_creative_one_pixel_and_visible_disclosure(self):
        page = a8.inject(fixture())
        parsed = Parsed(page)
        self.assertEqual(parsed.links, [{"href": a8.LINK, "rel": "nofollow"}])
        self.assertEqual(parsed.images, [{
            "border": "0", "width": "1", "height": "1",
            "src": a8.PIXEL, "alt": "",
        }])
        self.assertEqual(page.count(a8.AD_CREATIVE), 1)
        self.assertEqual(parsed.ids.count("a8-lenet-option"), 1)
        self.assertEqual(parsed.ids.count("a8-lenet-style"), 1)
        self.assertEqual(parsed.ids.count("a8-lenet-click-tracker"), 1)
        self.assertIn("広告｜A8.netアフィリエイト", page)
        self.assertIn("料金・対応品目・配送条件", page)

    def test_prices_ranking_metadata_stay_intact(self):
        original = fixture()
        result = a8.inject(original)
        self.assertIn('<section id="ranking">', result)
        self.assertIn("送料込み1,300円", result)
        self.assertIn('<a href="https://hb.afl.rakuten.co.jp/test">', result)
        self.assertEqual(result.count('rel="canonical"'), 1)
        self.assertEqual(result.count("<h1>"), 1)
        self.assertLess(result.index('id="ranking"'), result.index('id="a8-lenet-option"'))
        self.assertLess(result.index('id="a8-lenet-option"'), result.index('class="related-categories"'))

    def test_fails_closed_on_invalid_dom_or_tampered_pixel(self):
        self.assertEqual(a8.inject(a8.inject(fixture())), a8.inject(fixture()))
        with self.assertRaises(ValueError):
            a8.inject(fixture().replace("</main>", ""))
        with self.assertRaises(ValueError):
            a8.inject(a8.inject(fixture()).replace("www10.a8.net", "www15.a8.net"))
        with self.assertRaises(ValueError):
            a8.validate(a8.inject(fixture()) + a8.AD_CREATIVE)

    def test_coexists_with_matsukiyo_ad_without_duplicate_analytics(self):
        from scripts import add_a8_matsukiyo as matsukiyo
        with_retailer = matsukiyo.inject(fixture(), "laundry", "洗濯洗剤")
        with_both = a8.inject(with_retailer)
        a8.validate(with_both)
        matsukiyo.validate(with_both, "laundry")
        self.assertEqual(with_both.count("広告｜A8.netアフィリエイト"), 2)
        self.assertEqual(with_both.count("<h1>"), 1)
        self.assertLess(with_both.index('id="a8-matsukiyo-option"'), with_both.index('id="a8-lenet-option"'))

    def test_only_laundry_and_repeat_build_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for category in ("laundry", "tissue", "toilet-paper", "dish"):
                target = root / "categories" / category / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(fixture(), encoding="utf-8")
            self.assertEqual(a8.apply(root), 1)
            self.assertEqual(a8.apply(root), 0)
            page = (root / a8.TARGET).read_text(encoding="utf-8")
            a8.validate(page)
            for category in ("tissue", "toilet-paper", "dish"):
                self.assertNotIn(a8.MARKER, (root / "categories" / category / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
