import unittest

from scripts.gsc_six_sites_scorecard import scorecard, scorecard_markdown
from scripts.gsc_six_sites import SITES


def fixture():
    names = [name for name, _ in SITES]
    root = dict(SITES)
    def site(name, daily, query, inspection):
        return {
            "name": name, "property": root[name], "status": "OBSERVED",
            "analytics": {
                "daily_28d": {"status": "OBSERVED_ROWS", "rows": [
                    {"key": "2026-10-30", "clicks": 1 if name == "日用品" else 0, "impressions": daily},
                ]},
                "pages_28d": {"status": "OBSERVED_ROWS", "rows": [
                    {"key": root[name], "clicks": 0, "impressions": 999999}
                ]},
                "queries_28d": {"status": "OBSERVED_ROWS", "rows": [
                    {"key": x, "clicks": 0, "impressions": 1} for x in query
                ]} if query else {"status": "NO_ROWS", "rows": []},
                "query_pages_28d": {"status": "OBSERVED_ROWS", "rows": [
                    {"key": q, "path": path,
                     "page": root[name] + path.lstrip("/"),
                     "clicks": 0, "impressions": impressions,
                     "position": position}
                    for q, path, impressions, position in (
                        [("洗濯洗剤 安い 店 ランキング", "/categories/laundry/", 26, 7.65),
                         ("site:github.io", "/", 3, 3.0)]
                        if name == "日用品" else
                        [("ボード ゲーム 二 人 用", "/scenes/two-player/", 3, 72.67)]
                        if name == "ボードゲーム" else []
                    )
                ]} if name in ("日用品", "ボードゲーム")
                else {"status": "NO_ROWS", "rows": []},
            },
            "inspection": inspection,
        }
    pages = [
        {"path": "/", "status": "OBSERVED_SNAPSHOT", "verdict": "PASS",
         "coverage_state": "Submitted and indexed",
         "public": {"status": "PUBLIC_HTML", "http_status": 200,
                    "canonical": [root[names[0]]], "robots": ["index,follow"]}},
        {"path": "/tools/laundry-cost-per-wash/", "status": "OBSERVED_SNAPSHOT",
         "verdict": "NEUTRAL", "coverage_state": "URL is unknown to Google",
         "public": {"status": "PUBLIC_HTML", "http_status": 200,
                    "canonical": [root[names[0]] + "tools/laundry-cost-per-wash/"],
                    "robots": ["index,follow"]}},
    ]
    return {"source": "Google Search Console Search Analytics + URL Inspection APIs (read-only)",
            "status": "READY", "as_of_pacific": "2026-11-02",
            "date_windows": {"last_28": ["2026-10-03", "2026-10-30"],
                             "last_7": ["2026-10-24", "2026-10-30"]},
            "sites": [
                site(names[0], 111, ["洗濯洗剤 安い 店 ランキング", "site:github.io"], pages),
                site(names[1], 5, ["site:github.io"], []),
                site(names[2], 1, ["site:github.io"], []),
                site(names[3], 1, [], []),
                site(names[4], 35, ["2人用 ボードゲーム"], []),
                site(names[5], 4, ["site:github.io"], []),
            ]}


class GscSixSitesScorecardTests(unittest.TestCase):
    def test_exact_six_site_28day_daily_counts_ignore_non_additive_page_rows(self):
        board = scorecard(fixture())
        self.assertEqual(board["status"], "READY")
        rows = {s["name"]: s for s in board["sites"]}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows["日用品"]["daily"], {
            "impressions": 111, "clicks": 1, "reported_days": 1})
        self.assertNotEqual(rows["日用品"]["daily"]["impressions"], 999999)
        self.assertEqual(board["sites"][0]["name"], "日用品")
        self.assertEqual(board["sites"][1]["name"], "ボードゲーム")
        self.assertEqual(rows["食品"]["query_status"], "NO_ROWS")
        self.assertIsNone(rows["食品"]["natural_query_rows"])

    def test_site_operator_only_is_not_commercial_keyword_proof(self):
        rows = {s["name"]: s for s in scorecard(fixture())["sites"]}
        self.assertEqual(rows["日用品"]["query_status"], "NATURAL_ROWS")
        self.assertEqual(rows["日用品"]["natural_query_rows"], 1)
        self.assertEqual(rows["ベビー用品"]["query_status"], "ONLY_OPERATOR_ROWS")
        self.assertEqual(rows["ペット用品"]["natural_query_rows"], 0)
        self.assertEqual(rows["ボードゲーム"]["priority"], "QUERY_AND_LANDING_REVIEW")

    def test_google_snapshot_and_public_html_are_separate_evidence(self):
        d = {s["name"]: s for s in scorecard(fixture())["sites"]}["日用品"]["index"]
        self.assertEqual(d["indexed"], 1)
        self.assertEqual(d["unknown_to_google"], 1)
        self.assertEqual(d["http_and_canonical_ok"], 2)
        self.assertEqual(d["checked"], 2)
        report = fixture()
        report["sites"][0]["inspection"][1]["public"]["canonical"] = ["https://other.example/"]
        d = {s["name"]: s for s in scorecard(report)["sites"]}["日用品"]["index"]
        self.assertEqual(d["unknown_to_google"], 1)
        self.assertEqual(d["http_and_canonical_ok"], 1)

    def test_missing_daily_and_no_rows_are_unknown_not_zero_traffic(self):
        report = fixture()
        target = report["sites"][1]
        target["analytics"]["daily_28d"] = {"status": "NO_ROWS", "rows": []}
        board = scorecard(report)
        self.assertEqual(board["status"], "PARTIAL")
        row = next(s for s in board["sites"] if s["name"] == "ベビー用品")
        self.assertIsNone(row["daily"])
        self.assertEqual(row["priority"], "DATA_CHECK")
        self.assertIn("不明", scorecard_markdown(report))
        self.assertNotIn("0表示", scorecard_markdown(report))

    def test_bad_period_and_duplicate_day_prevent_fabricated_total(self):
        report = fixture()
        report["sites"][0]["analytics"]["daily_28d"]["rows"].append(
            report["sites"][0]["analytics"]["daily_28d"]["rows"][0].copy())
        self.assertIsNone(next(row for row in scorecard(report)["sites"] if row["name"] == "日用品")["daily"])
        report = fixture()
        report["sites"][0]["analytics"]["daily_28d"]["rows"][0]["key"] = "2026-11-04"
        self.assertIsNone(next(row for row in scorecard(report)["sites"] if row["name"] == "日用品")["daily"])
        report = fixture()
        report["sites"][0]["analytics"]["daily_28d"]["rows"][0]["impressions"] = -1
        self.assertIsNone(next(row for row in scorecard(report)["sites"] if row["name"] == "日用品")["daily"])

    def test_cross_site_property_mismatch_never_reuses_numbers(self):
        report = fixture()
        report["sites"][1]["property"] = report["sites"][0]["property"]
        rows = {s["name"]: s for s in scorecard(report)["sites"]}
        self.assertEqual(rows["ベビー用品"]["status"], "UNAVAILABLE_OR_MISMATCH")
        self.assertIsNone(rows["ベビー用品"]["daily"])
        report = fixture()
        report["sites"].append(report["sites"][1].copy())
        rows = {s["name"]: s for s in scorecard(report)["sites"]}
        self.assertIsNone(rows["ベビー用品"]["daily"])

    def test_markdown_is_bounded_and_does_not_expose_raw_queries(self):
        report = fixture()
        report["sites"][0]["analytics"]["queries_28d"]["rows"][0]["key"] = "<script>unsafe</script>"
        rendered = scorecard_markdown(report)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("unsafe", rendered)
        self.assertIn("日用品", rendered)
        self.assertIn("検索語と表示ページの意図を照合", rendered)
        self.assertIn("Google未認識1件", rendered)
        self.assertIn("111", rendered)


    def test_real_query_page_pair_examples_are_bounded_and_non_additive(self):
        board = scorecard(fixture())
        rows = {row["name"]: row for row in board["sites"]}
        d = rows["日用品"]["query_page_samples"]
        self.assertEqual(len(d), 1, "site: query must not become demand")
        self.assertEqual(d[0]["query"], "洗濯洗剤 安い 店 ランキング")
        self.assertEqual(d[0]["path"], "/categories/laundry/")
        self.assertEqual(d[0]["impressions"], 26)
        self.assertEqual(d[0]["position"], 7.65)
        self.assertEqual(rows["日用品"]["daily"]["impressions"], 111)
        self.assertEqual(rows["ボードゲーム"]["query_page_samples"][0]["position"], 72.67)
        summary = scorecard_markdown(fixture())
        self.assertIn("洗濯洗剤 安い 店 ランキング", summary)
        self.assertIn("/scenes/two-player/", summary)
        self.assertNotIn("site:github.io", summary)
        self.assertIn("/tools/laundry-cost-per-wash/", summary)

    def test_malicious_and_inapplicable_query_pairs_never_show_as_evidence(self):
        report = fixture()
        rows = report["sites"][0]["analytics"]["query_pages_28d"]["rows"]
        original = rows[0].copy()
        root = dict(SITES)
        rows.extend([
            {**original, "key": "連絡 test@example.com"},
            {**original, "key": "電話 090-1234-5678"},
            {**original, "key": "洗剤 site:example.jp"},
            {**original, "key": "価格 -site:example.jp"},
            {**original, "key": "<script>bad</script>"},
            {**original, "key": "他サイト", "page": root["食品"]},
            {**original, "key": "パス異常", "path": "//evil/"},
            {**original, "key": "重複", "impressions": -1},
            original.copy(),
        ])
        out = next(row for row in scorecard(report)["sites"] if row["name"] == "日用品")
        self.assertEqual(out["query_page_samples"],
                         [{"query": "洗濯洗剤 安い 店 ランキング",
                           "path": "/categories/laundry/", "impressions": 26,
                           "clicks": 0, "position": 7.65}])
        rendered = scorecard_markdown(report)
        self.assertNotIn("test@example.com", rendered)
        self.assertNotIn("090-1234-5678", rendered)
        self.assertNotIn("site:example.jp", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("&lt;script&gt;bad&lt;/script&gt;", rendered)

    def test_missing_query_pairs_are_unknown_not_empty_search_demand(self):
        report = fixture()
        report["sites"][0]["analytics"]["query_pages_28d"] = {"status": "UNAVAILABLE"}
        out = next(row for row in scorecard(report)["sites"] if row["name"] == "日用品")
        self.assertIsNone(out["query_page_samples"])
        self.assertIn("取得不明", scorecard_markdown(report))

    def test_partial_site_snapshot_stays_unknown(self):
        report = fixture()
        report["sites"][0]["inspection"].append(
            {"path": "/unavailable/", "status": "UNAVAILABLE"})
        row = scorecard(report)["sites"][0]
        self.assertEqual(row["index"]["uncertain"], 1)


if __name__ == "__main__":
    unittest.main()
