"""Synthetic financial fixtures only. No account/order/credential data in tests."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step7_private_revenue as r
import step7_google_monthly as g
from check_step7_public_boundary import inspect

MONTH='2026-09'
STAMP='2026-10-01T00:00:00Z'

def mapping(kind='confirmed_reward', row_format='summary', date=False):
    cols={'period':'期間','clicks' if kind=='rakuten_clicks' else 'amount':'値'}
    if kind=='order_status':
        cols['status']='状態'
        if row_format=='detail':cols['row_id']='明細ID'
    return {'kind':kind,'columns':cols,'period_format':'date_iso' if date else 'month_iso','encoding':'utf-8-sig','row_format':row_format}

class PrivateRevenue(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.conn=r.database(self.root)
    def tearDown(self):self.conn.close();self.temp.cleanup()
    def test_import_is_idempotent_and_renamed_reordered_files_do_not_sum(self):
        raw='期間,値\n2026-09,123\n'.encode();m=mapping()
        self.assertEqual(r.ingest(self.conn,raw,m,'main',MONTH,STAMP),'PRIVATE_SNAPSHOT_IMPORTED')
        self.assertEqual(r.ingest(self.conn,raw,m,'main',MONTH,STAMP),'DUPLICATE_NOT_ADDED')
        self.assertEqual(r.monthly_report(self.conn,'main',MONTH)['rakuten']['confirmed_reward']['confirmed_reward_yen'],123)
    def test_corrections_require_newer_snapshot_and_replace_instead_of_add(self):
        m=mapping();r.ingest(self.conn,b'\xe6\x9c\x9f\xe9\x96\x93,\xe5\x80\xa4\n2026-09,123\n',m,'main',MONTH,STAMP)
        raw='期間,値\n2026-09,120\n'.encode()
        with self.assertRaises(r.PrivateError):r.ingest(self.conn,raw,m,'main',MONTH,'2026-10-02T00:00:00Z')
        with self.assertRaises(r.PrivateError):r.ingest(self.conn,raw,m,'main',MONTH,'2026-09-30T00:00:00Z',True)
        r.ingest(self.conn,raw,m,'main',MONTH,'2026-10-02T00:00:00Z',True)
        self.assertEqual(r.monthly_report(self.conn,'main',MONTH)['rakuten']['confirmed_reward']['confirmed_reward_yen'],120)
    def test_new_official_correction_may_return_to_an_earlier_amount(self):
        for amount,stamp in [(123,STAMP),(120,'2026-10-02T00:00:00Z'),(123,'2026-10-03T00:00:00Z')]:
            r.ingest(self.conn,f'期間,値\n2026-09,{amount}\n'.encode(),mapping(),'main',MONTH,stamp,True)
        self.assertEqual(r.monthly_report(self.conn,'main',MONTH)['rakuten']['confirmed_reward']['confirmed_reward_yen'],123)
    def test_history_keeps_real_observed_months_without_filling_gaps(self):
        for period,n in [('2026-07',10),('2026-09',20)]:
            r.ingest(self.conn,f'期間,値\n{period},{n}\n'.encode(),mapping(),'main',period,STAMP)
        result=r.monthly_report(self.conn,'main',MONTH)
        self.assertEqual([x['month'] for x in result['confirmed_account_history']],['2026-09','2026-07'])
        self.assertIsNone(result['daily_cost_confirmed_reward_yen'])
        self.assertEqual(result['priorities'][0]['code'],'VERIFY_SITE_ATTRIBUTION')

    def test_detail_duplicates_and_conflicting_identity_fail_closed(self):
        m=mapping('order_status','detail',True)
        raw='期間,値,状態,明細ID,商品名\n2026-09-01,10,未確定,SYNTHETIC-1,架空のテスト商品\n2026-09-01,10,未確定,SYNTHETIC-1,架空のテスト商品\n'.encode()
        totals=r.aggregate(raw,m,MONTH);self.assertEqual(totals['order_status_yen']['pending'],10)
        self.assertIsNone(totals['order_status_yen']['discarded'])
        with self.assertRaises(r.PrivateError):r.aggregate(raw+b'2026-09-01,20,\xe7\xa2\xba\xe5\xae\x9a,SYNTHETIC-1,x\n',m,MONTH)
        r.ingest(self.conn,raw,m,'main',MONTH,STAMP)
        payload=' '.join(str(row) for row in self.conn.execute('SELECT * FROM snapshots'))
        self.assertNotIn('SYNTHETIC-1',payload);self.assertNotIn('架空のテスト商品',payload)
    def test_confirmed_pending_discarded_and_clicks_are_separate(self):
        raw='期間,値,状態\n2026-09,10,確定\n2026-09,20,未確定\n2026-09,30,破棄\n'.encode()
        r.ingest(self.conn,raw,mapping('order_status','status_totals'),'main',MONTH,STAMP)
        r.ingest(self.conn,'期間,値\n2026-09,5\n'.encode(),mapping('rakuten_clicks'),'main',MONTH,STAMP)
        result=r.monthly_report(self.conn,'main',MONTH)
        self.assertIsNone(result['rakuten']['confirmed_reward']);self.assertIsNone(result['daily_cost_confirmed_reward_yen'])
        self.assertEqual(result['rakuten']['order_status']['order_status_yen'],{'confirmed':10,'pending':20,'discarded':30})
        self.assertIn('未確認',r.markdown(result));self.assertFalse(result['cross_source_user_join'])
    def test_absent_data_and_empty_export_are_unknown_not_zero(self):
        result=r.monthly_report(self.conn,'main',MONTH)
        self.assertTrue(all(v is None for v in result['rakuten'].values()))
        with self.assertRaises(r.PrivateError):r.aggregate('期間,値\n'.encode(),mapping(),MONTH)
        self.assertEqual(r.aggregate('期間,値\n2026-09,0\n'.encode(),mapping(),MONTH)['confirmed_reward_yen'],0)
    def test_missing_headers_unknown_status_mixed_month_and_totals_rejected(self):
        for text in ['日,値\n2026-09,1\n','期間,値\n2026-08,1\n','期間,値\n2026-09,1\n2026-09,2\n']:
            with self.assertRaises(r.PrivateError):r.aggregate(text.encode(),mapping(),MONTH)
        with self.assertRaises(r.PrivateError):r.aggregate('期間,値,状態\n2026-09,1,不明\n'.encode(),mapping('order_status','status_totals'),MONTH)
    def test_strict_yen_and_encodings_never_guess_values(self):
        self.assertEqual(r.number('￥1,234円'),1234)
        for value in ['=100','-1','1.5','1e3','12,34','NaN','',True]:
            with self.assertRaises(r.PrivateError):r.number(value)
        m=mapping();m['encoding']='cp932'
        self.assertEqual(r.aggregate('期間,値\n2026-09,9\n'.encode('cp932'),m,MONTH)['confirmed_reward_yen'],9)
    def test_accounts_are_separate_and_no_site_attribution_inferred(self):
        for account,n in [('one',1),('two',2)]:r.ingest(self.conn,f'期間,値\n2026-09,{n}\n'.encode(),mapping(),account,MONTH,STAMP)
        self.assertEqual(r.monthly_report(self.conn,'one',MONTH)['rakuten']['confirmed_reward']['confirmed_reward_yen'],1)
        self.assertEqual(r.monthly_report(self.conn,'two',MONTH)['rakuten_scope'],'ACCOUNT_UNATTRIBUTED')
    def test_private_paths_reject_git_ignored_paths_symlinks_and_permissions(self):
        (self.root/'.git').mkdir()
        with self.assertRaises(r.PrivateError):r.protected_path(str(self.root/'anything'))
        (self.root/'.git').rmdir();link=self.root/'link';link.symlink_to(self.root/'other')
        with self.assertRaises(r.PrivateError):r.protected_path(str(link))
        self.assertEqual(r.private_root(str(self.root)),self.root)
        self.root.chmod(0o755)
        with self.assertRaises(r.PrivateError):r.private_root(str(self.root))
        self.root.chmod(0o700)
    def test_no_raw_financial_stdout_or_ci_processing(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(r.PrivateError,'FORBIDDEN_IN_CI'):r.main()
        self.assertEqual((self.root/'monthly.sqlite3').stat().st_mode&0o777,0o600)
    def test_private_report_cannot_enter_tracked_public_json_or_database(self):
        (self.root/'hidden.json').write_text(json.dumps({'source':r.SOURCE}))
        self.assertIn('PRIVATE_REPORT_IN_PUBLIC_TREE',inspect(self.root,['hidden.json']))
        (self.root/'orders.csv').write_text('synthetic-only')
        self.assertIn('PRIVATE_FILE_TYPE_IN_PUBLIC_TREE',inspect(self.root,['orders.csv']))
        (self.root/'renamed.bin').write_bytes(b'SQLite format 3\x00synthetic')
        self.assertIn('PRIVATE_DATABASE_IN_PUBLIC_TREE',inspect(self.root,['renamed.bin']))
        (self.root/'symlink').symlink_to(self.root/'hidden.json')
        self.assertIn('UNVERIFIABLE_SYMLINK_IN_PUBLIC_TREE',inspect(self.root,['symlink']))
    def test_reports_are_private_and_no_foreign_month_is_joined(self):
        r.save(self.root,'monthly-report.json',json.dumps(r.monthly_report(self.conn,'main',MONTH)))
        self.assertEqual((self.root/'monthly-report.json').stat().st_mode&0o777,0o600)
        obj=g.empty(dt.date(2026,8,1),dt.date(2026,8,31))
        with self.assertRaises(r.PrivateError):r.monthly_report(self.conn,'main',MONTH,obj)

class MonthlyGoogle(unittest.TestCase):
    def test_full_calendar_month_never_uses_28_day_windows(self):
        self.assertEqual(g.bounds(dt.date(2026,10,12)),(dt.date(2026,9,1),dt.date(2026,9,30)))
        self.assertEqual(g.bounds(dt.date(2024,3,10)),(dt.date(2024,2,1),dt.date(2024,2,29)))
    def test_operator_unknown_and_other_site_clicks_never_become_users(self):
        start,end=g.bounds(dt.date(2026,10,12));day=start
        rows=[(day,g.SITE,'1',3),(day,g.SITE,'0',2),(day,g.SITE,'(not set)',4),(day,'https://stusaurus.github.io/food-cost-jp/','0',10)]
        out=g.ga4_aggregate(rows,[(day,'/daily-cost-jp/',10)],start,end,True)
        self.assertEqual(out['affiliate_clicks_observed'],{'non_operator':2,'operator':3,'unknown':4})
        self.assertEqual(out['status'],'PARTIAL_OBSERVATIONS')
        out=g.ga4_aggregate(rows,[],start,end,False)
        self.assertIsNone(out['affiliate_clicks_observed']['non_operator']);self.assertIsNone(out['pageviews_observed'])
    def test_unknown_missing_or_private_extra_fields_are_rejected(self):
        out=g.empty(dt.date(2026,9,1),dt.date(2026,9,30));g.validate(out)
        out['token']='SYNTHETIC-NOT-A-TOKEN'
        with self.assertRaises(ValueError):g.validate(out)
    def test_monthly_google_report_cannot_be_a_revenue_report(self):
        out=g.empty(dt.date(2026,9,1),dt.date(2026,9,30));out['revenue_status']='OBSERVED'
        with self.assertRaises(ValueError):g.validate(out)
