#!/usr/bin/env python3
"""Read-only, publication-aligned GSC measurement for the laundry landing page.

PR #162 was merged 2026-11-09 11:45 UTC (Nov 9 in Pacific time).
Exclude the mixed release date; compare two complete Tue-Sun six-day periods.
Do not infer a ranking effect from short or missing samples.
"""
import datetime as dt
import html
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from scripts import gsc_six_sites as base
from scripts import gsc_category_query_delta as terms

SITE = dict(base.SITES)["日用品"]
PAGE = SITE + "categories/laundry/"
MERGED_UTC = "2026-11-09T11:45:19Z"
BEFORE = ("2026-11-03", "2026-11-08")
AFTER = ("2026-11-10", "2026-11-15")
OUTPUT = Path("audit-results")
ROW_LIMIT = 1000
LOW_SAMPLE_THRESHOLD = 30

def is_operator_query(value):
    normalized = unicodedata.normalize("NFKC", value).lower()
    return bool(re.search(r"(?:^|\s)-?site\s*:", normalized))

def fetch(session, window, query_rows=False):
    """One exact page-filtered GSC request. No other property or API actions."""
    body = {
        "startDate": window[0], "endDate": window[1],
        "type": "web", "dataState": "final",
        "dimensionFilterGroups": [{
            "groupType": "and",
            "filters": [{
                "dimension": "page", "operator": "equals", "expression": PAGE,
            }],
        }],
    }
    if query_rows:
        body.update({"dimensions": ["query"], "rowLimit": ROW_LIMIT})
    endpoint = base.ROOT + "/sites/" + quote(SITE, safe="") + "/searchAnalytics/query"
    response = session.post(endpoint, json=body, timeout=45)
    if response.status_code != 200:
        raise RuntimeError("EXACT_GSC_QUERY_UNAVAILABLE")
    return response.json()

def analyze(today, session=None, permissions=None):
    """Do not call GSC until *both* complete weeks are likely finalized."""
    finalized_through = base.date_windows(today)["last_7"][1]
    report = {
        "schemaVersion": 1,
        "source": "Google Search Console Search Analytics API (read-only)",
        "as_of_pacific": str(today),
        "finalized_through_pacific": finalized_through,
        "target_page": PAGE,
        "release_merge_utc": MERGED_UTC,
        "release_date_excluded_pacific": "2026-11-09",
        "periods": {"before": list(BEFORE), "after": list(AFTER)},
        "status": "WAITING_FOR_FINAL_DATA",
        "page": {"before": None, "after": None},
        "query_coverage": {"before": None, "after": None},
        "query_comparison": None,
        "page_change": None,
        "notes": [
            "Both periods cover Tuesday through Sunday, with the mixed release Monday excluded.",
            "The first finality-safe collection date is November 18 Pacific time (three-day reporting lag).",
            "Search Console query rows may be anonymized or omitted and cannot be summed into page totals.",
            "Unreturned query rows and missing page aggregates are unknown, never zero.",
            "Site-operator searches are excluded from the natural-search query comparison.",
            "A before/after difference does not prove causation, conversions, or visitor growth.",
            "No index submissions, SEO edits, affiliate clicks or product writes.",
        ],
    }
    if finalized_through < AFTER[1]:
        return report
    if session is None or not isinstance(permissions, dict) or permissions.get(SITE) not in base.AUTHORIZED_LEVELS:
        report["status"] = "UNAVAILABLE"
        report["reason"] = "EXACT_PROPERTY_ACCESS_MISSING"
        return report

    all_queries = {}
    for period, window in (("before", BEFORE), ("after", AFTER)):
        try:
            agg = base.aggregate(fetch(session, window))
            query_data = terms.parse_rows(fetch(session, window, query_rows=True))
        except Exception:
            report["status"] = "PARTIAL"
            report["reason"] = "GSC_API_OR_RESPONSE_UNAVAILABLE"
            return report
        report["page"][period] = agg["metrics"]
        report["query_coverage"][period] = {
            k: v for k, v in query_data.items() if k != "data"
        }
        all_queries[period] = {
            k: v for k, v in query_data["data"].items() if not is_operator_query(k)
        }

    before, after = report["page"]["before"], report["page"]["after"]
    result = terms.compare(
        {"status": "OBSERVED_ROWS", "data": all_queries["before"]},
        {"status": "OBSERVED_ROWS", "data": all_queries["after"]},
    )
    report["query_comparison"] = {
        "status": result["status"],
        "rows_considered": result["rows_considered"],
        "rows": result["rows"],
    }
    if before is None or after is None:
        report["status"] = "INSUFFICIENT_PAGE_DATA"
        return report

    report["page_change"] = {
        "impressions": after["impressions"] - before["impressions"],
        "clicks": after["clicks"] - before["clicks"],
        "ctr_percentage_points": round(100 * (after["ctr"] - before["ctr"]), 2),
        "position_difference": (round(after["position"] - before["position"], 2)
                                if before["position"] is not None and after["position"] is not None else None),
    }
    if min(before["impressions"], after["impressions"]) < LOW_SAMPLE_THRESHOLD:
        report["status"] = "OBSERVED_LOW_SAMPLE"
    else:
        report["status"] = "OBSERVED_DESCRIPTIVE_ONLY"
    return report

def markdown(report):
    def safe(s):
        return html.escape(str(s), quote=False).replace("|", "&#124;")
    def metrics(value):
        if value is None:
            return ["未確認"] * 4
        return [
            str(value["impressions"]), str(value["clicks"]),
            str(round(value["ctr"] * 100, 2)) + "%",
            str(value["position"]) if value["position"] is not None else "不明",
        ]
    lines = [
        "# 洗剤ページ・11月9日改善後のGSC厳格な前後比較",
        "",
        "- 状態：**" + report["status"] + "**",
        "- 確認基準日（太平洋時間）： " + report["as_of_pacific"],
        "- GSC確定確認の目安： " + report["finalized_through_pacific"],
        "- 対象URL： " + report["target_page"],
        "- PR #162マージ： " + report["release_merge_utc"] + "（11月9日の部分日は比較対象外）",
        "- 改善前： " + "〜".join(report["periods"]["before"]),
        "- 改善後： " + "〜".join(report["periods"]["after"]),
        "",
        "| 期間 | 表示 | クリック | CTR | 平均掲載順位 |",
        "|---|---:|---:|---:|---:|",
    ]
    for period, name in (("before", "公開前"), ("after", "公開後")):
        lines.append("| " + name + " | " + " | ".join(metrics(report["page"][period])) + " |")
    lines.append("")
    if report["page_change"] is not None:
        diff = report["page_change"]
        lines.append(
            "表示差 " + str(diff["impressions"]) + "、クリック差 " + str(diff["clicks"]) +
            "、CTR差 " + str(diff["ctr_percentage_points"]) + "pt。" +
            " 少数データやGoogleの外部要因による変化があるため公開施策の因果効果とは断定しません。"
        )
    if report["status"] == "WAITING_FOR_FINAL_DATA":
        lines.append("11月10〜15日の全日程が確定するまでAPI照会・前後評価を行いません。")
    if report.get("reason"):
        lines.append("取得制約：" + report["reason"] + "（不明をゼロ扱いしません）")
    comp = report.get("query_comparison")
    if comp is not None:
        lines.extend([
            "", "## 一致した検索語だけの参考比較（非網羅）", "",
            "site:指定検索と個人情報らしい検索語は除外。片方の期間で未返却なら増減は不明です。",
            "| 自然検索語 | 前表示 | 後表示 | 表示差 | 状態 |",
            "|---|---:|---:|---:|---|",
        ])
        for row in comp["rows"][:20]:
            b, a = row["prior_28"], row["last_28"]
            lines.append("| " + safe(row["query"]) + " | " +
                         (str(b["impressions"]) if b is not None else "未確認") + " | " +
                         (str(a["impressions"]) if a is not None else "未確認") + " | " +
                         (str(row["impression_change"]) if row["impression_change"] is not None else "算出不可") +
                         " | " + row["status"] + " |")
    lines.extend(["", "※測定と商品/SEOの改善判断は別です。GSCクリックとGA4/楽天クリック・収益も混同しません。", ""])
    return "\n".join(lines)

def main():
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if base.date_windows(today)["last_7"][1] < AFTER[1]:
        report = analyze(today)
    elif not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        report = analyze(today)
    else:
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            creds, _ = google.auth.default(scopes=[base.SCOPE])
            session = AuthorizedSession(creds)
            response = session.get(base.ROOT + "/sites", timeout=30)
            if response.status_code != 200:
                raise ValueError("property list unavailable")
            listing = response.json()
            if not isinstance(listing, dict) or not isinstance(listing.get("siteEntry"), list):
                raise ValueError("invalid property list")
            permissions = {
                r["siteUrl"]: r["permissionLevel"] for r in listing["siteEntry"]
                if isinstance(r, dict) and isinstance(r.get("siteUrl"), str)
                and isinstance(r.get("permissionLevel"), str)
            }
            report = analyze(today, session, permissions)
        except Exception:
            report = analyze(today)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "gsc-laundry-release-effect.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUTPUT / "gsc-laundry-release-effect.md").write_text(
        markdown(report), encoding="utf-8"
    )
    print("GSC_LAUNDRY_RELEASE_EFFECT " + report["status"])

if __name__ == "__main__":
    main()
