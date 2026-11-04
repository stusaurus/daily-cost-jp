"""Regression for the final visual layer overwriting intermediate purchase copy."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from verify_final_purchase_hero import validate, ROUTES

class FinalHeroTests(unittest.TestCase):
    def make(self,root,with_nav=True):
        for route in ROUTES:
            target=root/"categories"/route/"index.html"
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text("<title>product</title>",encoding="utf-8")
        style=root/"assets"/"art-purchase-entry.css"
        style.parent.mkdir(exist_ok=True)
        style.write_text(".art-purchase-links a{min-height:44px}",encoding="utf-8")
        nav='<nav class="art-purchase-links" aria-label="商品へ直行">' + ''.join(
            f'<a class="category-page-link" data-conversion-source="category" href="/daily-cost-jp/categories/{route}/">{route}</a>' for route in ROUTES
        )+'</nav>' if with_nav else ""
        html='<html><head><link rel="stylesheet" href="/daily-cost-jp/assets/art-purchase-entry.css?v=unit-test"></head><body><header class="art-cover"><h1>日用品の価格、単価も総額も。</h1><p class="lead">数量と支払額を確かめる</p>'+nav+'</header></body></html>'
        (root/"index.html").write_text(html,encoding="utf-8")

    def test_fully_rendered_hero_includes_valid_real_destinations(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make(root)
            self.assertEqual(validate(root),[])

    def test_missing_shortcut_fails_instead_of_silently_disappearing(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make(root,False)
            self.assertIn("final art purchase shortcuts are missing",validate(root))

    def test_broken_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.make(root)
            (root/"categories"/"laundry"/"index.html").unlink()
            self.assertIn("shortcut destination missing: laundry",validate(root))

if __name__=="__main__":unittest.main()
