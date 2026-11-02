"""Deterministic offline tests for page-filtered Search Console query deltas."""
import datetime as dt
import unittest
from scripts import gsc_category_query_delta as g


def row(term, views, clicks=0):
    return {"keys": [term], "impressions": views, "clicks": clicks,
            "ctr": clicks / views, "position": 9}


class Response:
    def __init__(self, code=200, rows=None):
        self.status_code = code
        self.rows = rows if rows is not None else []
    def json(self):
        return {"rows": self.rows}


class Session:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
    def post(self, endpoint, json=None, timeout=None):
        self.calls.append(json)
        page = json["dimensionFilterGroups"][0]["filters"][0]["expression"]
        prior = json["startDate"] == "2026-08-17"
        if self.fail and page.endswith("/tissue/") and prior:
            return Response(429)
        if page.endswith("/tissue/"):
            return Response(rows=([row("ティッシュ 安い", 20, 1),
                                   row("ティッシュ 箱", 7),
                                   row("somebody@example.com", 1)]
                                  if prior else
                                  [row("ティッシュ 安い", 4),
                                   row("ティシュー コスパ", 2)]))
        return Response()


class CategoryQueryTests(unittest.TestCase):
    def test_exact_pages_and_date_filters(self):
        session = Session()
        result = g.analyze(dt.date(2026, 10, 14), session,
                           {g.SITE: "siteRestrictedUser"})
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(len(session.calls), 4)
        self.assertEqual({p["path"] for p in result["pages"]}, set(g.PATHS))
        self.assertEqual(result["periods"]["prior_28"], ["2026-08-17", "2026-09-13"])
        self.assertEqual(result["periods"]["last_28"], ["2026-09-14", "2026-10-11"])
        for body in session.calls:
            self.assertEqual(body["dimensions"], ["query"])
            self.assertEqual(body["type"], "web")
            self.assertEqual(body["dataState"], "final")
            filt = body["dimensionFilterGroups"][0]["filters"][0]
            self.assertEqual(filt["operator"], "equals")
            self.assertEqual(filt["dimension"], "page")
            self.assertIn(filt["expression"], {g.SITE + p.lstrip("/") for p in g.PATHS})
        rows = {r["query"]: r for r in result["pages"][0]["comparison"]["rows"]}
        self.assertEqual(rows["ティッシュ 安い"]["impression_change"], -16)
        self.assertIsNone(rows["ティッシュ 箱"]["impression_change"])
        self.assertEqual(rows["ティシュー コスパ"]["status"], "QUERY_ROW_NOT_RETURNED")
        self.assertEqual(result["pages"][0]["coverage"]["prior_28"]["rows_suppressed_for_privacy"], 1)
        self.assertNotIn("somebody@example.com", str(result))

    def test_partial_api_failure_never_zero_fills(self):
        output = g.analyze(dt.date(2026, 10, 14), Session(fail=True),
                           {g.SITE: "siteRestrictedUser"})
        self.assertEqual(output["status"], "PARTIAL")
        self.assertEqual(output["pages"][0]["comparison"]["status"], "UNAVAILABLE")
        self.assertEqual(output["pages"][0]["comparison"]["rows"], [])

    def test_missing_permission_blocks_requests(self):
        session = Session()
        self.assertEqual(g.analyze(dt.date(2026, 10, 14), session, {})["status"], "UNAVAILABLE")
        self.assertEqual(session.calls, [])

    def test_no_rows_and_invalid_response(self):
        self.assertEqual(g.parse_rows({})["status"], "NO_ROWS")
        self.assertEqual(g.parse_rows({})["data"], {})
        with self.assertRaises(ValueError):
            g.parse_rows({"rows": [row("test", 2, 3)]})
        with self.assertRaises(ValueError):
            g.parse_rows({"rows": [{"keys": ["a", "b"], "impressions": 1,
                                    "clicks": 0, "ctr": 0, "position": 5}]})

    def test_escaped_markdown(self):
        result = g.analyze(dt.date(2026, 10, 14), Session(),
                           {g.SITE: "siteFullUser"})
        result["pages"][0]["comparison"]["rows"][0]["query"] = "<tissue> | test"
        text = g.markdown(result)
        self.assertIn("&lt;tissue&gt;", text)
        self.assertIn("&#124;", text)


if __name__ == "__main__":
    unittest.main()
