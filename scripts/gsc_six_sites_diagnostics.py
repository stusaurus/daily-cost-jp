#!/usr/bin/env python3
"""Read-only six-site GSC keyword, date and index-snapshot diagnostics.

No SEO edits, indexing requests, publishing, or affiliate actions. Missing data
and Search Console's anonymized query omissions are never recoded as zero.
"""
import datetime as dt
import html
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import gsc_six_sites as base

INDEX_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
OUTPUT = Path("audit-results")
ROW_LIMIT = 1000
TARGET_PATHS = {
    "日用品": ("/categories/laundry/", "/categories/tissue/", "/categories/toilet-paper/"),
    "ベビー用品": ("/", "/diapers/pants/m/"),
    "ペット用品": ("/", "/categories/pet-sheets/", "/categories/cat-litter/"),
    "食品": ("/", "/categories/rice/", "/categories/pack-rice/"),
    "ボードゲーム": ("/", "/scenes/two-player/"),
    "SOTOJITAKU": ("/", "/camp/", "/car-stay/", "/fishing/"),
}


def cleaned(value, max_length=180):
    """Show only bounded, single-line API text (never format an API response as HTML)."""
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:max_length]


def analytics_rows(payload, dimension, *, property_url=None):
    """Rows are a non-exhaustive sample of reported queries/dates, never totals."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rows", []), list):
        raise ValueError("invalid analytics payload")
    rows = payload.get("rows", [])
    if len(rows) > ROW_LIMIT:
        raise ValueError("unexpected row count")
    parsed = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("keys"), list) or len(row["keys"]) != 1:
            raise ValueError("invalid analytics key")
        key = row["keys"][0]
        if not isinstance(key, str) or not key:
            raise ValueError("empty analytics key")
        if dimension == "date":
            try:
                parsed_date = dt.date.fromisoformat(key)
            except ValueError as error:
                raise ValueError("invalid date dimension") from error
            if parsed_date.isoformat() != key:
                raise ValueError("invalid date format")
        if dimension == "query":
            key = cleaned(key)
        parsed.append({"key": key, **base.safe_metrics(row)})
    parsed.sort(key=(lambda r: r["key"]) if dimension == "date"
                else (lambda r: (-r["impressions"], -r["clicks"], r["key"])))
    return {
        "status": "NO_ROWS" if not rows else "TOP_ROWS_LIMIT_POSSIBLE" if len(rows) == ROW_LIMIT else "OBSERVED_ROWS",
        "rows_returned": len(rows),
        "rows": parsed,
        "note": "Reported grouped rows are not exhaustive; anonymized queries and low-volume rows can be missing.",
    }


def inspect_url(session, site, path):
    if not path.startswith("/") or path.startswith("//") or any(x in path for x in ("?", "#", "\\", "\n", "\r")):
        raise ValueError("non-canonical target path")
    url = site + path.lstrip("/")
    response = session.post(INDEX_ENDPOINT, json={"inspectionUrl": url, "siteUrl": site}, timeout=45)
    if response.status_code != 200:
        return {"path": path, "status": "UNAVAILABLE", "reason": "INSPECTION_HTTP_" + str(response.status_code)}
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("inspectionResult"), dict):
        return {"path": path, "status": "UNAVAILABLE", "reason": "INVALID_INSPECTION_RESPONSE"}
    result = payload["inspectionResult"].get("indexStatusResult")
    if not isinstance(result, dict):
        return {"path": path, "status": "UNAVAILABLE", "reason": "INDEX_STATUS_MISSING"}
    if not result.get("verdict") and not result.get("coverageState"):
        return {"path": path, "status": "UNAVAILABLE", "reason": "INDEX_VERDICT_MISSING"}
    canonical = cleaned(result.get("googleCanonical"), 350)
    user_canonical = cleaned(result.get("userCanonical"), 350)
    return {
        "path": path,
        "status": "OBSERVED_SNAPSHOT",
        "verdict": cleaned(result.get("verdict")),
        "coverage_state": cleaned(result.get("coverageState")),
        "indexing_state": cleaned(result.get("indexingState")),
        "robots_txt_state": cleaned(result.get("robotsTxtState")),
        "page_fetch_state": cleaned(result.get("pageFetchState")),
        "last_crawl_time": cleaned(result.get("lastCrawlTime")),
        "google_canonical": canonical,
        "user_canonical": user_canonical,
    }


def site_diagnostics(session, name, site, windows, permissions):
    result = {"name": name, "property": site, "status": "NOT_CONNECTED", "analytics": {}, "inspection": []}
    if permissions is None:
        result["reason"] = "PROPERTY_LIST_UNAVAILABLE"
        return result
    if permissions.get(site) not in base.AUTHORIZED_LEVELS:
        result["reason"] = "PROPERTY_ACCESS_MISSING"
        return result
    errors = []
    requests = (
        ("queries_28d", windows["last_28"], "query"),
        ("queries_7d", windows["last_7"], "query"),
        ("daily_28d", windows["last_28"], "date"),
    )
    for label, period, dimension in requests:
        try:
            response = base.query(session, site, period, [dimension])
            result["analytics"][label] = analytics_rows(response, dimension)
        except Exception:
            result["analytics"][label] = {"status": "UNAVAILABLE", "rows": [], "reason": "QUERY_FAILED_OR_INVALID_RESPONSE"}
            errors.append(label)
    for path in TARGET_PATHS[name]:
        try:
            inspected = inspect_url(session, site, path)
        except Exception:
            inspected = {"path": path, "status": "UNAVAILABLE", "reason": "INSPECTION_FAILED"}
        result["inspection"].append(inspected)
        if inspected["status"] != "OBSERVED_SNAPSHOT":
            errors.append(path)
    result["status"] = "PARTIAL" if errors else "OBSERVED"
    if errors:
        result["unavailable_parts"] = errors
    return result


def make_report(today, session=None, permissions=None, auth_problem=None):
    windows = base.date_windows(today)
    sites = []
    for name, site in base.SITES:
        if auth_problem:
            sites.append({"name": name, "property": site, "status": "NOT_CONNECTED", "reason": auth_problem,
                          "analytics": {}, "inspection": []})
        else:
            sites.append(site_diagnostics(session, name, site, windows, permissions))
    passed = sum(s["status"] == "OBSERVED" for s in sites)
    return {
        "source": "Google Search Console Search Analytics + URL Inspection APIs (read-only)",
        "as_of_pacific": today.isoformat(),
        "date_windows": windows,
        "status": "READY" if passed == 6 else "UNAVAILABLE" if all(s["status"] == "NOT_CONNECTED" for s in sites) else "PARTIAL",
        "sites": sites,
        "limitations": [
            "Query-level and page-level rows are not comprehensive; anonymized searches may be omitted.",
            "NO_ROWS is not proof of zero searches or zero impressions.",
            "URL Inspection describes Google's indexed snapshot, not a live URL test.",
            "Missing Google index evidence is not proof that a page is unindexed.",
            "No indexing requests, product changes, purchases, or SEO publications were made.",
        ],
    }


def markdown(report):
    lines = [
        "# 6サイト・検索キーワードとインデックス診断（読み取り専用）", "",
        "- 状態：**" + report["status"] + "**",
        "- 基準日（太平洋時間）：" + report["as_of_pacific"],
        "- 直近28日：" + "〜".join(report["date_windows"]["last_28"]),
        "- 直近7日：" + "〜".join(report["date_windows"]["last_7"]), "",
    ]
    for site in report["sites"]:
        lines.extend(["## " + site["name"], "", "- 診断：" + site["status"]])
        if "reason" in site:
            lines.append("- 理由：" + site["reason"])
        for label, title in (("queries_28d", "28日間"), ("queries_7d", "7日間")):
            data = site["analytics"].get(label, {})
            status = data.get("status", "UNAVAILABLE")
            lines.extend(["", "### 検索キーワード（" + title + "、最大上位15件）", "", "状態：" + status])
            if status in ("UNAVAILABLE", "NO_ROWS"):
                lines.append("該当する検索語を確認できません。検索表示0回とは判定しません。")
                continue
            lines.extend(["", "| 検索キーワード | 表示 | クリック | 順位 |", "|---|---:|---:|---:|"])
            for row in data["rows"][:15]:
                key = html.escape(row["key"], quote=False).replace("|", "\\|")
                lines.append("| " + key + " | " + str(row["impressions"]) + " | " +
                             str(row["clicks"]) + " | " + str(row["position"] or "不明") + " |")
        daily = site["analytics"].get("daily_28d", {})
        lines.extend(["", "### 日別検索表示（直近28日）", "", "状態：" + daily.get("status", "UNAVAILABLE")])
        if daily.get("status") not in ("UNAVAILABLE", "NO_ROWS"):
            lines.extend(["", "| 日付（太平洋時間） | 表示 | クリック |", "|---|---:|---:|"])
            for row in daily.get("rows", []):
                lines.append("| " + row["key"] + " | " + str(row["impressions"]) + " | " + str(row["clicks"]) + " |")
        lines.extend(["", "### 主要URLのGoogle登録スナップショット", "",
                      "| 対象パス | 検査状態 | 判定 | カバレッジ | 最終クロール |",
                      "|---|---|---|---|---|"])
        for item in site["inspection"]:
            vals = [item["path"], item["status"], item.get("verdict") or "不明",
                    item.get("coverage_state") or "不明", item.get("last_crawl_time") or "不明"]
            lines.append("| " + " | ".join(html.escape(v, quote=False).replace("|", "\\|") for v in vals) + " |")
        lines.append("")
    lines.extend(["", "※検索キーワードとページの内訳は匿名化等で欠落します。集計値と足し合わせないでください。",
                  "※インデックス検査はGoogleが保存する状態であり、ライブページ検査ではありません。",
                  "※未取得と実際の0件を混同せず、API失敗時はUNAVAILABLEとします。",
                  "※サイトや商品データ、検索設定への書き込みはありません。", ""])
    return "\n".join(lines)


def main():
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        report = make_report(today, auth_problem="GOOGLE_CREDENTIALS_MISSING")
    else:
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=[base.SCOPE])
            session = AuthorizedSession(credentials)
            response = session.get(base.ROOT + "/sites", timeout=30)
            if response.status_code != 200:
                report = make_report(today, auth_problem="PROPERTY_LIST_HTTP_" + str(response.status_code))
            else:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("siteEntry", []), list):
                    raise ValueError("invalid permission list")
                permissions = {item["siteUrl"]: item["permissionLevel"]
                               for item in data.get("siteEntry", []) if isinstance(item, dict)
                               and isinstance(item.get("siteUrl"), str)
                               and isinstance(item.get("permissionLevel"), str)}
                report = make_report(today, session, permissions)
        except Exception:
            report = make_report(today, auth_problem="AUTH_OR_PROPERTY_LIST_FAILED")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "gsc-six-sites-diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "gsc-six-sites-diagnostics.md").write_text(markdown(report), encoding="utf-8")
    print("Six-site GSC discovery diagnostics: " + report["status"])
    if report["status"] != "READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
