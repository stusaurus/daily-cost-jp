import shutil
import json
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_laundry_cost_page import build


class QuestionFirstPageTests(unittest.TestCase):
    def _site(self, tmp):
        site = Path(tmp)
        target = site / "categories/laundry/index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('<!doctype html><html lang="ja"><head>'
                          '<title>既存の洗剤ページ</title></head><body>'
                          '<main id="lab-content"><section id="current-ranking">'
                          '商品一覧</section></main></body></html>',
                          encoding="utf-8")
        return site, target

    def test_build_generates_one_distinct_page_and_crawlable_internal_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, category = self._site(tmp)
            build(site)
            page = site / "tools/laundry-cost-per-wash/index.html"
            self.assertTrue(page.is_file())
            self.assertTrue((site / "assets/laundry-per-wash.js").is_file())
            content = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
            self.assertEqual(len(content.select("h1")), 1)
            self.assertEqual(content.html["lang"], "ja")
            self.assertEqual(content.select_one('link[rel="canonical"]')["href"],
                             "https://stusaurus.github.io/daily-cost-jp/tools/laundry-cost-per-wash/")
            self.assertEqual(content.select_one('meta[name="robots"]')["content"],
                             "index,follow")
            self.assertEqual(len(content.select('#wash-calc input')), 14)
            self.assertIsNotNone(content.select_one("#wash-result[hidden]"))
            self.assertIsNotNone(content.select_one("#wash-period[max=\"12\"]"))
            self.assertIsNotNone(content.select_one("#wash-a-payment"))
            self.assertIsNotNone(content.select_one("#wash-b-unused"))
            self.assertIn("支払額と安い方は判定しません", content.get_text())
            self.assertEqual(content.select_one("#wash-a-order-shipping").get("value", ""), "")
            self.assertIsNotNone(content.select_one('script[src="/daily-cost-jp/assets/laundry-per-wash.js"]'))
            self.assertIsNone(content.select_one("a[href*='rakuten.co.jp']"))
            self.assertIn("楽天アフィリエイト", content.get_text())
            link = BeautifulSoup(category.read_text(encoding="utf-8"), "html.parser")
            self.assertEqual(len(link.select('#wash-cost-link')), 1)
            self.assertEqual(link.select_one("#wash-cost-link a")["href"],
                             "/daily-cost-jp/tools/laundry-cost-per-wash/")
            self.assertIsNotNone(link.select_one("#current-ranking"))

    def test_verified_catalog_prefill_requires_recent_safe_quantity_and_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, _ = self._site(tmp)
            item = {
                "name": "アタック 洗濯洗剤 詰め替え 850g",
                "metric": "100g", "price": 850, "unit_price": 100,
                "postage": "送料込み", "confidence": .99,
                "url": "https://item.rakuten.co.jp/example-shop/850g/",
            }
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "categories": {"laundry": {"items": [item]}}
            }
            source = site / "data.json"
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            build(site)
            page = BeautifulSoup((site / "tools/laundry-cost-per-wash/index.html")
                                 .read_text(encoding="utf-8"), "html.parser")
            cards = page.select("#wash-verified-picks .pick-card")
            self.assertEqual(len(cards), 1)
            a = cards[0].select_one('button[data-pick-target="a"]')
            self.assertEqual(a["data-pick-price"], "850")
            self.assertEqual(a["data-pick-total"], "850")
            self.assertEqual(a["data-pick-unit"], "g")
            self.assertNotIn("data-pick-dose", a.attrs)
            self.assertIsNone(page.select_one('#wash-verified-picks a[href*="rakuten"]'))

            payload["updated_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            build(site)
            stale = (site / "tools/laundry-cost-per-wash/index.html").read_text(encoding="utf-8")
            self.assertNotIn('id="wash-verified-picks"', stale)

    def test_generator_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, category = self._site(tmp)
            build(site)
            first = category.read_bytes()
            build(site)
            self.assertEqual(category.read_bytes(), first)
            self.assertEqual(category.read_text(encoding="utf-8").count('id="wash-cost-link"'), 1)

    def test_existing_step6_seo_markup_is_byte_preserved(self):
        marker = '<section id="step6-comparison-help"><p data-verification="a &amp; b">重要FAQ</p></section>'
        with tempfile.TemporaryDirectory() as tmp:
            site, category = self._site(tmp)
            original = category.read_text(encoding="utf-8").replace(
                '<section id="current-ranking">', marker + '<section id="current-ranking">')
            category.write_text(original, encoding="utf-8")
            build(site)
            updated = category.read_text(encoding="utf-8")
            self.assertIn(marker, updated)
            self.assertEqual(updated.count(marker), 1)
            self.assertEqual(updated.replace(
                '\n' + updated[updated.index('<section id="wash-cost-link"'):
                   updated.index('</section>', updated.index('<section id="wash-cost-link"')) + len('</section>')] + '\n', ''),
                original)

    def test_orphan_page_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            with self.assertRaises(RuntimeError):
                build(site)
            self.assertFalse((site / "tools").exists())

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_javascript_calculation_and_error_boundaries(self):
        result = subprocess.run(
            ["node", "--test", str(ROOT / "tests/test_laundry_per_wash.cjs")],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
