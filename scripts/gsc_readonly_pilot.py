#!/usr/bin/env python3
"""Google Search Console read-only connection pilot for the daily-cost site.

- Reuses keyless GitHub -> Google Workload Identity Federation authentication.
- Never writes to Search Console or the website, and never invents zero traffic.
- Requires access to this *exact* URL-prefix property; no fallback to the user's
  broader github.io Search Console property (which may include other sites).
- Pure report normalization and suggestion logic can be tested offline.
"""
import datetime as dt
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

SITE = "https://stusaurus.github.io/daily-cost-jp/"
PROPERTY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
API_ROOT = "https://www.googleapis.com/webmasters/v3"
MAX_ROWS = 25000
FOCUS = ("/categories/laundry/", "/categories/tissue/", "/categories/toilet-paper/")
ACTION_NAMES = {
    "CHECK_SEARCH_VISIBILITY": "検索での表示機会が少ない。検索意図とページの対応を確認",
    "CHECK_SEARCH_RESULT_SNIPPET": "表示はあるが検索結果のクリックが少ない。タイトルや説明文を調査",
    "CHECK_LANDING_EXPERIENCE": "検索クリックはある。GA4の購入導線と照合する候補",
    "OBSERVE": "現段階で十分な根拠がないため経過観察",
}


def periods(today):
    """Final GSC calendar periods, ending three days before the run."""
    end = today - dt.timedelta(days=3)
    def date_range(length, offset=0):
        last = end - dt.timedelta(days=offset)
        return [(last - dt.timedelta(days=length - 1)).isoformat(), last.isoformat()]
    return {"last_7": date_range(7), "prior_7": date_range(7, 7),
            "last_28": date_range(28), "prior_28": date_range(28, 28)}


def normalize_path(url):
    """Fail closed: only HTTPS pages below the exact site's URL prefix."""
    try:
        parsed = urlsplit(url)
        root = urlsplit(SITE)
        if (parsed.scheme != "https" or parsed.hostname != root.hostname or
                parsed.username or parsed.password or parsed.port is not None or
                not parsed.path.startswith(root.path)):
            return None
        suffix = parsed.path[len(root.path):]
        if any(value in suffix for value in ("\x00", "\r", "\n")):
            return None
        return "/" + suffix
    except (ValueError, TypeError):
        return None


def metrics(value):
    if not isinstance(value, dict):
        raise ValueError("Malformed GSC metrics")
    clicks = value.get("clicks")
    impressions = value.get("impressions")
    ctr = value.get("ctr")
    position = value.get("position")
    if (type(clicks) not in (int, float) or type(impressions) not in (int, float)
            or type(ctr) not in (int, float) or type(position) not in (int, float)):
        raise ValueError("Incomplete GSC metrics")
    if not (float(clicks).is_integer() and float(impressions).is_integer()):
        raise ValueError("Fractional click or impression counts")
    if not (0 <= clicks and 0 <= impressions and 0 <= ctr <= 1 and position >= 1):
        raise ValueError("Unexpected GSC metrics range")
    return {"clicks": int(clicks), "impressions": int(impressions),
            "ctr": round(ctr, 6), "position": round(position, 2)}


def aggregate_response(response):
    """No rows -> unavailable/zero distinction is NOT independently verifiable."""
    if not isinstance(response, dict) or "rows" not in response:
        return {"status": "NO_ROWS", "metrics": None}
    rows = response["rows"]
    if not isinstance(rows, list):
        raise ValueError("Malformed GSC aggregate response")
    if not rows:
        return {"status": "NO_ROWS", "metrics": None}
    if len(rows) != 1 or rows[0].get("keys"):
        raise ValueError("Expected one site-wide aggregate row")
    return {"status": "OBSERVED", "metrics": metrics(rows[0])}


def page_response(response):
    if not isinstance(response, dict):
        raise ValueError("Malformed GSC page response")
    rows = response.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed GSC page rows")
    result = {}
    discarded = 0
    for row in rows:
        keys = row.get("keys", [])
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
            raise ValueError("Expected one GSC page dimension")
        path = normalize_path(keys[0])
        if path is None:
            discarded += 1
            continue
        if path in result:
            raise ValueError("Duplicate GSC page dimension")
        result[path] = metrics(row)
    return {
        "status": "TOP_ROWS_LIMIT_POSSIBLE" if len(rows) >= MAX_ROWS else
                  "NO_ROWS" if not rows else "OBSERVED_TOP_ROWS",
        "rows_count": len(rows),
        "discarded_out_of_scope": discarded,
        "pages": result,
    }


def query_response(response):
    """Only aggregated, sufficiently frequent queries; avoid long-tail details."""
    if not isinstance(response, dict):
        raise ValueError("Malformed GSC query response")
    rows = response.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Malformed GSC query rows")
    filtered = []
    for row in rows:
        keys = row.get("keys", [])
        if not isinstance(keys, list) or len(keys) != 2 or not all(isinstance(k, str) for k in keys):
            raise ValueError("Expected page,query GSC dimensions")
        path = normalize_path(keys[0])
        if path is None:
            continue
        m = metrics(row)
        q = keys[1].strip()
        # Avoid exposing rare searches to public-repo GitHub Actions artifacts.
        if m["impressions"] < 20 or not q or len(q) > 120:
            continue
        filtered.append({"page": path, "query": q, **m})
    filtered.sort(key=lambda row: (-row["impressions"], -row["clicks"], row["page"], row["query"]))
    return {"status": "TOP_ROWS_LIMIT_POSSIBLE" if len(rows) >= MAX_ROWS else "OBSERVED_TOP_ROWS",
            "queries": filtered[:20], "row_limit_reached": len(rows) >= MAX_ROWS}


def decide(last28, last7):
    """Research hypothesis, never permission to rewrite a page or to change a title."""
    m = last28
    if m is None or last7 is None:
        return "OBSERVE", "検索データが未取得のため判断を保留"
    if m["impressions"] < 20:
        return "CHECK_SEARCH_VISIBILITY", ACTION_NAMES["CHECK_SEARCH_VISIBILITY"]
    if m["impressions"] >= 50 and m["ctr"] < 0.02 and 4 <= m["position"] <= 30:
        return "CHECK_SEARCH_RESULT_SNIPPET", ACTION_NAMES["CHECK_SEARCH_RESULT_SNIPPET"]
    if m["clicks"] >= 5:
        return "CHECK_LANDING_EXPERIENCE", ACTION_NAMES["CHECK_LANDING_EXPERIENCE"]
    return "OBSERVE", ACTION_NAMES["OBSERVE"]


def build_report(today, aggregates, per_page, queries):
    windows = periods(today)
    if set(aggregates) != set(windows) or set(per_page) != set(windows):
        raise ValueError("Incomplete GSC report time windows")
    all_paths = set()
    for result in per_page.values():
        all_paths.update(result["pages"])
    pages = []
    for path in all_paths | set(FOCUS):
        recent = per_page["last_28"]["pages"].get(path)
        last7 = per_page["last_7"]["pages"].get(path)
        previous = per_page["prior_28"]["pages"].get(path)
        action, explanation = decide(recent, last7)
        pages.append({
            "path": path, "last_7": last7, "prior_7": per_page["prior_7"]["pages"].get(path),
            "last_28": recent, "prior_28": previous,
            "investigation": action, "hypothesis": explanation,
        })
    # High-confidence, frequently visible pages first. Focus pages win ties.
    pages.sort(key=lambda p: (
        p["investigation"] == "OBSERVE",
        p["path"] not in FOCUS,
        -(p["last_28"] or {}).get("impressions", 0), p["path"]))
    status = "NO_SEARCH_DATA" if all(a["status"] == "NO_ROWS" for a in aggregates.values()) else "PROVISIONAL"
    if any(p["status"] == "TOP_ROWS_LIMIT_POSSIBLE" for p in per_page.values()):
        status = "TOP_ROW_COVERAGE_UNCERTAIN"
    return {
        "source": "Search Console Search Analytics API",
        "site_property": SITE,
        "status": status,
        "windows": windows,
        "site_aggregates": aggregates,
        "page_row_coverage": {k: {key: v[key] for key in ("status", "rows_count", "discarded_out_of_scope")}
                              for k, v in per_page.items()},
        "pages": pages,
        "priority_pages": pages[:10],
        "top_queries": queries["queries"],
        "query_row_limit_reached": queries["row_limit_reached"],
        "notes": [
            "GSC clicks are visits from Google Search, not Rakuten affiliate clicks or purchases.",
            "GSC average position is impression-weighted; it is NOT a stable ranking for each keyword.",
            "An absent page/query row may be true zero or missing due to privacy, thresholds, and top-row limits.",
            "No Search Console sitemap submissions, product data changes, or automatic publishing.",
        ],
    }


def markdown(report):
    lines = [
        "## 日用品サイト：Google検索流入の読み取り専用診断",
        "",
        "- 接続状態：**" + report["status"] + "**",
        "- 対象Search Consoleプロパティ：" + SITE,
    ]
    if report["status"] == "NOT_CONNECTED":
        lines += [
            "- 理由：" + report.get("reason", "権限またはAPI設定の確認が必要"),
            "- 検索の表示数・クリック数は**未取得**です。0件という意味ではありません。",
        ]
        return "\n".join(lines) + "\n"
    lines += [
        "- **Google検索クリックと楽天アフィリエイトクリックは別の指標。**",
        "",
        "| 対象 | 28日間の検索表示 | 28日間の検索クリック | 平均掲載順位 | 次の調査 |",
        "|---|---:|---:|---:|---|",
    ]
    for entry in report["priority_pages"][:10]:
        m = entry["last_28"]
        lines.append("| " + entry["path"].replace("|", "%7C") +
                     " | " + (str(m["impressions"]) if m else "不明") +
                     " | " + (str(m["clicks"]) if m else "不明") +
                     " | " + (str(m["position"]) if m else "不明") +
                     " | " + entry["hypothesis"] + " |")
    for key in ("last_7", "last_28"):
        item = report["site_aggregates"][key]
        lines.append("")
        lines.append("- " + key + " サイト全体の検索実績：" +
                     (str(item["metrics"]) if item["metrics"] else "未取得／表示なし（0とは断定不可）"))
    lines += ["", "※検索順位やクリック率だけで原因は断定しません。まず検索意図・見出し・導線を実画面検証します。",
              "※Googleのプライバシー処理・上位行制限により、全検索クエリを網羅する保証はありません。",
              "※商品・価格・楽天リンク・サイトのコードは変更していません。", ""]
    return "\n".join(lines)


def not_connected(reason):
    if reason not in ("SEARCH_CONSOLE_API_DISABLED_OR_FORBIDDEN",
                      "PROPERTY_ACCESS_MISSING",
                      "SEARCH_CONSOLE_UNAVAILABLE",
                      "SEARCH_CONSOLE_UNAUTHORIZED",
                      "SEARCH_CONSOLE_BAD_REQUEST",
                      "MISSING_WORKLOAD_IDENTITY",
                      "AUTHENTICATION_FAILED"):
        reason = "SEARCH_CONSOLE_UNAVAILABLE"
    return {"source": "Search Console Search Analytics API", "site_property": SITE,
            "status": "NOT_CONNECTED", "reason": reason, "site_aggregates": {},
            "priority_pages": [], "pages": [], "top_queries": [],
            "notes": ["No verified Search Console data; do not infer zero impressions."]}


def send_report(report):
    output = Path("audit-results")
    output.mkdir(parents=True, exist_ok=True)
    (output / "gsc-search-pilot.json").write_text(json.dumps(
        report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "gsc-search-pilot.md").write_text(markdown(report), encoding="utf-8")
    print("GSC read-only pilot status=" + report["status"] +
          "; reason=" + report.get("reason", "read-only provisional analytics"))


def api_error_reason(status):
    return {
        400: "SEARCH_CONSOLE_BAD_REQUEST",
        401: "SEARCH_CONSOLE_UNAUTHORIZED",
        403: "SEARCH_CONSOLE_API_DISABLED_OR_FORBIDDEN",
        404: "PROPERTY_ACCESS_MISSING",
    }.get(status, "SEARCH_CONSOLE_UNAVAILABLE")


def fetch():
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        send_report(not_connected("MISSING_WORKLOAD_IDENTITY"))
        return
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        credentials, _ = google.auth.default(scopes=[PROPERTY_SCOPE])
        session = AuthorizedSession(credentials)
    except Exception:
        send_report(not_connected("AUTHENTICATION_FAILED"))
        return

    try:
        access = session.get(API_ROOT + "/sites", timeout=30)
    except Exception:
        send_report(not_connected("SEARCH_CONSOLE_UNAVAILABLE"))
        return
    if access.status_code != 200:
        send_report(not_connected(api_error_reason(access.status_code)))
        return
    try:
        authorized = access.json().get("siteEntry", [])
        if not any(
            row.get("siteUrl") == SITE and row.get("permissionLevel") in
            ("siteOwner", "siteFullUser", "siteRestrictedUser")
            for row in authorized):
            send_report(not_connected("PROPERTY_ACCESS_MISSING"))
            return
    except (TypeError, ValueError):
        send_report(not_connected("SEARCH_CONSOLE_UNAVAILABLE"))
        return

    def query(body):
        url = API_ROOT + "/sites/" + quote(SITE, safe="") + "/searchAnalytics/query"
        try:
            response = session.post(url, json=body, timeout=45)
        except Exception as error:
            raise ConnectionError("Search Console request failed") from error
        if response.status_code != 200:
            raise ConnectionError("Search Console request HTTP " + str(response.status_code))
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Malformed Search Console API JSON")
        return payload

    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    periods_by_name = periods(today)
    aggregate_data, page_data = {}, {}
    try:
        for label, (start, end) in periods_by_name.items():
            common = {"startDate": start, "endDate": end, "type": "web",
                      "dataState": "final"}
            aggregate_data[label] = aggregate_response(query(common))
            page_data[label] = page_response(query({
                **common, "dimensions": ["page"], "rowLimit": MAX_ROWS,
            }))
        start, end = periods_by_name["last_28"]
        query_data = query_response(query({
            "startDate": start, "endDate": end, "type": "web",
            "dataState": "final", "dimensions": ["page", "query"],
            "rowLimit": MAX_ROWS,
        }))
    except (ValueError, ConnectionError) as error:
        # Auth+site rights are verified; a failed query is a measurement/API
        # failure and must fail closed, not be reclassified as zero traffic.
        send_report(not_connected("SEARCH_CONSOLE_BAD_REQUEST"
                                  if isinstance(error, ValueError) else "SEARCH_CONSOLE_UNAVAILABLE"))
        return
    report = build_report(today, aggregate_data, page_data, query_data)
    report["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    send_report(report)


if __name__ == "__main__":
    fetch()
