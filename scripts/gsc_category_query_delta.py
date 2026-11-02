#!/usr/bin/env python3
"""Optional read-only GSC query comparison for two exact daily-cost pages.

Query rows can be anonymized or omitted. Missing rows are never zero traffic.
"""
import datetime as dt
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from scripts import gsc_six_sites as base

SITE = dict(base.SITES)["日用品"]
PATHS = ("/categories/tissue/", "/categories/toilet-paper/")
ROW_LIMIT = 1000
DISPLAY_LIMIT = 30
PRIVATE = re.compile(r"@|https?://|(?:\d[\s-]?){7,}")


def parse_rows(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("rows", []), list):
        raise ValueError("invalid GSC payload")
    raw = payload.get("rows", [])
    if len(raw) > ROW_LIMIT:
        raise ValueError("unexpected GSC row count")
    found = {}
    suppressed = 0
    for row in raw:
        keys = row.get("keys") if isinstance(row, dict) else None
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
            raise ValueError("invalid query dimension")
        metrics = base.safe_metrics(row)
        term = " ".join(keys[0].split())
        if not term:
            raise ValueError("empty query dimension")
        if len(term) > 120 or PRIVATE.search(term) or any(ord(ch) < 32 for ch in term):
            suppressed += 1
            continue
        if term in found:
            raise ValueError("duplicate normalized query")
        found[term] = metrics
    return {
        "status": ("NO_ROWS" if not raw else
                   "TOP_ROW_LIMIT_POSSIBLE" if len(raw) == ROW_LIMIT else
                   "ROWS_SUPPRESSED" if not found else "OBSERVED_ROWS"),
        "rows_returned": len(raw),
        "rows_suppressed_for_privacy": suppressed,
        "data": found,
    }


def compare(prior, recent):
    if prior["status"] == "UNAVAILABLE" or recent["status"] == "UNAVAILABLE":
        return {"status": "UNAVAILABLE", "rows": [], "rows_considered": None}
    rows = []
    for term in set(prior["data"]) | set(recent["data"]):
        before, after = prior["data"].get(term), recent["data"].get(term)
        both = before is not None and after is not None
        rows.append({
            "query": term, "prior_28": before, "last_28": after,
            "status": "OBSERVED_IN_BOTH" if both else "QUERY_ROW_NOT_RETURNED",
            "impression_change": after["impressions"] - before["impressions"] if both else None,
            "click_change": after["clicks"] - before["clicks"] if both else None,
        })
    rows.sort(key=lambda r: (
        -max((r["prior_28"] or {}).get("impressions", 0),
             (r["last_28"] or {}).get("impressions", 0)), r["query"]))
    return {"status": "OBSERVED_NONEXHAUSTIVE" if rows else "NO_COMPARABLE_QUERY_ROWS",
            "rows": rows[:DISPLAY_LIMIT], "rows_considered": len(rows)}


def query(session, path, period):
    if path not in PATHS:
        raise ValueError("non-target page")
    payload = {
        "startDate": period[0], "endDate": period[1],
        "type": "web", "dataState": "final",
        "dimensions": ["query"], "rowLimit": ROW_LIMIT,
        "dimensionFilterGroups": [{"groupType": "and", "filters": [
            {"dimension": "page", "operator": "equals",
             "expression": SITE + path.lstrip("/")}]}],
    }
    url = base.ROOT + "/sites/" + quote(SITE, safe="") + "/searchAnalytics/query"
    response = session.post(url, json=payload, timeout=45)
    if response.status_code != 200:
        raise ValueError("GSC query unavailable")
    return parse_rows(response.json())


def analyze(today, session=None, permissions=None):
    date_windows = base.date_windows(today)
    output = {
        "source": "GSC Search Analytics API (read-only)",
        "site": SITE, "as_of_pacific": str(today),
        "periods": {key: date_windows[key] for key in ("prior_28", "last_28")},
        "status": "UNAVAILABLE", "pages": [],
        "limitations": [
            "Two exact page filters, two non-overlapping finalized 28-day periods.",
            "Returned queries are non-exhaustive; anonymized queries can be omitted.",
            "Absent terms are unknown rather than zero and not included in deltas.",
            "Query rows must not be summed as page or site totals.",
            "No site, authentication, index request, or affiliate changes.",
        ],
    }
    if session is None or permissions is None:
        output["reason"] = "AUTH_OR_PROPERTY_UNAVAILABLE"
        return output
    if permissions.get(SITE) not in base.AUTHORIZED_LEVELS:
        output["reason"] = "EXACT_PROPERTY_ACCESS_MISSING"
        return output
    had_error = False
    for path in PATHS:
        entries = {}
        for label in ("prior_28", "last_28"):
            try:
                entries[label] = query(session, path, date_windows[label])
            except Exception:
                had_error = True
                entries[label] = {"status": "UNAVAILABLE", "rows_returned": None,
                                  "rows_suppressed_for_privacy": None, "data": {}}
        change = compare(entries["prior_28"], entries["last_28"])
        # The original API payload and suppressed search terms are not persisted.
        coverage = {key: {k: v for k, v in value.items() if k != "data"}
                    for key, value in entries.items()}
        output["pages"].append({"path": path, "coverage": coverage, "comparison": change})
    output["status"] = "PARTIAL" if had_error else "OBSERVED"
    return output


def markdown(report):
    lines = ["# 日用品・ティッシュとトイレットペーパーの検索語別前後28日比較", "",
             "- 状態：" + report["status"],
             "- 前28日：" + "〜".join(report["periods"]["prior_28"]),
             "- 直近28日：" + "〜".join(report["periods"]["last_28"]), "",
             "注：Googleから返らない検索語は0回ではなく未確認です。公開用に一部長文・個人情報らしい文字列を除外します。", ""]
    for page in report["pages"]:
        lines.extend(["## " + page["path"], ""])
        for label in ("prior_28", "last_28"):
            info = page["coverage"][label]
            lines.append("- " + label + ": " + info["status"] +
                         "（取得 " + str(info["rows_returned"]) + "行、公開除外 " +
                         str(info["rows_suppressed_for_privacy"]) + "行）")
        lines.extend(["", "| 検索語 | 前28日表示 | 直近28日表示 | 差 | 判定 |",
                      "|---|---:|---:|---:|---|"])
        for row in page["comparison"]["rows"]:
            term = html.escape(row["query"], quote=False).replace("|", "&#124;")
            before, after = row["prior_28"], row["last_28"]
            value = lambda x: str(x["impressions"]) if x is not None else "未確認"
            delta = str(row["impression_change"]) if row["impression_change"] is not None else "算出不可"
            lines.append("| " + term + " | " + value(before) + " | " +
                         value(after) + " | " + delta + " | " + row["status"] + " |")
        lines.append("")
    lines.append("※検索語の増減だけでGoogleの評価変更、検索需要変化、順位低下の因果は証明できません。")
    return "\n".join(lines) + "\n"


def main():
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    session = permissions = None
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=[base.SCOPE])
            session = AuthorizedSession(credentials)
            response = session.get(base.ROOT + "/sites", timeout=30)
            if response.status_code == 200:
                rows = response.json().get("siteEntry", [])
                if isinstance(rows, list):
                    permissions = {r["siteUrl"]: r["permissionLevel"] for r in rows
                                   if isinstance(r, dict) and
                                   isinstance(r.get("siteUrl"), str) and
                                   isinstance(r.get("permissionLevel"), str)}
        except Exception:
            session = permissions = None
    report = analyze(today, session=session, permissions=permissions)
    output = Path("audit-results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "gsc-category-query-delta.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "gsc-category-query-delta.md").write_text(markdown(report), encoding="utf-8")
    print("GSC category query delta: " + report["status"])
    if report["status"] != "OBSERVED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
