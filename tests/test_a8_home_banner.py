"""Regression checks for isolated A8 home creative and original tracking URLs."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/add_a8_home_banner.py'
spec = importlib.util.spec_from_file_location('add_a8_home_banner', SCRIPT)
banner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(banner)

HOME = '''<!doctype html><html lang="ja"><head><title>home</title></head>
<body><main class="container"><section id="home-products">Product ranking</section>
</main><footer>Footer</footer></body></html>'''


class A8HomeBannerTests(unittest.TestCase):
    def test_inject_one_banner_preserves_content_and_links(self):
        markup = banner.inject(HOME)
        self.assertIn('id="home-products"', markup)
        self.assertIn('Product ranking', markup)
        self.assertLess(markup.index('Product ranking'), markup.index(banner.MARKER))
        self.assertLess(markup.index(banner.MARKER), markup.index('</main>'))
        self.assertIn('rel="nofollow sponsored"', markup)
        self.assertIn('aria-label="スポンサーの広告主サイトを開く"', markup)
        self.assertIn(banner.LINK_URL, markup)
        self.assertIn(banner.IMAGE_URL, markup)
        self.assertIn(banner.PIXEL_URL, markup)
        self.assertEqual(markup, banner.inject(markup))
        banner.validate(markup)

    def test_fail_closed_on_unexpected_structure(self):
        with self.assertRaises(ValueError):
            banner.inject('<html><body><main></main></body></html>')
        with self.assertRaises(ValueError):
            banner.inject(HOME.replace('</main>', '</main></main>'))

    def test_fail_closed_on_duplicate_creative(self):
        markup = banner.inject(HOME)
        with self.assertRaises(ValueError):
            banner.inject(markup.replace(banner.PIXEL_URL, banner.PIXEL_URL + banner.PIXEL_URL))

    def test_only_homepage_is_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / 'index.html').write_text(HOME, encoding='utf-8')
            cat = site / 'categories' / 'laundry'
            cat.mkdir(parents=True)
            (cat / 'index.html').write_text(HOME, encoding='utf-8')
            self.assertTrue(banner.apply(site))
            self.assertFalse(banner.apply(site))
            self.assertIn(banner.MARKER, (site / 'index.html').read_text())
            self.assertNotIn(banner.MARKER, (cat / 'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
