"""Offline priority, safety and dedupe tests. No network or secrets."""
import datetime as dt
import json
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import autonomous_operations_triage as triage
import autonomous_operations_issue as issue

SITE = triage.SITE
TISSUE = "/categories/tissue/"


def joined(code="CHECK_SEARCH_RESULT_APPEAL", impressions=124):
    return {"source": triage.JOINT_SOURCE, "site": SITE, "status": "JOINT_PROVISIONAL",
            "top_investigations": [{
                "path": TISSUE, "code": code,
                "gsc_last_28": {"impressions": impressions, "clicks": 2,
                                "ctr": .016, "position": 12},
                "confidence": "INVESTIGATION_ONLY",
            }]}


def browser(fail=False):
    status = "FAIL" if fail else "PASS"
    return {"site": SITE, "read_only": True,
            "observations": [
                {"path": TISSUE, "viewport": width, "status": status,
                 "problems": [{"code": "CTA"}] if fail else []}
                for width in (1440, 390, 320)]}


def health(fail=False):
    return {"result": "fail" if fail else "pass", "checks": [
        {"path": "/", "status": "fail" if fail else "pass"},
        {"path": "/categories/tissue/", "status": "pass"}]}


def quality(state="FRESH", errors=None, warnings=None):
    return {"status": state, "errors": errors or [], "warnings": warnings or []}


def evaluate(*, j=None, b=None, h=None, q=None, g=None):
    return triage.evaluate(joined() if j is None else j,
                           browser() if b is None else b,
                           health() if h is None else h,
                           quality() if q is None else q, g)


class PriorityTests(unittest.TestCase):
    def test_low_ctr_is_only_research_not_auto_title_rewrite(self):
        r = evaluate()
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertEqual(r["findings"][0]["code"], "SEO_SNIPPET_RESEARCH")
        self.assertEqual(r["findings"][0]["severity"], "P2")
        for key in ("automatic_website_edits", "automatic_pull_requests",
                    "automatic_merge", "affiliate_sales_verified"):
            self.assertFalse(r[key])

    def test_bad_http_outweighs_seo_and_cannot_autofix(self):
        r = evaluate(h=health(fail=True))
        self.assertEqual(r["status"], "URGENT_REVIEW")
        self.assertEqual(r["findings"][0]["code"], "LIVE_HTTP_FAILURE")
        self.assertFalse(r["findings"][0]["auto_fix_allowed"])

    def test_failed_browser_on_three_widths_produces_one_issue(self):
        r = evaluate(b=browser(fail=True))
        faults = [x for x in r["findings"] if x["code"] == "BROWSER_CTA_FAILURE"]
        self.assertEqual(len(faults), 1)
        self.assertEqual(faults[0]["severity"], "P1")

    def test_stale_quality_is_unknown_not_pass(self):
        r = evaluate(q=quality("STALE", errors=["old test error"]))
        self.assertTrue(any(x["code"] == "QUALITY_REPORT_UNAVAILABLE" for x in r["findings"]))
        self.assertFalse(any(x["code"] == "PRODUCT_QUALITY_FAILURE" for x in r["findings"]))

    def test_fresh_quality_error_requires_review_and_no_raw_text_is_published(self):
        msg = "private name+special@example.org - quantity mismatch"
        r = evaluate(q=quality(errors=[msg]))
        failures = [x for x in r["findings"] if x["code"] == "PRODUCT_QUALITY_FAILURE"]
        self.assertEqual(len(failures), 1)
        self.assertNotIn("special@example.org", json.dumps(r))

    def test_search_missing_is_not_zero_impressions(self):
        bad = joined()
        bad["status"] = "GSC_UNAVAILABLE"
        r = evaluate(j=bad)
        self.assertTrue(any(x["code"] == "GSC_DATA_UNAVAILABLE" for x in r["findings"]))
        self.assertFalse(any(x["code"] == "SEO_SNIPPET_RESEARCH" for x in r["findings"]))

    def test_different_search_impressions_do_not_spam_identical_issue(self):
        first = evaluate(j=joined(impressions=124))
        second = evaluate(j=joined(impressions=120))
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_operator_unknown_is_priority_one(self):
        r = evaluate(j=joined(code="VERIFY_CLICK_ATTRIBUTION"))
        self.assertEqual(r["findings"][0]["code"], "GA4_CLICK_ATTRIBUTION_UNCERTAIN")
        self.assertEqual(r["findings"][0]["severity"], "P1")

    def test_invalid_site_is_rejected_for_browser_and_joint_evidence(self):
        j = joined()
        j["site"] = "https://stusaurus.github.io/sotojitaku/"
        b = browser()
        b["site"] = j["site"]
        r = evaluate(j=j, b=b)
        codes = [f["code"] for f in r["findings"]]
        self.assertIn("ANALYTICS_JOIN_UNAVAILABLE", codes)
        self.assertIn("BROWSER_AUDIT_UNAVAILABLE", codes)

    def test_invalid_path_cannot_escape_site(self):
        self.assertFalse(triage.good_path("//evil.example/"))
        self.assertFalse(triage.good_path("/../.git/"))
        self.assertFalse(triage.good_path("https://example.org/"))
        self.assertTrue(triage.good_path(TISSUE))

    def test_missing_monitoring_is_not_marked_ok(self):
        r = triage.evaluate(None, None, None, None, None)
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertGreater(len(r["findings"]), 0)
        self.assertIn("未取得", triage.markdown(r))

    def test_quality_url_must_be_exact(self):
        with self.assertRaises(ValueError):
            triage.fetch_public_quality("https://evil.example/status")

    def test_fetch_quality_healthy_and_expired(self):
        now = dt.datetime.now(dt.timezone.utc)
        src = {"updated_at": now.isoformat(), "errors": [], "warnings": []}
        response = MagicMock()
        response.status = 200
        response.geturl.return_value = triage.QUALITY_URL
        response.read.return_value = json.dumps(src).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(triage, "urlopen", return_value=response):
            self.assertEqual(triage.fetch_public_quality()["status"], "FRESH")
        src["updated_at"] = (now - dt.timedelta(days=10)).isoformat()
        response.read.return_value = json.dumps(src).encode()
        with patch.object(triage, "urlopen", return_value=response):
            self.assertEqual(triage.fetch_public_quality()["status"], "STALE")

    def test_markdown_reports_priorities_and_sales_unknown(self):
        r = evaluate()
        txt = triage.markdown(r)
        self.assertIn("収益・成約件数は未接続", txt)
        self.assertIn("SEO_SNIPPET_RESEARCH", json.dumps(r))
        self.assertNotIn("サイトの変更を実行しました", txt)


class IssueDedupeTests(unittest.TestCase):
    def report(self):
        return evaluate()

    def test_one_issue_created_when_findings_exist(self):
        with patch.object(issue, "github_request", side_effect=[
            [], {"number": 55, "html_url": f"https://github.com/{issue.REPO}/issues/55"}]) as api:
            answer = issue.sync_issue(self.report(), "fake", "38048780107",
                                      "refs/heads/main", issue.REPO)
        self.assertEqual(answer["status"], "CREATED")
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args.args[0], "/issues")
        self.assertIn(issue.MARKER, api.call_args.args[3]["body"])

    def test_same_findings_within_week_never_updates_issue(self):
        r = self.report()
        old = {"number": 55, "title": issue.ISSUE_TITLE,
               "body": issue.render_issue(r, f"https://github.com/{issue.REPO}/actions/runs/12345678"),
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "html_url": f"https://github.com/{issue.REPO}/issues/55"}
        with patch.object(issue, "github_request", return_value=[old]) as api:
            answer = issue.sync_issue(r, "fake", "38048780107", "refs/heads/main", issue.REPO)
        self.assertEqual(answer["status"], "UNCHANGED")
        self.assertEqual(api.call_count, 1)

    def test_changed_queue_updates_same_issue_not_creates_new_one(self):
        oldr = self.report()
        newr = evaluate(b=browser(fail=True))
        old = {"number": 55, "title": issue.ISSUE_TITLE,
               "body": issue.render_issue(oldr, f"https://github.com/{issue.REPO}/actions/runs/12345678"),
               "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        with patch.object(issue, "github_request", side_effect=[
            [old], {"number": 55, "html_url": "https://github.com/.../issues/55"}]) as api:
            answer = issue.sync_issue(newr, "fake", "38048780107", "refs/heads/main", issue.REPO)
        self.assertEqual(answer["status"], "UPDATED")
        self.assertEqual(api.call_args.args[0], "/issues/55")
        self.assertEqual(api.call_args.args[2], "PATCH")

    def test_duplicate_rolling_issues_fail_closed(self):
        r = self.report()
        duplicate = {"number": 1, "title": issue.ISSUE_TITLE,
                     "body": issue.MARKER, "html_url": "x"}
        with patch.object(issue, "github_request", return_value=[duplicate, duplicate]):
            with self.assertRaises(ValueError):
                issue.sync_issue(r, "fake", "38048780107", "refs/heads/main", issue.REPO)

    def test_not_on_main_cannot_publish_issue(self):
        with patch.object(issue, "github_request") as api:
            with self.assertRaises(ValueError):
                issue.sync_issue(self.report(), "fake", "38048780107",
                                 "refs/heads/pull/4/merge", issue.REPO)
            api.assert_not_called()

    def test_invalid_repo_and_run_url_are_rejected(self):
        with self.assertRaises(ValueError):
            issue.sync_issue(self.report(), "fake", "38048780107", "refs/heads/main",
                             "other/website")
        with self.assertRaises(ValueError):
            issue.render_issue(self.report(), "https://evil.example/actions/42")


if __name__ == "__main__":
    unittest.main()
