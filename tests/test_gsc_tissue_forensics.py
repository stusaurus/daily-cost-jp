"""No-key, offline tests for the Search Console tissue decline investigation."""
import importlib.util
import pathlib
import unittest

target = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gsc_tissue_forensics.py"
spec = importlib.util.spec_from_file_location("gsc_tissue_forensics", target)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(keys=None, impressions=20, clicks=2, position=10):
    obj = {"impressions": impressions, "clicks": clicks, "ctr": clicks / impressions if impressions else 0, "position": position}
    if keys is not None:
        obj["keys"] = keys
    return obj


def make_period(views, mobile=None, pc=None, queries=5):
    devices = []
    if mobile is not None:
        devices.append(row(["MOBILE"], mobile, min(mobile, 1)))
    if pc is not None:
        devices.append(row(["DESKTOP"], pc, min(pc, 1)))
    return {
        "aggregate": module.aggregate({"rows": [row(impressions=views, clicks=min(views, 2))]}),
        "devices": module.device_rows({"rows": devices}),
        "anonymous_queries": module.anonymous_query_coverage({
            "rows": [row(["private_query_" + str(i)], 2, 0) for i in range(queries)]
        }),
    }


class TissueForensicsTests(unittest.TestCase):
    def test_fixed_before_and_after_windows_are_disjoint(self):
        self.assertEqual(module.PERIODS["before"], ["2026-09-20", "2026-09-26"])
        self.assertEqual(module.PERIODS["after"], ["2026-09-27", "2026-10-03"])

    def test_metrics_reject_invalid_negatives_floats_and_nan(self):
        for bad in [
            row(impressions=-1, clicks=0),
            row(impressions=2.5, clicks=1),
            {"impressions": 10, "clicks": float("nan"), "ctr": .1, "position": 8},
            {"impressions": 10, "clicks": 1, "ctr": 1.2, "position": 8},
            {"impressions": 10, "clicks": 1, "ctr": .1, "position": -2},
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.metric(bad)

    def test_missing_aggregate_does_not_become_zero(self):
        self.assertEqual(module.aggregate({})["status"], "NO_ROW_UNKNOWN")
        self.assertIsNone(module.aggregate({"rows": []})["metrics"])

    def test_aggregate_row_with_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            module.aggregate({"rows": [row(["some-key"])]})

    def test_device_aggregation_keeps_missing_device_unknown(self):
        output = module.device_rows({"rows": [
            row(["MOBILE"], 20, 1), row(["DESKTOP"], 10, 2)]})
        self.assertEqual(output["devices"]["MOBILE"]["impressions"], 20)
        self.assertIsNone(output["devices"]["TABLET"])
        self.assertEqual(output["returned_rows"], 2)

    def test_invalid_and_duplicate_device_rows_rejected(self):
        cases = [
            {"rows": [row(["MOBILE"], 20), row(["MOBILE"], 10)]},
            {"rows": [row(["TELEVISION"], 20)]},
            {"rows": [row(["MOBILE", "DESKTOP"], 20)]},
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.device_rows(bad)

    def test_raw_query_strings_never_saved(self):
        source = {"rows": [
            row(["someone_name private address"], 2, 0),
            row(["another private phrase"], 3, 1),
        ]}
        result = module.anonymous_query_coverage(source)
        self.assertEqual(result["rows_returned"], 2)
        self.assertEqual(result["visible_row_impressions"], 5)
        self.assertFalse(result["raw_queries_exported"])
        self.assertNotIn("private", str(result))
        self.assertNotIn("someone_name", str(result))

    def test_query_dimension_shape_rejected(self):
        with self.assertRaises(ValueError):
            module.anonymous_query_coverage({"rows": [row(["query", "device"])]})

    def test_index_snapshot_limits_fields_and_marks_history_unavailable(self):
        response = {"inspectionResult": {"indexStatusResult": {
            "verdict": "PASS", "coverageState": "Submitted and indexed",
            "lastCrawlTime": "2026-10-04T08:20:00Z",
            "googleCanonical": module.PAGE,
            "referringUrls": ["https://somewhere.example/internal/private"],
        }}}
        parsed = module.inspection_snapshot(response)
        self.assertEqual(parsed["status"], "OBSERVED")
        self.assertFalse(parsed["historical_status_available"])
        self.assertEqual(parsed["index"]["googleCanonical"], module.PAGE)
        self.assertNotIn("referringUrls", parsed["index"])

    def test_external_canonical_is_not_exported_unfiltered(self):
        output = module.inspection_snapshot({"inspectionResult": {"indexStatusResult": {
            "verdict": "NEUTRAL", "googleCanonical": "https://other.example/private?secret=x"
        }}})
        self.assertEqual(output["index"]["googleCanonical"], "OTHER_CANONICAL_REQUIRES_REVIEW")
        self.assertNotIn("secret", str(output))

    def test_conservative_comparison_handles_small_samples(self):
        out = module.compare({"metrics": module.metric(row(impressions=30))},
                             {"metrics": module.metric(row(impressions=1, clicks=0))})
        self.assertEqual(out["impression_change"], -29)
        self.assertEqual(out["status"], "LOW_SAMPLE")
        self.assertEqual(out["cause"], "UNKNOWN")

    def test_missing_period_blocks_comparison(self):
        out = module.compare({"metrics": None}, {"metrics": module.metric(row())})
        self.assertEqual(out["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(out["impression_change"])

    def test_full_report_shows_devices_and_index_without_causal_claim(self):
        data = {
            "before": make_period(34, mobile=20, pc=14),
            "after": make_period(3, mobile=2, pc=1),
        }
        index = module.inspection_snapshot({"inspectionResult": {"indexStatusResult": {
            "verdict": "PASS", "pageFetchState": "SUCCESSFUL",
        }}})
        result = module.report_for(data, index)
        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertEqual(result["change"]["impression_change"], -31)
        self.assertEqual(result["devices"]["MOBILE"]["impression_change"], -18)
        self.assertIsNone(result["devices"]["TABLET"]["impression_change"])
        self.assertTrue(result["no_keyword_strings_exported"])
        self.assertTrue(result["no_automatic_seo_edits"])
        self.assertIn("9月27", module.markdown(result))
        self.assertIn("Googleに記録", module.markdown(result))

    def test_device_totals_mismatch_is_labeled_not_misrepresented(self):
        data = {
            "before": make_period(50, mobile=30, pc=5, queries=0),
            "after": make_period(8, mobile=8, pc=None, queries=0),
        }
        result = module.report_for(data, {"status": "NO_INDEX_STATUS"})
        self.assertEqual(result["device_coverage"]["before"]["status"],
                         "DIFFERENT_GROUPED_TOTALS")
        self.assertEqual(result["device_coverage"]["after"]["status"], "MATCHED")
        message = module.markdown(result)
        self.assertIn("端末別集計の整合性：DIFFERENT_GROUPED_TOTALS", message)
        self.assertIn("集計行 0行", message)
        self.assertIn("実際の検索語総数ではありません", message)

    def test_partial_data_report_is_not_sold_as_zero(self):
        before = make_period(12, mobile=10, pc=2)
        after = make_period(2)
        after["aggregate"] = module.aggregate({})
        result = module.report_for({"before": before, "after": after},
                                   {"status": "HTTP_403_FORBIDDEN_OR_QUOTA"})
        self.assertEqual(result["status"], "DATA_LIMITED")
        self.assertEqual(result["index_inspection"]["status"], "HTTP_403_FORBIDDEN_OR_QUOTA")
        self.assertIn("不明", module.markdown(result))

    def test_invalid_window_list_rejected(self):
        with self.assertRaises(ValueError):
            module.report_for({"before": make_period(10)}, {"status": "UNAVAILABLE"})

    def test_exception_reasons_are_sanitized(self):
        self.assertEqual(module.sanitized_api_error(429), "HTTP_429_QUOTA")
        self.assertEqual(module.sanitized_api_error(403), "HTTP_403_FORBIDDEN_OR_QUOTA")
        self.assertEqual(module.sanitized_api_error(503), "HTTP_5XX_SERVER")


if __name__ == "__main__":
    unittest.main()
