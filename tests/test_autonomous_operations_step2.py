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
import autonomous_operations_step2 as s


def report(codes=()):
    return {'source': s.SOURCE, 'site': s.SITE, 'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'findings': [{'code': c, 'path': '/', 'auto_fix_allowed': True, 'command': 'echo unsafe'} for c in codes]}


class Safety(unittest.TestCase):
    def test_current_issue_requires_investigation_and_human(self):
        out = s.classify(report(['GA4_CLICK_ATTRIBUTION_UNCERTAIN', 'PRODUCT_QUALITY_WARNINGS',
                                'SEO_SNIPPET_RESEARCH']), s.ANCHOR + s.LEGACY)
        self.assertEqual([d['decision'] for d in out['decisions']], ['INVESTIGATE', 'HUMAN_ONLY', 'HUMAN_ONLY'])
        self.assertIsNone(out['candidate'])

    def test_unknown_and_forged_recipe_cannot_authorize_write(self):
        r = report(['OPS_SAFETY_DOCUMENTATION_MISSING', 'UNKNOWN'])
        r['findings'][0]['recipe'] = s.RECIPE
        self.assertTrue(all(d['decision'] == 'INVESTIGATE' for d in s.classify(r, s.ANCHOR + s.LEGACY)['decisions']))

    def test_all_protected_domains(self):
        out = s.classify(report(sorted(s.PROTECTED)), s.ANCHOR + s.LEGACY)
        self.assertTrue(all(d['decision'] == 'HUMAN_ONLY' for d in out['decisions']))

    def test_missing_stale_future_and_wrong_source(self):
        for r in [None, {}, {**report(), 'site': 'https://evil.example/'},
                  {**report(), 'generated_at_utc': '2020-01-01T00:00:00+00:00'},
                  {**report(), 'generated_at_utc': '2099-01-01T00:00:00+00:00'}]:
            with self.assertRaises((ValueError, KeyError)):
                s.classify(r, s.ANCHOR)

    def test_workflow_tests_before_publish_and_no_deploy(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/ga4-three-day-analysis.yml').read_text()
        job = workflow.split('  safe-repair-preparation:')[1]
        self.assertLess(job.index('check_step2_candidate.py'), job.index('step2.py publish'))
        self.assertEqual(job.count('GITHUB_TOKEN:'), 1)
        self.assertIn('persist-credentials: false', job)
        self.assertNotIn('deploy-pages', job)
        self.assertNotIn('pull_request_target', workflow)

    def test_naive_or_malformed_timestamp_rejected(self):
        for value in [None, 123, '2026-10-10T00:00:00']:
            with self.assertRaises(ValueError):
                s.classify({**report(), 'generated_at_utc': value}, s.ANCHOR)

    def test_pr_writes_require_separate_opt_in(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/ga4-three-day-analysis.yml').read_text()
        self.assertIn("if: vars.STEP2_ENABLE_PR_WRITES == 'true'", workflow)
        verification = (Path(__file__).resolve().parents[1] / '.github/workflows/step2-token-verification.yml').read_text()
        self.assertIn('default: false', verification)
        self.assertNotIn('schedule:', verification)
        self.assertNotIn('push:', verification)
        self.assertIn('group: ga4-three-day-readonly', verification)

    def test_exact_recipe_and_idempotence(self):
        out = s.classify(report(), s.ANCHOR + '\nExisting policy.\n')
        self.assertEqual(out['decisions'][0]['decision'], 'AUTO_FIX')
        self.assertEqual(out['candidate'], s.ANCHOR + '\n' + s.GUARD + '\nExisting policy.\n')
        self.assertIsNone(s.repair(out['candidate']))
        self.assertIsNone(s.repair(s.ANCHOR * 2))
        self.assertIsNone(s.repair('no anchor'))


class Publication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        Path('docs').mkdir()
        Path(s.TARGET).write_text(s.ANCHOR + '\nExisting policy.\n')
        Path('.gitignore').write_text('audit-results/\n')
        subprocess.run(['git', 'init', '-q'], check=True)
        subprocess.run(['git', '-c', 'user.email=test@example.invalid', '-c', 'user.name=Test', 'add', '.'], check=True)
        subprocess.run(['git', '-c', 'user.email=test@example.invalid', '-c', 'user.name=Test', 'commit', '-qm', 'fixture'], check=True)
        Path('audit-results').mkdir()
        Path('audit-results/autonomous-operations.json').write_text(json.dumps(report()))
        s.prepare()
        self.plan = s.read_optional('audit-results/step2-plan.json')
        self.receipt = {'base_sha': self.plan['base_sha'], 'candidate_hash': self.plan['candidate_hash'], 'tests': 'PASS'}
        self.env = {'GITHUB_REPOSITORY': s.REPO, 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_EVENT_NAME': 'schedule', 'GITHUB_RUN_ID': '123456789'}
        self.calls = []
        self.prs = []
        self.branch_exists = False
        self.main_sha = self.plan['base_sha']

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()

    def request(self, path, token, method='GET', payload=None):
        self.calls.append((path, method, payload))
        if path.startswith('/pulls?'):
            return self.prs
        if path == '/git/ref/heads/main':
            return {'object': {'sha': self.main_sha}}
        if path.startswith('/git/ref/heads/auto-ops/'):
            if self.branch_exists:
                return {'object': {'sha': 'existing'}}
            raise HTTPError('https://api.github.com', 404, 'missing', {}, None)
        if path.startswith('/git/commits/'):
            return {'tree': {'sha': 'base-tree'}}
        if path in ('/git/trees', '/git/commits'):
            return {'sha': 'new-object'}
        if path == '/pulls':
            self.prs.append({'body': payload['body'], 'head': {'ref': payload['head']}, 'html_url': 'https://github.com/mock/pr/1'})
            return {'html_url': 'https://github.com/mock/pr/1'}
        return {}

    def publish(self):
        return s.publish(self.plan, self.receipt, 'fake-token-never-logged', self.env, self.request)

    def test_draft_actual_payload_tests_and_dedup(self):
        self.assertEqual(self.publish()['status'], 'DRAFT_CREATED')
        post = next(c for c in self.calls if c[0] == '/pulls')
        self.assertTrue(post[2]['draft'])
        self.assertEqual(post[2]['base'], 'main')
        self.assertIn(self.plan['candidate_hash'], post[2]['body'])
        self.assertNotIn('fake-token', post[2]['body'])
        writes = sum(c[1] != 'GET' for c in self.calls)
        self.assertEqual(self.publish()['status'], 'DUPLICATE_OR_DISMISSED')
        self.assertEqual(writes, sum(c[1] != 'GET' for c in self.calls))
        self.assertFalse(any('merge' in c[0] or 'deployment' in c[0] for c in self.calls))

    def test_closed_pr_suppresses_recreation(self):
        self.prs = [{'state': 'closed', 'head': {'ref': 'auto-ops/' + self.plan['fingerprint']}}]
        self.assertEqual(self.publish()['status'], 'DUPLICATE_OR_DISMISSED')

    def test_failed_checks_no_writes(self):
        for receipt in [None, {**self.receipt, 'tests': 'FAIL'}, {**self.receipt, 'candidate_hash': 'wrong'}]:
            with self.assertRaises(ValueError):
                s.publish(self.plan, receipt, 'token', self.env, self.request)
        self.assertEqual(self.calls, [])

    def test_no_candidate_no_api(self):
        self.assertEqual(s.publish({'recipe': None}, None, 'token', self.env, self.request)['status'], 'NO_SAFE_FIX')
        self.assertEqual(self.calls, [])

    def test_main_moved_or_orphan_branch_no_writes(self):
        self.main_sha = 'different'
        self.assertEqual(self.publish()['status'], 'MAIN_CHANGED_RETRY_NEXT_CADENCE')
        self.main_sha = self.plan['base_sha']
        self.branch_exists = True
        self.assertEqual(self.publish()['status'], 'EXISTING_BRANCH_REQUIRES_REVIEW')
        self.assertTrue(all(c[1] == 'GET' for c in self.calls))

    def test_invalid_run_no_writes(self):
        self.env['GITHUB_RUN_ID'] = 'untrusted'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertTrue(all(c[1] == 'GET' for c in self.calls))

    def test_pagination_checks_older_dismissed_pr(self):
        def request(path, token, method='GET', payload=None):
            if path.endswith('page=1'):
                return [{} for _ in range(100)]
            if path.endswith('page=2'):
                return [{'head': {'ref': 'auto-ops/' + self.plan['fingerprint']}}]
            raise AssertionError('No writes expected')
        self.assertEqual(s.publish(self.plan, self.receipt, 'token', self.env, request)['status'], 'DUPLICATE_OR_DISMISSED')

    def test_nonmain_forbidden(self):
        self.env['GITHUB_REF'] = 'refs/pull/1/merge'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def make_verification(self):
        Path(s.TARGET).write_text(subprocess.check_output(['git', 'show', 'HEAD:' + s.TARGET]).decode())
        self.env.update({'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_WORKFLOW': s.VERIFY_WORKFLOW,
                         'STEP2_VERIFY_TOKEN': 'true'})
        s.prepare_verification(self.env)
        self.plan = s.read_optional('audit-results/step2-plan.json')
        self.receipt = {'base_sha': self.plan['base_sha'], 'candidate_hash': self.plan['candidate_hash'], 'tests': 'PASS'}

    def test_manual_token_verification_uses_same_tested_publisher(self):
        self.make_verification()
        def api(path, token, method='GET', payload=None):
            if path == '/pulls/123':
                return {'draft': True, 'auto_merge': None, 'user': {'login': 'github-actions[bot]'},
                        'base': {'ref': 'main'}, 'head': {'sha': 'new-object'}}
            if path == '/pulls/123/files?per_page=100':
                return [{'filename': s.VERIFY_TARGET, 'status': 'added'}]
            value = self.request(path, token, method, payload)
            if path == '/pulls':
                self.assertIn('DO NOT MERGE', payload['title'])
                self.assertEqual(payload['draft'], True)
                self.assertTrue(payload['title'].endswith('[skip netlify]'))
                value['number'] = 123
            return value
        result = s.publish(self.plan, self.receipt, 'token', self.env, api)
        self.assertEqual(result['status'], 'DRAFT_CREATED')
        self.assertTrue(next(c for c in self.calls if c[0] == '/git/commits')[2]['message'].endswith('[skip netlify]'))
        tree = next(c for c in self.calls if c[0] == '/git/trees')[2]['tree']
        self.assertEqual(tree, [{'path': s.VERIFY_TARGET, 'mode': '100644', 'type': 'blob', 'content': s.VERIFY_CONTENT}])
        self.assertEqual(s.publish(self.plan, self.receipt, 'token', self.env, api)['status'], 'DUPLICATE_OR_DISMISSED')

    def test_scheduled_or_unconfirmed_verification_forbidden(self):
        with self.assertRaises(ValueError):
            s.prepare_verification(self.env)
        self.make_verification()
        self.env['STEP2_VERIFY_TOKEN'] = 'false'
        with self.assertRaises(ValueError):
            self.publish()
        self.env['STEP2_VERIFY_TOKEN'] = 'true'
        self.env['GITHUB_EVENT_NAME'] = 'schedule'
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_fixed_verification_file_cannot_be_overwritten_or_tampered(self):
        self.make_verification()
        with self.assertRaises(ValueError):
            s.prepare_verification(self.env)
        Path(s.VERIFY_TARGET).write_text('arbitrary code or content')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_verification_checks_real_pr_state_and_diff(self):
        self.make_verification()
        def api(path, token, method='GET', payload=None):
            if path == '/pulls/123':
                return {'draft': False, 'auto_merge': None}
            value = self.request(path, token, method, payload)
            if path == '/pulls':
                value['number'] = 123
            return value
        with self.assertRaises(ValueError):
            s.publish(self.plan, self.receipt, 'token', self.env, api)

    def test_verification_rejects_auto_merge_wrong_author_and_wrong_files(self):
        self.make_verification()
        good = {'draft': True, 'auto_merge': None, 'user': {'login': 'github-actions[bot]'},
                'base': {'ref': 'main'}, 'head': {'sha': 'new-object'}}
        for mutation in [{'auto_merge': {}}, {'user': {'login': 'other'}}, {'base': {'ref': 'other'}},
                         {'head': {'sha': 'wrong'}}, {'files': 'wrong'}]:
            self.prs = []
            def api(path, token, method='GET', payload=None):
                if path == '/pulls/123':
                    return {**good, **{k: v for k, v in mutation.items() if k != 'files'}}
                if path == '/pulls/123/files?per_page=100':
                    return [{'filename': 'price.json', 'status': 'added'}]
                value = self.request(path, token, method, payload)
                if path == '/pulls':
                    value['number'] = 123
                return value
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                s.publish(self.plan, self.receipt, 'token', self.env, api)

    def test_price_code_untracked_or_tampered_diff_forbidden(self):
        for path in [Path('price.json'), Path(s.TARGET)]:
            original = path.read_text() if path.exists() else None
            path.write_text('malicious change')
            with self.assertRaises(ValueError):
                self.publish()
            if original is None:
                path.unlink()
            else:
                path.write_text(original)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
