#!/usr/bin/env python3
"""Read-only evidence-led operations queue for daily-cost-jp.

Combines GA4/GSC, browser verification, production health and already-published
product-quality status. Produces a bounded action queue, NEVER code changes,
sales claims, rankings changes, automatic merges or affiliate actions.
"""
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SITE = "https://stusaurus.github.io/daily-cost-jp/"
QUALITY_URL = SITE + "quality-status.json"
JOINT_SOURCE = "GA4 + Search Console read-only page triage"
PATH_PATTERN = re.compile(r"^/(?:[a-z0-9_-]+/)*$", re.IGNORECASE)
LEVELS = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
MAX_FINDINGS = 20
MAX_QUALITY_BYTES = 200_000


def good_path(path):
    return (isinstance(path, str) and len(path) <= 140 and
            PATH_PATTERN.fullmatch(path) is not None and
            ".." not in path and not path.startswith("//"))


def short(text, limit=170):
    if not isinstance(text, str):
        return "未取得"
    return re.sub(r"[\r\n\t|<>]", " ", text).strip()[:limit]


def read_optional(path):
    file = Path(path)
    if not file.is_file():
        return None
    if file.stat().st_size > 1_000_000:
        raise ValueError("Input report exceeds size limit")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Report must be a JSON object")
    return data


def fetch_public_quality(url=QUALITY_URL):
    """Best effort; same-site public JSON only. Failure is UNKNOWN, not healthy."""
    parsed = urlsplit(url)
    if url != QUALITY_URL or parsed.scheme != "https" or parsed.netloc != "stusaurus.github.io":
        raise ValueError("Quality source must be exact published daily-cost URL")
    try:
        with urlopen(Request(url, headers={"User-Agent": "DailyCost-OperationsTriage/1.0"}),
                     timeout=12) as response:
            if response.status != 200 or urlsplit(response.geturl()).netloc != parsed.netloc:
                return {"status": "UNAVAILABLE"}
            blob = response.read(MAX_QUALITY_BYTES + 1)
            if len(blob) > MAX_QUALITY_BYTES:
                return {"status": "INVALID_OR_OVERSIZE"}
        obj = json.loads(blob)
        if not isinstance(obj, dict):
            return {"status": "INVALID"}
        if not isinstance(obj.get("errors"), list) or not isinstance(obj.get("warnings"), list):
            return {"status": "INVALID"}
        updated = obj.get("updated_at")
        try:
            instant = dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("Missing timezone")
            age_hours = max(0, (dt.datetime.now(dt.timezone.utc) -
                                instant.astimezone(dt.timezone.utc)).total_seconds() / 3600)
        except (ValueError, TypeError, AttributeError):
            return {"status": "UNKNOWN_FRESHNESS"}
        return {"status": "FRESH" if age_hours <= 72 else "STALE",
                "age_hours": round(age_hours, 1),
                "errors": obj["errors"][:30], "warnings": obj["warnings"][:30],
                "counts": obj.get("counts", {})}
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"status": "UNAVAILABLE"}


def new_finding(level, code, path, message, next_action, *, evidence=""):
    if level not in LEVELS or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,70}", code):
        raise ValueError("Unsafe finding code or severity")
    scope = path if good_path(path) else "/"
    return {
        "id": code + ":" + scope,
        "severity": level,
        "code": code,
        "path": scope,
        "message": short(message),
        "evidence": short(evidence),
        "next_action": short(next_action),
        "auto_fix_allowed": False,
    }


def evaluate(joined, browser, health, quality, ga4=None):
    findings = []
    def add(*args, **kwargs):
        findings.append(new_finding(*args, **kwargs))

    if not isinstance(health, dict) or health.get("result") not in ("pass", "fail"):
        add("P2", "HEALTH_REPORT_MISSING", "/", "公開サイトの稼働監査が未取得",
            "サイト監査を再実行し、正常と断定しない")
    elif health["result"] == "fail":
        for check in health.get("checks", [])[:10]:
            if isinstance(check, dict) and check.get("status") == "fail":
                add("P0", "LIVE_HTTP_FAILURE", check.get("path", "/"),
                    "公開サイトの応答を複数回確認できなかった",
                    "公開サイト・GitHub Pages・直近のデプロイを確認",
                    evidence="HTTP/通信監査で失敗")

    if not isinstance(quality, dict) or quality.get("status") != "FRESH":
        state = quality.get("status", "NOT_COLLECTED") if isinstance(quality, dict) else "NOT_COLLECTED"
        add("P2", "QUALITY_REPORT_UNAVAILABLE", "/",
            "商品品質の直近の監査結果を確認できない",
            "quality-status.jsonの公開・更新時刻とビルド結果を確認",
            evidence=state)
    else:
        for index, err in enumerate(quality.get("errors", [])[:10]):
            # Strings can contain product data; never publish those verbatim.
            if isinstance(err, str):
                add("P0", "PRODUCT_QUALITY_FAILURE", "/",
                    "商品品質の自動判定にエラーを検出",
                    "直近の品質ログを調査。数量・送料判定を緩めない",
                    evidence=f"品質エラー {index + 1}／計{len(quality['errors'])}件")
        if quality.get("warnings"):
            add("P2", "PRODUCT_QUALITY_WARNINGS", "/",
                "商品候補の数量判定などに警告を検出",
                "品質レポートを精査し、誤商品混入防止ルールを維持",
                evidence=f"警告 {len(quality['warnings'])}件")

    if not isinstance(browser, dict) or browser.get("site") != SITE or not browser.get("read_only"):
        add("P1", "BROWSER_AUDIT_UNAVAILABLE", "/",
            "PC・スマホの公開サイト監査が未取得",
            "実ブラウザ監査の失敗ログを確認")
    else:
        observations = browser.get("observations")
        if not isinstance(observations, list):
            add("P1", "BROWSER_AUDIT_UNAVAILABLE", "/",
                "PC・スマホの監査結果形式が不正",
                "実ブラウザ監査結果を再生成")
        else:
            for obs in observations[:75]:
                if not isinstance(obs, dict) or obs.get("status") not in ("FAIL", "REVIEW"):
                    continue
                path = obs.get("path")
                if not good_path(path):
                    continue
                code = "BROWSER_CTA_FAILURE" if obs["status"] == "FAIL" else "BROWSER_REVIEW"
                level = "P1" if obs["status"] == "FAIL" else "P2"
                add(level, code, path,
                    "公開ページの購入導線・画面表示に検証項目あり",
                    "PC・スマホのスクリーンショットとHTMLを照合し、別PRで修正",
                    evidence=f"{obs.get('viewport', '不明')}px / {obs['status']}")

    if not isinstance(joined, dict) or joined.get("source") != JOINT_SOURCE or joined.get("site") != SITE:
        add("P1", "ANALYTICS_JOIN_UNAVAILABLE", "/",
            "GA4・Search Consoleの統合判断が未取得",
            "データ取得・接続権限・レポート形式を確認")
    elif joined.get("status") != "JOINT_PROVISIONAL":
        add("P2", "GSC_DATA_UNAVAILABLE", "/",
            "Search Consoleを取得できない。検索表示0回とは断定できない",
            "API権限・接続・再実行結果を調査")
    else:
        items = joined.get("top_investigations", [])
        if not isinstance(items, list):
            items = []
        for item in items[:8]:
            if not isinstance(item, dict) or not good_path(item.get("path")):
                continue
            code = item.get("code")
            if code in ("VERIFY_CLICK_ATTRIBUTION", "VERIFY_GA4_OPERATOR_DIMENSION"):
                add("P1", "GA4_CLICK_ATTRIBUTION_UNCERTAIN", item["path"],
                    "運営者テストを一般ユーザーの楽天クリックと区別できない",
                    "GA4のoperator_test計測とイベント設定を調査")
            elif code == "CHECK_SEARCH_RESULT_APPEAL":
                metrics = item.get("gsc_last_28") or {}
                if metrics.get("impressions", 0) >= 50:
                    add("P2", "SEO_SNIPPET_RESEARCH", item["path"],
                        "検索表示数に対するクリックが少ない可能性",
                        "検索クエリ・端末・競合を確認。タイトルは自動変更しない",
                        evidence="28日表示=" + str(metrics.get("impressions", "不明")))
            elif code == "INVESTIGATE_SEARCH_EXPOSURE_CHANGE":
                add("P2", "SEARCH_EXPOSURE_CHANGE", item["path"],
                    "検索表示数の変化を要調査",
                    "日別・端末別のデータを確認。順位低下とは断定しない")
            elif code == "INSPECT_LANDING_TO_AFFILIATE_JOURNEY":
                add("P2", "LANDING_CTA_RESEARCH", item["path"],
                    "検索着地後の購入導線に改善余地がある可能性",
                    "訪問者数・購入導線・商品充実度を別途調査")

    if isinstance(ga4, dict) and ga4.get("source") == "GA4 Data API":
        summary = ga4.get("summary", {})
        if isinstance(summary, dict) and summary.get("unknown_operator_clicks", 0) > 0:
            add("P1", "GA4_UNKNOWN_TEST_CLICKS", "/",
                "楽天クリックの一部で運営者テスト区分が不明",
                "GA4イベント送信とカスタムディメンションを点検",
                evidence=f"区分不明={summary['unknown_operator_clicks']}件")

    # Deduplicate by structural finding identity, not fluctuating metrics or viewport.
    unique = {}
    for f in findings:
        original = unique.get(f["id"])
        if original is None or LEVELS[f["severity"]] < LEVELS[original["severity"]]:
            unique[f["id"]] = f
    selected = sorted(unique.values(), key=lambda v: (LEVELS[v["severity"]], v["path"], v["code"]))[:MAX_FINDINGS]
    actionable = [f for f in selected if f["severity"] in ("P0", "P1", "P2")]
    signature = hashlib.sha256("\n".join(
        f"{f['severity']}:{f['id']}" for f in actionable).encode("utf-8")).hexdigest()[:20]
    return {
        "source": "daily-cost autonomous operations triage v1",
        "site": SITE,
        "status": ("URGENT_REVIEW" if any(f["severity"] == "P0" for f in selected) else
                   "REVIEW_REQUIRED" if actionable else "NO_ACTIONABLE_FINDINGS"),
        "findings": selected,
        "fingerprint": signature,
        "summary": {p: sum(f["severity"] == p for f in selected) for p in LEVELS},
        "automation_scope": "read_only_analysis_and_single_rolling_issue",
        "automatic_website_edits": False,
        "automatic_pull_requests": False,
        "automatic_merge": False,
        "affiliate_sales_verified": False,
        "notes": [
            "Search Console visits and GA4 clicks cannot be used to infer purchase rate.",
            "Missing/stale monitoring data is unknown, never interpreted as zero problems.",
            "Search CTR hypotheses do not authorize automatic SEO copy changes.",
            "Product quantity, postage, merchant URLs and affiliate tracking remain protected.",
            "Only one rolling GitHub issue may be created/updated to avoid noisy repeated reports.",
        ],
    }


def markdown(report):
    counts = report["summary"]
    lines = [
        "## 自動運営｜改善の優先順位（読み取り専用）",
        "",
        "- 状態：**" + report["status"] + "**",
        f"- 要対応件数：P0={counts['P0']} / P1={counts['P1']} / P2={counts['P2']}",
        "- **実サイトや楽天リンクの変更は行っていません。**",
        "- 収益・成約件数は未接続のため判定できません。",
        "",
        "| 重要度 | 対象 | 調査項目 | 次の作業 |",
        "|---|---|---|---|",
    ]
    for f in report["findings"][:12]:
        lines.append("| " + f["severity"] + " | " + f["path"] +
                     " | " + f["message"] + " | " + f["next_action"] + " |")
    if not report["findings"]:
        lines.append("| ― | ― | 新たに確認できた問題なし | 次の定期検査まで監視 |")
    lines += [
        "",
        "※監査対象外やデータ不足の箇所を「問題なし」と断定していません。",
        "※収益化の改善策と実際の売上は別。作業候補は人がレビューするまで実装・公開しません。",
        "",
    ]
    return "\n".join(lines)


def main():
    root = Path("audit-results")
    joined = read_optional(root / "search-affiliate-joint.json")
    browser = read_optional(root / "live-cta-qa" / "report.json")
    health = read_optional(root / "health.json")
    ga4 = read_optional(root / "ga4-three-day-report.json")
    quality = fetch_public_quality()
    report = evaluate(joined, browser, health, quality, ga4)
    report["generated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["quality_source_status"] = quality.get("status", "UNAVAILABLE")
    root.mkdir(parents=True, exist_ok=True)
    (root / "autonomous-operations.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "autonomous-operations.md").write_text(markdown(report), encoding="utf-8")
    print("Autonomous operations triage: " + report["status"] +
          "; findings=" + str(len(report["findings"])))


if __name__ == "__main__":
    main()
