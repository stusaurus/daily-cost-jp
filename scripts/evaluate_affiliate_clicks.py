#!/usr/bin/env python3
"""Evaluate 3-day affiliate-click health from a verified daily GA4 export.

Input JSON: {"days":[{"date":"YYYY-MM-DD","affiliate_click":2,"sessions":100,
"operator_test_clicks":0,"data_complete":true}, ...]}
No credentials, no inferred revenue, no website modifications.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

def evaluate(payload, today):
    rows = payload.get("days", [])
    indexed = {}
    for row in rows:
        day = dt.date.fromisoformat(row["date"])
        if day in indexed:
            raise ValueError("Duplicate date in GA4 export")
        indexed[day] = row
    end = today - dt.timedelta(days=1)
    dates = [end - dt.timedelta(days=i) for i in (2, 1, 0)]
    selected = [indexed.get(day) for day in dates]
    if any(row is None or row.get("data_complete") is not True for row in selected):
        return {"status": "DATA_UNAVAILABLE", "period": [str(dates[0]), str(end)],
                "reason": "Three complete days of verified GA4 data are required", "action": "OBSERVE"}
    for row in selected:
        for key in ("affiliate_click", "sessions", "operator_test_clicks"):
            value = row.get(key)
            if type(value) is not int or value < 0:
                raise ValueError(f"Invalid {key}")
        if row["operator_test_clicks"] > row["affiliate_click"]:
            raise ValueError("Test clicks exceed total clicks")
    clicks = sum(row["affiliate_click"] - row["operator_test_clicks"] for row in selected)
    sessions = sum(row["sessions"] for row in selected)
    if clicks == 0:
        action = "CHECK_TRACKING_AND_TRAFFIC"
    elif clicks < 5:
        action = "INSPECT_TRAFFIC_AND_CTA"
    elif clicks < 10:
        action = "IDENTIFY_EFFECTIVE_LANDING_PAGES"
    else:
        action = "REVIEW_REPEATABLE_SUCCESSES"
    return {"status": "NEEDS_ATTENTION" if clicks < 5 else "OBSERVE",
            "period": [str(dates[0]), str(end)], "qualified_clicks": clicks,
            "sessions": sessions, "clicks_per_session": round(clicks / sessions, 4) if sessions else None,
            "action": action, "revenue": "NOT_CHECKED",
            "caveat": "Test-excluded GA4 events are provisional, not verified sales"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--today", default=dt.date.today().isoformat())
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.input).read_text(encoding="utf-8")), dt.date.fromisoformat(args.today))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
