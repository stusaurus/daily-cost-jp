"""Strict regression guards for four new unit-price categories."""
import ast
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import product_quality as q
from candidate_acquisition import SUPPLEMENTAL_QUERIES, MAX_REQUESTS


def constant_from_file(path, name):
    tree=ast.parse((ROOT/path).read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f'Missing {name} from {path}')


class NewCategorySafetyTests(unittest.TestCase):
    CATEGORIES=('toothpaste','wet-wipes','kitchen-paper','sink-net')

    def test_all_twenty_five_categories_have_safety_contract(self):
        original=constant_from_file('scripts/build_site.py','CATEGORIES')
        additional=constant_from_file('scripts/build_site_growth.py','ADDITIONAL_CATEGORIES')
        ids=[row['id'] for row in original+additional]
        self.assertEqual(len(ids),25)
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),set(q.REQUIRED))
        self.assertEqual(set(ids),set(q.EXCLUDED))
        self.assertTrue(set(self.CATEGORIES).issubset(ids))
        self.assertEqual(set(self.CATEGORIES)-{'toothpaste'},
                         set(self.CATEGORIES)&set(q.COUNT_UNITS))
        for cid in self.CATEGORIES:
            self.assertIn(cid,SUPPLEMENTAL_QUERIES)
            self.assertLessEqual(MAX_REQUESTS,5)

    def test_toothpaste_requires_explicit_mass_not_volume(self):
        self.assertEqual(q.parsed_quantity('toothpaste','薬用 歯磨き粉120g')['metric'],'100g')
        self.assertEqual(q.parsed_quantity('toothpaste','歯磨き粉120g x 3本')['quantity'],3.6)
        self.assertIsNone(q.parsed_quantity('toothpaste','歯磨き粉120ml'))
        self.assertFalse(q.category_is_suitable('toothpaste','歯磨き粉100g 歯ブラシセット'))
        self.assertFalse(q.category_is_suitable('toothpaste','犬用 歯磨き粉100g'))

    def test_sheet_count_and_multipliers_are_not_guessed(self):
        for cid,title,expected in [
            ('wet-wipes','アルコール 除菌ウェットティッシュ 80枚x3袋',240),
            ('kitchen-paper','クッキングペーパー シート型 100枚x2袋',200),
            ('sink-net','キッチン 排水口ネット 50枚x4袋',200),
        ]:
            with self.subTest(cid=cid):
                self.assertTrue(q.category_is_suitable(cid,title))
                self.assertEqual(q.parsed_quantity(cid,title)['quantity'],expected)
        for cid,title in [
            ('wet-wipes','アルコール 除菌ウェットティッシュ80枚 3袋'),
            ('kitchen-paper','キッチンペーパー100枚 2パック'),
            ('sink-net','台所 排水口ネット50枚 4袋')
        ]:
            with self.subTest(cid=cid):
                self.assertEqual(q.category_rejection(cid,title),'package_multiplier_unconfirmed')

    def test_shorthand_nested_packs_and_rolled_sheets_fail_closed(self):
        self.assertEqual(
            q.category_rejection('wet-wipes','除菌ウェットティッシュ 80枚x3P'),
            'package_multiplier_unconfirmed')
        self.assertEqual(
            q.category_rejection('sink-net','キッチン 排水口ネット 50枚x2袋x3セット'),
            'multiple_unverified_pack_levels')
        self.assertEqual(
            q.category_rejection('wet-wipes','除菌ウェットティッシュ 80枚x3ケース'),
            'multiple_unverified_pack_levels')
        self.assertFalse(q.category_is_suitable('kitchen-paper','キッチンペーパー80枚x3巻'))

    def test_rolls_other_uses_and_accessories_rejected(self):
        for cid,bad in [
            ('wet-wipes','トイレ用 除菌ウェットティッシュ80枚'),
            ('wet-wipes','犬用 除菌ウェットティッシュ80枚'),
            ('wet-wipes','ウェットティッシュケース 除菌用80枚'),
            ('kitchen-paper','キッチンペーパー100カット2ロール'),
            ('kitchen-paper','キッチンペーパー ロール80枚'),
            ('sink-net','浴室 排水口ネット100枚'),
            ('sink-net','キッチン 排水口ネットケース100枚'),
            ('toothpaste','歯磨き粉 120ml')
        ]:
            with self.subTest(title=bad):
                row=q.parsed_quantity(cid,bad)
                self.assertTrue(q.category_rejection(cid,bad) is not None or row is None)

    def test_quality_requires_matching_price_shipping_and_metric(self):
        goods=[
            ('toothpaste','薬用 歯磨き粉120g','100g',1.2),
            ('wet-wipes','除菌ウェットティッシュ80枚','sheet',80),
            ('kitchen-paper','キッチンペーパー シート 100枚','sheet',100),
            ('sink-net','台所 排水口 ネット 100枚','sheet',100),
        ]
        for cid,name,metric,qty in goods:
            with self.subTest(cid=cid):
                base={'name':name,'price':1200,'unit_price':1200/qty,
                      'metric':metric,'confidence':.99,'postage':'送料込み',
                      'url':'https://item.rakuten.co.jp/example/ok/'}
                self.assertIsNone(q.item_rejection(cid,base))
                self.assertEqual(len(q.filter_items(cid,[base])),1)
                for key,value in [('postage','送料別'),('unit_price',1),('metric','box')]:
                    row={**base,key:value}
                    self.assertIsNotNone(q.item_rejection(cid,row))


if __name__=='__main__':
    unittest.main()
