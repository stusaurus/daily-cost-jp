"""Six-site GSC evidence board using EXISTING read-only final-data reports.

No Google calls, SEO edits, automatic rankings, product publication or second
monitor. Only validated daily rows are summed for the site summary; page/query
dimensions must NEVER be added to daily results or substituted as totals.
"""
import datetime as dt
import html
import re

from scripts.gsc_six_sites import SITES

VALID_STATES = ("OBSERVED_ROWS", "TOP_ROWS_LIMIT_POSSIBLE")
GSC_SOURCE = "Google Search Console Search Analytics + URL Inspection APIs (read-only)"
# Never treat search operators, URLs, contact details, or long digit strings as
# commercial search demand or quote them in a public GitHub workflow summary.
SITE_OPERATOR = re.compile(r"(?<![a-zA-Z0-9])-?site\s*:", re.IGNORECASE)
PRIVATE_QUERY = re.compile(r"@|https?://|(?:\d[\s-]?){7,}", re.IGNORECASE)
SAFE_PATH = re.compile(r"^/(?:[a-zA-Z0-9_./%-]+)?$")


def _checked_daily(part, period):
    if not isinstance(part, dict) or part.get("status") not in VALID_STATES:
        return None
    rows = part.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    try:
        start, end = [dt.date.fromisoformat(x) for x in period]
        if start > end:
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    seen = set()
    impressions = clicks = 0
    for row in rows:
        if not isinstance(row, dict):
            return None
        try:
            day = dt.date.fromisoformat(row["key"])
        except (TypeError, ValueError, KeyError, AttributeError):
            return None
        i, c = row.get("impressions"), row.get("clicks")
        if (day < start or day > end or day in seen
                or type(i) is not int or type(c) is not int
                or i < 0 or c < 0 or c > i):
            return None
        seen.add(day)
        impressions += i
        clicks += c
    return {"impressions": impressions, "clicks": clicks, "reported_days": len(seen)}


def _natural_queries(part):
    if not isinstance(part, dict):
        return "UNKNOWN", None
    status = part.get("status")
    if status not in VALID_STATES + ("NO_ROWS",):
        return "UNKNOWN", None
    if status == "NO_ROWS":
        return "NO_ROWS", None
    rows = part.get("rows")
    if not isinstance(rows, list):
        return "UNKNOWN", None
    count = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            return "UNKNOWN", None
        key = row["key"]
        if not key or len(key) > 500:
            return "UNKNOWN", None
        # site: queries are verification searches, never evidence of a
        # commercial natural-language search intent.
        if not SITE_OPERATOR.search(key):
            count += 1
    return ("NATURAL_ROWS" if count else "ONLY_OPERATOR_ROWS"), count


def _query_page_evidence(part, property_url):
    """Up to 3 independently returned query × landing rows, never a total."""
    if not isinstance(part, dict):
        return None
    status = part.get("status")
    if status == "NO_ROWS":
        return []
    if status not in VALID_STATES or not isinstance(part.get("rows"), list):
        return None
    candidates = []
    seen = set()
    for row in part["rows"][:1000]:
        if not isinstance(row, dict):
            return None
        query, path, page = row.get("key"), row.get("path"), row.get("page")
        if (not isinstance(query, str) or not query.strip() or len(query) > 120
                or SITE_OPERATOR.search(query) or PRIVATE_QUERY.search(query)):
            continue
        if (not isinstance(path, str) or not SAFE_PATH.fullmatch(path)
                or path.startswith("//") or ".." in path.split("/")
                or page != property_url + path.lstrip("/")):
            continue
        impressions, clicks, position = (
            row.get("impressions"), row.get("clicks"), row.get("position"))
        if (type(impressions) is not int or type(clicks) is not int
                or impressions <= 0 or not 0 <= clicks <= impressions
                or not isinstance(position, (float, int))
                or isinstance(position, bool) or not 1 <= position <= 1000):
            continue
        identity = (query, path)
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append({"query": query.strip(), "path": path,
                           "impressions": impressions, "clicks": clicks,
                           "position": round(position, 2)})
    # The returned query-page rows are a non-exhaustive Search Analytics
    # selection. We display only those rows, not inferred popular queries.
    candidates.sort(key=lambda x: (-x["impressions"], -x["clicks"], x["query"]))
    return candidates[:3]

def _index_snapshot(site):
    inspected = site.get("inspection", [])
    if not isinstance(inspected, list):
        return {"checked": 0, "indexed": 0, "unknown_to_google": 0,
                "uncertain": 0, "http_and_canonical_ok": 0}
    counted = set()
    indexed = unknown = uncertain = public_ok = 0
    unknown_paths = []
    root = site["property"]
    for row in inspected:
        if not isinstance(row, dict):
            uncertain += 1
            continue
        path = row.get("path")
        if (not isinstance(path, str) or not path.startswith("/")
                or path.startswith("//") or ".." in path.split("/") or path in counted):
            uncertain += 1
            continue
        counted.add(path)
        if row.get("status") != "OBSERVED_SNAPSHOT":
            uncertain += 1
            continue
        if row.get("verdict") == "PASS" and row.get("coverage_state") == "Submitted and indexed":
            indexed += 1
        elif row.get("coverage_state") == "URL is unknown to Google":
            unknown += 1
            unknown_paths.append(path)
        else:
            uncertain += 1
        url = root + path.lstrip("/")
        published = row.get("public") or {}
        if (isinstance(published, dict)
                and published.get("status") == "PUBLIC_HTML"
                and published.get("http_status") == 200
                and published.get("canonical") == [url]
                and not any("noindex" in str(x).lower() for x in published.get("robots") or [])
                and not "noindex" in str(published.get("x_robots_tag") or "").lower()):
            public_ok += 1
    return {"checked": len(counted), "indexed": indexed,
            "unknown_to_google": unknown, "uncertain": uncertain,
            "http_and_canonical_ok": public_ok,
            "unknown_paths": unknown_paths[:8]}


def scorecard(report):
    """Conservative six-site investigation board. No new SEO recommendation."""
    sites = report.get("sites") if isinstance(report, dict) else None
    windows = report.get("date_windows") if isinstance(report, dict) else None
    if not isinstance(sites, list) or not isinstance(windows, dict):
        return {"status": "UNAVAILABLE", "sites": [], "period": None}
    period = windows.get("last_28")
    if not (isinstance(period, list) and len(period) == 2):
        period = None
    rows = []
    for name, property_url in SITES:
        found = [s for s in sites if isinstance(s, dict) and s.get("name") == name]
        site = found[0] if len(found) == 1 else None
        if not site or site.get("property") != property_url:
            rows.append({"name": name, "status": "UNAVAILABLE_OR_MISMATCH",
                         "daily": None, "query_status": "UNKNOWN",
                         "natural_query_rows": None, "index": None,
                         "query_page_samples": None,
                         "priority": "DATA_CHECK"})
            continue
        analytics = site.get("analytics")
        analytics = analytics if isinstance(analytics, dict) else {}
        daily = _checked_daily(analytics.get("daily_28d"), period)
        query_status, count = _natural_queries(analytics.get("queries_28d"))
        idx = _index_snapshot(site)
        samples = _query_page_evidence(analytics.get("query_pages_28d"), property_url)
        if daily is None:
            focus = "DATA_CHECK"
        elif daily["impressions"] >= 20 and count:
            focus = "QUERY_AND_LANDING_REVIEW"
        elif query_status == "NATURAL_ROWS":
            focus = "QUERY_EVIDENCE_SMALL"
        else:
            focus = "EXPOSURE_EVIDENCE_SMALL_OR_PRIVATE"
        rows.append({"name": name, "status": site.get("status", "UNKNOWN"),
                     "daily": daily, "query_status": query_status,
                     "natural_query_rows": count, "index": idx,
                     "query_page_samples": samples,
                     "priority": focus})
    rows.sort(key=lambda row: (
        row["daily"] is None,
        -(row["daily"] or {}).get("impressions", 0),
        next(i for i, (name, _) in enumerate(SITES) if name == row["name"])))
    return {"status": "READY" if all(r["daily"] is not None for r in rows) else "PARTIAL",
            "period": period, "sites": rows,
            "method": "sum of API-returned DAILY rows only; never sum page or query rows"}


def scorecard_markdown(report):
    board = scorecard(report)
    lines = ["## 6サイト横断・検索流入の根拠一覧（読み取り専用）", "",
             "最新の確定GSC日別返却行だけを集計し、ページ別・検索語別の行は加算しません。",
             "検索語の未返却・匿名化とAPI未取得をゼロ扱いしません。", "",
             "| サイト | 日別返却28日表示 | クリック | 通常検索語の返却 | Google登録スナップショット | 調査区分 |",
             "|---|---:|---:|---|---|---|"]
    labels = {
        "DATA_CHECK": "API／期間を確認",
        "QUERY_AND_LANDING_REVIEW": "検索語と表示ページの意図を照合",
        "QUERY_EVIDENCE_SMALL": "少数の通常検索語を継続観測",
        "EXPOSURE_EVIDENCE_SMALL_OR_PRIVATE": "小標本・検索語非開示を区別",
    }
    for row in board["sites"]:
        daily = row["daily"]
        idx = row["index"]
        query = row["query_status"]
        qlabel = ("通常語" + str(row["natural_query_rows"]) + "行（非網羅）"
                  if query == "NATURAL_ROWS" else
                  "site:等のみ" if query == "ONLY_OPERATOR_ROWS" else
                  "検索語なし（不明）" if query == "NO_ROWS" else "不明")
        found = (str(idx["indexed"]) + "件登録／Google未認識" +
                 str(idx["unknown_to_google"]) + "件（検査対象のみ）") if idx else "未取得"
        values = [row["name"], str(daily["impressions"]) if daily else "不明",
                  str(daily["clicks"]) if daily else "不明",
                  qlabel, found, labels[row["priority"]]]
        lines.append("| " + " | ".join(
            html.escape(v, quote=False).replace("|", "\\|") for v in values) + " |")
    lines.extend(["", "### 実際に返された検索語と表示ページ（各サイト最大3件）", "",
                  "Search Analyticsの返却行の一部です。\`site:\`等の確認検索、個人情報らしい語句は除外し、全検索需要に換算しません。", "",
                  "| サイト | 検索語 | 表示ページ | 表示 | クリック | 平均順位 |",
                  "|---|---|---|---:|---:|---:|"])
    for row in board["sites"]:
        samples = row.get("query_page_samples")
        if samples is None or len(samples) == 0:
            state = "取得不明" if samples is None else "通常語×ページの返却行なし"
            lines.append("| " + html.escape(row["name"]) + " | " + state + " | — | — | — | — |")
            continue
        for sample in samples:
            parts = [row["name"], sample["query"], sample["path"],
                     str(sample["impressions"]), str(sample["clicks"]),
                     str(sample["position"])]
            lines.append("| " + " | ".join(
                html.escape(value, quote=False).replace("|", "\\\\|")
                for value in parts) + " |")
    lines.extend(["", "### Google保存済みスナップショットで未認識のURL", "",
                  "公開可否・今後の登録可否を意味するものではなく、次回公式診断の照合対象です。"])
    for row in board["sites"]:
        paths = row.get("index", {}).get("unknown_paths", []) if row.get("index") else []
        if paths:
            escaped = "、".join(html.escape(p, quote=False).replace("|", "\\\\|") for p in paths)
            lines.append("- " + html.escape(row["name"]) + "：" + escaped)
    lines.append("")
    lines.extend(["", "※Google未認識は保存済みURL Inspectionの状態で、公開失敗やインデックス不可の証明ではありません。",
                  "※ページ別表示回数の合計は、日別の合計と一致するとは限りません。サイト全体に換算しません。",
                  "※運営用の調査区分であり、CTR改善・検索順位上昇・購入成果を保証せず、SEOを自動編集しません。", ""])
    return "\n".join(lines)
