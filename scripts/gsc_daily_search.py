#!/usr/bin/env python3
"""Read-only Search Console daily inspection for the daily-cost site's core pages.

Absence of a Search Console row is NOT silently converted to zero. The daily
series separates search exposure from changes in average ranking, and never
automatically proposes SEO changes or triggers publication.
"""
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlsplit

SITE = "https://stusaurus.github.io/daily-cost-jp/"
CORE = ("/categories/tissue/", "/categories/laundry/", "/categories/toilet-paper/")
SOURCE = "Search Console Search Analytics API"
MAX_ROWS = 25000


def path_from_url(url):
    """Only accept exact HTTPS URL-prefix property; never another GitHub site."""
    if not isinstance(url, str):
        return None
    try:
        value, root = urlsplit(url), urlsplit(SITE)
        if (value.scheme != "https" or value.netloc != root.netloc or
                value.username or value.password or not value.path.startswith(root.path)):
            return None
        suffix = value.path[len(root.path):]
        if any(x in suffix for x in ("\x00", "\r", "\n")):
            return None
        return "/" + suffix
    except (TypeError, ValueError):
        return None


def parse_count_metrics(row):
    if not isinstance(row, dict):
        raise ValueError("Missing daily result record")
    impressions, clicks = row.get("impressions"), row.get("clicks")
    if (type(impressions) not in (int, float) or
            type(clicks) not in (int, float) or
            not float(impressions).is_integer() or not float(clicks).is_integer() or
            impressions < 0 or clicks < 0):
        raise ValueError("Invalid daily impression or search-click metrics")
    return {"impressions": int(impressions), "clicks": int(clicks)}


def normalize_daily(site_response, page_response, dates):
    """Preserve only core-category per-day rows and the site's daily aggregates."""
    if (not isinstance(dates, list) or len(dates) != 2 or
            not all(isinstance(s, str) for s in dates)):
        raise ValueError("Invalid daily date range")
    try:
        first, last = (dt.date.fromisoformat(value) for value in dates)
    except ValueError as error:
        raise ValueError("Unparseable daily dates") from error
    if first > last or (last - first).days > 56:
        raise ValueError("Invalid date order or unusually broad window")
    if not isinstance(site_response, dict) or not isinstance(page_response, dict):
        raise ValueError("Daily API responses must be JSON objects")
    site_rows = site_response.get("rows", [])
    page_rows = page_response.get("rows", [])
    if not isinstance(site_rows, list) or not isinstance(page_rows, list):
        raise ValueError("Malformed Search Console daily rows")

    def valid_date(key):
        if not isinstance(key, str):
            raise ValueError("Invalid date key type")
        try:
            date = dt.date.fromisoformat(key)
        except ValueError as error:
            raise ValueError("Invalid date key") from error
        if not first <= date <= last:
            raise ValueError("Daily row outside requested range")
        return date.isoformat()

    site = {}
    for row in site_rows:
        keys = row.get("keys", []) if isinstance(row, dict) else None
        if not isinstance(keys, list) or len(keys) != 1:
            raise ValueError("Expected Search Console [date] row")
        date = valid_date(keys[0])
        if date in site:
            raise ValueError("Duplicate site daily row")
        site[date] = parse_count_metrics(row)

    pages = {path: {} for path in CORE}
    discarded = 0
    for row in page_rows:
        keys = row.get("keys", []) if isinstance(row, dict) else None
        if not isinstance(keys, list) or len(keys) != 2:
            raise ValueError("Expected Search Console [date,page] row")
        date = valid_date(keys[0])
        pathname = path_from_url(keys[1])
        if pathname not in CORE:
            discarded += 1
            continue
        if date in pages[pathname]:
            raise ValueError("Duplicate category/date row")
        pages[pathname][date] = parse_count_metrics(row)

    return {
        "status": ("TOP_ROW_LIMIT_POSSIBLE" if max(len(site_rows), len(page_rows)) >= MAX_ROWS
                   else "NO_OBSERVED_DAYS" if not site else "OBSERVED_DAILY_ROWS"),
        "window": [first.isoformat(), last.isoformat()],
        "site": site,
        "core_pages": pages,
        "site_dates_observed": len(site),
        "site_row_count": len(site_rows),
        "page_row_count": len(page_rows),
        "other_pages_discarded": discarded,
        "note": "Missing date/page rows are unknown, not proof of zero search impressions.",
    }


def observed_change(current, previous):
    """Comparative descriptive count, never a proof of a ranking or SEO cause."""
    if not isinstance(current, dict) or not isinstance(previous, dict):
        return {"status": "UNKNOWN", "previous": None, "current": None, "difference": None}
    a, b = previous.get("impressions"), current.get("impressions")
    if type(a) is not int or type(b) is not int or a < 0 or b < 0:
        return {"status": "UNKNOWN", "previous": None, "current": None, "difference": None}
    delta = b - a
    status = ("LOW_SAMPLE" if a + b < 50 else
              "OBSERVED_DECLINE" if a >= 30 and b <= a * 0.5 else
              "OBSERVED_INCREASE" if b >= 30 and b >= a * 1.5 else
              "OBSERVE")
    return {"status": status, "previous": a, "current": b, "difference": delta,
            "percent_change": round(100 * delta / a, 1) if a else None}


def weekly_comparison(report):
    if not isinstance(report, dict) or report.get("source") != SOURCE or report.get("site_property") != SITE:
        raise ValueError("Wrong source or Search Console property")
    if report.get("status") not in ("PROVISIONAL", "TOP_ROW_COVERAGE_UNCERTAIN"):
        return {"status": "GSC_UNAVAILABLE", "message": "Search Consoleの取得失敗。0回とは扱わない",
                "site": observed_change(None, None), "pages": []}

    site_agg = report.get("site_aggregates", {})
    current = (site_agg.get("last_7") or {}).get("metrics")
    previous = (site_agg.get("prior_7") or {}).get("metrics")
    site = observed_change(current, previous)
    comparison = []
    for path in CORE:
        row = next((p for p in report.get("pages", []) if p.get("path") == path), {})
        item = observed_change(row.get("last_7"), row.get("prior_7"))
        comparison.append({"path": path, **item})
    comparison.sort(key=lambda p: (p["difference"] is None,
                                   p["difference"] if p["difference"] is not None else 0,
                                   p["path"]))

    series = report.get("daily_series") or {"status": "NOT_COLLECTED"}
    if not isinstance(series, dict):
        raise ValueError("Malformed daily series")
    status = series.get("status", "NOT_COLLECTED")
    expected_28 = (site_agg.get("last_28") or {}).get("metrics") or {}
    # Grouped-by-date API data may differ from non-dimensioned totals.
    # If there is any disagreement, suppress claims of complete daily coverage.
    if status == "OBSERVED_DAILY_ROWS":
        grouped_sum = sum(x["impressions"] for x in series.get("site", {}).values())
        if (type(expected_28.get("impressions")) is not int or
                grouped_sum != expected_28["impressions"]):
            status = "AGGREGATION_MISMATCH"
    return {
        "source": "Search Console daily exposure diagnostics",
        "site_property": SITE,
        "status": "OBSERVED_WITH_CAUTION",
        "site": site,
        "pages": comparison,
        "largest_observed_decrease": next(
            (x["path"] for x in comparison if x["difference"] is not None and x["difference"] < 0),
            None),
        "daily_status": status,
        "daily": series if status == "OBSERVED_DAILY_ROWS" else None,
        "weekly_windows": {key: report.get("windows", {}).get(key)
                           for key in ("last_7", "prior_7")},
        "no_automatic_seo_rewrite": True,
        "cautions": [
            "Changes are descriptive counts, not a causal diagnosis or proof of ranking loss.",
            "Low impression volumes and missing daily rows can make comparisons unstable.",
            "Missing page rows are not proven zero; date-level APIs can be thresholded.",
            "Average position with one or two impressions should not be overinterpreted.",
            "No Search Console writes, search title changes, product edits, or auto-deploy.",
        ],
    }


def markdown(report):
    lines = ["## Google検索表示の減少｜日別・ページ別調査", "",
             "- 判定：" + report["status"],
             "- **数値上の減少と、順位下落・検索障害は同義ではありません。**",
             "- データが少ない期間は原因を断定しません。", ""]
    if report["status"] == "GSC_UNAVAILABLE":
        return "\n".join(lines + ["Search Console未取得。検索表示は0回と扱いません。"]) + "\n"
    lines += [
        "| 対象 | 前7日表示 | 直近7日表示 | 増減 | 判定 |",
        "|---|---:|---:|---:|---|",
    ]
    items = [{"path": "サイト全体", **report["site"]}] + report["pages"]
    def label(v):
        return str(v) if v is not None else "不明"
    for item in items:
        lines.append("| " + item["path"] + " | " + label(item["previous"]) +
                     " | " + label(item["current"]) + " | " +
                     label(item["difference"]) + " | " + item["status"] + " |")
    lines.extend(["", "- 日別集計の状態：" + report["daily_status"]])
    if report["daily"] is not None:
        series = report["daily"]
        first = dt.date.fromisoformat(series["window"][0])
        last = dt.date.fromisoformat(series["window"][1])
        lines.extend([
            "- この日別データでは行がない日を0回と埋めていません。",
            "",
            "| 日付 | サイト全体の表示 | ティッシュ | 洗濯洗剤 | トイレットペーパー |",
            "|---|---:|---:|---:|---:|",
        ])
        day = first
        while day <= last:
            key = day.isoformat()
            site = series["site"].get(key)
            row = [key, label(site["impressions"] if site else None)]
            for path in CORE:
                item = series["core_pages"][path].get(key)
                row.append(label(item["impressions"] if item else None))
            lines.append("| " + " | ".join(row) + " |")
            day += dt.timedelta(days=1)
    else:
        lines.append("- 日別の行は取得不足・集計不整合のため参考表示を保留。週別集計はそのまま利用可能。")
    lines += ["", "※順位の下落、検索需要、インデックス、競合など原因候補はこの数字だけでは確定できません。",
              "※タイトル・説明文・サイト内容を自動で変更しません。", ""]
    return "\n".join(lines)


def main():
    folder = Path("audit-results")
    source = folder / "gsc-search-pilot.json"
    if not source.exists():
        raise SystemExit("GSC pilot output missing; do not replace missing data with zeros")
    report = weekly_comparison(json.loads(source.read_text(encoding="utf-8")))
    (folder / "gsc-daily-search-change.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "gsc-daily-search-change.md").write_text(markdown(report), encoding="utf-8")
    print("GSC daily changes: " + report["status"] + "; daily=" + report.get("daily_status", "UNKNOWN"))


if __name__ == "__main__":
    main()
