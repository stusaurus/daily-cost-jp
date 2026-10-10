#!/usr/bin/env python3
"""Read-only GA4 three-day audit. No content changes, commits or link clicks.

Uses the site's existing production/operator classifier. Requires the event-scoped
GA4 custom dimension operator_test for a non-operator breakdown; if absent or
uncertain, the audit explicitly withholds an optimization decision.
"""
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from report_daily_clicks import aggregate

PROJECT_SITE = "stusaurus.github.io/daily-cost-jp"
METRIC_KEYS = (
    "production_operator", "production_non_operator", "production_unknown",
    "development", "other_site", "unscoped",
)


def window(today):
    """Use 3 completed JST days ending 2 days ago, allowing GA4 reporting latency."""
    end = today - dt.timedelta(days=2)
    start = today - dt.timedelta(days=4)
    return [start + dt.timedelta(days=i) for i in range(3)]


def check_response(response):
    if response.row_count > len(response.rows):
        raise ValueError("GA4 response truncated; do not interpret as complete")
    metadata = getattr(response, "metadata", None)
    if metadata and (getattr(metadata, "data_loss_from_other_row", False)
                     or getattr(metadata, "subject_to_thresholding", False)):
        raise ValueError("GA4 data quality warning; do not use aggregated/thresholded data")
    return response.rows


def accumulate_clicks(rows, expected_dates, operator_dimension):
    """Rows are (YYYYMMDD, pageLocation, operator_test, eventCount) tuples."""
    keys = {day.strftime("%Y%m%d"): day.isoformat() for day in expected_dates}
    per_day = {day.isoformat(): [] for day in expected_dates}
    for date, location, flag, count in rows:
        if date not in keys:
            raise ValueError("Unexpected date in GA4 click response")
        if type(count) is not int or count < 0:
            raise ValueError("Invalid GA4 event count")
        per_day[keys[date]].append({
            "eventName": "affiliate_click",
            "pageLocation": location,
            "operator_test": flag if operator_dimension else "",
            "eventCount": str(count),
        })
    return {day: aggregate(rows) for day, rows in per_day.items()}


def accumulate_sessions(rows, expected_dates):
    """Rows are (YYYYMMDD, sessions) tuples; absent dates stay unknown."""
    keys = {day.strftime("%Y%m%d"): day.isoformat() for day in expected_dates}
    counts = {day.isoformat(): None for day in expected_dates}
    for date, sessions in rows:
        if date not in keys or counts[keys[date]] is not None:
            raise ValueError("Unexpected or duplicate GA4 sessions date")
        if type(sessions) is not int or sessions < 0:
            raise ValueError("Invalid GA4 sessions count")
        counts[keys[date]] = sessions
    return counts


def evaluate(click_buckets, sessions, operator_dimension):
    """Only return a decision when all three days can be assessed."""
    dates = sorted(click_buckets)
    totals = {key: sum(click_buckets[d][key] for d in dates) for key in METRIC_KEYS}
    production_raw = sum(totals[k] for k in (
        "production_operator", "production_non_operator", "production_unknown"))
    summary = {
        "status": "DATA_LIMITED",
        "reason": None,
        "period": [dates[0], dates[-1]],
        "production_raw_clicks": production_raw,
        "known_operator_test_clicks": totals["production_operator"],
        "provisional_non_operator_clicks": totals["production_non_operator"] if operator_dimension else None,
        "unknown_operator_clicks": totals["production_unknown"],
        "sessions": sum(sessions.values()) if all(v is not None for v in sessions.values()) else None,
        "out_of_scope_events": sum(totals[k] for k in ("development", "other_site", "unscoped")),
        "revenue": "NOT_CHECKED",
        "decision_confidence": "PROVISIONAL_ONLY",
        "recommended_action": "OBSERVE",
    }
    if not operator_dimension:
        summary["reason"] = "operator_test custom event dimension is not registered in GA4"
    elif any(sessions[d] is None for d in dates):
        summary["reason"] = "Missing date in site-specific sessions report; not assumed zero"
    elif totals["production_unknown"]:
        summary["reason"] = "Unknown operator_test values; non-operator total incomplete"
    else:
        clicks = totals["production_non_operator"]
        visits = summary["sessions"]
        summary["status"] = "NEEDS_ATTENTION" if clicks < 5 else "OBSERVE"
        summary["clicks_per_session"] = round(clicks / visits, 4) if visits else None
        summary["recommended_action"] = (
            "CHECK_MEASUREMENT_AND_TRAFFIC" if clicks == 0 else
            "INSPECT_TRAFFIC_AND_CTA" if clicks < 5 else
            "REVIEW_LANDING_PAGE_INTENT" if clicks < 10 else
            "REVIEW_REPEATABLE_SUCCESSES"
        )
    return summary


def make_report(click_rows, session_rows, expected_dates, operator_dimension):
    buckets = accumulate_clicks(click_rows, expected_dates, operator_dimension)
    sessions = accumulate_sessions(session_rows, expected_dates)
    return {
        "source": "GA4 Data API",
        "site_scope": PROJECT_SITE,
        "window_policy": "JST days 4 through 2 before run; check GA4 property timezone",
        "operator_test_custom_dimension_registered": operator_dimension,
        "days": [
            {"date": day.isoformat(), "click_buckets": buckets[day.isoformat()],
             "site_sessions": sessions[day.isoformat()]}
            for day in expected_dates
        ],
        "summary": evaluate(buckets, sessions, operator_dimension),
        "safety": "Read-only provisional metrics; no website edits or automated performance decisions",
    }



def markdown_report(result):
    """Short Japanese report visible in GitHub Actions without ZIP download."""
    summary = result["summary"]
    fmt = lambda value: "不明" if value is None else str(value)
    lines = [
        "## 日用品サイト：GA4 3日間の読み取り専用分析",
        "",
        f"- 対象期間：{summary['period'][0]} ～ {summary['period'][1]}",
        f"- 判定：**{summary['status']}**",
        f"- 本番サイトの総クリック（テスト含む）：**{summary['production_raw_clicks']}件**",
        f"- 運営者テストと判明したクリック：{summary['known_operator_test_clicks']}件",
        f"- テストではない可能性があるクリック：{fmt(summary['provisional_non_operator_clicks'])}件（未検証）",
        f"- テスト区分不明のクリック：{summary['unknown_operator_clicks']}件",
        f"- 本番サイトのセッション：{fmt(summary['sessions'])}",
        f"- 調査の候補：{summary['recommended_action']}",
        "- 売上：**未取得**（クリックと購入は別）",
        "",
        "| 日付 | 本番クリック | テスト | 区分不明 | セッション |",
        "|---|---:|---:|---:|---:|",
    ]
    for day in result["days"]:
        b = day["click_buckets"]
        total = sum(b[k] for k in ("production_operator", "production_non_operator", "production_unknown"))
        lines.append(
            f"| {day['date']} | {total} | {b['production_operator']} | "
            f"{b['production_unknown']} | {fmt(day['site_sessions'])} |"
        )
    lines += [
        "",
        f"**注意：** {summary['reason'] or 'すべて暫定値。購入・収益の証拠ではありません。'}",
        "",
        "自動的な商品修正・リンク変更・サイト公開は行っていません。",
    ]
    return "\n".join(lines) + "\n"

def fetch():
    property_id = os.environ["GA4_PROPERTY_ID"]
    if not property_id.isdigit():
        raise ValueError("GA4_PROPERTY_ID must be a numeric GA4 property ID")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("GitHub Workload Identity credentials unavailable")

    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Filter, FilterExpression, FilterExpressionList,
        Metric, RunReportRequest,
    )

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    client = BetaAnalyticsDataClient(credentials=credentials)
    property_resource = f"properties/{property_id}"
    metadata = client.get_metadata(name=f"{property_resource}/metadata")
    operator_dimension = any(
        dim.api_name == "customEvent:operator_test" for dim in metadata.dimensions
    )
    days = window(dt.datetime.now(ZoneInfo("Asia/Tokyo")).date())
    date_range = [DateRange(start_date=days[0].isoformat(),
                            end_date=days[-1].isoformat())]
    clicks_request = RunReportRequest(
        property=property_resource,
        date_ranges=date_range,
        dimensions=[Dimension(name="date"), Dimension(name="pageLocation")] +
                   ([Dimension(name="customEvent:operator_test")] if operator_dimension else []),
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="affiliate_click"))),
        limit=10000,
    )
    click_response = client.run_report(clicks_request)
    click_rows = []
    for row in check_response(click_response):
        date = row.dimension_values[0].value
        location = row.dimension_values[1].value
        operator_flag = row.dimension_values[2].value if operator_dimension else ""
        click_rows.append((date, location, operator_flag, int(row.metric_values[0].value)))

    sessions_request = RunReportRequest(
        property=property_resource,
        date_ranges=date_range,
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="sessions")],
        dimension_filter=FilterExpression(and_group=FilterExpressionList(expressions=[
            FilterExpression(filter=Filter(
                field_name="hostName",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.EXACT,
                    value="stusaurus.github.io"))),
            FilterExpression(filter=Filter(
                field_name="pagePath",
                string_filter=Filter.StringFilter(
                    match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                    value="/daily-cost-jp/"))),
        ])),
        limit=1000,
    )
    sessions_response = client.run_report(sessions_request)
    session_rows = [
        (row.dimension_values[0].value, int(row.metric_values[0].value))
        for row in check_response(sessions_response)
    ]
    result = make_report(click_rows, session_rows, days, operator_dimension)
    result["property_id"] = property_id
    result["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    Path("audit-results").mkdir(exist_ok=True)
    path = Path("audit-results/ga4-three-day-report.json")
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    Path("audit-results/ga4-three-day-report.md").write_text(
        markdown_report(result), encoding="utf-8"
    )
    summary = result["summary"]
    print(
        f"GA4 3-day read-only audit: {summary['status']}; "
        f"raw clicks={summary['production_raw_clicks']}; "
        f"reason={summary['reason'] or 'provisional only'}"
    )


if __name__ == "__main__":
    fetch()
