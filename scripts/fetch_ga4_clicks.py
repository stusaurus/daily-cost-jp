#!/usr/bin/env python3
"""Read-only GA4 affiliate_click export via GitHub OIDC; no static credential keys.

Output intentionally remains RAW: operator_test exclusion and data completeness
must be verified before feeding a three-day optimization decision.
"""
import json
import os
from pathlib import Path


def normalize(rows):
    """Normalize GA4 date/event rows without treating absent dates as zero."""
    counts = {}
    for date, event, count in rows:
        if event != "affiliate_click":
            continue
        if len(date) != 8 or not date.isdigit():
            raise ValueError("Unexpected GA4 date")
        value = int(count)
        if value < 0:
            raise ValueError("Negative event count")
        day = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        counts[day] = counts.get(day, 0) + value
    return [{"date": day, "affiliate_click_raw": value} for day, value in sorted(counts.items())]


def fetch():
    property_id = os.environ["GA4_PROPERTY_ID"]
    if not property_id.isdigit():
        raise ValueError("GA4_PROPERTY_ID must be numeric")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("Workload Identity Federation credentials unavailable")

    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    client = BetaAnalyticsDataClient(credentials=credentials)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date="4daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="date"), Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        limit=10000,
    )
    response = client.run_report(request)
    if response.row_count > len(response.rows):
        raise RuntimeError("GA4 result truncated; cannot trust export")
    rows = (
        (row.dimension_values[0].value, row.dimension_values[1].value, row.metric_values[0].value)
        for row in response.rows
    )
    result = {
        "source": "GA4",
        "property_id": property_id,
        "data_status": "RAW_UNVERIFIED",
        "note": "No operator_test exclusion, session denominator, or verified completeness. Never infer zero sales or zero clicks from missing rows.",
        "days": normalize(rows),
    }
    Path("audit-results").mkdir(exist_ok=True)
    Path("audit-results/ga4-clicks-raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Exported unverified GA4 raw clicks; optimization decisions remain disabled.")


if __name__ == "__main__":
    fetch()
