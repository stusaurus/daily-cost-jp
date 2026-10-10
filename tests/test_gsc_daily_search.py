"""Synthetic offline checks for Search Console day-level decline analysis."""
import copy
import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gsc_daily_search.py"
spec = importlib.util.spec_from_file_location("gsc_daily_search", path)
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)

ROOT = target.SITE
TISSUE = "/categories/tissue/"
LAUNDRY = "/categories/laundry/"
TOILET = "/categories/toilet-paper/"
DATES = ["2026-09-10", "2026-10-07"]


def sample():
    return {
        "source": target.SOURCE,
        "site_property": ROOT,
        "status": "PROVISIONAL",
        "windows": {
            "last_7": ["2026-10-01", "2026-10-07"],
            "prior_7": ["2026-09-24", "2026-09-30"],
        },
        "site_aggregates": {
            "last_7": {"metrics": {"impressions": 8, "clicks": 0}},
            "prior_7": {"metrics": {"impressions": 36, "clicks": 1}},
            "last_28": {"metrics": {"impressions": 44, "clicks": 1}},
        },
        "pages": [
            {"path": TISSUE, "last_7": {"impressions": 1, "clicks": 0},
             "prior_7": {"impressions": 30, "clicks": 1}},
            {"path": LAUNDRY, "last_7": {"impressions": 4, "clicks": 0},
             "prior_7": {"impressions": 3, "clicks": 0}},
            {"path": TOILET, "last_7": {"impressions": 2, "clicks": 0},
             "prior_7": {"impressions": 1, "clicks": 0}},
        ],
    }


def row(keys, impressions=1, clicks=0):
    return {"keys": keys, "impressions": impressions, "clicks": clicks}


class DailySearchTests(unittest.TestCase):
    def test_exact_site_scope_only(self):
        self.assertEqual(target.path_from_url(ROOT + "categories/tissue/"), TISSUE)
        for other in (
            "https://stusaurus.github.io/sotojitaku/",
            "https://fake.example/daily-cost-jp/categories/tissue/",
            "http://stusaurus.github.io/daily-cost-jp/categories/tissue/",
            "https://stusaurus.github.io.evil/daily-cost-jp/categories/tissue/",
            "https://stusaurus.github.io:8888/daily-cost-jp/categories/tissue/",
        ):
            self.assertIsNone(target.path_from_url(other), other)

    def test_date_response_keeps_categories_and_excludes_unrelated_pages(self):
        site = {"rows": [row(["2026-09-10"], 40), row(["2026-10-07"], 4)]}
        pages = {"rows": [
            row(["2026-09-10", ROOT + "categories/tissue/"], 30),
            row(["2026-10-07", ROOT + "categories/tissue/"], 1),
            row(["2026-10-07", ROOT + "categories/laundry/"], 3),
            row(["2026-10-07", ROOT + "categories/bath-cleaner/"], 1),
            row(["2026-10-07", "https://stusaurus.github.io/sotojitaku/"], 1),
        ]}
        normalized = target.normalize_daily(site, pages, DATES)
        self.assertEqual(normalized["status"], "OBSERVED_DAILY_ROWS")
        self.assertEqual(normalized["site_dates_observed"], 2)
        self.assertEqual(normalized["site"]["2026-09-10"]["impressions"], 40)
        self.assertEqual(normalized["core_pages"][TISSUE]["2026-10-07"]["impressions"], 1)
        self.assertEqual(normalized["other_pages_discarded"], 2)
        self.assertNotIn("2026-10-06", normalized["site"])

    def test_empty_api_rows_are_not_fabricated_zero_series(self):
        output = target.normalize_daily({}, {}, DATES)
        self.assertEqual(output["status"], "NO_OBSERVED_DAYS")
        self.assertEqual(output["site"], {})
        self.assertEqual(output["core_pages"][TISSUE], {})

    def test_malformed_duplicate_or_out_of_range_rows_fail_closed(self):
        bad = [
            {"rows": [row(["2026-10-08"])]},
            {"rows": [row(["2026-09-10"]), row(["2026-09-10"])]},
            {"rows": [row(["not-a-date"])]},
            {"rows": [row(["2026-10-01", "extra"])]},
            {"rows": [row(["2026-09-10"], -1)]},
            {"rows": [row(["2026-09-10"], 1.5)]},
        ]
        for response in bad:
            with self.subTest(response=response), self.assertRaises(ValueError):
                target.normalize_daily(response, {}, DATES)

    def test_category_duplicate_day_rejected(self):
        page = ROOT + "categories/tissue/"
        rows = {"rows": [row(["2026-09-10", page]), row(["2026-09-10", page])]}
        with self.assertRaises(ValueError):
            target.normalize_daily({}, rows, DATES)

    def test_descriptive_decline_36_to_8_is_low_sample_not_search_penalty(self):
        report = target.weekly_comparison(sample())
        self.assertEqual(report["site"]["previous"], 36)
        self.assertEqual(report["site"]["current"], 8)
        self.assertEqual(report["site"]["difference"], -28)
        self.assertEqual(report["site"]["status"], "LOW_SAMPLE")
        self.assertEqual(report["largest_observed_decrease"], TISSUE)
        self.assertIn("原因を断定しません", target.markdown(report))
        self.assertTrue(report["no_automatic_seo_rewrite"])

    def test_tissue_accounts_for_decline_while_other_categories_rise(self):
        out = target.weekly_comparison(sample())
        parts = {part["path"]: part for part in out["pages"]}
        self.assertEqual(parts[TISSUE]["previous"], 30)
        self.assertEqual(parts[TISSUE]["current"], 1)
        self.assertEqual(parts[TISSUE]["difference"], -29)
        self.assertEqual(parts[LAUNDRY]["difference"], 1)
        self.assertEqual(parts[TOILET]["difference"], 1)
        self.assertEqual(parts[TISSUE]["status"], "LOW_SAMPLE")

    def test_missing_page_row_is_unknown_not_zero(self):
        fixture = sample()
        fixture["pages"] = fixture["pages"][:1]
        data = target.weekly_comparison(fixture)
        selected = {r["path"]: r for r in data["pages"]}
        self.assertEqual(selected[LAUNDRY]["status"], "UNKNOWN")
        self.assertIsNone(selected[LAUNDRY]["previous"])
        self.assertIn("不明", target.markdown(data))

    def test_invalid_property_does_not_mix_other_site_data(self):
        fixture = sample()
        fixture["site_property"] = "https://stusaurus.github.io/"
        with self.assertRaises(ValueError):
            target.weekly_comparison(fixture)

    def test_lost_connection_is_not_interpreted_as_zero(self):
        fixture = sample()
        fixture["status"] = "NOT_CONNECTED"
        result = target.weekly_comparison(fixture)
        self.assertEqual(result["status"], "GSC_UNAVAILABLE")
        self.assertIsNone(result["site"]["current"])
        self.assertIn("0回と扱いません", target.markdown(result))

    def test_daily_aggregate_mismatch_withholds_misleading_day_chart(self):
        fixture = sample()
        fixture["daily_series"] = target.normalize_daily(
            {"rows": [row(["2026-09-10"], 100)]},
            {"rows": [row(["2026-09-10", ROOT + "categories/tissue/"], 30)]},
            DATES,
        )
        result = target.weekly_comparison(fixture)
        self.assertEqual(result["daily_status"], "AGGREGATION_MISMATCH")
        self.assertIsNone(result["daily"])
        self.assertIn("集計不整合", target.markdown(result))

    def test_matching_daily_aggregates_support_dated_table_without_zero_fill(self):
        fixture = sample()
        fixture["daily_series"] = target.normalize_daily(
            {"rows": [row(["2026-09-10"], 36), row(["2026-10-07"], 8)]},
            {"rows": [row(["2026-09-10", ROOT + "categories/tissue/"], 30),
                      row(["2026-10-07", ROOT + "categories/tissue/"], 1)]},
            DATES,
        )
        result = target.weekly_comparison(fixture)
        self.assertEqual(result["daily_status"], "OBSERVED_DAILY_ROWS")
        self.assertEqual(result["daily"]["site_dates_observed"], 2)
        content = target.markdown(result)
        self.assertIn("| 2026-10-07 | 8 | 1 | 不明 | 不明 |", content)
        self.assertIn("| 2026-10-06 | 不明 | 不明 | 不明 | 不明 |", content)


if __name__ == "__main__":
    unittest.main()
