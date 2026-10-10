#!/usr/bin/env python3
"""Read-only 7/28 day GA4 page diagnostics; no GSC or purchase claims."""
import datetime as dt
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ga4_three_day_report import check_response
from report_daily_clicks import aggregate

HOST = "stusaurus.github.io"
PREFIX = "/daily-cost-jp/"
FOCUS_PAGES = (
    "/categories/laundry/", "/categories/tissue/", "/categories/toilet-paper/",
    "/products/", "/today/", "/",
)
BUCKETS = ("production_operator", "production_non_operator", "production_unknown")


def dates_for(today):
    """56 property-calendar days, ending two completed days before the run."""
    end = today - dt.timedelta(days=2)
    return [end - dt.timedelta(days=i) for i in range(55, -1, -1)]


def path_from_location(value):
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or url.hostname != HOST or url.username
                or url.password or url.port is not None or
                not url.path.startswith(PREFIX)):
            return None
        return "/" + url.path[len(PREFIX):]
    except (TypeError, ValueError):
        return None


def path_from_pagepath(value):
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return None
    return "/" + value[len(PREFIX):].split("?", 1)[0].split("#", 1)[0]


def process_rows(click_rows, view_rows, dates, operator_registered):
    valid = {d.strftime("%Y%m%d"): d.isoformat() for d in dates}
    views = defaultdict(lambda: defaultdict(int))
    clicks = defaultdict(lambda: defaultdict(lambda: {k: 0 for k in BUCKETS}))
    covered = set()
    duplicates = set()
    excluded = defaultdict(int)
    for day, path, value in view_rows:
        if day not in valid or type(value) is not int or value < 0:
            raise ValueError("Invalid/out-of-range GA4 pageview row")
        page = path_from_pagepath(path)
        if page is None:
            raise ValueError("Pageview report returned out-of-scope path")
        key = (valid[day], page)
        if key in duplicates:
            raise ValueError("Duplicate date/pageview row")
        duplicates.add(key)
        covered.add(valid[day])
        views[page][valid[day]] = value
    for day, location, operator, value in click_rows:
        if day not in valid or type(value) is not int or value < 0:
            raise ValueError("Invalid/out-of-range GA4 click row")
        buckets = aggregate([{
            "eventName": "affiliate_click",
            "pageLocation": location,
            "operator_test": operator if operator_registered else "",
            "eventCount": str(value),
        }])
        page = path_from_location(location)
        if page is None:
            for key, count in buckets.items():
                excluded[key] += count
            continue
        for key in BUCKETS:
            clicks[page][valid[day]][key] += buckets[key]
    return views, clicks, covered, dict(excluded)


def period_totals(page, views, clicks, dates):
    periods = {
        "last_7": dates[-7:], "prior_7": dates[-14:-7],
        "last_28": dates[-28:], "prior_28": dates[-56:-28],
    }
    result = {}
    for label, days in periods.items():
        keys = [d.isoformat() for d in days]
        result[label] = {
            "pageviews": sum(views[page].get(d, 0) for d in keys),
            "clicks": {key: sum(clicks[page].get(d, {}).get(key, 0) for d in keys)
                       for key in BUCKETS},
        }
    return result


def diagnose(stats, operator_registered, coverage_complete):
    recent = stats["last_28"]
    current, previous = stats["last_7"], stats["prior_7"]
    views = recent["pageviews"]
    counts = recent["clicks"]
    total = sum(counts.values())
    if not operator_registered:
        return 1, "CHECK_OPERATOR_DIMENSION", "GA4で運営者テストの区別を確認"
    if counts["production_unknown"]:
        return 1, "CHECK_UNKNOWN_TEST_EVENTS", "テスト区分不明のクリックを確認"
    if not coverage_complete:
        return 2, "CHECK_DATA_COVERAGE", "比較期間に表示データのない日があり判断保留"
    if total and not views:
        return 1, "CHECK_MEASUREMENT_SCOPE", "クリックとページ表示の計測の整合性を確認"
    if (current["pageviews"] >= 20 and previous["pageviews"] >= 30 and
            current["pageviews"] * 10 <= previous["pageviews"] * 6):
        return 2, "INVESTIGATE_PAGEVIEW_DROP", "直近7日で表示が減少。流入元を別途確認"
    if views >= 50 and counts["production_non_operator"] == 0:
        return 2, "AUDIT_CTA_AND_LINKS", "表示はあるがテスト外クリック未観測。購入導線を点検する仮説"
    if views >= 100 and counts["production_non_operator"] * 100 < views:
        return 3, "REVIEW_PRODUCT_FIT", "クリック密度が低い。商品適合性・CTAを調査する仮説"
    if views < 50:
        return 4, "OBSERVE_LOW_TRAFFIC", "表示が少なく現時点で導線の良否は判定できない"
    return 5, "OBSERVE", "問題を特定できるだけの根拠がない"


def make_report(click_rows, view_rows, today, operator_registered):
    dates = dates_for(today)
    views, clicks, covered, excluded = process_rows(
        click_rows, view_rows, dates, operator_registered)
    last28 = {d.isoformat() for d in dates[-28:]}
    coverage_complete = last28.issubset(covered)
    previous28 = {d.isoformat() for d in dates[:-28]}
    previous28_complete = previous28.issubset(covered)
    candidates = []
    for page in set(views) | set(clicks):
        stats = period_totals(page, views, clicks, dates)
        priority, action, reason = diagnose(stats, operator_registered, coverage_complete)
        denom = stats["last_28"]["pageviews"]
        recent_clicks = stats["last_28"]["clicks"]
        candidates.append({
            "page": page, "periods": stats, "priority": priority,
            "action_code": action, "hypothesis": reason,
            "provisional_clicks_per_100_pageviews": (
                round(100 * recent_clicks["production_non_operator"] / denom, 2)
                if denom and operator_registered and not recent_clicks["production_unknown"]
                and coverage_complete else None),
        })
    candidates.sort(key=lambda x: (
        x["priority"], -x["periods"]["last_28"]["pageviews"],
        x["page"] not in FOCUS_PAGES, x["page"]))
    return {
        "source": "GA4 Data API",
        "period_last_7": [dates[-7].isoformat(), dates[-1].isoformat()],
        "period_last_28": [dates[-28].isoformat(), dates[-1].isoformat()],
        "status": ("NO_PAGEVIEWS" if not covered else
                   "OPERATOR_DIMENSION_UNAVAILABLE" if not operator_registered else
                   "COVERAGE_UNCERTAIN" if not coverage_complete else "PROVISIONAL"),
        "operator_dimension_registered": operator_registered,
        "pageview_dates_observed_in_last_28": len(last28 & covered),
        "pageview_dates_observed_in_previous_28": len(previous28 & covered),
        "previous_28_coverage_complete": previous28_complete,
        "excluded_clicks": excluded,
        "pages": candidates,
        "top_investigations": candidates[:6],
        "caveat": "GA4 pageviews are not users or sessions. Clicks/pageviews is not sales conversion. GSC and affiliate commissions not connected. No automatic site modifications.",
    }


def markdown_report(report):
    lines = [
        "## 日用品サイト：ページ別7日・28日間の改善候補",
        "",
        "- **状態：** " + report["status"],
        "- 対象7日間：" + " ～ ".join(report["period_last_7"]),
        "- 対象28日間：" + " ～ ".join(report["period_last_28"]),
        "- 28日間で表示記録のある日：" + str(report["pageview_dates_observed_in_last_28"]) + "/28",
        "- 前28日間で表示記録のある日：" + str(report["pageview_dates_observed_in_previous_28"]) + "/28",
        "- **クリックは購入・売上ではありません。** GA4のみの調査仮説です。",
        "",
        "| ページ | 直近7日表示 | 前7日表示 | 直近28日表示 | 前28日表示 | テスト外クリック（暫定・28日） | 調査候補 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for candidate in report["top_investigations"]:
        periods = candidate["periods"]
        counts = periods["last_28"]["clicks"]
        valid = (report["operator_dimension_registered"] and
                 report["status"] == "PROVISIONAL" and
                 counts["production_unknown"] == 0)
        click_text = str(counts["production_non_operator"]) if valid else "不明"
        page = candidate["page"].replace("|", "%7C").replace("\n", "")
        last7 = str(periods["last_7"]["pageviews"])
        prev7 = str(periods["prior_7"]["pageviews"])
        last28 = str(periods["last_28"]["pageviews"])
        prev28 = (str(periods["prior_28"]["pageviews"])
                  if report["previous_28_coverage_complete"] else "不明")
        reason = candidate["hypothesis"].replace("|", "、")
        lines.append(
            "| " + page + " | " + last7 + " | " + prev7 + " | " +
            last28 + " | " + prev28 + " | " + click_text + " | " + reason + " |"
        )
    if not report["top_investigations"]:
        lines.append("| データなし | — | — | — | — | — | 計測状況を確認 |")
    lines += [
        "",
        "**注意：** 表示数から流入経路や原因は断定できません。商品・価格・楽天リンクを自動変更しません。",
        "Search Consoleと楽天の成果報酬データは未接続です。",
        "",
    ]
    return "\n".join(lines)


def fetch():
    prop_id = os.environ["GA4_PROPERTY_ID"]
    if not prop_id.isdigit():
        raise ValueError("GA4 property ID must be numeric")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("Workload identity credentials missing")
    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Filter, FilterExpression, FilterExpressionList,
        Metric, RunReportRequest,
    )
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    client = BetaAnalyticsDataClient(credentials=creds)
    prop = "properties/" + prop_id
    metadata = client.get_metadata(name=prop + "/metadata")
    registered = any(dim.api_name == "customEvent:operator_test"
                     for dim in metadata.dimensions)
    if not any(metric.api_name == "screenPageViews" for metric in metadata.metrics):
        raise RuntimeError("GA4 screenPageViews metric not available")
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    days = dates_for(today)
    range_ = [DateRange(start_date=days[0].isoformat(),
                        end_date=days[-1].isoformat())]
    raw_clicks = client.run_report(RunReportRequest(
        property=prop, date_ranges=range_,
        dimensions=[Dimension(name="date"), Dimension(name="pageLocation")] +
                   ([Dimension(name="customEvent:operator_test")] if registered else []),
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT, value="affiliate_click"))),
        limit=100000,
    ))
    click_rows = [
        (row.dimension_values[0].value, row.dimension_values[1].value,
         row.dimension_values[2].value if registered else "",
         int(row.metric_values[0].value))
        for row in check_response(raw_clicks)
    ]
    raw_views = client.run_report(RunReportRequest(
        property=prop, date_ranges=range_,
        dimensions=[Dimension(name="date"), Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews")],
        dimension_filter=FilterExpression(and_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="hostName",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT, value=HOST))),
            FilterExpression(filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.BEGINS_WITH, value=PREFIX))),
        ])),
        limit=100000,
    ))
    view_rows = [
        (row.dimension_values[0].value, row.dimension_values[1].value,
         int(row.metric_values[0].value))
        for row in check_response(raw_views)
    ]
    report = make_report(click_rows, view_rows, today, registered)
    report["property_id"] = prop_id
    report["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    output = Path("audit-results")
    output.mkdir(exist_ok=True)
    (output / "ga4-page-diagnostics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "ga4-page-diagnostics.md").write_text(
        markdown_report(report), encoding="utf-8")
    print("GA4 page diagnostics: " + report["status"] +
          "; pages=" + str(len(report["pages"])))


if __name__ == "__main__":
    fetch()
