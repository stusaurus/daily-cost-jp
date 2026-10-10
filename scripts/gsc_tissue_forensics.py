#!/usr/bin/env python3
"""One-off, read-only GSC tissue-page investigation around 2026-09-27.

Only aggregate/device observations and *counts* of query rows are published.
Raw search query text is deliberately never written to files, logs or Actions
summaries. URL Inspection describes Google's CURRENT indexed copy, not its
historical status at the September decline.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.parse import quote

SITE = "https://stusaurus.github.io/daily-cost-jp/"
PAGE = SITE + "categories/tissue/"
SEARCH_API = "https://www.googleapis.com/webmasters/v3"
INSPECTION_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
PERIODS = {
    "before": ["2026-09-20", "2026-09-26"],
    "after": ["2026-09-27", "2026-10-03"],
}
DEVICES = ("DESKTOP", "MOBILE", "TABLET")
MAX_ROWS = 25000


def metric(row):
    if not isinstance(row, dict):
        raise ValueError("Malformed Search Console row")
    count = {}
    for key in ("clicks", "impressions"):
        v = row.get(key)
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0 or not float(v).is_integer():
            raise ValueError("Invalid GSC " + key)
        count[key] = int(v)
    for key in ("ctr", "position"):
        v = row.get(key)
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError("Invalid GSC " + key)
        if (key == "ctr" and not 0 <= v <= 1) or (key == "position" and v < 1):
            raise ValueError("Out-of-range GSC " + key)
        count[key] = round(float(v), 5 if key == "ctr" else 2)
    return count


def aggregate(body):
    """A row's absence is unknown, not a verified zero."""
    if not isinstance(body, dict):
        raise ValueError("Malformed aggregate response")
    rows = body.get("rows", [])
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError("Wrong aggregate response shape")
    if not rows:
        return {"status": "NO_ROW_UNKNOWN", "metrics": None}
    if rows[0].get("keys"):
        raise ValueError("Unexpected dimensions in aggregate")
    return {"status": "OBSERVED", "metrics": metric(rows[0])}


def device_rows(body):
    if not isinstance(body, dict):
        raise ValueError("Malformed device response")
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed device rows")
    devices = {}
    for r in rows:
        keys = r.get("keys") if isinstance(r, dict) else None
        if not isinstance(keys, list) or len(keys) != 1 or keys[0] not in DEVICES:
            raise ValueError("Unknown GSC device")
        if keys[0] in devices:
            raise ValueError("Duplicate device row")
        devices[keys[0]] = metric(r)
    return {"status": "OBSERVED" if rows else "NO_ROWS_UNKNOWN",
            "devices": {d: devices.get(d) for d in DEVICES},
            "returned_rows": len(rows)}


def anonymous_query_coverage(body):
    """Never retain raw query keys. Only counts of API-visible aggregate rows."""
    if not isinstance(body, dict):
        raise ValueError("Malformed query response")
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed query rows")
    total_impressions = total_clicks = 0
    for row in rows:
        keys = row.get("keys") if isinstance(row, dict) else None
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
            raise ValueError("Unexpected query dimension")
        m = metric(row)
        total_impressions += m["impressions"]
        total_clicks += m["clicks"]
    return {
        "rows_returned": len(rows),
        "visible_row_impressions": total_impressions,
        "visible_row_clicks": total_clicks,
        "top_rows_limit_possible": len(rows) >= MAX_ROWS,
        "raw_queries_exported": False,
        "note": "Anonymized or low-volume queries may be omitted. Raw query strings are NOT stored.",
    }


def inspection_snapshot(response):
    """A current index snapshot. Only safe, bounded state fields are exported."""
    if not isinstance(response, dict):
        raise ValueError("Invalid URL Inspection response")
    result = response.get("inspectionResult", {})
    if not isinstance(result, dict):
        raise ValueError("Malformed URL Inspection result")
    index = result.get("indexStatusResult")
    if not isinstance(index, dict):
        return {"status": "NO_INDEX_STATUS", "historical_status_available": False}
    allowed = (
        "verdict", "coverageState", "robotsTxtState", "indexingState",
        "pageFetchState", "lastCrawlTime", "googleCanonical", "userCanonical",
        "crawledAs",
    )
    snapshot = {}
    for key in allowed:
        v = index.get(key)
        if v is not None:
            if not isinstance(v, str):
                raise ValueError("Invalid inspection field")
            # Don't emit unexpected URLs or unbounded free text to public artifacts.
            if key in ("googleCanonical", "userCanonical") and not v.startswith("https://stusaurus.github.io/"):
                snapshot[key] = "OTHER_CANONICAL_REQUIRES_REVIEW"
            else:
                snapshot[key] = v[:220]
    return {
        "status": "OBSERVED",
        "historical_status_available": False,
        "note": "Snapshot of indexed version at request time; NOT an index-status history for 2026-09-27.",
        "index": snapshot,
    }


def compare(before, after):
    a, b = before.get("metrics"), after.get("metrics")
    if a is None or b is None:
        return {"status": "INSUFFICIENT_DATA", "before": a, "after": b,
                "impression_change": None, "cause": "UNKNOWN"}
    difference = b["impressions"] - a["impressions"]
    return {
        "status": "LOW_SAMPLE" if a["impressions"] + b["impressions"] < 100 else "OBSERVED_DESCRIPTIVE",
        "before": a, "after": b,
        "impression_change": difference,
        "change_percent": round(100 * difference / a["impressions"], 1) if a["impressions"] else None,
        "cause": "UNKNOWN",
    }


def report_for(data, inspection):
    if set(data) != set(PERIODS):
        raise ValueError("Both comparison periods are required")
    for period in data.values():
        if not isinstance(period, dict) or not all(
                name in period for name in ("aggregate", "devices", "anonymous_queries")):
            raise ValueError("Incomplete forensics window")
    change = compare(data["before"]["aggregate"], data["after"]["aggregate"])
    device_change = {}
    for dev in DEVICES:
        before = data["before"]["devices"]["devices"][dev]
        after = data["after"]["devices"]["devices"][dev]
        device_change[dev] = {
            "before": before,
            "after": after,
            "impression_change": (
                after["impressions"] - before["impressions"] if before and after else None
            ),
        }
    if not isinstance(inspection, dict):
        raise ValueError("Inspection status missing")
    coverage = {}
    for key in PERIODS:
        agg = data[key]["aggregate"]["metrics"]
        observed = data[key]["devices"]["devices"]
        device_sum = sum(v["impressions"] for v in observed.values() if v is not None)
        coverage[key] = {
            "rows": data[key]["devices"]["returned_rows"],
            "device_impressions": device_sum,
            "aggregate_impressions": agg["impressions"] if agg else None,
            "status": ("UNKNOWN" if agg is None else
                       "MATCHED" if device_sum == agg["impressions"] else "DIFFERENT_GROUPED_TOTALS"),
        }
    return {
        "source": "GSC Search Analytics + URL Inspection read-only",
        "site": SITE, "page": PAGE, "historical_windows": PERIODS,
        "status": "PROVISIONAL" if change["before"] and change["after"] else "DATA_LIMITED",
        "change": change, "devices": device_change,
        "observed_query_coverage": {
            name: data[name]["anonymous_queries"] for name in PERIODS
        },
        "device_coverage": coverage,
        "index_inspection": inspection,
        "not_historical_index_proof": True,
        "no_keyword_strings_exported": True,
        "no_automatic_seo_edits": True,
        "interpretation": [
            "This comparison is descriptive. It cannot establish whether search demand, ranking, or indexing CAUSED the drop.",
            "An absent GSC dimension row is unknown, not proof of zero.",
            "GSC query rows omit some searches; query-group sums need not match impression totals.",
            "URL Inspection is a CURRENT Google indexed-copy snapshot, not an index-change history.",
            "No sitemap submission, live index request, page edit or affiliate link change was performed.",
        ],
    }


def markdown(out):
    lines = [
        "## ティッシュ：9月27日前後の検索減少調査",
        "",
        "- 調査対象：" + PAGE,
        "- 比較：9/20〜9/26 → 9/27〜10/3",
        "- 状態：**" + out["status"] + "**",
        "- **インデックスや順位下落が原因だと断定できません。**",
        "",
        "| 期間 | 検索表示 | 検索クリック | 平均順位 |",
        "|---|---:|---:|---:|",
    ]
    def fmt(x):
        return str(x) if x is not None else "不明"
    for key, label in (("before", "9/20〜9/26"), ("after", "9/27〜10/3")):
        m = out["change"][key]
        lines.append("| " + label + " | " +
                     fmt(m["impressions"] if m else None) + " | " +
                     fmt(m["clicks"] if m else None) + " | " +
                     fmt(m["position"] if m else None) + " |")
    lines += [
        "",
        "### PC・スマホ別",
        "",
        "| 端末 | 前期の表示 | 後期の表示 | 増減 |",
        "|---|---:|---:|---:|",
    ]
    for dev, name in (("MOBILE", "スマホ"), ("DESKTOP", "PC"), ("TABLET", "タブレット")):
        v = out["devices"][dev]
        lines.append("| " + name + " | " +
                     fmt(v["before"]["impressions"] if v["before"] else None) +
                     " | " + fmt(v["after"]["impressions"] if v["after"] else None) +
                     " | " + fmt(v["impression_change"]) + " |")
    for key, label in (("before", "前期"), ("after", "後期")):
        info = out["device_coverage"][key]
        lines.append("- " + label + "の端末別集計の整合性：" + info["status"])
    lines += ["", "### 検索クエリの取得範囲（検索語は非公開）"]
    for key, label in (("before", "前期"), ("after", "後期")):
        query = out["observed_query_coverage"][key]
        lines.append("- " + label + "：APIで取得できた検索語の集計行 " +
                     str(query["rows_returned"]) + "行。実際の検索語総数ではありません。")
    lines += ["", "### Googleのインデックス情報（現在の状態）", ""]
    ix = out["index_inspection"]
    lines.append("- 状態：" + ix.get("status", "UNKNOWN"))
    for name in ("verdict", "coverageState", "lastCrawlTime",
                 "googleCanonical", "indexingState", "robotsTxtState"):
        if isinstance(ix.get("index"), dict):
            lines.append("- " + name + "：" + fmt(ix["index"].get(name)))
    lines += [
        "",
        "※このURL検査はGoogleに記録されている**現在のインデックスの状態**。9月27日に何が起きたかを直接証明しません。",
        "※検索語の生データは公開成果物に保存していません。表示の少ない検索語や匿名化された検索は集計から欠ける場合があります。",
        "※タイトル・説明文・商品価格・楽天リンク・公開サイトは変更していません。",
        "",
    ]
    return "\n".join(lines)


def sanitized_api_error(status):
    if status == 403:
        return "HTTP_403_FORBIDDEN_OR_QUOTA"
    if status == 404:
        return "HTTP_404_NOT_FOUND"
    if status == 429:
        return "HTTP_429_QUOTA"
    if status >= 500:
        return "HTTP_5XX_SERVER"
    return "HTTP_REQUEST_FAILED"


def run():
    output = Path("audit-results")
    output.mkdir(parents=True, exist_ok=True)
    period_data = {}
    inspect = {"status": "NOT_ATTEMPTED", "historical_status_available": False}
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=[SCOPE])
        session = AuthorizedSession(credentials)
    except Exception:
        report = {"source": "GSC Search Analytics + URL Inspection read-only",
                  "site": SITE, "page": PAGE, "status": "NOT_CONNECTED",
                  "reason": "AUTHENTICATION_UNAVAILABLE",
                  "no_automatic_seo_edits": True}
        output_report(output, report)
        return

    # Require exact URL-prefix property. Never borrow permissions on other repos.
    try:
        permissions = session.get(SEARCH_API + "/sites", timeout=30)
        if permissions.status_code != 200:
            raise ConnectionError("SITE_LIST_HTTP_ERROR")
        site_entries = permissions.json().get("siteEntry", [])
        if not any(item.get("siteUrl") == SITE and item.get("permissionLevel") in
                   ("siteOwner", "siteFullUser", "siteRestrictedUser") for item in site_entries):
            raise PermissionError("EXACT_PROPERTY_ACCESS_MISSING")
    except (ConnectionError, ValueError, PermissionError) as e:
        report = {"source": "GSC Search Analytics + URL Inspection read-only",
                  "site": SITE, "page": PAGE, "status": "NOT_CONNECTED",
                  "reason": str(e)[:90], "no_automatic_seo_edits": True}
        output_report(output, report)
        return

    search_url = SEARCH_API + "/sites/" + quote(SITE, safe="") + "/searchAnalytics/query"
    def search(start, end, dimensions):
        body = {
            "startDate": start, "endDate": end, "dataState": "final",
            "type": "web", "dimensions": dimensions,
            "dimensionFilterGroups": [{"groupType": "and", "filters": [{
                "dimension": "page", "operator": "equals", "expression": PAGE}]}],
            "rowLimit": MAX_ROWS,
        }
        response = session.post(search_url, json=body, timeout=45)
        if response.status_code != 200:
            raise ConnectionError(sanitized_api_error(response.status_code))
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("GSC API returned invalid JSON")
        return value

    try:
        for label, dates in PERIODS.items():
            raw_aggregate = search(*dates, [])
            raw_devices = search(*dates, ["device"])
            raw_queries = search(*dates, ["query"])
            period_data[label] = {
                "aggregate": aggregate(raw_aggregate),
                "devices": device_rows(raw_devices),
                "anonymous_queries": anonymous_query_coverage(raw_queries),
            }
    except (ConnectionError, ValueError) as exc:
        report = {"source": "GSC Search Analytics + URL Inspection read-only",
                  "site": SITE, "page": PAGE,
                  "status": "DATA_UNAVAILABLE", "reason": str(exc)[:90],
                  "no_automatic_seo_edits": True}
        output_report(output, report)
        return

    try:
        resp = session.post(INSPECTION_API,
                            json={"inspectionUrl": PAGE, "siteUrl": SITE,
                                  "languageCode": "ja-JP"}, timeout=45)
        inspect = (inspection_snapshot(resp.json()) if resp.status_code == 200
                   else {"status": sanitized_api_error(resp.status_code),
                         "historical_status_available": False})
    except (ConnectionError, ValueError, KeyError):
        inspect = {"status": "INDEX_INSPECTION_UNAVAILABLE",
                   "historical_status_available": False}
    result = report_for(period_data, inspect)
    result["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    output_report(output, result)


def output_report(folder, report):
    # Never write the raw Google query rows, even in debug/error cases.
    (folder / "gsc-tissue-forensics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "gsc-tissue-forensics.md").write_text(
        markdown(report) if "change" in report else
        ("## ティッシュGSC調査\n\n**" + report["status"] +
         "**。検索データ未取得。0回とは判定しません。\n"),
        encoding="utf-8")
    print("Tissue Search Console investigation: " + report["status"] +
          "; index=" + report.get("index_inspection", {}).get("status", "UNAVAILABLE"))


if __name__ == "__main__":
    run()
