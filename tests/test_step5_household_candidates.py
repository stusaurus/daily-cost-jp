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

    def followup(self, extra, audit=False):
        ranked=[offer(qty=60,unit_price=70,suffix='bulk')]
        small=offer(qty=5,unit_price=400,suffix='small')
        everyday=offer(qty=15,unit_price=100,suffix='daily')
        calls=[]
        def fetch(cat,page):
            calls.append((cat['keyword'],page))
            if cat['keyword']==h.QUERIES['tissue']['small'][0]:return [small]
            if cat['keyword']==h.QUERIES['tissue']['everyday'][0]:return [everyday]
            if isinstance(extra,Exception):raise extra
            return extra
        before=copy.deepcopy(ranked)
        acquire=h.audit_acquisition if audit else h.acquire_household
        pool,report=acquire({'id':'tissue'},ranked,fetch,lambda row,cat:row,lambda n:None)
        self.assertEqual(ranked,before)
        self.assertLessEqual(len(calls),4);self.assertEqual(len(calls),len(set(calls)))
        return pool,report,calls,ranked

    def test_payment_inversion_uses_only_unused_fixed_query_and_preserves_other_slots(self):
        pool,report,calls,ranked=self.followup([offer(qty=10,unit_price=100,suffix='better')])
        self.assertEqual(len(calls),3)
        follow=report['requests'][-1]
        self.assertEqual((follow['purpose'],follow['phase'],follow['query_index']),('small','PAYMENT_FOLLOWUP',1))
        self.assertEqual(follow['decision'],'LOWER_CHECKOUT_TOTAL_SELECTED')
        slots=select_category('tissue',{'items':ranked,'purpose_candidates':pool})['slots']
        self.assertEqual(slots['small']['offer']['price'],1000)
        self.assertEqual(slots['everyday']['offer']['item_code'],'shop:daily')
        self.assertEqual(slots['bulk']['offer']['item_code'],'shop:bulk')

    def test_no_payment_inversion_keeps_early_exit_and_request_budget(self):
        _,report,calls=self.acquire([offer(qty=5,suffix='small'),offer(qty=15,suffix='daily')])
        self.assertEqual(len(calls),2)
        self.assertTrue(all(r['phase']=='INITIAL' for r in report['requests']))

    def test_followup_rejects_no_benefit_shipping_unknown_and_same_offer(self):
        for rows in ([offer(qty=10,unit_price=300,suffix='higher')],
                     [{**offer(qty=10,unit_price=100,suffix='bad'),'postage':'送料不明'}],
                     [offer(qty=5,unit_price=400,suffix='small')],
                     [offer(qty=60,unit_price=20,suffix='wrong-band')]):
            with self.subTest(rows=rows):
                pool,report,_,ranked=self.followup(rows)
                selected=select_category('tissue',{'items':ranked,'purpose_candidates':pool})['slots']['small']
                self.assertEqual(selected['offer']['item_code'],'shop:small')
                self.assertEqual(report['requests'][-1]['decision'],'KEEP_EXISTING_SELECTION')

    def test_followup_error_preserves_verified_pool_and_unknown_is_not_zero(self):
        pool,report,_,_=self.followup(RuntimeError('private 403 token'))
        self.assertTrue(pool);self.assertEqual(report['status'],'VERIFIED_CANDIDATES')
        row=report['requests'][-1]
        self.assertEqual(row['status'],'API_FETCH_FAILURE');self.assertIsNone(row['received'])
        self.assertNotIn('private',str(report))

    def test_followup_cannot_crowd_an_existing_purpose_out_of_thirty_offer_pool(self):
        extra=[offer(qty=10,unit_price=100,suffix=f'new{i}') for i in range(30)]
        pool,report,_,ranked=self.followup(extra)
        self.assertEqual(report['requests'][-1]['decision'],'KEEP_EXISTING_SELECTION')
        slots=select_category('tissue',{'items':ranked,'purpose_candidates':pool})['slots']
        self.assertEqual(slots['small']['offer']['item_code'],'shop:small')
        self.assertEqual(slots['everyday']['offer']['item_code'],'shop:daily')
        self.assertLessEqual(len(pool),h.MAX_CANDIDATES)

    def test_empty_or_failed_queries_never_exceed_original_four_request_cap(self):
        for result in ([],RuntimeError('429 private response')):
            _,report,calls=self.acquire(result)
            self.assertEqual(len(calls),h.MAX_REQUESTS)
            self.assertEqual(len(report['requests']),4)
            self.assertTrue(all(r['phase']=='INITIAL' for r in report['requests']))

    def test_live_audit_replays_baseline_without_second_api_acquisition(self):
        _,report,calls,_=self.followup([offer(qty=10,unit_price=100,suffix='better')],audit=True)
        proof=report['comparison']
        self.assertEqual((proof['baseline_request_count'],proof['candidate_request_count'],len(calls)),(2,3,3))
        self.assertEqual(proof['baseline_extra_api_requests'],0)
        self.assertEqual(proof['lower_total_purposes'],['small'])
        self.assertEqual(proof['baseline']['slots']['small']['total_yen'],2000)
        self.assertEqual(proof['candidate']['slots']['small']['total_yen'],1000)
        self.assertFalse(proof['same_product_savings_claim'])
        self.assertNotIn('shop:',str(proof));self.assertNotIn('https:',str(proof))


if __name__=='__main__':unittest.main()
