import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step4_automation as a
from test_step4_purchase_audit import offer,snapshot,NOW

def catalog():
    return snapshot({cid:{'items':[offer()]} if cid=='tissue' else {'items':[]} for cid in a.CATEGORIES})

def event_report(period,views,clicks,unknown=0):
    buckets=lambda n:{'non_operator':n,'operator':10,'unknown':unknown}
    return {'source':'GA4 Data API','response_complete':True,'operator_dimension_registered':True,'pageview_days_observed':28,'period':period,
       'events':{p:{'page_view':buckets(views if p=='/' else 0),'affiliate_click':buckets(clicks if p=='/' else 0)} for p in ('/','/categories/laundry/','/categories/tissue/','/categories/toilet-paper/')}}

class AutomationTests(unittest.TestCase):
    def test_acquisition_failure_is_unknown_not_verified_shortage(self):
        source=catalog()
        source['categories']['laundry']['household_acquisition']={
            'status':'ACQUISITION_UNAVAILABLE','reasons':{'api_fetch_failure':4}}
        c=a.diagnose(source,now=NOW)
        missing=[d for d in c['decisions'] if d['path']=='/categories/laundry/' and d['code'].startswith('PURCHASE_')]
        self.assertTrue(all(d['reason']=='ACQUISITION_UNKNOWN' for d in missing))
        report={'source':'daily-cost autonomous operations triage v1','findings':[]}
        with patch.object(a,'feedback_valid',return_value=True): result=a.integrate(report,c)
        matched=[f for f in result['findings'] if f['code']=='PURCHASE_ACQUISITION_UNKNOWN']
        self.assertEqual(len(matched),1)

    def test_only_fixed_content_is_auto_and_all_code_human(self):
        c=a.diagnose(catalog(),True,now=NOW)
        self.assertEqual(c['content_action'],'ALLOW_FIXED_SELECTION')
        self.assertEqual(c['maximum_draft_prs'],1);self.assertFalse(c['automatic_merge']);self.assertFalse(c['automatic_deploy'])
        self.assertTrue(any(d['classification']=='AUTO_CONTENT' for d in c['decisions']))
        self.assertTrue(all(d['classification']=='HUMAN_ONLY' for d in c['decisions'] if d['code'] in ('PRODUCT_QUALITY','POSTAGE','CODE_CSS_NEW_FEATURE','RAKUTEN_URL')))
    def test_default_disabled_and_manual_pause(self):
        self.assertFalse(any(d['classification']=='AUTO_CONTENT' for d in a.diagnose(catalog(),now=NOW)['decisions']))
        c=a.diagnose(catalog(),True,True,now=NOW);self.assertEqual(c['reason'],'MANUAL_PAUSE');self.assertEqual(c['content_action'],'STOP_AND_FALLBACK')
    def test_quality_unknown_quantity_and_api_fail_stop(self):
        for p in (None,{**catalog(),'updated_at':'2020-01-01T00:00:00+00:00'},snapshot({'tissue':{'items':[offer()]}}),snapshot({**catalog()['categories'],'tissue':{'items':[{**offer(),'postage':'不明'}]}})):
            c=a.diagnose(p,True,now=NOW);self.assertEqual(c['content_action'],'STOP_AND_FALLBACK')
    def test_deterministic_same_input_no_rotation(self):
        one=a.diagnose(catalog(),True,now=NOW);two=a.diagnose(catalog(),True,now=NOW);self.assertEqual(one,two)
    def test_no_early_rate_stop_with_unknown_or_low_samples(self):
        prior=event_report(['2026-08-17','2026-09-13'],2000,100)
        for current in (None,event_report(['2026-09-14','2026-10-11'],20,0),event_report(['2026-09-14','2026-10-11'],2000,0,1)):
            self.assertEqual(a.reaction_safeguard(current,prior),'INSUFFICIENT_COMPARABLE_DATA')
    def test_comparable_rate_drop_triggers_fallback_without_claiming_sales(self):
        prior=event_report(['2026-08-17','2026-09-13'],2000,100);current=event_report(['2026-09-14','2026-10-11'],2000,20)
        self.assertEqual(a.reaction_safeguard(current,prior),'PAUSE_FOR_RATE_DROP_REVIEW')
        c=a.diagnose(catalog(),True,current_events=current,prior_events=prior,now=NOW)
        self.assertEqual(c['content_action'],'STOP_AND_FALLBACK');self.assertEqual(c['sales_status'],'NOT_CONNECTED')
    def test_unrelated_periods_not_comparable(self):
        self.assertEqual(a.reaction_safeguard(event_report(['2026-09-14','2026-10-11'],2000,20),event_report(['2026-08-01','2026-08-28'],2000,100)),'PERIOD_MISMATCH')
    def test_stale_untrusted_feedback_blocked(self):
        c=a.diagnose(catalog(),True,now=NOW)
        self.assertTrue(a.feedback_valid(c,now=NOW));self.assertFalse(a.feedback_valid(c,now=NOW+dt.timedelta(days=5)))
        self.assertFalse(a.feedback_valid({**c,'source':'injected'},now=NOW))
    def test_report_text_cannot_authorize_code_or_paths(self):
        c=a.diagnose(catalog(),True,now=NOW)
        c['decisions']=[{'path':'../../secret','code':'RUN_SHELL','classification':'AUTO_CONTENT'}]
        self.assertFalse(a.feedback_valid(c,now=NOW))
    def test_existing_queue_integrates_once_max20(self):
        c=a.diagnose(catalog(),True)
        queue={'source':'daily-cost autonomous operations triage v1','findings':[],'summary':{}}
        x=a.integrate(queue,c);y=a.integrate(x,c);self.assertEqual(x,y);self.assertLessEqual(len(x['findings']),20)
    def test_no_second_publisher_and_existing_switch_maintained(self):
        source=Path('scripts/autonomous_operations_step2.py').read_text();workflow=Path('.github/workflows/ga4-three-day-analysis.yml').read_text()
        self.assertEqual(workflow.count('scripts/autonomous_operations_step2.py publish'),1)
        self.assertIn("vars.STEP2_ENABLE_PR_WRITES == 'true'",workflow)
        self.assertNotIn('create_pull_request',Path('scripts/step4_automation.py').read_text())
        self.assertIn('STEP4 adds classifications only',source)
    def test_daily_fallback_keeps_fresh_data_and_source_markup(self):
        p=catalog();p['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as folder:
            site=Path(folder);raw=json.dumps(p);(site/'data.json').write_text(raw)
            markup='<html><head></head><body><main>original ranking</main></body></html>';(site/'index.html').write_text(markup)
            r=a.build_content(site,{'STEP4_ENABLE_CONTENT':'true'},feedback=None)
            self.assertEqual(r['reason'],'FRESH_MAIN_FEEDBACK_UNAVAILABLE');self.assertEqual((site/'data.json').read_text(),raw);self.assertEqual((site/'index.html').read_text(),markup)
    def test_valid_feedback_activates_only_current_catalog(self):
        p=catalog();p['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        c=a.diagnose(p,True)
        with tempfile.TemporaryDirectory() as folder:
            site=Path(folder);raw=json.dumps(p);(site/'data.json').write_text(raw);(site/'index.html').write_text('<html><head></head><body><main>original ranking</main></body></html>')
            a.build_content(site,{'STEP4_ENABLE_CONTENT':'true'},c)
            self.assertEqual((site/'data.json').read_text(),raw);self.assertIn('data-step4-category',(site/'index.html').read_text())
            state=json.loads((site/'step4-content-state.json').read_text());self.assertFalse(state['automatic_merge'])
if __name__=='__main__':unittest.main()

class FeedbackArtifactTests(unittest.TestCase):
    def test_exact_success_main_artifact_only_and_no_extraction(self):
        import io,zipfile
        now=dt.datetime.now(dt.timezone.utc)
        control=a.diagnose(catalog(),True,now=now)
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('step4-control.json',json.dumps(control))
        response=unittest.mock.MagicMock();response.__enter__.return_value.read.return_value=buf.getvalue()
        opener=unittest.mock.MagicMock();opener.open.return_value=response
        runs={'workflow_runs':[{'id':123456,'head_branch':'main','event':'workflow_dispatch','conclusion':'success','updated_at':now.isoformat()}]}
        artifacts={'artifacts':[{'id':42,'name':'step4-operations-feedback','expired':False,'size_in_bytes':1000}]}
        with patch('autonomous_operations_issue.github_request',side_effect=[runs,artifacts]) as api,patch('urllib.request.build_opener',return_value=opener):
            r=a.read_feedback('fake-test-token')
        self.assertTrue(a.feedback_valid(r));self.assertEqual(r['evidence_run_id'],123456)
        self.assertIn('branch=main',api.call_args_list[0].args[0]);self.assertIn('/actions/runs/123456/',api.call_args_list[1].args[0])
    def test_other_branch_and_bad_archive_cannot_authorize_content(self):
        runs={'workflow_runs':[{'id':123456,'head_branch':'malicious','event':'workflow_dispatch','conclusion':'success'}]}
        with patch('autonomous_operations_issue.github_request',return_value=runs):self.assertIsNone(a.read_feedback('fake-test-token'))
        self.assertIsNone(a.read_feedback(''))
