"""GSC-based wording adjustment, without unsupported store-wide rankings."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import improve_category_seo as seo


class LaundryIntentMetadataTests(unittest.TestCase):
    def test_description_is_narrower_than_global_cheap_shop_claim(self):
        t=seo.SEARCH_TARGETS["laundry"]
        self.assertIn("安い店", t["title"])
        self.assertIn("単価ランキング", t["title"])
        self.assertIn("掲載店比較", t["title"])
        self.assertIn("楽天全店の最安値は保証しません", t["description"])
        self.assertIn("送料込み支払総額", t["lead"])
        for unit in ("100g", "100ml"):
            for key in ("lead", "description"):
                self.assertIn(unit+"あたり", seo.render_search_copy(t[key], unit))
            self.assertNotIn("必ず最安", seo.render_search_copy(t["description"], unit))

    def test_rewriting_seo_does_not_change_actual_ranking_or_canonical(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            path=root/"categories/laundry/index.html"
            path.parent.mkdir(parents=True)
            canonical="https://stusaurus.github.io/daily-cost-jp/categories/laundry/"
            initial=(
                "<html><head><title>旧タイトル</title>"
                '<meta name="description" content="以前の説明">'
                f'<link rel="canonical" href="{canonical}"></head>'
                '<body><main class="container"><h1>旧見出し</h1>'
                '<p class="lead">以前の説明</p>'
                '<section id="laundry"><span data-fixture="rank">¥89.26／100g</span></section>'
                '<section class="related-categories"></section></main></body></html>'
            )
            path.write_text(initial,encoding="utf-8")
            payload={"categories":{"laundry":{"metric":"100g"}}}
            with patch.object(seo,"SITE_DIR",root):
                self.assertTrue(seo.enhance_page("laundry","洗濯洗剤","🧴","洗濯洗剤",payload))
            rendered=path.read_text(encoding="utf-8")
            self.assertEqual(rendered.count('<link rel="canonical"'),1)
            self.assertIn(canonical,rendered)
            self.assertIn('data-fixture="rank">¥89.26／100g',rendered)
            self.assertIn("楽天全店の最安値は保証しません",rendered)
            self.assertIn("洗濯洗剤の安い店は？",rendered)
            self.assertIn('id="category-seo-schema"',rendered)


if __name__=="__main__":
    unittest.main()
