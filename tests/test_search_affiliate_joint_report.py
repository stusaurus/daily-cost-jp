"""Offline safety and cross-source interpretation tests for GSC+GA4 reports."""
import copy
import importlib.util
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("search_affiliate_joint_report", SCRIPTS / "search_affiliate_joint_report.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SITE = "https://stusaurus.github.io/daily-cost-jp/"
TISSUE = "/categories/tissue/"
LAUNDRY = "/categories/laundry/"
TOILET = "/categories/toilet-paper/"


def gsc_metrics(clicks=2, views=100, ctr=None, rank=12):
    return {"clicks": clicks, "impressions": views,
            "ctr": clicks / views if ctr is None else ctr, "position": rank}


def gsc_report(pages=None, status="PROVISIONAL"):
    selected = pages if pages is not None else [
        {"path": TISSUE, "last_28": gsc_metrics(2, 124, rank=12.02),
         "last_7": gsc_metrics(0, 3), "prior_7": gsc_metrics(1, 25)},
        {"path": LAUNDRY, "last_28": gsc_metrics(2, 117, rank=13.32),
         "last_7": gsc_metrics(0, 2), "prior_7": gsc_metrics(1, 20)},
        {"path": TOILET, "last_28": gsc_metrics(1, 81, rank=12.36),
         "last_7": gsc_metrics(0, 2), "prior_7": gsc_metrics(0, 10)},
    ]
    return {"source": module.SOURCE_GSC, "site_property": SITE, "status": status,
            "windows": {"last_28": ["2026-09-10", "2026-10-07"],
                        "last_7": ["2026-10-01", "2026-10-07"],
                        "prior_7": ["2026-09-24", "2026-09-30"]},
            "pages": selected, "reason": None}


def ga4_report(rows=None, dim=True):
    data = rows if rows is not None else [
        {"page": TISSUE, "periods": {"last_28": {
            "pageviews": 49, "clicks": {"production_operator": 1,
                                      "production_non_operator": 0,
                                      "production_unknown": 0}}}},
        {"page": LAUNDRY, "periods": {"last_28": {
            "pageviews": 17, "clicks": {"production_operator": 0,
                                      "production_non_operator": 0,
                                      "production_unknown": 0}}}},
    ]
    return {"source": module.SOURCE_GA4, "period_last_28": ["2026-09-11", "2026-10-08"],
            "operator_dimension_registered": dim, "status": "PARTIAL_OBSERVED_DAYS",
            "pages": data}


class JointReportTests(unittest.TestCase):
    def test_sources_are_reported_with_separate_non_matching_periods(self):
        result = module.combine(ga4_report(), gsc_report())
        self.assertEqual(result["status"], "JOINT_PROVISIONAL")
        self.assertTrue(result["not_same_population_or_period"])
        self.assertFalse(result["conversion_rate_calculated"])
        self.assertNotEqual(result["gsc_period_last_28"], result["ga4_period_last_28"])
        self.assertIn("成約率は算出しません", module.markdown(result))

    def test_organic_search_click_not_equated_to_rakuten_click(self):
        result = module.combine(ga4_report(), gsc_report())
        row = next(x for x in result["page_diagnostics"] if x["path"] == TISSUE)
        self.assertEqual(row["gsc_last_28"]["clicks"], 2)
        self.assertEqual(row["ga4_last_28"]["operator_tests"], 1)
        self.assertEqual(row["ga4_last_28"]["provisional_non_operator_clicks"], 0)
        self.assertNotIn("conversion_rate", row)
        self.assertIn("楽天クリックは売上", module.markdown(result))

    def test_known_high_impression_low_ctr_prompts_snippet_research(self):
        result = module.combine(ga4_report(), gsc_report())
        page = next(x for x in result["page_diagnostics"] if x["path"] == TISSUE)
        self.assertEqual(page["code"], "CHECK_SEARCH_RESULT_APPEAL")

    def test_unknown_operator_clicks_precede_all_funnel_hypotheses(self):
        ga = ga4_report()
        ga["pages"][0]["periods"]["last_28"]["clicks"]["production_unknown"] = 5
        result = module.combine(ga, gsc_report())
        page = next(x for x in result["page_diagnostics"] if x["path"] == TISSUE)
        self.assertEqual(page["code"], "VERIFY_CLICK_ATTRIBUTION")
        self.assertIn(" | 不明 | ", module.markdown(result))

    def test_no_gsc_file_does_not_turn_into_zero_impressions(self):
        result = module.combine(ga4_report(), None)
        self.assertEqual(result["status"], "GSC_UNAVAILABLE")
        self.assertEqual(result["top_investigations"][0]["code"], "GSC_CONNECTION_REQUIRED")
        self.assertIn("検索データがない", module.markdown(result))
        self.assertIn("不明", module.markdown(result))

    def test_explicit_not_connected_remains_unavailable(self):
        disconnected = {"source": module.SOURCE_GSC, "site_property": SITE,
                        "status": "NOT_CONNECTED", "reason": "PROPERTY_ACCESS_MISSING"}
        result = module.combine(ga4_report(), disconnected)
        self.assertEqual(result["gsc_unavailable_reason"], "PROPERTY_ACCESS_MISSING")
        self.assertEqual(result["status"], "GSC_UNAVAILABLE")

    def test_other_site_is_never_merged(self):
        wrong = gsc_report()
        wrong["site_property"] = "https://stusaurus.github.io/sotojitaku/"
        with self.assertRaises(ValueError):
            module.combine(ga4_report(), wrong)

    def test_other_site_ga4_source_is_rejected(self):
        ga4 = ga4_report()
        ga4["source"] = "Untrusted data"
        with self.assertRaises(ValueError):
            module.combine(ga4, gsc_report())

    def test_missing_gsc_row_is_unknown_not_zero(self):
        report = gsc_report(pages=[
            {"path": TISSUE, "last_28": gsc_metrics(3, 100),
             "last_7": gsc_metrics(1, 20), "prior_7": gsc_metrics(1, 50)}])
        result = module.combine(ga4_report(), report)
        missing = next(x for x in result["page_diagnostics"] if x["path"] == LAUNDRY)
        self.assertEqual(missing["code"], "GSC_PAGE_NOT_REPORTED")
        self.assertIsNone(missing["gsc_last_28"])
        self.assertIn(" | 不明 | ", module.markdown(result))

    def test_limited_search_exposure_is_research_not_an_error(self):
        report = gsc_report(pages=[
            {"path": TOILET, "last_28": gsc_metrics(0, 12), "last_7": gsc_metrics(0, 3),
             "prior_7": gsc_metrics(0, 7)}])
        result = module.combine(ga4_report(), report)
        selected = next(x for x in result["page_diagnostics"] if x["path"] == TOILET)
        self.assertEqual(selected["code"], "RESEARCH_SEARCH_DEMAND_OR_INDEXING")

    def test_search_click_and_ga4_zero_clicks_cannot_identify_same_users(self):
        report = gsc_report(pages=[
            {"path": TISSUE, "last_28": gsc_metrics(8, 180, rank=3),
             "last_7": gsc_metrics(3, 30), "prior_7": gsc_metrics(3, 40)}])
        ga = ga4_report()
        ga["pages"][0]["periods"]["last_28"]["pageviews"] = 70
        result = module.combine(ga, report)
        selected = next(x for x in result["page_diagnostics"] if x["path"] == TISSUE)
        self.assertEqual(selected["code"], "INSPECT_LANDING_TO_AFFILIATE_JOURNEY")
        self.assertIn("同一ユーザーの行動は不明", selected["hypothesis"])

    def test_disabled_operator_dimension_withholds_nonoperator_clicks_in_summary(self):
        result = module.combine(ga4_report(dim=False), gsc_report())
        self.assertFalse(result["ga4_operator_dimension_registered"])
        self.assertIn(" | 不明 | ", module.markdown(result))

    def test_unsafe_pages_are_not_followed(self):
        g = gsc_report(pages=[
            {"path": "//evil.example/", "last_28": gsc_metrics(1, 100)},
            {"path": "/a/../../secret/", "last_28": gsc_metrics(1, 100)}])
        report = module.combine(ga4_report(), g)
        self.assertTrue(all(module.safe_path(x["path"]) for x in report["page_diagnostics"]))
        self.assertNotIn("//evil.example/", [x["path"] for x in report["page_diagnostics"]])

    def test_invalid_periods_are_rejected(self):
        g = gsc_report()
        g["windows"]["last_28"] = ["2026-10-07", "2026-09-10"]
        with self.assertRaises(ValueError):
            module.combine(ga4_report(), g)

    def test_no_reportable_queries_blocks_seo_rewrites_without_claiming_zero_demand(self):
        output = module.combine(ga4_report(), gsc_report())
        self.assertEqual(output["gsc_public_query_rows"], 0)
        self.assertEqual(output["gsc_query_evidence_status"], "NO_REPORTABLE_QUERY_ROWS")
        self.assertFalse(output["seo_copy_change_authorized"])
        self.assertIn("クエリ不足", module.markdown(output))

    def test_threshold_filtered_query_count_is_metadata_only(self):
        gsc = gsc_report()
        gsc["top_queries"] = [{
            "page": TISSUE, "query": "ティッシュ 値段",
            "impressions": 25, "clicks": 1, "ctr": .04, "position": 10,
        }]
        output = module.combine(ga4_report(), gsc)
        self.assertEqual(output["gsc_public_query_rows"], 1)
        self.assertEqual(output["gsc_query_evidence_status"], "SOME_THRESHOLD_FILTERED_QUERY_ROWS")
        self.assertFalse(output["seo_copy_change_authorized"])

    def test_search_console_missing_keeps_query_coverage_unavailable(self):
        output = module.combine(ga4_report(), None)
        self.assertEqual(output["gsc_query_evidence_status"], "GSC_UNAVAILABLE")
        self.assertEqual(output["gsc_public_query_rows"], 0)
        self.assertFalse(output["seo_copy_change_authorized"])

    def test_top_rows_incomplete_does_not_claim_zero(self):
        result = module.combine(ga4_report(), gsc_report(status="TOP_ROW_COVERAGE_UNCERTAIN"))
        self.assertEqual(result["status"], "JOINT_PROVISIONAL")
        self.assertEqual(result["gsc_source_status"], "TOP_ROW_COVERAGE_UNCERTAIN")


if __name__ == "__main__":
    unittest.main()
