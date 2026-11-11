"""Offline regression tests for strict, fixed-period laundry release evidence."""
import datetime as dt
import unittest

from scripts import gsc_laundry_release_effect as g

class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = {} if payload is None else payload
    def json(self):
        return self.payload

def row(term, views, clicks=0, position=9):
    return {"keys": [term], "impressions": views, "clicks": clicks,
            "ctr": clicks / views if views else 0, "position": position if views else 0}

class Session:
    def __init__(self, *, fail_on=0, missing_page=False):
        self.calls=[]
        self.fail_on=fail_on
        self.missing_page=missing_page
    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        if self.fail_on and len(self.calls) == self.fail_on:
            return Response(status=429)
        before = json["startDate"] == "2026-11-03"
        if json.get("dimensions")==["query"]:
            return Response(payload={"rows": (
                [row("洗濯洗剤 安い 店 ランキング", 8),
                 row("site:stusaurus.github.io", 3),
                 row("someone@example.com", 1),
                 row("先週だけ", 2)]
                if before else
                [row("洗濯洗剤 安い 店 ランキング", 11, 1),
                 row("今週だけ", 2), row("ＳＩＴＥ：test", 1)]
            )})
        if self.missing_page and not before:
            return Response(payload={"rows": []})
        views,clicks,position=(15,0,11) if before else (20,1,9)
        return Response(payload={"rows":[{
            "impressions":views,"clicks":clicks,
            "ctr":clicks/views,"position":position,
        }]})

class StrictReleaseComparisonTests(unittest.TestCase):
    def auth(self):
        return {g.SITE:"siteRestrictedUser"}

    def test_fixed_periods_exclude_the_partly_published_monday(self):
        self.assertEqual(g.BEFORE,("2026-11-03","2026-11-08"))
        self.assertEqual(g.AFTER,("2026-11-10","2026-11-15"))
        self.assertTrue(g.MERGED_UTC.startswith("2026-11-09"))
        for period in (g.BEFORE,g.AFTER):
            self.assertEqual((dt.date.fromisoformat(period[1])-dt.date.fromisoformat(period[0])).days,5)
            self.assertEqual(dt.date.fromisoformat(period[0]).weekday(),1)
            self.assertEqual(dt.date.fromisoformat(period[1]).weekday(),6)

    def test_no_early_queries_even_if_a_session_exists(self):
        s=Session()
        report=g.analyze(dt.date(2026,11,17),s,self.auth())
        self.assertEqual(report["status"],"WAITING_FOR_FINAL_DATA")
        self.assertEqual(s.calls,[])
        self.assertIsNone(report["page_change"])
        self.assertEqual(report["finalized_through_pacific"],"2026-11-14")

    def test_first_finality_safe_date_and_exact_page_filters(self):
        s=Session()
        report=g.analyze(dt.date(2026,11,18),s,self.auth())
        self.assertEqual(report["finalized_through_pacific"],"2026-11-15")
        self.assertEqual(report["status"],"OBSERVED_LOW_SAMPLE")
        self.assertEqual(len(s.calls),4)
        self.assertEqual([c[1]["startDate"] for c in s.calls],
                         ["2026-11-03","2026-11-03","2026-11-10","2026-11-10"])
        for url, body, timeout in s.calls:
            self.assertTrue(url.endswith("/searchAnalytics/query"))
            self.assertIn("%3A%2F%2F",url)
            self.assertEqual(body["type"],"web")
            self.assertEqual(body["dataState"],"final")
            self.assertEqual(timeout,45)
            self.assertEqual(body["dimensionFilterGroups"],[{
                "groupType":"and", "filters":[{
                    "dimension":"page","operator":"equals","expression":g.PAGE
                }]
            }])
        self.assertEqual([bool(c[1].get("dimensions")) for c in s.calls],
                         [False,True,False,True])
        self.assertEqual(report["page"]["before"]["impressions"],15)
        self.assertEqual(report["page"]["after"]["clicks"],1)
        self.assertEqual(report["page_change"]["impressions"],5)
        self.assertEqual(report["page_change"]["clicks"],1)
        self.assertEqual(report["page_change"]["ctr_percentage_points"],5.0)
        self.assertEqual(report["page_change"]["position_difference"],-2.0)

    def test_operator_queries_are_excluded_and_unreturned_rows_are_not_zero(self):
        r=g.analyze(dt.date(2026,11,18),Session(),self.auth())
        q={x["query"]:x for x in r["query_comparison"]["rows"]}
        self.assertEqual(q["洗濯洗剤 安い 店 ランキング"]["impression_change"],3)
        self.assertIsNone(q["先週だけ"]["impression_change"])
        self.assertEqual(q["先週だけ"]["status"],"QUERY_ROW_NOT_RETURNED")
        self.assertIsNone(q["今週だけ"]["impression_change"])
        self.assertNotIn("site:stusaurus.github.io",str(r))
        self.assertNotIn("ＳＩＴＥ",str(r))
        self.assertNotIn("someone@example.com",str(r))

    def test_absent_page_aggregate_remains_unknown_not_zero(self):
        r=g.analyze(dt.date(2026,11,18),Session(missing_page=True),self.auth())
        self.assertEqual(r["status"],"INSUFFICIENT_PAGE_DATA")
        self.assertIsNone(r["page"]["after"])
        self.assertIsNone(r["page_change"])
        self.assertIn("未確認",g.markdown(r))

    def test_429_marks_partial_without_zero_filling_or_retrying(self):
        s=Session(fail_on=3)
        r=g.analyze(dt.date(2026,11,18),s,self.auth())
        self.assertEqual(r["status"],"PARTIAL")
        self.assertEqual(r["reason"],"GSC_API_OR_RESPONSE_UNAVAILABLE")
        self.assertEqual(len(s.calls),3)
        self.assertIsNone(r["page"]["after"])
        self.assertIsNone(r["page_change"])

    def test_missing_exact_property_never_queries(self):
        s=Session()
        for permissions in (None,{},{"https://stusaurus.github.io/baby-cost-jp/":"siteOwner"},
                            {g.SITE:"siteUnverifiedUser"}):
            with self.subTest(permissions=permissions):
                r=g.analyze(dt.date(2026,11,18),s,permissions)
                self.assertEqual(r["status"],"UNAVAILABLE")
                self.assertIsNone(r["page_change"])
        self.assertEqual(s.calls,[])

    def test_markdown_escapes_untrusted_query_terms_and_shows_release_day_warning(self):
        report=g.analyze(dt.date(2026,11,18),Session(),self.auth())
        report["query_comparison"]["rows"][0]["query"]="<tag> | any"
        rendered=g.markdown(report)
        self.assertIn("&lt;tag&gt; &#124; any",rendered)
        self.assertNotIn("<tag>",rendered)
        self.assertIn("11月9日の部分日は比較対象外",rendered)
        self.assertIn("少数データ",rendered)

    def test_waiting_report_does_not_claim_organic_growth(self):
        r=g.analyze(dt.date(2026,11,11))
        markdown=g.markdown(r)
        self.assertEqual(r["status"],"WAITING_FOR_FINAL_DATA")
        self.assertIsNone(r["page_change"])
        self.assertIn("API照会・前後評価を行いません",markdown)

if __name__=="__main__":
    unittest.main()
