"""Regression contract: every published category gets honest buyer guidance."""
import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import improve_category_seo as seo

NEW = {
    "toothpaste": ("100g", "歯磨き粉", "ml"),
    "wet-wipes": ("1枚", "除菌ウェットティッシュ", "アルコール"),
    "kitchen-paper": ("1枚", "キッチンペーパー", "ロール"),
    "sink-net": ("1枚", "排水口ネット（キッチン用）", "浅型"),
}


def literal_list(path, name):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


class FourCategorySearchGuidanceTests(unittest.TestCase):
    def test_seo_registry_covers_all_published_categories(self):
        old = literal_list("scripts/build_site.py", "CATEGORIES")
        more = literal_list("scripts/build_site_growth.py", "ADDITIONAL_CATEGORIES")
        ids = {entry["id"] for entry in old + more}
        self.assertEqual(len(ids), 25)
        self.assertEqual(set(seo.CATEGORIES), ids)
        self.assertEqual(set(seo.RELATED_CATEGORY_LINKS), set(NEW))
        for cid in NEW:
            self.assertIn(cid, seo.SEARCH_TARGETS)
            self.assertIn(cid, seo.PRIORITY_FAQS)

    def test_new_guides_match_displayed_comparison_units(self):
        for cid, (expected_unit, name, topic) in NEW.items():
            with self.subTest(cid=cid):
                data = {"categories": {cid: {
                    "metric": "100g" if cid == "toothpaste" else "sheet"
                }}}
                unit = seo.metric_label(cid, data)
                self.assertEqual(unit, expected_unit)
                title, emoji, alias = seo.CATEGORIES[cid]
                self.assertEqual(name, title)
                guide = seo.seo_section(cid, title, alias, unit)
                faq = seo.faq_section(cid, title, unit)
                self.assertIn(expected_unit + "あたり", guide)
                self.assertIn(topic, faq + guide)
                self.assertEqual(faq.count("<details>"), 5)
                self.assertNotIn("{comparison_unit}", faq + guide)
                self.assertIn("送料込み", guide)
                links = seo.priority_links(cid)
                self.assertEqual(links.count("<a "), 2)
                self.assertIn("一緒に比較したい日用品", links)
                self.assertNotIn('href="../' + cid + '/"', links)

    def test_enrichment_preserves_exact_purchase_links_and_is_idempotent(self):
        fixture = ('<html><head><title>Before</title>'
                   '<meta name="description" content="Before">'
                   '<link rel="canonical" href="{canonical}"></head>'
                   '<body><header><h1>Before</h1><p class="lead">Before</p></header>'
                   '<main class="container">'
                   '<div class="category-summary">送料込み確認済み</div>'
                   '<section data-fixture="original-ranking">'
                   '<a class="buy-button" href="https://item.rakuten.co.jp/shop/sku/" '
                   'rel="nofollow sponsored noopener" data-shipping-price="2345">購入</a>'
                   '</section><section class="related-categories"></section>'
                   '</main></body></html>')
        purchase = ('<a class="buy-button" href="https://item.rakuten.co.jp/shop/sku/" '
                    'rel="nofollow sponsored noopener" data-shipping-price="2345">購入</a>')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"categories": {
                cid: {"metric": "100g" if cid == "toothpaste" else "sheet"}
                for cid in NEW
            }}
            for cid in NEW:
                p = root / "categories" / cid / "index.html"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(fixture.format(canonical=seo.BASE_URL +
                             f"categories/{cid}/"), encoding="utf-8")
            with patch.object(seo, "SITE_DIR", root):
                for cid in NEW:
                    name, emoji, alias = seo.CATEGORIES[cid]
                    self.assertTrue(seo.enhance_page(cid, name, emoji, alias, payload))
                    p = root / "categories" / cid / "index.html"
                    new = p.read_text(encoding="utf-8")
                    self.assertIn(purchase, new)
                    self.assertIn(f'href="{seo.BASE_URL}categories/{cid}/"', new)
                    for needle in ('id="category-seo-schema"', 'id="compare-guide"',
                                   'id="category-faq"', 'class="search-priority-links"'):
                        self.assertEqual(new.count(needle), 1, (cid, needle))
                    self.assertEqual(new.count("<h1>"), 1)
                    self.assertNotIn('<meta name="description" content="Before">', new)
                    self.assertTrue(seo.enhance_page(cid, name, emoji, alias, payload))
                    self.assertEqual(p.read_text(encoding="utf-8"), new)

    def test_unknown_toothpaste_metric_is_not_guessed(self):
        self.assertEqual(seo.metric_label("toothpaste", {
            "categories": {"toothpaste": {"metric": "unknown"}}
        }), "同じ単位")


if __name__ == "__main__":
    unittest.main()
