import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
os.environ.setdefault('RAKUTEN_APPLICATION_ID', 'offline-test')
os.environ.setdefault('RAKUTEN_ACCESS_KEY', 'offline-test')
import build_site_entry as entry


class QuantityRankingTests(unittest.TestCase):
    def test_selectable_packs_cannot_be_ranked_at_maximum_pack_size(self):
        for title in ['【選べる1～4個】アタックZERO 2100g', 'アリエール2580g×6袋 4袋 2袋']:
            self.assertIsNone(entry.safer_parse_measure_quantity(title, 'measure'))
            self.assertFalse(entry.category_is_suitable('laundry', title))

    def test_stock_limit_is_not_pack_size(self):
        result = entry.safer_parse_measure_quantity('先着100本限定 マウスウォッシュ500ml 1本', 'measure')
        self.assertEqual(result['quantity'], 5)

    def test_safe_bulk_pack_keeps_its_quantity(self):
        self.assertEqual(entry.safer_parse_measure_quantity('【6個セット】さらさ1490g', 'measure')['quantity'], 89.4)

    def test_iri_bulk_sheet_pack_is_not_counted_as_one_pack(self):
        title = '山崎産業 フローリング用 ウェットシート 20枚入り×50個（1ケース）'
        parsed = entry.safer_parse_count_quantity(title, {'枚': 'sheet'})
        self.assertEqual(parsed['quantity'], 1000)
        from sale_quantity import sale_quantity_for_item
        self.assertEqual(sale_quantity_for_item(title, 4480, 4.48, 'sheet')['sale_quantity_label'], '20枚×50個')
