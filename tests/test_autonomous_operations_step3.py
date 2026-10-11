import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import autonomous_operations_step3 as u
import autonomous_operations_step2 as s

CSS = '.lab-masthead{}.lab-section-head{}'


def report(sha='a' * 40):
    return {'source': 'daily-cost UI audit v1', 'site': u.SITE, 'base_sha': sha,
            'read_only': True, 'mode': 'live', 'status': 'PASS',
            'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'observations': [{'path': p, 'viewport': w, 'status': 'PASS', 'http_status': 200,
                              'css_hash': u.digest(CSS), 'screenshot': 'screen.png', 'issues': [],
                              'target': {'count': 1, 'tag': 'A', 'href': 'trends/', 'display': 'inline',
                                         'minHeight': '0px', 'rect': {'width': 180, 'height': 16}} if p == '/' else None}
                             for p in u.PAGES for w in u.WIDTHS]}


class Registry(unittest.TestCase):
    def test_fixed_recipe_not_metric_or_ai_authority(self):
        r = report();r['recipe'] = 'run-shell';r['command'] = 'echo unsafe'
        result = u.ui_decisions(r, CSS, 'a' * 40)
        self.assertEqual(result['recipe'], u.RECIPE)
        self.assertEqual(result['candidate'], CSS + u.BLOCK)
        self.assertIsNone(u.repair(result['candidate']))
        self.assertIsNone(u.repair('body{overflow:hidden}'))
        self.assertNotIn('overflow', u.BLOCK)

    def test_unknown_missing_stale_snapshot_wrong_source_are_not_fixes(self):
        invalid = [None, {}, {**report(), 'mode': 'snapshot'}, {**report(), 'base_sha': 'b' * 40},
                   {**report(), 'source': 'issue body'}, {**report(), 'status': 'UNAVAILABLE'},
                   {**report(), 'generated_at_utc': 'invalid'}, {**report(), 'generated_at_utc': '2020-01-01T00:00:00+00:00'},
                   {**report(), 'generated_at_utc': '2026-01-01T00:00:00'},
                   {**report(), 'observations': report()['observations'][:-1]}]
        for r in invalid:
            with self.subTest(r=r):
                self.assertIsNone(u.ui_decisions(r, CSS, 'a' * 40)['recipe'])

    def test_wrong_cause_target_styles_and_partial_widths_rejected(self):
        for field, value in [('href', 'https://evil.test'), ('count', 2), ('tag', 'BUTTON'),
                             ('minHeight', '44px'), ('display', 'block'), ('rect', {'width': 180, 'height': 44}),
                             ('rect', {'width': 180, 'height': float('nan')})]:
            r = report();r['observations'][0]['target'][field] = value
            self.assertIsNone(u.ui_decisions(r, CSS, 'a' * 40)['recipe'])
        r = report();r['observations'][0]['css_hash'] = 'unknown'
        self.assertIsNone(u.ui_decisions(r, CSS, 'a' * 40)['recipe'])
        r = report();r['observations'][1] = copy.deepcopy(r['observations'][0])
        self.assertIsNone(u.ui_decisions(r, CSS, 'a' * 40)['recipe'])

    def test_protected_domains_and_metrics_do_not_authorize_features(self):
        rows = [{'code': c, 'path': '/products/'} for c in u.HUMAN]
        self.assertTrue(all(x['decision'] == 'HUMAN_ONLY' for x in u.feature_decisions({'findings': rows}, {})[:-1]))
        joined = {'source': 'GA4 + Search Console read-only page triage', 'top_investigations': [{'path': '/products/', 'auto_fix': True}]}
        self.assertEqual(u.feature_decisions({}, joined)[0]['decision'], 'INVESTIGATE')

    def test_baseline_missing_unknown_test_and_period_mismatch(self):
        self.assertEqual(u.baseline(None)['status'], 'UNAVAILABLE')
        j = {'source': 'GA4 + Search Console read-only page triage', 'site': u.SITE, 'status': 'JOINT_PROVISIONAL',
             'ga4_source_status': 'PROVISIONAL', 'ga4_operator_dimension_registered': True,
             'gsc_period_last_28': ['2026-09-01', '2026-09-28'], 'ga4_period_last_28': ['2026-09-02', '2026-09-29'],
             'page_diagnostics': [{'path': '/products/', 'gsc_last_28': {'impressions': 100, 'clicks': 3},
                                   'ga4_last_28': {'pageviews': 50, 'operator_tests': 9, 'unknown_operator_clicks': 0, 'provisional_non_operator_clicks': 2}}]}
        b = u.baseline(j)
        self.assertFalse(b['periods_aligned']);self.assertIsNone(b['cross_source_conversion_rate'])
        self.assertEqual(b['pages'][0]['click_evidence'], 'LOW_SAMPLE')
        self.assertEqual(b['pages'][0]['known_operator_tests'], 9)
        self.assertEqual(b['comparison_save_filter_usage'], 'NOT_COLLECTED')
        j['page_diagnostics'][0]['ga4_last_28']['unknown_operator_clicks'] = 1
        self.assertIsNone(u.baseline(j)['pages'][0]['non_operator_affiliate_clicks'])
        j['ga4_source_status'] = 'PARTIAL_OBSERVED_DAYS'
        self.assertEqual(u.baseline(j)['pages'][0]['click_evidence'], 'UNAVAILABLE')


class Publisher(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd();self.temp = tempfile.TemporaryDirectory();os.chdir(self.temp.name)
        Path('docs').mkdir();Path(s.TARGET).write_text(s.ANCHOR+s.LEGACY+'\n')
        Path(u.TARGET).parent.mkdir(parents=True);Path(u.TARGET).write_text(CSS)
        subprocess.run(['git', 'init', '-q'], check=True);subprocess.run(['git', 'add', '.'], check=True)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'base'], check=True)
        self.sha = s.git('rev-parse', 'HEAD');Path('audit-results/step3-ui').mkdir(parents=True)
        Path('audit-results/autonomous-operations.json').write_text(json.dumps({'source':s.SOURCE,'site':u.SITE,'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'findings':[]}))
        Path('audit-results/step3-ui/report.json').write_text(json.dumps(report(self.sha)))
        s.prepare();self.plan = s.read_optional('audit-results/step2-plan.json')
        proof = {'status':'PASS','mode':'live','screens':18,'base_sha':self.sha,'candidate_hash':s.digest(Path(u.TARGET).read_text()),
                 'report_hash':s.digest(Path('audit-results/step3-ui/report.json').read_text()),'differences_hash':s.digest('[]')}
        Path('audit-results/step3-ui/differences.json').write_text('[]');Path('audit-results/step3-ui/verification.json').write_text(json.dumps(proof))
        self.receipt = {'base_sha':self.sha,'candidate_hash':self.plan['candidate_hash'],'tests':'PASS','ui_verification_hash':s.digest(json.dumps(proof))}
        self.env = {'GITHUB_REPOSITORY':s.REPO,'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'schedule','GITHUB_RUN_ID':'123456789'}
        self.calls=[];self.prs=[]

    def tearDown(self):
        os.chdir(self.cwd);self.temp.cleanup()

    def api(self, url, token, method='GET', payload=None):
        self.calls.append((url,method,payload))
        if url.startswith('/pulls?'):return self.prs
        if url=='/git/ref/heads/main':return {'object':{'sha':self.sha}}
        if url.startswith('/git/ref/heads/auto-ops/'):raise HTTPError('https://api.github.com',404,'missing',{},None)
        if url.startswith('/git/commits/'):return {'tree':{'sha':'tree'}}
        if url in ('/git/trees','/git/commits'):return {'sha':'commit'}
        if url=='/pulls':
            self.prs.append({'body':payload['body'],'head':{'ref':payload['head']},'html_url':'https://github.com/mock/pr'})
            return {'html_url':'https://github.com/mock/pr'}
        return {}

    def test_ui_uses_shared_draft_publisher_and_closed_history_dedup(self):
        self.assertEqual(self.plan['recipe'], u.RECIPE)
        self.assertEqual(s.publish(self.plan,self.receipt,'fake',self.env,self.api)['status'],'DRAFT_CREATED')
        tree=next(c[2] for c in self.calls if c[0]=='/git/trees')['tree']
        self.assertEqual(tree,[{'path':u.TARGET,'mode':'100644','type':'blob','content':CSS+u.BLOCK}])
        pr=next(c[2] for c in self.calls if c[0]=='/pulls')
        self.assertTrue(pr['draft']);self.assertEqual(pr['base'],'main');self.assertIn('18 before/after',pr['body'])
        self.assertTrue(pr['title'].endswith('[skip netlify]'))
        self.assertFalse(any('/merge' in c[0] or '/deploy' in c[0] for c in self.calls))
        self.prs[0]['state']='closed'
        self.assertEqual(s.publish(self.plan,self.receipt,'fake',self.env,self.api)['status'],'DUPLICATE_OR_DISMISSED')

    def test_browser_proof_failed_stale_snapshot_and_tampering_no_api(self):
        p=Path('audit-results/step3-ui/verification.json');original=p.read_text()
        for key,value in [('status','FAIL'),('mode','snapshot'),('screens',17),('base_sha','b'*40),('candidate_hash','wrong'),('report_hash','wrong')]:
            proof=json.loads(original);proof[key]=value;p.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):s.publish(self.plan,self.receipt,'fake',self.env,self.api)
            self.assertEqual(self.calls,[])
        p.write_text(original);Path(u.TARGET).write_text(CSS+u.BLOCK+'body{overflow:hidden}')
        with self.assertRaises(ValueError):s.publish(self.plan,self.receipt,'fake',self.env,self.api)
        self.assertEqual(self.calls,[])

    def test_documentation_recipe_has_priority_and_one_pr_maximum(self):
        Path(u.TARGET).write_text(CSS);Path(s.TARGET).write_text(s.ANCHOR+'Existing policy.\n')
        s.prepare();self.assertEqual(s.read_optional('audit-results/step2-plan.json')['recipe'],s.RECIPE)
        self.assertEqual(Path(u.TARGET).read_text(),CSS)
