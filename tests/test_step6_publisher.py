import datetime as dt
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import test_autonomous_operations_step2 as old
import autonomous_operations_step2 as s
import step6_seo_content as c
from test_step6_seo import CONFIG, technical, gsc
import step6_seo_audit as a


class Publisher(unittest.TestCase):
    def setUp(self):
        self.fixture=old.Publication('test_price_code_untracked_or_tampered_diff_forbidden')
        self.fixture.setUp()
        Path('scripts').mkdir()
        Path(c.TARGET).write_text(CONFIG)
        subprocess.run(['git','add','.'],check=True)
        subprocess.run(['git','-c','user.email=test@example.invalid','-c','user.name=Test','commit','-qm','fixed policy'],check=True)
        self.sha=s.git('rev-parse','HEAD')
        src=gsc();src['generated_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        from gsc_readonly_pilot import periods
        src['windows']=periods(dt.datetime.now(dt.timezone.utc).date())
        report=a.analyze(technical(),src,CONFIG,self.sha)
        Path('audit-results/step6-seo.json').write_text(json.dumps(report))
        evidence=a.candidate(report,CONFIG,self.sha)
        self.plan={'recipe':c.recipe('laundry'),'base_sha':self.sha,'candidate_hash':s.digest(evidence['candidate']),
                   'original_hash':s.digest(CONFIG),'fingerprint':s.digest(c.recipe('laundry')+':'+c.TARGET)[:24],
                   'seo_evidence_hash':evidence['evidence_hash'],'seo_path':'/categories/laundry/'}
        Path(c.TARGET).write_text(evidence['candidate'])
        Path('audit-results/step6-verification.json').write_text('{}')
        self.receipt={'base_sha':self.sha,'candidate_hash':self.plan['candidate_hash'],'tests':'PASS','seo_verification_hash':s.digest('{}')}
        self.fixture.main_sha=self.sha
        self.proof=patch('step6_verification.validate_receipt',return_value=True);self.proof.start()

    def tearDown(self):
        self.proof.stop();self.fixture.tearDown()

    def publish(self):
        return s.publish(self.plan,self.receipt,'never-logged',self.fixture.env,self.fixture.request)

    def test_single_draft_source_policy_human_approval_and_no_deploy(self):
        self.assertEqual(self.publish()['status'],'DRAFT_CREATED')
        posts=[payload for path,method,payload in self.fixture.calls if path=='/pulls' and method=='POST']
        self.assertEqual(len(posts),1);self.assertTrue(posts[0]['draft'])
        self.assertIn('STEP6 SEO hypothesis',posts[0]['body'])
        self.assertIn('HUMAN_ONLY',posts[0]['body'])
        tree=next(p for path,method,p in self.fixture.calls if path=='/git/trees')
        self.assertEqual([v['path'] for v in tree['tree']],[c.TARGET])
        self.assertEqual(self.publish()['status'],'DUPLICATE_OR_DISMISSED')

    def test_closed_rejected_pr_does_not_repeat(self):
        self.fixture.prs=[{'state':'closed','body':'<!-- daily-cost-step2:'+self.plan['fingerprint']+' -->'}]
        self.assertEqual(self.publish()['status'],'DUPLICATE_OR_DISMISSED')
        self.assertFalse(any(method!='GET' for _,method,_ in self.fixture.calls))

    def test_different_open_seo_hypothesis_blocks_another_page(self):
        self.fixture.prs=[{'state':'open','body':'STEP6 SEO hypothesis for another page'}]
        self.assertEqual(self.publish()['status'],'OPEN_SEO_PROPOSAL_REQUIRES_REVIEW')

    def test_branch_conflict_and_main_moved_stop(self):
        self.fixture.branch_exists=True
        self.assertEqual(self.publish()['status'],'EXISTING_BRANCH_REQUIRES_REVIEW')
        self.fixture.main_sha='b'*40
        self.assertEqual(self.publish()['status'],'MAIN_CHANGED_RETRY_NEXT_CADENCE')

    def test_failed_or_missing_validation_no_api_write(self):
        self.proof.stop();self.proof=patch('step6_verification.validate_receipt',return_value=False);self.proof.start()
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.fixture.calls,[])

    def test_tampered_recipe_source_evidence_and_receipt_stop(self):
        self.receipt['seo_verification_hash']='wrong'
        with self.assertRaises(ValueError):self.publish()
        self.receipt['seo_verification_hash']=s.digest('{}')
        Path(c.TARGET).write_text('unverified external code')
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.fixture.calls,[])


if __name__=='__main__':unittest.main()
