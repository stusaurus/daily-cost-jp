"""Published category claims must match actual nonempty catalog categories."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_daily_deals import render_page
from redesign_laboratory import category_links, footer, published_category_count


class PublishedCategoryCountTests(unittest.TestCase):
    def test_count_follows_only_categories_with_published_items(self):
        categories = {
            "tissue": {"name": "ティッシュ", "items": [{"metric": "box"}]},
            "laundry": {"name": "洗濯洗剤", "items": [{"metric": "100g"}]},
            "empty": {"name": "候補なし", "items": []},
        }
        self.assertEqual(published_category_count(categories), 2)
        links = BeautifulSoup(category_links(categories), "html.parser")
        self.assertEqual(len(links.select("a.lab-category-link")), 2)
        self.assertIn("2カテゴリの比較", footer(published_category_count(categories)))
        categories["empty"]["items"] = [{"metric": "sheet"}]
        self.assertEqual(published_category_count(categories), 3)

    def test_daily_page_uses_runtime_count_not_stale_literal(self):
        now = datetime(2026, 11, 20, 9, tzinfo=ZoneInfo("Asia/Tokyo"))
        for count in (1, 25, 26):
            with self.subTest(count=count):
                page = render_page([], now, category_count=count)
                self.assertIn(f"楽天市場の日用品{count}カテゴリを送料込み", page)
                self.assertNotIn("21カテゴリ", page)
        self.assertIn("楽天市場の日用品を送料込み", render_page([], now))

    def test_no_hardcoded_old_catalog_size_in_display_generators(self):
        for path in (
            "scripts/redesign_laboratory.py",
            "scripts/build_daily_deals.py",
            "scripts/polish_home_design.py",
        ):
            with self.subTest(path=path):
                self.assertNotIn("21カテゴリ", (ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
