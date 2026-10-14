import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step4_recommendations as r
from test_step4_purchase_audit import offer, snapshot, NOW

class RecommendationsTests(unittest.TestCase):
    def test_bulk_ranking_and_small_independent(self):
        small=offer(qty=5,suffix='small')
        bulk=offer(qty=60,suffix='bulk',unit_price=70,title='ボックスティッシュ 200組 5箱×12パック')
        source={'items':[bulk], 'small_pack_offer':small};before=copy.deepcopy(source)
        result=r.select_category('tissue',source)
        self.assertEqual(source,before)
        self.assertEqual(result['slots']['small']['quantity'],5)
        self.assertEqual(result['slots']['bulk']['quantity'],60)
        self.assertIsNone(result['slots']['everyday'])
    def test_six_detergents_bulk_only(self):
        p=offer('laundry',30,'100ml',title='洗濯洗剤 500ml×6本')
        slots=r.select_category('laundry',{'items':[p]})['slots']
        self.assertIsNone(slots['small']);self.assertIsNone(slots['everyday']);self.assertIsNotNone(slots['bulk'])
    def test_six_small_bottles_never_fill_trial(self):
        p=offer('laundry',6,'100ml',title='洗濯洗剤 100ml×6')
        slots=r.select_category('laundry',{'items':[p]})['slots']
        self.assertIsNone(slots['small']);self.assertIsNone(slots['everyday']);self.assertIsNotNone(slots['bulk'])
    def test_three_offers_one_pack_not_three_choices(self):
        rows=[offer(qty=5,suffix=str(i)) for i in range(3)]
        result=r.select_category('tissue',{'items':rows})
        self.assertEqual(sum(x is not None for x in result['slots'].values()),1)
        self.assertIsNone(result['distinct_sku_count'])
    def test_unknown_or_mismatched_identity_rejected(self):
        for edit in ({'item_code':''},{'item_code':'shop:wrong'},{'url':'https://bad.rakuten.co.jp/shop/1/'},{'url':'https://item.rakuten.co.jp@evil.example/shop/1/'}):
            with self.subTest(edit=edit):
                p={**offer(),**edit};self.assertEqual(r.select_category('tissue',{'items':[p]})['status'],'NO_VERIFIED_CANDIDATES')
    def test_shipping_units_variable_price_url_rejected(self):
        for edit in ({'postage':'送料不明'},{'metric':'pack'},{'name':'ボックスティッシュ 5箱〜60箱から選べる'},{'name':'ボックスティッシュ 容量不明'},{'price':1},{'url':'http://item.rakuten.co.jp/shop/1/'}):
            self.assertEqual(r.select_category('tissue',{'items':[{**offer(),**edit}]})['status'],'NO_VERIFIED_CANDIDATES')
    def test_no_guessed_ply_or_mass_volume_comparison(self):
        p=offer('toilet-paper',12,'roll')
        self.assertEqual(r.select_category('toilet-paper',{'items':[p]})['status'],'NO_VERIFIED_CANDIDATES')
        rows=[offer('laundry',5,'100ml',suffix='a'),offer('laundry',20,'100g',suffix='b',title='洗濯洗剤 2000g')]
        self.assertIn('MULTIPLE_COMPARISON_FAMILIES_USE_CATEGORY_RANKING',r.select_category('laundry',{'items':rows})['reasons'])
    def test_untrusted_empty_api_failure_fail_closed(self):
        self.assertEqual(r.select(None, NOW)['categories'],{})
        self.assertEqual(r.select_category('tissue',{'items':[]})['status'],'NO_VERIFIED_CANDIDATES')
        self.assertEqual(r.select_category('tissue',{'items':[offer()],'error':'API'})['status'],'NO_VERIFIED_CANDIDATES')
    def test_selection_deterministic_and_no_brand_substitution(self):
        rows=[offer(qty=5,suffix='b',title='エリエール ボックスティッシュ 200組 5箱'),offer(qty=5,suffix='a')]
        a=r.select_category('tissue',{'items':rows});b=r.select_category('tissue',{'items':list(reversed(rows))})
        self.assertEqual(a,b)
        markup=r.block('tissue',a,'ティッシュ')
        self.assertIn('いつもの商品を探す',markup);self.assertNotIn('ブランド一致',markup)
    def test_safe_empty_guides_search(self):
        markup=r.block('tissue',r.select_category('tissue',{'items':[]}),'ティッシュ')
        self.assertEqual(markup.count('確認できる候補なし'),3);self.assertNotIn('class="buy-button"',markup)

if __name__=='__main__':unittest.main()
