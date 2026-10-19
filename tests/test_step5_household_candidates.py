import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from test_step4_purchase_audit import offer
import step5_household_candidates as h
from step4_recommendations import select_category


class HouseholdTests(unittest.TestCase):
    def acquire(self, rows, ranked=None, cid='tissue'):
        baseline = ranked or [offer(qty=60, title='ボックスティッシュ 200組 5箱×12パック')]
        calls = []
        def fetch(cat, page):
            calls.append(cat)
            if isinstance(rows, Exception): raise rows
            if callable(rows):return rows(cat,page)
            return rows
        pool, report = h.acquire_household({'id':cid}, baseline, fetch, lambda r,c:r, lambda n:None)
        return pool, report, calls

    def test_small_and_everyday_independent_without_ranking_mutation(self):
        rows = [offer(qty=5, suffix='small'), offer(qty=15, suffix='daily')]
        pool, report, calls = self.acquire(rows)
        self.assertEqual(report['eligible_by_purpose'], {'small':1, 'everyday':1, 'bulk':0})
        data={'items':[offer(qty=60, title='ボックスティッシュ 200組 5箱×12パック')]};before=copy.deepcopy(data['items'])
        h.attach(data,pool,report)
        self.assertEqual(data['items'],before)
        slots=select_category('tissue',data)['slots']
        self.assertEqual([slots[p]['quantity'] for p in slots],[5,15,60])
        self.assertTrue(all(c['_household'] and c['_supplementary'] for c in calls))

    def test_shipping_quantity_identity_and_invalid_urls_remain_rejected(self):
        for edit in ({'postage':'送料不明'},{'name':'ボックスティッシュ 5箱〜60箱から選べる'},
                     {'item_code':''},{'url':'https://evil.example/item'}, {'metric':'pack'}):
            with self.subTest(edit=edit):
                pool,report,calls=self.acquire([{**offer(),**edit}]);self.assertEqual(pool,[])
                self.assertLessEqual(len(calls),4);self.assertTrue(report['reasons'])

    def test_api_failure_not_zero_and_empty_response_distinguished(self):
        self.assertEqual(self.acquire(RuntimeError('private API key'))[1]['status'],'ACQUISITION_UNAVAILABLE')
        report=self.acquire([])[1]
        self.assertEqual(report['status'],'NO_VERIFIED_CANDIDATES')
        self.assertTrue(all(r['status']=='API_RESPONSE_ZERO' for r in report['requests']))
        self.assertNotIn('private',str(self.acquire(RuntimeError('private API key'))[1]))

    def test_case_bulk_never_fills_small_or_everyday(self):
        pool,report,calls=self.acquire([offer(qty=60,title='ボックスティッシュ 200組 5箱×12パック')])
        self.assertEqual(pool,[]);self.assertGreater(report['reasons']['requested_purpose_mismatch'],0)

    def test_detergent_six_pack_not_household(self):
        p=offer('laundry',30,'100g',title='洗濯洗剤 500g×6本')
        bulk=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        self.assertEqual(self.acquire([p],[bulk],'laundry')[0],[])

    def test_no_mass_volume_or_ply_replacement(self):
        volume=offer('laundry',15,'100ml',title='洗濯洗剤 1500ml')
        mass=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        pool,report,_=self.acquire([volume],[mass],'laundry')
        self.assertEqual(pool,[]);self.assertIn('incompatible_comparison_family',report['reasons'])

    def test_deterministic_and_duplicate_offers_not_distinct_sku(self):
        a=offer(qty=5,suffix='a');b=offer(qty=15,suffix='b')
        p,r,_=self.acquire([a,b,a]);p2,r2,_=self.acquire([b,a,a])
        self.assertEqual(p,p2);self.assertIsNone(r['distinct_sku_count'])
        self.assertLessEqual(len(p),30)

    def test_malformed_untrusted_pool_cannot_recommend(self):
        for pool in ([None],[offer()]*31,'not a list'):
            slots=select_category('tissue',{'items':[],'purpose_candidates':pool})['slots']
            self.assertTrue(all(v is None for v in slots.values()))

    def test_workwear_specific_product_not_everyday_household(self):
        p=offer('laundry',20,'100g',title='洗濯洗剤 作業着専用 詰め替え 2000g')
        bulk=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        pool,report,_=self.acquire([p],[bulk],'laundry')
        self.assertEqual(pool,[]);self.assertGreater(report['reasons']['specialized_household_use_unconfirmed'],0)

    def test_specialized_lotion_tissue_not_default_household_replacement(self):
        p=offer(qty=20,title='ボックスティッシュ 鼻セレブ 保湿 200組 20箱')
        pool,report,_=self.acquire([p])
        self.assertEqual(pool,[]);self.assertGreater(report['reasons']['specialized_household_use_unconfirmed'],0)

    def test_business_only_offer_not_recommended_to_households(self):
        for title in ('ボックスティッシュ 220組 20箱 法人・企業様限定販売',
                      'ボックスティッシュ 200組 20箱 事業者限定'):
            pool,report,_=self.acquire([offer(qty=20,title=title)])
            self.assertEqual(pool,[])
            self.assertGreater(report['reasons']['specialized_household_use_unconfirmed'],0)

    def test_request_trace_distinguishes_fallback_from_early_exit(self):
        def rows(cat,page):
            if cat['keyword']==h.QUERIES['tissue']['small'][0]:
                return [offer(qty=60),{**offer(),'postage':'送料不明'}]
            if cat['keyword']==h.QUERIES['tissue']['small'][1]:return [offer(suffix='small')]
            return [offer(qty=20,suffix='everyday')]
        pool,report,calls=self.acquire(rows)
        self.assertEqual(len(calls),3)
        first,second,third=report['requests']
        self.assertEqual([r['query_index'] for r in report['requests']],[0,1,0])
        self.assertEqual([r['early_exit'] for r in report['requests']],[False,False,True])
        self.assertEqual(first['excluded_reasons']['requested_purpose_mismatch'],1)
        self.assertEqual(first['eligible'],0)
        self.assertEqual(second['excluded_reasons'],{})
        self.assertEqual(report['eligible_by_purpose'],{'small':1,'everyday':1,'bulk':0})
        self.assertEqual(report['request_diagnostics_scope'],'PER_RESPONSE_BEFORE_WHOLE_POOL_GATE')

    def test_request_failures_remain_unknown_and_do_not_expose_exception(self):
        _,report,calls=self.acquire(RuntimeError('403 private token'))
        self.assertEqual(len(calls),h.MAX_REQUESTS)
        for r in report['requests']:
            self.assertIsNone(r['received']);self.assertFalse(r['early_exit'])
            self.assertEqual(r['excluded_reasons'],{'api_fetch_failure':1})
        self.assertNotIn('private',str(report));self.assertNotIn('403',str(report))

    def test_query_dedupe_reasons_and_public_counts_do_not_claim_distinct_skus(self):
        a=offer(suffix='small');b=offer(qty=20,suffix='daily')
        _,report,_=self.acquire([a,a,b])
        self.assertEqual(report['requests'][0]['excluded_reasons']['duplicate_offer'],1)
        self.assertIsNone(report['distinct_sku_count'])
        self.assertNotIn('shop:',str(report));self.assertNotIn('ボックスティッシュ',str(report))


if __name__=='__main__':unittest.main()
