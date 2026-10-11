import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step5_evaluation as e
from test_step4_purchase_audit import offer,snapshot


class EvaluationTests(unittest.TestCase):
    def test_missing_data_not_zero_revenue_or_success(self):
        r=e.evaluate(None)
        self.assertIsNone(r['sales']['confirmed_reward_yen']);self.assertIsNone(r['sales']['orders'])
        self.assertIsNone(r['ga4']['current']);self.assertEqual(r['evaluation'],'INSUFFICIENT_COMPARABLE_DATA')

    def test_unregistered_dimension_counts_unknown_or_unavailable(self):
        rows=[('2026-10-01','https://stusaurus.github.io/daily-cost-jp/','small','0',5)]
        r=e.aggregate_purpose(rows,['2026-09-12','2026-10-09'],{'purchase_purpose':True,'operator_test':False})
        self.assertEqual(r['counts']['/']['small']['unknown'],5)
        self.assertIsNone(e.aggregate_purpose(rows,['2026-09-12','2026-10-09'],{})['counts'])

    def test_operator_unknown_and_out_of_scope_never_users(self):
        rows=[('2026-10-08','https://stusaurus.github.io/daily-cost-jp/products/?q=private-address',p,f,n) for p,f,n in [('small','1',4),('bulk','(not set)',2),('everyday','0',1)]]
        rows.append(('2026-10-08','https://evil.example/daily-cost-jp/','small','0',500))
        r=e.aggregate_purpose(rows,['2026-09-12','2026-10-09'],{'purchase_purpose':True,'operator_test':True})
        self.assertEqual(r['counts']['/products/']['small']['operator'],4)
        self.assertEqual(r['counts']['/products/']['bulk']['unknown'],2)
        self.assertFalse(r['real_users_verified']);self.assertNotIn('private',json.dumps(r));self.assertNotIn('evil',json.dumps(r))

    def test_equal_seven_windows_and_invalid_count(self):
        r=e.aggregate_purpose([('2026-10-01','https://stusaurus.github.io/daily-cost-jp/','small','0',2),('2026-10-08','https://stusaurus.github.io/daily-cost-jp/','small','0',3)],['2026-09-12','2026-10-09'],{'purchase_purpose':True,'operator_test':True})
        self.assertEqual(r['seven_day_windows']['last_7']['clicks']['non_operator'],3)
        self.assertEqual(r['seven_day_windows']['prior_7']['clicks']['non_operator'],2)
        with self.assertRaises(ValueError):e.aggregate_purpose([('2026-10-01','x','small','0',-1)],['2026-09-12','2026-10-09'],{})

    def test_gsc_only_aggregate_independent_not_raw_query(self):
        r=e.evaluate(None,gsc={'source':'Search Console Search Analytics API','queries':['private raw text'],'windows':{},'site_aggregates':{}})
        self.assertNotIn('private',json.dumps(r));self.assertFalse(r['cross_source_user_join'])

    def test_assortment_amounts_empty_slots_no_source_mutation(self):
        tissue={'items':[offer(qty=60,title='ボックスティッシュ 200組 5箱×12パック')],'purpose_candidates':[offer(qty=5,suffix='s'),offer(qty=15,suffix='d')]}
        s=snapshot({'tissue':tissue,'laundry':{'items':[]},'toilet-paper':{'items':[]}});before=copy.deepcopy(s)
        r=e.assortment(s)
        self.assertEqual(s,before);self.assertEqual(r['empty_slots'],6)
        self.assertEqual(r['categories']['tissue']['slots']['small']['total_yen'],500)
        self.assertIsNone(r['categories']['tissue']['distinct_sku_count'])

    def test_bad_supplement_does_not_invent_candidates(self):
        s=snapshot({c:{'items':[],'purpose_candidates':'bad'} for c in e.CATEGORIES})
        r=e.assortment(s);self.assertEqual(r['empty_slots'],9)

    def test_sufficient_data_ready_for_review_never_automatic_success(self):
        def window(period):
            return {'source':'GA4 Data API','period':period,'response_complete':True,'operator_dimension_registered':True,
                'pageview_days_observed':28,'events':{p:{'page_view':{'non_operator':1000,'operator':0,'unknown':0},
                'affiliate_click':{'non_operator':30,'operator':0,'unknown':0}} for p in ('/','/categories/laundry/','/categories/tissue/','/categories/toilet-paper/')}}
        current=window(['2026-09-12','2026-10-09']);prior=window(['2026-08-15','2026-09-11'])
        details={'source':'GA4 Data API','status':'AGGREGATES_ONLY','current':{'period':current['period']},'prior':{'period':prior['period']}}
        r=e.evaluate(None,current,prior,details)
        self.assertEqual(r['evaluation'],'READY_FOR_HUMAN_REVIEW_NOT_CAUSAL_PROOF')
        self.assertIsNone(r['sales']['confirmed_reward_yen']);self.assertFalse(r['automatic_code_change'])

    def test_existing_audit_sees_verified_supplement_without_ranking_mutation(self):
        from step4_purchase_audit import inspect_category
        c={'items':[offer(qty=60,title='ボックスティッシュ 200組 5箱×12パック')],
           'purpose_candidates':[offer(qty=5,suffix='small')]};before=copy.deepcopy(c)
        r=inspect_category('tissue',c)
        self.assertEqual(c,before);self.assertEqual(r['coverage']['small'],1)
        self.assertNotIn('NO_VERIFIED_HOUSEHOLD_SIZE_IN_SNAPSHOT',r['codes'])
        self.assertEqual(r['offers'][-1]['source'],'PURPOSE_SUPPLEMENT')
        c['purpose_candidates'][0]['item_code']='shop:wrong'
        self.assertEqual(inspect_category('tissue',c)['coverage']['small'],0)


if __name__=='__main__':unittest.main()
