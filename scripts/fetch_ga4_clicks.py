#!/usr/bin/env python3
"""Fetch read-only GA4 affiliate click counts using GitHub OIDC via Workload Identity Federation.

Requires google-auth and google-analytics-data; no static service account key.
Environment: GA4_PROPERTY_ID, GCP_WIF_PROVIDER, GCP_SERVICE_ACCOUNT.
This is a separate, optional step; fail closed if any credential is missing.
"""
import datetime as dt
import json
import os
from pathlib import Path

def fetch():
    property_id = os.environ["GA4_PROPERTY_ID"]
    provider = os.environ["GCP_WIF_PROVIDER"]
    service_account = os.environ["GCP_SERVICE_ACCOUNT"]
    if not property_id.isdigit():
        raise ValueError("GA4_PROPERTY_ID must be numeric")
    import google.auth
    from google.auth import identity_pool
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
    # google-github-actions/auth creates GOOGLE_APPLICATION_CREDENTIALS for WIF.
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("Workload Identity Federation credentials unavailable")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    client = BetaAnalyticsDataClient(credentials=credentials)
    # GA4 reports are queried by property timezone; do not silently infer JST.
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date="4daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="date"), Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        limit=10000,
    )
    response = client.run_report(req)
    clicks = {}
    for row in response.rows:
        date, event = [v.value for v in row.dimension_values]
        if event != "affiliate_click":
            continue
        key = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        clicks[key] = clicks.get(key, 0) + int(row.metric_values[0].value)
    output = {"source": "GA4", "property_id": property_id, "note": "Raw affiliate_click events; operator_test not filtered; data completeness not guaranteed", "days": [{"date": d, "affiliate_click_raw": n} for d,n in sorted(clicks.items())]}
    Path("audit-results").mkdir(exist_ok=True)
    Path("audit-results/ga4-clicks-raw.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GA4 read-only raw click export created; no revenue inference.")

if __name__ == "__main__":
    fetch()
