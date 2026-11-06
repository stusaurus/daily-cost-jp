"""Offline contract checks for public Pages verification, not live assertions."""
import unittest
from scripts.six_site_live_release import ORIGIN, CHECKS, assess, make_report


class LiveReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.daily = CHECKS[0]
        self.baby = CHECKS[1]
        self.url = ORIGIN + self.daily["path"]

    def html(self, spec, extra="", *, canonical=None, robots="index,follow"):
        canonical = canonical if canonical is not None else ORIGIN + spec["path"]
        return (f'<html><head><link rel="canonical" href="{canonical}">'
                f'<meta name="robots" content="{robots}"></head>'
                f'<body><h1>比較</h1>{extra}</body></html>')

    def test_expected_live_marker_passes(self):
        result = assess(self.daily, self.html(self.daily, self.daily["marker"]),
                        final_url=self.url)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["canonical"], self.url)
        self.assertEqual(result["h1Count"], 1)

    def test_missing_required_marker_is_deployment_mismatch(self):
        result = assess(self.daily, self.html(self.daily))
        self.assertEqual(result["status"], "FEATURE_MISSING")

    def test_unshown_conditional_link_is_not_false_failure(self):
        result = assess(self.baby, self.html(self.baby))
        self.assertEqual(result["status"], "CONDITIONAL_FEATURE_NOT_SHOWN")

    def test_noindex_and_wrong_canonical_cannot_pass_as_seo_ready(self):
        for body in (self.html(self.daily, self.daily["marker"], robots="noindex"),
                     self.html(self.daily, self.daily["marker"], canonical=ORIGIN + "/wrong/"),
                     "<html><head></head><body>no headings</body></html>"):
            with self.subTest(body=body[:55]):
                self.assertEqual(assess(self.daily, body)["status"],
                                 "SEO_METADATA_MISMATCH")

    def test_optional_product_page_may_safely_be_noindex(self):
        spec = CHECKS[2]
        result = assess(spec, self.html(spec, robots="noindex"))
        self.assertEqual(result["status"], "CONDITIONAL_FEATURE_NOT_SHOWN")

    def test_non_200_and_cross_path_redirect_fail(self):
        self.assertEqual(assess(self.daily, "", status_code=503)["status"], "HTTP_ERROR")
        self.assertEqual(assess(self.daily, self.html(self.daily, self.daily["marker"]),
                                final_url=ORIGIN + "/elsewhere/")["status"],
                         "REDIRECTED")

    def test_javascript_does_not_require_html_canonical(self):
        spec = CHECKS[4]
        self.assertEqual(assess(spec, "function calculateWithStock(){}")["status"], "PASS")

    def test_report_keeps_missing_critical_and_conditional_distinct(self):
        report = make_report([
            {"site": "daily", "status": "PASS"},
            {"site": "baby", "status": "CONDITIONAL_FEATURE_NOT_SHOWN"},
            {"site": "food", "status": "FEATURE_MISSING"},
            {"site": "pet", "status": "NETWORK_ERROR"},
        ], observed_at="2026-11-06T00:00:00+00:00")
        self.assertEqual((report["passed"], report["conditionalNotShown"],
                          report["failures"]), (1, 1, 2))


if __name__ == "__main__":
    unittest.main()
