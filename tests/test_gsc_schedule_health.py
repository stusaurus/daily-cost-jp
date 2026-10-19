import datetime as dt
import unittest
from unittest.mock import patch
from scripts import gsc_schedule_health as g


class ScheduleTests(unittest.TestCase):
    def now(self, day=20, hour=1):
        return dt.datetime(2026, 10, day, hour, tzinfo=dt.timezone.utc)

    def receipt(self, event='schedule', conclusion='success', date='2026-10-19T02:00:00Z', branch='main'):
        return dict(id=1, event=event, head_branch=branch, created_at=date, status='completed', conclusion=conclusion)

    def test_manual_success_never_hides_missing_schedule(self):
        r = g.evaluate(self.now(), 0, [self.receipt(event='workflow_dispatch')])
        self.assertEqual(r['status'], 'MISSING_SCHEDULE')

    def test_delayed_schedule_within_grace_is_not_failure(self):
        self.assertEqual(g.evaluate(self.now(19, 3), 0, [])['status'], 'WAITING_WITHIN_24H_GRACE')

    def test_success_failed_prior_week_and_wrong_branch(self):
        self.assertEqual(g.evaluate(self.now(), 0, [self.receipt()])['status'], 'HEALTHY')
        self.assertEqual(g.evaluate(self.now(), 0, [self.receipt(conclusion='failure')])['status'], 'FAILED_SCHEDULE')
        for receipt in (self.receipt(date='2026-10-12T01:00:00Z'), self.receipt(branch='feature')):
            self.assertEqual(g.evaluate(self.now(), 0, [receipt])['status'], 'MISSING_SCHEDULE')

    def test_newest_attempt_wins_and_stuck_run_is_not_success(self):
        failed = self.receipt(conclusion='failure', date='2026-10-19T03:00:00Z')
        self.assertEqual(g.evaluate(self.now(), 0, [self.receipt(), failed])['status'], 'FAILED_SCHEDULE')
        running = {**failed, 'status': 'in_progress', 'conclusion': None}
        self.assertEqual(g.evaluate(self.now(), 0, [running])['status'], 'SCHEDULE_NOT_COMPLETED')

    def test_monday_before_diagnostics_due_checks_previous_week(self):
        now = dt.datetime(2026, 10, 19, 0, 20, tzinfo=dt.timezone.utc)
        receipt = self.receipt(date='2026-10-12T01:00:00Z')
        self.assertEqual(g.evaluate(now, 45, [receipt])['status'], 'HEALTHY')
