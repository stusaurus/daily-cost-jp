#!/usr/bin/env python3
"""Read-only Google URL Inspection for three established search-entry pages.

Uses the existing GSC Workload Identity Federation read-only credentials.
This API returns Google's indexed snapshot, not a live URL test.
No crawling requests, sitemap submissions, code changes, or indexing requests.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

SITE = "https://stusaurus.github.io/daily-cost-jp/"
URLS = (
    SITE + "categories/laundry/",
    SITE + "categories/tissue/",
    SITE + "categories/toilet-paper/",
)
API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
FIELDS = (
    "verdict", "coverageState", "robotsTxtState", "indexingState",
    "lastCrawlTime", "pageFetchState", "googleCanonical", "userCanonical",
    "crawledAs",
)


def extract(url, payload):
    """Only the documented index fields; absent fields remain unknown."""
    if url not in URLS:
        raise ValueError("URL outside approved inspection targets")
    if not isinstance(payload, dict):
        return {"url": url, "status": "MALFORMED_RESPONSE"}
    data = (payload.get("inspectionResult") or {}).get("indexStatusResult")
    if not isinstance(data, dict):
        return {"url": url, "status": "INDEX_STATUS_UNAVAILABLE"}
    record = {key: data.get(key) for key in FIELDS}
    google_canonical = data.get("googleCanonical")
    record.update({
        "url": url,
        "status": "RETURNED",
        "canonical_mismatch": (
            google_canonical != url if isinstance(google_canonical, str)
            and google_canonical else None
        ),
    })
    return record


def collect(session):
    """Three fixed, read-only inspection requests; errors cannot become zero."""
    rows = []
    for url in URLS:
        try:
            response = session.post(
                API, json={"inspectionUrl": url, "siteUrl": SITE},
                timeout=35,
            )
            if response.status_code != 200:
                rows.append({"url": url, "status": "API_HTTP_" + str(response.status_code)})
            else:
                rows.append(extract(url, response.json()))
        except (ValueError, TypeError, KeyError):
            rows.append({"url": url, "status": "MALFORMED_RESPONSE"})
        except Exception:
            rows.append({"url": url, "status": "REQUEST_UNAVAILABLE"})
    returned = sum(row["status"] == "RETURNED" for row in rows)
    return {
        "source": "Google Search Console URL Inspection API (indexed snapshot)",
        "property": SITE,
        "status": "COMPLETE" if returned == len(URLS) else
                  "PARTIAL" if returned else "UNAVAILABLE",
        "urls": rows,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "notes": [
            "This API inspects Google's indexed version; it does not test the live URL.",
            "Missing fields, 403/429, and absent results are UNKNOWN, not non-indexed.",
            "A PASS verdict is not evidence of stable rankings or impressions.",
            "No indexing requests, submissions, SEO rewrites or affiliate clicks.",
        ],
    }


def markdown(report):
    lines = [
        "## 主要3ページ：Google URL検査（読み取り専用）", "",
        "- 取得状態: " + report["status"],
        "- Googleの登録済みスナップショットを調査。公開ページのライブ検査ではありません。",
        "- 未取得・未返却は未確認。インデックス未登録とは判定しません。",
        "",
        "| ページ | URL検査 | 判定 | Google選択canonical | 最終クロール | robots | noindex |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report.get("urls", []):
        path = row["url"].removeprefix(SITE)
        def val(key):
            return str(row.get(key) or "未確認").replace("|", "%7C").replace("\n", " ")
        lines.append("| /" + path + " | " + val("status") + " | " + val("verdict") +
                     " / " + val("coverageState") + " | " + val("googleCanonical") +
                     " | " + val("lastCrawlTime") + " | " + val("robotsTxtState") +
                     " | " + val("indexingState") + " |")
    lines += [
        "", "※Google選択canonical・最終クロール・登録状態の不一致があっても、",
        "まずGoogle側の認識と公開ソースを照合。自動SEO変更・自動マージは行いません。", "",
    ]
    return "\n".join(lines)


def save(report):
    folder = Path("audit-results")
    folder.mkdir(exist_ok=True)
    (folder / "gsc-url-inspection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "gsc-url-inspection.md").write_text(markdown(report), encoding="utf-8")


def main():
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        report = {"status": "UNAVAILABLE", "urls": [],
                  "reason": "MISSING_WORKLOAD_IDENTITY"}
        save(report)
        return
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=[SCOPE])
        report = collect(AuthorizedSession(credentials))
    except Exception:
        report = {"status": "UNAVAILABLE", "urls": [],
                  "reason": "AUTHENTICATION_OR_API_UNAVAILABLE"}
    save(report)
    print("GSC URL Inspection read-only status=" + report["status"])


if __name__ == "__main__":
    main()
