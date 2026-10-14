import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step4_measurement as m

class MeasurementTests(unittest.TestCase):
    def test_operator_unknown_never_real_user(self):
        rows=[('2026-10-01','affiliate_click','https://stusaurus.github.io/daily-cost-jp/?q=private',f,1) for f in ['0','1','(not set)']]
        r=m.aggregate_events(rows,['2026-09-14','2026-10-11'],True)
        self.assertEqual(r['events']['/']['affiliate_click'],{'non_operator':1,'operator':1,'unknown':1})
        self.assertNotIn('private',json.dumps(r));self.assertIsNone(r['conversion_rate']);self.assertEqual(r['pageview_days_observed'],0)
    def test_absent_operator_dimension_never_non_operator(self):
        rows=[('2026-10-01','affiliate_click','https://stusaurus.github.io/daily-cost-jp/','0',5)]
        r=m.aggregate_events(rows,['2026-09-14','2026-10-11'],False)
        self.assertEqual(r['events']['/']['affiliate_click']['unknown'],5);self.assertEqual(r['events']['/']['affiliate_click']['non_operator'],0)
    def test_unavailable_not_zero(self):
        r=m.report();self.assertIsNone(r['new_event_counts']);self.assertEqual(r['sales_status'],'NOT_CONNECTED');self.assertEqual(r['pages'],[])
        r=m.aggregate_events([],['2026-09-14','2026-10-11'],True,False);self.assertIsNone(r['events'])
    def test_incomplete_periods_and_invalid_samples_rejected(self):
        with self.assertRaises(ValueError):m.aggregate_events([],['2026-10-01','2026-10-11'],True)
        with self.assertRaises(ValueError):m.aggregate_events([('2026-10-01','affiliate_click','x','0',-1)],['2026-09-14','2026-10-11'],True)
    def test_pageviews_do_not_make_unknown_clicks_success(self):
        ga={'source':'GA4 Data API','status':'PARTIAL_OBSERVED_DAYS','period_last_28':['2026-09-14','2026-10-11'],'pageview_dates_observed_in_last_28':5,'operator_dimension_registered':True,'pages':[{'page':'/','periods':{'last_28':{'pageviews':100,'clicks':{'production_non_operator':2,'production_operator':3,'production_unknown':4}}}}]}
        r=m.report(ga,gsc={'anything':'private'});self.assertEqual(r['observed_days'],5);self.assertIsNone(r['pages'][0]['click_ratio']);self.assertIsNone(r['pages'][0]['real_user_pageviews']);self.assertEqual(r['recommendation_decision'],'INVESTIGATE');self.assertFalse(r['periods_aligned']);self.assertNotIn('private',json.dumps(r))
if __name__=='__main__':unittest.main()
