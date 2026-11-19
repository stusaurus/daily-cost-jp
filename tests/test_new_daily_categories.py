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
        # "ケース" is already blocked by the earlier accessory gate.
        # Either reject reason protects against inventing a total sheet count.
        self.assertIsNotNone(
            q.category_rejection('wet-wipes','除菌ウェットティッシュ 80枚x3ケース'))
        self.assertFalse(q.category_is_suitable('kitchen-paper','キッチンペーパー80枚 3巻'))

    def test_kitchen_paper_rolls_require_proven_sheet_total(self):
        for name,total in [
            ('キッチンペーパー80枚x2ロール',160),
            ('クッキングペーパー100カットx2ロール',200),
            ('キッチンタオル80枚x3巻',240),
        ]:
            with self.subTest(name=name):
                self.assertTrue(q.category_is_suitable('kitchen-paper',name),name)
                parsed=q.parsed_quantity('kitchen-paper',name)
                self.assertEqual(parsed['metric'],'sheet')
                self.assertEqual(parsed['quantity'],total)
        for name in [
            'キッチンペーパー80枚 2ロール',
            'キッチンペーパー100カット 3ロール',
            'キッチンペーパー80枚x2ロール 10袋'
        ]:
            with self.subTest(name=name):
                self.assertFalse(q.category_is_suitable('kitchen-paper',name),name)

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

    def test_seller_cannot_pass_bundled_holder_as_sink_net(self):
        unsafe=[
            '排水口 水切りネットホルダー ステンレス シンク対応 ネット100枚',
            '吸盤式 キッチン水切りネットホルダー 100枚付き',
            'キッチンドレイン 生ごみスタンド 水切りネット100枚付き',
            'シンク 排水口 ゴミ受け ホルダー ネット100枚',
        ]
        for name in unsafe:
            with self.subTest(name=name):
                self.assertEqual(q.category_rejection('sink-net',name),'wrong_use_or_type')
        self.assertTrue(q.category_is_suitable(
            'sink-net','台所 排水口 水切りネット 100枚入り'))
        self.assertTrue(q.category_is_suitable(
            'sink-net','水切りネット 浅型 排水口用 100枚入り'))


    def test_wet_wipe_selectable_type_is_not_fixed(self):
        self.assertFalse(q.category_is_suitable(
            'wet-wipes','除菌ウェットティッシュ80枚 アルコールorノンアルコール'))
        self.assertEqual(q.category_rejection('wet-wipes',
            '除菌ウェットティッシュ80枚 アルコール/ノンアルコール'),
            'selectable_type_variant')
        self.assertTrue(q.category_is_suitable(
            'wet-wipes','ノンアルコール 除菌ウェットティッシュ 80枚'))
        self.assertEqual(q.category_rejection(
            'wet-wipes','除菌ウェットティッシュ 480枚 WTS-60N WTS-60A'),
            'selectable_type_variant')


    def test_explicit_nested_kitchen_paper_packages_count_all_sheets(self):
        for name,total in [
            ('リード クッキングペーパー 100枚×2ロ−ル×8袋 1 ケース キッチンペーパー',1600),
            ('フジ キッチンペーパー 100枚×2ロール×10袋／ケース 不織布',2000),
            ('花王 シェフ キッチンペーパー 100枚×2ロール×6 ケース販売',1200),
            ('キッチンペーパー NEO 1箱 80枚×2ロール×10袋',1600),
        ]:
            with self.subTest(name=name):
                self.assertTrue(q.category_is_suitable('kitchen-paper', name))
                parsed=q.parsed_quantity('kitchen-paper',name)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed['metric'],'sheet')
                self.assertEqual(parsed['quantity'],total)
                row={'name':name,'price':4000,'unit_price':4000/total,'metric':'sheet',
                     'confidence':.99,'postage':'送料込み',
                     'url':'https://item.rakuten.co.jp/example/paper/'}
                self.assertIsNone(q.item_rejection('kitchen-paper',row))
        for title in [
            'キッチンペーパー80枚×2ロール×6',
            'キッチンペーパー80枚×2ロール 6袋入',
            'キッチンペーパー80枚×2ロール×6袋×2ケース',
            'キッチンペーパー80枚×2ロール×6袋 50枚入り',
            'キッチンペーパー80枚×2ロール×6袋 2ロールおまけ',
        ]:
            with self.subTest(title=title):
                self.assertFalse(q.category_is_suitable('kitchen-paper',title)
                                 and q.parsed_quantity('kitchen-paper',title) is not None)

    def test_kitchen_paper_retail_context_is_not_mistaken_for_accessory(self):
        # Seller descriptions may mention nonwoven paper or storage use;
        # neither identifies the item as a cloth or a storage container.
        safe = [
            'キッチンペーパー 厚手 不織布 80枚×2ロール 食器の収納にも',
            '大黒工業 キッチンペーパー 80枚×2ロール ケース販売 お徳用'
        ]
        for title in safe:
            with self.subTest(title=title):
                self.assertTrue(q.category_is_suitable('kitchen-paper',title),title)
                self.assertEqual(q.parsed_quantity('kitchen-paper',title)['quantity'],160)
        self.assertFalse(q.category_is_suitable(
            'kitchen-paper','キッチンペーパーホルダー 80枚×2ロール'))

    def test_selectable_wet_wipe_formulas_with_ampersand_are_excluded(self):
        for title in [
            '除菌ウェットティッシュ 80枚 アルコール&ノンアルコール',
            '除菌ウェットティッシュ 80枚 ノンアルコールorアルコール',
            '除菌ウェットティッシュ 80枚 アルコール/ノンアルコール'
        ]:
            with self.subTest(title=title):
                self.assertEqual(q.category_rejection('wet-wipes',title),'selectable_type_variant')
        self.assertTrue(q.category_is_suitable(
            'wet-wipes','除菌ウェットティッシュ80枚 ノンアルコール'))

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
