import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from test_step4_purchase_audit import offer
import step5_household_candidates as h
from step5_prepare_preview import acquire_preview, public_query_evidence
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

    def test_current_small_query_comparison_reuses_responses_and_protects_source(self):
        bulk=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本',suffix='bulk')
        old=offer('laundry',3.8,'100g',title='洗濯洗剤 380g',unit_price=2500/3.8,suffix='old')
        current=offer('laundry',8.5,'100g',title='洗濯洗剤 850g',unit_price=1000/8.5,suffix='new')
        everyday=offer('laundry',20,'100g',title='洗濯洗剤 2000g',unit_price=75,suffix='daily')
        snapshot={'categories':{'laundry':{'items':[bulk,old]}}};original=copy.deepcopy(snapshot)
        plan=copy.deepcopy(h.QUERIES);calls=[]
        def fetch(cat,page):
            q=cat['keyword'];calls.append(q)
            if '850g' in q:return [current]
            if '400g' in q or '900g' in q:return []
            return [everyday]
        revised,result=acquire_preview(snapshot,[{'id':'laundry'}],fetch,lambda r,c:r,lambda n:None)
        self.assertEqual(snapshot,original);self.assertEqual(h.QUERIES,plan)
        self.assertEqual(revised['categories']['laundry']['items'],original['categories']['laundry']['items'])
        self.assertEqual(len(calls),4);self.assertEqual(len(calls),len(set(calls)))
        self.assertEqual(result['status'],'OBSERVED');self.assertTrue(result['small_payment_lower'])
        self.assertTrue(result['other_slots_unchanged'])
        self.assertEqual(result['candidate']['small']['quantity'],8.5)
        self.assertEqual(result['candidate']['small']['price_total_yen'],1000)
        self.assertNotIn('shop:',str(result));self.assertNotIn('洗濯洗剤 850g',str(result))

    def test_query_comparison_api_failure_is_unknown_not_improvement(self):
        bulk=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        calls=[];plan=copy.deepcopy(h.QUERIES)
        def fetch(cat,page):
            calls.append(cat['keyword']);raise RuntimeError('403 private token')
        _,result=acquire_preview({'categories':{'laundry':{'items':[bulk]}}},
            [{'id':'laundry'}],fetch,lambda r,c:r,lambda n:None)
        self.assertEqual(len(calls),5);self.assertEqual(len(set(calls)),5)
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['small_payment_lower'])
        self.assertEqual(h.QUERIES,plan);self.assertNotIn('private',str(result))

    def test_query_comparison_does_not_create_or_mix_other_sites_or_categories(self):
        snapshot={'categories':{'other':{'items':[{'untouched':True}]}}}
        revised,result=acquire_preview(snapshot,[{'id':'other'}],
            lambda *args:self.fail('Unexpected API call'),lambda r,c:r,lambda n:None)
        self.assertEqual(revised,snapshot);self.assertIsNone(result)

    def test_query_comparison_without_confirmed_family_is_unknown(self):
        mass=offer('laundry',90,'100g',title='洗濯洗剤 1500g×6本')
        volume=offer('laundry',90,'100ml',title='洗濯洗剤 1500ml×6本')
        _,result=acquire_preview({'categories':{'laundry':{'items':[mass,volume]}}},
            [{'id':'laundry'}],lambda *args:self.fail('Unexpected API call'),lambda r,c:r,lambda n:None)
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['small_payment_lower'])
        self.assertEqual(result['unique_api_queries'],0)

    def test_tissue_plan_comparison_preserves_small_bulk_and_uses_actual_pack_quantity(self):
        bulk=offer(qty=60,suffix='bulk',title='ボックスティッシュ 400枚 200組 5箱×12パック')
        small=offer(qty=5,suffix='small')
        daily=offer(qty=15,unit_price=120,suffix='daily',title='ボックスティッシュ 300枚 150組 5箱×3個')
        premium=offer(qty=20,unit_price=350,suffix='premium')
        snapshot={'categories':{'tissue':{'items':[bulk]}}};before=copy.deepcopy(snapshot)
        calls=[]
        def fetch(cat,page):
            q=cat['keyword'];calls.append(q)
            if q==h.QUERIES['tissue']['small'][0]:return [small]
            if q=='ボックスティッシュ 15箱':return [] if cat.get('_household_require_reviews') else [daily,bulk]
            return [premium]
        revised,r=acquire_preview(snapshot,[{'id':'tissue'}],fetch,lambda row,c:row,lambda n:None,
            comparison_category='tissue',baseline_queries={'everyday':('ボックスティッシュ 15箱','ボックスティッシュ 20箱')},
            baseline_tissue_reviews=True)
        self.assertEqual(snapshot,before);self.assertEqual(len(calls),4)
        self.assertEqual({q['has_review_flag'] for q in r['query_evidence']
                          if q['keyword']=='ボックスティッシュ 15箱'},{0,1})
        self.assertEqual(r['payment_lower_purposes'],['everyday'])
        self.assertEqual(r['unchanged_purposes'],['small','bulk'])
        self.assertEqual(r['candidate']['everyday']['tissue_specification'],
            {'boxes':15,'pairs_per_box':150,'total_pairs':2250,'sheets_per_box':300,'sheets_per_pair':2})
        self.assertIsNone(r['candidate']['small']['tissue_specification']['sheets_per_pair'])
        self.assertEqual(revised['categories']['tissue']['household_acquisition']['requests'][1]['excluded_reasons'],{'requested_purpose_mismatch':1})

    def test_non_laundry_comparison_requires_explicit_baseline(self):
        with self.assertRaises(ValueError):
            acquire_preview({},[],lambda *args:[],lambda r,c:r,lambda n:None,comparison_category='tissue')

    def test_public_evidence_allowlist_drops_credentials_and_keeps_actual_title_quantity(self):
        raw={'Item':{'itemName':'ボックスティッシュ 200組 5箱×3パック','itemCode':'shop:item',
            'itemPrice':1800,'postageFlag':0,'itemUrl':'https://item.rakuten.co.jp/shop/item/',
            'applicationId':'SECRET_APP','accessKey':'SECRET_KEY','itemCaption':'not exported'}}
        result=public_query_evidence({'id':'tissue','keyword':'ティッシュ 15箱'},1,[raw],
            lambda r,c:offer(qty=15,title=r['Item']['itemName']))
        text=str(result)
        self.assertNotIn('SECRET',text);self.assertNotIn('itemCaption',text)
        self.assertEqual(result['items'][0]['parsed_quantity']['quantity'],15)
        self.assertEqual(result['items'][0]['itemCode'],'shop:item')
        self.assertIsNone(result['items'][0]['individual_gate_reason'])
        self.assertEqual(public_query_evidence({'id':'tissue','keyword':'x'},1,[],lambda *a:None)['status'],'API_RESPONSE_ZERO')
        self.assertEqual(public_query_evidence({'id':'tissue','keyword':'x'},1,{'error':'secret'},lambda *a:None)['status'],'MALFORMED')

    def test_review_filter_changes_only_tissue_everyday_household_requests(self):
        from unittest.mock import patch
        from urllib.parse import urlsplit,parse_qs
        import os
        with patch.dict(os.environ,{'RAKUTEN_APPLICATION_ID':'offline-test','RAKUTEN_ACCESS_KEY':'offline-test'}):
            import build_site_entry as entry
        base={'id':'tissue','keyword':'ボックスティッシュ 15箱','_household':True,
              '_supplementary':True,'_household_purpose':'everyday'}
        for overrides,flag in (({},'0'),({'_household_require_reviews':True},'1'),
            ({'_household_purpose':'small'},'1'),({'id':'laundry'},'1'),
            ({'_household':False},'1'),({'_household_purpose':None},'1')):
            with self.subTest(overrides=overrides),patch.object(entry,'fetch_json',return_value={'Items':[]}) as fetch:
                entry.fetch_page({**base,**overrides},1)
                params=parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)
                self.assertEqual(params['hasReviewFlag'],[flag])
                self.assertEqual(params['postageFlag'],['1'])
                self.assertEqual(params['imageFlag'],['1'])
                self.assertEqual(params['hits'],['30'])

    def test_review_filter_cache_separates_both_plans_with_five_query_cap(self):
        bulk=offer(qty=60,suffix='bulk',title='ボックスティッシュ 400枚 200組 5箱×12パック')
        small=offer(qty=5,suffix='small');premium=offer(qty=20,suffix='premium')
        calls=[]
        def fetch(cat,page):
            calls.append((cat['keyword'],cat.get('_household_require_reviews')))
            if cat['_household_purpose']=='small':return [small]
            if cat['keyword'].endswith('15箱'):return []
            return [premium]
        _,r=acquire_preview({'categories':{'tissue':{'items':[bulk]}}},[{'id':'tissue'}],
            fetch,lambda x,c:x,lambda n:None,comparison_category='tissue',
            baseline_queries={'everyday':h.QUERIES['tissue']['everyday']},baseline_tissue_reviews=True)
        self.assertEqual(len(calls),5);self.assertEqual(r['unique_api_queries'],5)
        self.assertEqual(r['status'],'OBSERVED');self.assertEqual(r['payment_lower_purposes'],[])


if __name__=='__main__':unittest.main()
