import copy
import json
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
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
    def test_detergent_unbracketed_multipacks_are_bulk_not_everyday(self):
        cases = (
            ('【3セット】 洗濯洗剤 850g', 'bulk'),
            ('洗濯洗剤 850g 3セット', 'bulk'),
            ('洗濯洗剤 850g 3本セット', 'bulk'),
            ('洗濯洗剤 850g×3袋', 'bulk'),
            ('洗濯洗剤 850g 2セット', 'everyday'),
            ('洗濯洗剤 850g 先着3セット限定', 'everyday'),
        )
        for name,expected in cases:
            with self.subTest(name=name):
                self.assertEqual(r.sale_band('laundry',{'name':name,'metric':'100g'},25.5),expected)

    def test_unbracketed_three_sets_cannot_enter_everyday_supplementary_pool(self):
        bulk=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        three=offer('laundry',25.5,'100g',title='洗濯洗剤 850g 3セット',suffix='three')
        result=r.select_category('laundry',{'items':[bulk],'purpose_candidates':[three]})
        self.assertIsNone(result['slots']['everyday'])
        self.assertIsNone(result['slots']['small'])
        self.assertIsNotNone(result['slots']['bulk'])

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

    def test_priority_pages_have_one_gated_quantity_selector_and_exact_links(self):
        from redesign_laboratory import buying_modes_markup
        categories={
            'tissue':{'items':[offer(qty=n,suffix=f't{n}') for n in (5,15,60)]},
            'laundry':{'items':[offer('laundry',n,'100ml',suffix=f'l{n}') for n in (5,20,100)]},
            'toilet-paper':{'items':[offer('toilet-paper',n,'roll',suffix=f'p{n}',
                title=f'トイレットペーパー ダブル 30m {n}ロール') for n in (12,24,48)]}}
        source=snapshot(categories);before=copy.deepcopy(source)
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/'data.json').write_text(json.dumps(source))
            original={}
            for cid,c in categories.items():
                path=site/'categories'/cid/'index.html';path.parent.mkdir(parents=True)
                original[cid]='<html><head><title>比較</title></head><body><main>'+buying_modes_markup(cid,c)+'<section id="purchase-tools"></section><a id="rank" href="'+c['items'][0]['url']+'">単価ランキング</a></main></body></html>'
                path.write_text(original[cid])
            with patch.object(r,'select',wraps=partial(r.select,now=NOW)):
                r.apply(site,enabled=False)
                for cid in categories:
                    self.assertEqual((site/'categories'/cid/'index.html').read_text(),original[cid])
                report=r.apply(site,enabled=True)
            for cid in categories:
                markup=BeautifulSoup((site/'categories'/cid/'index.html').read_text(),'html.parser')
                self.assertFalse(markup.select('.lab-buy-modes'))
                self.assertEqual(len(markup.select('.step4-recommendations')),1)
                self.assertEqual(len(markup.select('.step4-purpose')),3)
                self.assertEqual(markup.select_one('#rank')['href'],categories[cid]['items'][0]['url'])
                links=markup.select('[data-purchase-purpose]')
                self.assertEqual(len({a['href'] for a in links}),3)
                for a in links:
                    row=report['categories'][cid]['slots'][a['data-purchase-purpose']]
                    self.assertEqual(a['href'],row['offer']['url'])
                    self.assertEqual(float(a['data-shipping-price']),row['offer']['price'])
                    self.assertIn('sponsored',a['rel'])
            self.assertEqual(source,before)

    def test_untrusted_catalog_does_not_restore_legacy_recommendations(self):
        from redesign_laboratory import buying_modes_markup
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/'data.json').write_text(json.dumps(snapshot({'tissue':{'items':[offer()]}})))
            page=site/'index.html';markup='<html><head></head><body><main>'+buying_modes_markup('tissue',{'items':[offer()]})+'</main></body></html>'
            page.write_text(markup)
            with patch.object(r,'select',return_value={'status':'UNTRUSTED','categories':{},'catalog_updated_at':None}):
                r.apply(site,enabled=True)
            self.assertEqual(page.read_text(),markup)
            self.assertNotIn('lab-buy-modes',markup)

if __name__=='__main__':unittest.main()
