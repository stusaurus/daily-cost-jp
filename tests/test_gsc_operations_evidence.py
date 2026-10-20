"""Offline regressions: provenance, missing != zero, periods, privacy, queue."""
import copy
import datetime as dt
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gsc_operations_evidence as e
import autonomous_operations_triage as t
from test_autonomous_operations_triage import joined, browser, health, quality

NOW = dt.datetime(2026, 10, 19, 12, tzinfo=dt.timezone.utc)


def metric(n=100, clicks=0, position=12):
    return {'impressions': n, 'clicks': clicks, 'ctr': clicks/n if n else 0,
            'position': position if n else None}


def report(kind='aggregate', day='2026-10-19'):
    sites = [{'name': name, 'property': site, 'status': 'OBSERVED',
              'windows': {label: {'status': 'NO_ROWS', 'metrics': None} for label in ('last_28','prior_28','last_7','prior_7')},
              'top_pages': [], 'analytics': {}, 'inspection': []} for name, site in e.SITES]
    return {'source': e.CONFIG[kind][3], e.CONFIG[kind][4]: day,
            'date_windows': e.date_windows(dt.date.fromisoformat(day)), 'sites': sites}


def receipt(kind='aggregate', **changes):
    return {'id': 123, 'head_sha': 'a'*40, 'head_branch': 'main', 'event': 'schedule',
            'status': 'completed', 'conclusion': 'success', 'created_at': '2026-10-19T02:00:00Z',
            'path': '.github/workflows/' + e.CONFIG[kind][0], 'repository': {'full_name': e.REPO}, **changes}


def observation(r, day='2026-10-19', run_id=123):
    return {'report': r, 'as_of': day, 'run_id': run_id, 'sha': 'a'*40, 'artifact_id': 42}


class EvidenceTests(unittest.TestCase):
    def test_valid_receipt_and_exact_properties_windows(self):
        self.assertEqual(e.validate(report(), receipt(), 'aggregate', NOW), '2026-10-19')
        for changes in ({'event': 'pull_request'}, {'head_branch':'feature'}, {'head_sha':'oops'},
                        {'conclusion':'failure'}, {'path':'.github/workflows/other.yml'},
                        {'repository':{'full_name':'other/repo'}}, {'created_at':'2026-10-09T11:59:59Z'},
                        {'created_at':'2026-10-20T00:00:00Z'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                e.validate(report(), receipt(**changes), 'aggregate', NOW)
        for change in ('property', 'duplicate', 'windows', 'source'):
            r=report()
            if change=='property': r['sites'][0]['property']=e.SITES[1][1]
            if change=='duplicate': r['sites'][0]=r['sites'][1]
            if change=='windows': r['date_windows']['last_28'][0]='2026-01-01'
            if change=='source': r['source']='unverified'
            with self.assertRaises(ValueError): e.validate(r, receipt(), 'aggregate', NOW)

    def test_old_report_cannot_be_refreshed_by_recent_rerun(self):
        with self.assertRaises(ValueError): e.validate(report(day='2026-10-08'), receipt(), 'aggregate', NOW)

    def test_observed_zero_detected_no_rows_failure_and_low_sample_suppressed(self):
        for status, n, prior, expect in [('OBSERVED',0,100,True), ('OBSERVED',50,100,True),
                ('OBSERVED',51,100,False), ('OBSERVED',0,99,False), ('NO_ROWS',0,100,False),
                ('UNAVAILABLE',0,100,False), ('PERMISSION_DENIED',0,100,False)]:
            r=report(); w=r['sites'][0]['windows']
            w['prior_28']={'status':'OBSERVED','metrics':metric(prior)}
            w['last_28']={'status':status,'metrics':metric(n)}
            findings,_=e.findings_for(r,'aggregate')
            self.assertEqual(any(f['code']=='GSC_IMPRESSIONS_DROP_28' for f in findings.values()), expect)

    def test_week_boundary_and_malformed_metrics(self):
        r=report(); w=r['sites'][0]['windows']
        w['prior_7']={'status':'OBSERVED','metrics':metric(50)}
        w['last_7']={'status':'OBSERVED','metrics':metric(20)}
        f=next(iter(e.findings_for(r,'aggregate')[0].values()))
        self.assertEqual(f['period'], r['date_windows']['last_7'])
        for bad in ({'impressions': True}, {'ctr':float('nan')}, {'clicks':-1}):
            self.assertIsNone(e.metrics({**metric(), **bad}))

    def test_rank_ctr_thresholds_and_site_identity(self):
        r=report()
        for site in r['sites'][:2]: site['top_pages']=[{'path':'/categories/test/', **metric(62,1)}]
        f=e.findings_for(r,'aggregate')[0]
        self.assertEqual(len(f),4)
        self.assertEqual(len(set(f)),4)
        r['sites'][0]['top_pages']=[{'path':'//bad/', **metric(100)}, {'path':'/', **metric(29)}]
        self.assertEqual(len(e.findings_for(r,'aggregate')[0]),2)

    def test_persistence_distinct_dates_not_reruns_and_clearance(self):
        r=report();r['sites'][0]['top_pages']=[{'path':'/', **metric(40)}]
        a=observation(r)
        for history, expected in ([a],'P3'), ([a,observation(r,run_id=124)],'P3'), ([a,observation(r,'2026-10-18',124)],'P2'):
            result=e.assess(history,'aggregate')
            self.assertEqual(result['findings'][0]['severity'],expected)
        cleared=e.assess([observation(report()),observation(r,'2026-10-18',124)],'aggregate')
        self.assertEqual(cleared['findings'],[])
        self.assertEqual(e.assess([],'aggregate')['status'],'UNKNOWN')

    def test_intra_window_drop_requires_28_observed_consecutive_days(self):
        r = report('diagnostic')
        period = r['date_windows']['last_28']
        start = dt.date.fromisoformat(period[0])
        rows = [{'key':(start + dt.timedelta(days=i)).isoformat(),
                 'impressions':11 if i < 14 else 2, 'clicks':0} for i in range(28)]
        daily = {'status':'OBSERVED_ROWS','rows_returned':28,'rows':rows}
        r['sites'][0]['analytics']['daily_28d'] = daily
        signal = e.within_28d_exposure_drop(r['sites'][0]['analytics'], period)
        self.assertEqual((signal['before'],signal['after']), (154,28))
        findings, summaries = e.findings_for(r,'diagnostic')
        matched = [f for f in findings.values() if f['code'] == 'GSC_WITHIN_28D_EXPOSURE_DROP']
        self.assertEqual(len(matched),1)
        self.assertEqual(matched[0]['severity'],'P3')
        self.assertFalse(matched[0]['auto_fix_allowed'])
        self.assertIn('154',matched[0]['evidence'])
        self.assertEqual(summaries[0]['within_28d_exposure_drop'],signal)

    def test_intra_window_drop_missing_days_ambiguous_or_small_samples_suppressed(self):
        r=report('diagnostic')
        period=r['date_windows']['last_28']
        start=dt.date.fromisoformat(period[0])
        original=[{'key':(start+dt.timedelta(days=i)).isoformat(),
                   'impressions':11 if i<14 else 2,'clicks':0} for i in range(28)]
        for scenario in ('missing','no_rows','unavailable','unsorted','duplicate',
                         'bad_date','bool','negative','bad_clicks','small_before',
                         'not_a_drop','bad_count','bad_period'):
            rows=copy.deepcopy(original)
            daily={'status':'OBSERVED_ROWS','rows_returned':28,'rows':rows}
            window=period[:]
            if scenario=='missing': rows.pop()
            if scenario=='no_rows': daily['status']='NO_ROWS'
            if scenario=='unavailable': daily['status']='UNAVAILABLE'
            if scenario=='unsorted': rows[6],rows[7]=rows[7],rows[6]
            if scenario=='duplicate': rows[6]['key']=rows[5]['key']
            if scenario=='bad_date': rows[6]['key']='2026-01-01'
            if scenario=='bool': rows[6]['impressions']=True
            if scenario=='negative': rows[6]['impressions']=-1
            if scenario=='bad_clicks': rows[6]['clicks']=20
            if scenario=='small_before':
                for x in rows[:14]: x['impressions']=7
            if scenario=='not_a_drop':
                for x in rows[14:]: x['impressions']=9
            if scenario=='bad_count': daily['rows_returned']=27
            if scenario=='bad_period': window[0]='2026-01-01'
            with self.subTest(scenario=scenario):
                self.assertIsNone(e.within_28d_exposure_drop({'daily_28d':daily},window))
        self.assertIsNone(e.within_28d_exposure_drop({},period))

    def test_intra_window_shift_needs_week_apart_to_escalate(self):
        r=report('diagnostic')
        start=dt.date.fromisoformat(r['date_windows']['last_28'][0])
        r['sites'][0]['analytics']['daily_28d']={
            'status':'OBSERVED_ROWS','rows_returned':28,
            'rows':[{'key':(start+dt.timedelta(days=i)).isoformat(),
                     'impressions':11 if i<14 else 2,'clicks':0} for i in range(28)]}
        def severity(obs):
            result=e.assess(obs,'diagnostic')
            return next(f['severity'] for f in result['findings']
                        if f['code']=='GSC_WITHIN_28D_EXPOSURE_DROP')
        self.assertEqual(severity([observation(r)]),'P3')
        self.assertEqual(severity([observation(r), observation(r,run_id=124)]),'P3')
        self.assertEqual(severity([observation(r), observation(r,'2026-10-18',124)]),'P3')
        self.assertEqual(severity([observation(r), observation(r,'2026-10-12',124)]),'P2')

    def test_saved_inspection_and_api_failure_are_different(self):
        r=report('diagnostic'); s=r['sites'][3]
        s['inspection']=[{'path':'/categories/pack-rice/','status':'OBSERVED_SNAPSHOT','verdict':'NEUTRAL',
                          'public':{'status':'PUBLIC_HTML'},'google_canonical':None},
                         {'path':'/','status':'UNAVAILABLE','reason':'INSPECTION_HTTP_403'}]
        f,summary=e.findings_for(r,'diagnostic')
        self.assertEqual(len(f),2); self.assertEqual(summary[3]['index_observed'],1)
        self.assertEqual(summary[3]['inspection_unavailable'],1)
        self.assertEqual(summary[3]['index_snapshots'][0]['verdict'],'NEUTRAL')
        self.assertIsNone(summary[3]['index_snapshots'][0]['last_crawl_time'])
        s['inspection'][0].update(verdict='PASS',google_canonical=s['property'],page_fetch_state='SERVER_ERROR')
        codes={x['code'] for x in e.findings_for(r,'diagnostic')[0].values()}
        self.assertEqual(codes, {'GSC_CANONICAL_REVIEW','GSC_CRAWL_REVIEW','GSC_INSPECTION_DATA_UNKNOWN'})

    def test_anonymized_operator_and_natural_rows_no_sum_no_query_leak(self):
        r=report('diagnostic');s=r['sites'][0]
        rows=[{'key':'site:github.io 秘密', **metric(100)}, {'key':'ティッシュ 安い 個人語', **metric(30)}]
        s['analytics']['queries_28d']={'status':'OBSERVED_ROWS','rows':rows}
        s['analytics']['query_pages_28d']={'status':'OBSERVED_ROWS','rows':[
            {**x,'page':s['property'],'path':'/'} for x in rows] + [
            {'key':'ティッシュ 安い','page':e.SITES[1][1], 'path':'/', **metric(100)}]}
        f,summary=e.findings_for(r,'diagnostic')
        self.assertEqual(len(f),1)
        self.assertEqual(summary[0]['returned_query_rows'],{'operator':1,'natural':1})
        output=json.dumps(e.assess([observation(r)],'diagnostic'),ensure_ascii=False)
        self.assertNotIn('秘密',output);self.assertNotIn('個人語',output)
        self.assertNotIn('total_impressions',output)
        self.assertTrue(e.operator_query('ＳＩＴＥ：github.io'))

    def test_collector_permission_or_rate_error_not_zero(self):
        with patch.object(e,'github_request',side_effect=OSError('403')):
            with self.assertRaises(OSError): e.collect('aggregate','token',NOW)
        for error in ('403','429'):
            with patch.object(e,'github_request',return_value={'workflow_runs':[receipt()]}), patch.object(e,'download',side_effect=OSError(error)):
                self.assertEqual(e.assess(e.collect('aggregate','token',NOW),'aggregate')['status'],'UNKNOWN')

    def test_collector_same_day_is_not_persistence(self):
        with patch.object(e,'github_request',return_value={'workflow_runs':[receipt(),receipt(id=124)]}), patch.object(e,'download',return_value=(report(),42)):
            self.assertEqual(len(e.collect('aggregate','token',NOW)),1)

    def test_zip_oversized_member_rejected_without_extraction(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('gsc-six-sites.json','x'*1_000_001)
        response=MagicMock();response.__enter__.return_value.read.return_value=stream.getvalue()
        artifact={'artifacts':[{'id':1,'name':e.CONFIG['aggregate'][1],'expired':False,'size_in_bytes':1000}]}
        with patch.object(e,'github_request',return_value=artifact), patch.object(e,'build_opener') as opener:
            opener.return_value.open.return_value=response
            with self.assertRaises(ValueError): e.download(receipt(),'aggregate','token')

    def test_queue_uses_same_issue_schema_dedupes_and_cannot_authorize_edits(self):
        r=report();r['sites'][0]['top_pages']=[{'path':'/', **metric(40)}]
        source=e.assess([observation(r)],'aggregate')
        evidence={'source':e.SOURCE,'generated_at_utc':NOW.isoformat(),'sources':{'aggregate':source,'diagnostic':e.assess([],'diagnostic')}}
        result=t.evaluate(joined(),browser(),health(),quality(),six_site=evidence,now=NOW)
        self.assertEqual(result['source'],'daily-cost autonomous operations triage v1')
        self.assertLessEqual(len(result['findings']),20)
        self.assertFalse(result['automatic_merge'])
        self.assertTrue(all(f['auto_fix_allowed'] is False for f in result['findings']))
        self.assertIn('GSC_DIAGNOSTIC_EVIDENCE_UNKNOWN',{f['code'] for f in result['findings']})
        self.assertIn('統計的有意差',t.markdown(result))
        stale=t.evaluate(joined(),browser(),health(),quality(),six_site=evidence,now=NOW+dt.timedelta(days=1))
        self.assertIsNone(stale['six_site_evidence'])

    def test_product_legacy_collision_freshness_and_no_revenue_leak(self):
        product={'source':'daily-cost step5 evaluation v1', 'assortment':{
            'status':'TRUSTED_RECENT','catalog_updated_at':NOW.isoformat(),
            'categories':{'laundry':{'legacy_role_collision':True}}},
            'sales':{'confirmed_reward_yen':123456789}}
        fresh=t.evaluate(joined(),browser(),health(),quality(),product=product,now=NOW)
        self.assertIn('PURCHASE_LEGACY_ROLE_COLLISION',{f['code'] for f in fresh['findings']})
        self.assertNotIn('123456789',json.dumps(fresh))
        stale=t.evaluate(joined(),browser(),health(),quality(),product=product,now=NOW+dt.timedelta(days=4))
        self.assertNotIn('PURCHASE_LEGACY_ROLE_COLLISION',{f['code'] for f in stale['findings']})

    def test_cross_site_findings_cannot_be_promoted_to_step2_recipes(self):
        import autonomous_operations_step2 as step2
        r=report('diagnostic')
        r['sites'][3]['inspection']=[{'path':'/categories/pack-rice/','status':'OBSERVED_SNAPSHOT','verdict':'NEUTRAL'}]
        evidence={'source':e.SOURCE,'generated_at_utc':NOW.isoformat(),
                  'sources':{'aggregate':e.assess([],'aggregate'),'diagnostic':e.assess([observation(r)],'diagnostic')}}
        queued=t.evaluate(joined(),browser(),health(),quality(),six_site=evidence,now=NOW)
        queued['generated_at_utc']=NOW.isoformat()
        # Even forged report permission flags cannot authorize arbitrary fixes.
        for f in queued['findings']: f['auto_fix_allowed']=True
        text=Path(step2.TARGET).read_text()
        plan=step2.classify(queued,text,now=NOW)
        self.assertIsNone(plan['recipe'])
        self.assertTrue(all(d['decision']!='AUTO_FIX' for d in plan['decisions']))


if __name__ == '__main__': unittest.main()
