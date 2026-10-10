#!/usr/bin/env python3
"""Read-only join of GSC search observations and GA4 site/affiliate-click observations.

Both products retain distinct date windows and attribution boundaries. The
output is a ranked queue of *investigation hypotheses*, never conversion
rates, paid sales, or permission to change a production website.
"""
import json
import re
from pathlib import Path

GSC_SITE = "https://stusaurus.github.io/daily-cost-jp/"
CORE = ("/categories/laundry/", "/categories/tissue/", "/categories/toilet-paper/")
VALID_PATH = re.compile(r"^/(?:[a-z0-9_/-]*)$", re.IGNORECASE)
SOURCE_GSC = "Search Console Search Analytics API"
SOURCE_GA4 = "GA4 Data API"
SOURCE_JOINED = "GA4 + Search Console read-only page triage"


def safe_path(path):
    return (isinstance(path, str) and len(path) <= 160 and
            VALID_PATH.fullmatch(path) is not None and
            not path.startswith("//") and ".." not in path.split("/"))


def valid_period(pair):
    return (isinstance(pair, list) and len(pair) == 2 and
            all(isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
                for v in pair) and pair[0] <= pair[1])


def parse_metric(entry):
    """An absent GSC row is unknown; never silently convert it to zero."""
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ValueError("Malformed GSC page metrics")
    clicks, impressions = entry.get("clicks"), entry.get("impressions")
    ctr, position = entry.get("ctr"), entry.get("position")
    if (type(clicks) is not int or type(impressions) is not int or
            type(ctr) not in (int, float) or type(position) not in (int, float) or
            clicks < 0 or impressions < 0 or not 0 <= ctr <= 1 or position < 1):
        raise ValueError("Invalid GSC page metrics")
    return {"clicks": clicks, "impressions": impressions, "ctr": round(ctr, 5),
            "position": round(position, 2)}


def parse_affiliate(row):
    """Return observations with operator-test attribution but without purchase claims."""
    if row is None:
        return None
    if not isinstance(row, dict):
        raise ValueError("Malformed GA4 page diagnostics")
    stats = row.get("periods", {}).get("last_28")
    if not isinstance(stats, dict):
        raise ValueError("Missing GA4 last_28")
    clicks = stats.get("clicks")
    views = stats.get("pageviews")
    if (type(views) is not int or views < 0 or not isinstance(clicks, dict)):
        raise ValueError("Malformed GA4 page counts")
    keys = ("production_operator", "production_non_operator", "production_unknown")
    if any(type(clicks.get(key)) is not int or clicks[key] < 0 for key in keys):
        raise ValueError("Malformed GA4 click buckets")
    return {"pageviews": views, "operator_tests": clicks["production_operator"],
            "provisional_non_operator_clicks": clicks["production_non_operator"],
            "unknown_operator_clicks": clicks["production_unknown"]}


def priority(gsc_28, gsc_7, gsc_prior7, ga4_28, known_operator):
    """The output tells where to investigate, never why a person did not purchase."""
    if gsc_28 is None:
        return (8, "GSC_PAGE_NOT_REPORTED",
                "検索ページ別データが未取得。表示0回や未登録とは断定できない")
    if ga4_28 and ga4_28["unknown_operator_clicks"]:
        return (1, "VERIFY_CLICK_ATTRIBUTION",
                "GA4の運営者テスト区分が不明。楽天クリックの評価を保留")
    if gsc_28["impressions"] >= 50 and gsc_28["ctr"] < 0.02 and 4 <= gsc_28["position"] <= 30:
        return (2, "CHECK_SEARCH_RESULT_APPEAL",
                "検索表示に対しクリックが少ない。検索意図・タイトルを調査する仮説")
    if (gsc_7 and gsc_prior7 and gsc_prior7["impressions"] >= 30 and
            gsc_7["impressions"] >= 10 and
            10 * gsc_7["impressions"] <= 6 * gsc_prior7["impressions"]):
        return (3, "INVESTIGATE_SEARCH_EXPOSURE_CHANGE",
                "前7日間より検索表示が減った可能性。検索クエリと季節性を確認")
    if (known_operator and gsc_28["clicks"] >= 5 and ga4_28 and
            ga4_28["pageviews"] >= 30 and
            ga4_28["provisional_non_operator_clicks"] == 0):
        return (3, "INSPECT_LANDING_TO_AFFILIATE_JOURNEY",
                "検索流入とページ表示はあるが、同時期にテスト外楽天クリックを観測していない。導線の調査候補（同一ユーザーの行動は不明）")
    if gsc_28["impressions"] < 20:
        return (5, "RESEARCH_SEARCH_DEMAND_OR_INDEXING",
                "検索での表示が少ない。需要・ページ内容・インデックス状態を調査")
    if not known_operator:
        return (6, "VERIFY_GA4_OPERATOR_DIMENSION",
                "検索データは取得済み。GA4側の運営者テスト区分は未確認")
    return (7, "OBSERVE", "データのみでは原因を特定できないため継続観察")


def combine(ga4, gsc):
    if not isinstance(ga4, dict) or ga4.get("source") != SOURCE_GA4:
        raise ValueError("GA4 diagnostics source mismatch")
    if not valid_period(ga4.get("period_last_28")):
        raise ValueError("Invalid GA4 date window")
    status = "GSC_NOT_CONNECTED"
    reason = "NO_GSC_REPORT"
    gsc_ok = False
    if gsc is not None:
        if not isinstance(gsc, dict) or gsc.get("source") != SOURCE_GSC:
            raise ValueError("GSC source mismatch")
        if gsc.get("site_property") != GSC_SITE:
            raise ValueError("GSC URL-prefix property mismatch")
        status = gsc.get("status", "GSC_UNKNOWN")
        reason = gsc.get("reason", "")
        gsc_ok = status in ("PROVISIONAL", "TOP_ROW_COVERAGE_UNCERTAIN")
        if gsc_ok:
            windows = gsc.get("windows", {})
            if (not isinstance(windows, dict) or
                    any(not valid_period(windows.get(name)) for name in
                        ("last_28", "last_7", "prior_7"))):
                raise ValueError("Invalid GSC date windows")
            if not isinstance(gsc.get("pages"), list):
                raise ValueError("Malformed GSC pages")
    ga4_pages = {}
    for row in ga4.get("pages", []):
        page = row.get("page") if isinstance(row, dict) else None
        if safe_path(page):
            ga4_pages[page] = parse_affiliate(row)
    # Published Search Console rows are threshold-filtered to protect rare
    # queries. Zero published rows NEVER implies that no real queries exist.
    safe_queries = (gsc.get("top_queries", []) if gsc_ok else [])
    if not isinstance(safe_queries, list):
        raise ValueError("Malformed published GSC query evidence")
    query_evidence = ("GSC_UNAVAILABLE" if not gsc_ok else
                      "NO_REPORTABLE_QUERY_ROWS" if not safe_queries else
                      "SOME_THRESHOLD_FILTERED_QUERY_ROWS")
    gsc_pages = {}
    if gsc_ok:
        for row in gsc["pages"]:
            page = row.get("path") if isinstance(row, dict) else None
            if safe_path(page):
                gsc_pages[page] = row
    selected = set(CORE) | set(ga4_pages) | set(gsc_pages)
    operator_known = ga4.get("operator_dimension_registered") is True
    entries = []
    for page in selected:
        g = gsc_pages.get(page)
        recent = parse_metric(g.get("last_28")) if g else None
        g7 = parse_metric(g.get("last_7")) if g else None
        prior7 = parse_metric(g.get("prior_7")) if g else None
        a = ga4_pages.get(page)
        if not gsc_ok:
            rank, code, hypothesis = (9, "GSC_CONNECTION_REQUIRED",
                                      "Search Consoleの検索実績を取得できないため統合判断を保留")
        else:
            rank, code, hypothesis = priority(recent, g7, prior7, a, operator_known)
        entries.append({
            "path": page, "rank": rank, "code": code, "hypothesis": hypothesis,
            "gsc_last_28": recent, "gsc_last_7": g7, "ga4_last_28": a,
            "confidence": "INVESTIGATION_ONLY" if gsc_ok else "NO_JOINED_DECISION",
        })
    entries.sort(key=lambda item: (item["rank"], item["path"] not in CORE,
                                   -(item["gsc_last_28"] or {}).get("impressions", 0),
                                   item["path"]))
    return {
        "source": SOURCE_JOINED,
        "site": GSC_SITE,
        "status": "JOINT_PROVISIONAL" if gsc_ok else "GSC_UNAVAILABLE",
        "gsc_source_status": status,
        "gsc_unavailable_reason": reason if not gsc_ok else None,
        "gsc_public_query_rows": len(safe_queries),
        "gsc_query_evidence_status": query_evidence,
        "seo_copy_change_authorized": False,
        "ga4_source_status": ga4.get("status", "UNKNOWN"),
        "ga4_operator_dimension_registered": operator_known,
        "gsc_period_last_28": gsc.get("windows", {}).get("last_28") if gsc_ok else None,
        "ga4_period_last_28": ga4["period_last_28"],
        "not_same_population_or_period": True,
        "affiliate_clicks_are_not_sales": True,
        "conversion_rate_calculated": False,
        "page_diagnostics": entries,
        "top_investigations": entries[:8],
        "quality_notes": [
            "Search Console search clicks are NOT Rakuten affiliate clicks.",
            "GA4 total pageviews include channels beyond Google Search; events cannot be attributed to GSC searchers.",
            "The GSC and GA4 28-day windows END ON DIFFERENT DATES. No cross-source conversion rate is valid.",
            "Missing GSC page rows cannot be interpreted as zero impressions.",
            "Unknown GA4 operator-test flags exclude reliable non-operator click conclusions.",
            "Investigation only: NO automatic edits, GitHub write access or publishing.",
        ],
    }


def markdown(result):
    period = lambda value: "未取得" if value is None else " ～ ".join(value)
    lines = [
        "## Google検索 × 楽天導線｜3日ごとの統合調査",
        "",
        "- 統合状態：**" + result["status"] + "**",
        "- Search Console：**" + result["gsc_source_status"] + "**",
        "- 検索データ期間：" + period(result["gsc_period_last_28"]),
        "- GA4ページ表示・楽天クリック期間：" + period(result["ga4_period_last_28"]),
        "- **集計期間とユーザー母集団が異なるため、検索→購入の成約率は算出しません。**",
        "- **楽天クリックは売上・購入の証拠ではありません。**",
        "- 検索クエリの根拠：" + result["gsc_query_evidence_status"] +
          "（公開可能な集計行：" + str(result["gsc_public_query_rows"]) + "件）",
        "- **クエリ不足や平均CTRだけでSEOタイトル・説明文を自動変更しません。**",
        "",
        "| ページ | 検索表示（28日） | 検索クリック | 平均掲載順位 | GA4表示（28日） | テスト外楽天クリック（暫定） | 優先調査 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in result["top_investigations"]:
        g, a = item["gsc_last_28"], item["ga4_last_28"]
        f = lambda value: "不明" if value is None else str(value)
        operator_valid = (result["ga4_operator_dimension_registered"] and a is not None and
                          a["unknown_operator_clicks"] == 0 and
                          item["confidence"] == "INVESTIGATION_ONLY")
        c = f(a["provisional_non_operator_clicks"]) if operator_valid else "不明"
        lines.append("| " + item["path"].replace("|", "%7C") + " | " +
                     f(g["impressions"] if g else None) + " | " +
                     f(g["clicks"] if g else None) + " | " +
                     f(g["position"] if g else None) + " | " +
                     f(a["pageviews"] if a else None) + " | " + c + " | " +
                     item["hypothesis"].replace("|", "、") + " |")
    if result["status"] != "JOINT_PROVISIONAL":
        lines += ["", "**検索データがないため、検索流入の原因を断定せず保留します。**"]
    lines += ["", "※検索順位は表示に基づく平均値。個々の検索語の固定順位ではありません。",
              "※購入ボタン・SEO・商品情報・楽天リンク・計測設定の自動変更は行っていません。", ""]
    return "\n".join(lines)


def run():
    folder = Path("audit-results")
    ga4 = json.loads((folder / "ga4-page-diagnostics.json").read_text(encoding="utf-8"))
    gsc_path = folder / "gsc-search-pilot.json"
    # Absence must not turn the existing GA4 job into a fake zero.
    if gsc_path.exists():
        gsc = json.loads(gsc_path.read_text(encoding="utf-8"))
    else:
        gsc = None
    report = combine(ga4, gsc)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "search-affiliate-joint.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "search-affiliate-joint.md").write_text(
        markdown(report), encoding="utf-8")
    print("Joint GSC + GA4 status=" + report["status"] +
          "; pages=" + str(len(report["page_diagnostics"])))


if __name__ == "__main__":
    run()
