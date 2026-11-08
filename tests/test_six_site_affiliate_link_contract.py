"""Public affiliate CTA checks must not pretend that missing stock is a 404."""
import unittest
from scripts.six_site_affiliate_link_contract import (
    TARGETS, inspect_anchor, audit_html, audit_camp_source, is_candidate,
)


class SixSiteAffiliateContractTests(unittest.TestCase):
    def test_rakuten_https_sponsored_new_tab_safe(self):
        link = inspect_anchor({
            "href": "https://hb.afl.rakuten.co.jp/hgc/example?pc=abc",
            "target": "_blank", "rel": "nofollow sponsored noopener",
        })
        self.assertEqual(link["problems"], [])
        self.assertEqual(link["host"], "hb.afl.rakuten.co.jp")
        self.assertFalse(link["externalHostNeedsReview"])

    def test_disallowed_url_schemes_missing_sponsored_and_opener(self):
        for url in (None, "https://[bad-host",
                    "javascript:alert(1)", "http://item.rakuten.co.jp/test/",
                    "//item.rakuten.co.jp/test/", "https://someone@example.com/"):
            with self.subTest(url=url):
                errors = inspect_anchor({
                    "href": url, "target": "_blank", "rel": "nofollow",
                })["problems"]
                self.assertIn("INVALID_OR_NON_HTTPS_URL", errors)
                self.assertIn("MISSING_SPONSORED_REL", errors)
                self.assertIn("MISSING_NOOPENER", errors)

    def test_unknown_https_host_gets_review_not_invented_seller_failure(self):
        checked = inspect_anchor({
            "href": "https://redirect.example/path", "target": "_blank",
            "rel": "sponsored noopener",
        })
        self.assertEqual(checked["problems"], [])
        self.assertTrue(checked["externalHostNeedsReview"])

    def test_eligible_cta_selection_does_not_include_internal_links(self):
        self.assertTrue(is_candidate("daily", {"class": "cta buy-button"}))
        self.assertFalse(is_candidate("daily", {"class": "view-details"}))
        self.assertTrue(is_candidate("pet", {"data-affiliate-link": None}))
        self.assertFalse(is_candidate("pet", {"data-merchant": "rakuten"}))
        self.assertTrue(is_candidate("baby", {"data-affiliate": "rakuten"}))
        self.assertTrue(is_candidate("food", {"data-affiliate": "rakuten"}))
        self.assertTrue(is_candidate("kyo-bodo", {"data-affiliate": "rakuten"}))

    def test_productless_static_page_is_not_declared_broken(self):
        html = '<html><a href="#guide">料金の計算方法</a></html>'
        for site, _ in TARGETS:
            result = audit_html(site, html)
            self.assertEqual(result["status"], "NO_RENDERED_CTA")
            self.assertEqual(result["ctaCount"], 0)

    def test_bad_sponsored_link_is_detected_without_exposing_url(self):
        html = ('<a class="buy-button" href="http://example.test/id123" '
                'target="_blank">買う</a>')
        result = audit_html("daily", html)
        self.assertEqual(result["status"], "UNSAFE_LINK_CONTRACT")
        self.assertEqual(result["ctaCount"], 1)
        self.assertEqual(result["problemCounts"]["MISSING_SPONSORED_REL"], 1)
        self.assertNotIn("id123", str(result))

    def test_source_only_camp_check_cannot_claim_browser_verified(self):
        s = ('data-affiliate="sample" 楽天で価格・在庫を確認 '
             'これを楽天で買う rel="sponsored nofollow noopener" '
             'affiliateClickSource(route) '
             'purchaseSelectionContext(t.dataset.category,plan(state,data))')
        result = audit_camp_source(s)
        self.assertEqual(result["status"], "SOURCE_CONTRACT_PRESENT")
        self.assertEqual(result["inspection"], "LIVE_JS_SOURCE_ONLY")
        self.assertNotIn("ctaCount", result)
        self.assertEqual(audit_camp_source("no affiliate JS")["status"],
                         "SOURCE_CONTRACT_MISSING")


if __name__ == "__main__":
    unittest.main()
