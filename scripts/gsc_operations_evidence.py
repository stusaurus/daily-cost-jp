"""Adapt official six-site artifacts to the EXISTING operations queue.

No Google requests, new queue, PR publisher or SEO/product writes. Thresholds
are operational heuristics, not statistical significance or causal evidence.
"""
import datetime as dt
import io
import json
import os
import re
import unicodedata
import zipfile
from pathlib import Path
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from autonomous_operations_issue import github_request, REPO
from step6_reference_report import StripAuthorization
from gsc_six_sites import SITES, date_windows, safe_metrics, safe_page

SOURCE = "six-site operations evidence v1"
CONFIG = {
    "aggregate": ("gsc-six-sites.yml", "gsc-six-sites-readonly", "gsc-six-sites.json",
                  "Google Search Console Search Analytics API (read-only)", "as_of"),
    "diagnostic": ("gsc-six-sites-diagnostics.yml", "gsc-six-sites-discovery-readonly",
                   "gsc-six-sites-diagnostics.json",
                   "Google Search Console Search Analytics + URL Inspection APIs (read-only)", "as_of_pacific"),
}
MAX_BYTES = 2_000_000


def instant(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone missing")
    return parsed.astimezone(dt.timezone.utc)


def validate(report, run, kind, now):
    """An authenticated main run is provenance, NOT a PR's unverified JSON.

    We retain the source SHA; it need not equal today's catalog-update SHA.
    No claim is made that this proves arbitrary source commits are equivalent.
    """
    workflow, _, _, source, date_key = CONFIG[kind]
    if (run.get("head_branch") != "main" or run.get("event") not in ("schedule", "workflow_dispatch", "push")
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("path") != ".github/workflows/" + workflow
            or run.get("repository", {}).get("full_name") != REPO
            or not re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", ""))
            or type(run.get("id")) is not int or run["id"] <= 0):
        raise ValueError("unverified main receipt")
    age = now - instant(run["created_at"])
    day = dt.date.fromisoformat(report[date_key])
    days_old = (now.astimezone(ZoneInfo("America/Los_Angeles")).date() - day).days
    if not dt.timedelta(0) <= age <= dt.timedelta(days=10) or not 0 <= days_old <= 10:
        raise ValueError("stale or future evidence")
    if report.get("source") != source or report.get("date_windows") != date_windows(day):
        raise ValueError("source or period mismatch")
    sites = report.get("sites")
    if (not isinstance(sites, list) or len(sites) != len(SITES)
            or sorted((s.get("name"), s.get("property")) for s in sites) != sorted(SITES)):
        raise ValueError("mixed or duplicate properties")
    return day.isoformat()


def download(run, kind, token):
    _, artifact_name, member_name, _, _ = CONFIG[kind]
    artifacts = github_request(f"/actions/runs/{run['id']}/artifacts?per_page=100", token)["artifacts"]
    matches = [a for a in artifacts if a.get("name") == artifact_name and not a.get("expired")
               and 0 < a.get("size_in_bytes", 0) <= MAX_BYTES]
    if len(matches) != 1:
        raise ValueError("unique bounded artifact missing")
    artifact = matches[0]
    if artifact.get("workflow_run", {}).get("id", run["id"]) != run["id"]:
        raise ValueError("artifact run mismatch")
    req = Request(f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip",
                  headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    with build_opener(StripAuthorization()).open(req, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized artifact")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist().count(member_name) != 1:
            raise ValueError("nonunique report member")
        member = archive.getinfo(member_name)
        if member.file_size > 1_000_000:
            raise ValueError("oversized report member")
        report = json.loads(archive.read(member))
    return report, artifact["id"]


def collect(kind, token, now):
    workflow = CONFIG[kind][0]
    runs = github_request(f"/actions/workflows/{workflow}/runs?branch=main&status=success&per_page=10", token)["workflow_runs"]
    observations, days = [], set()
    # Bounded GitHub reads only. A same-day rerun cannot manufacture persistence.
    for run in runs[:10]:
        try:
            if run.get("event") == "pull_request":
                continue
            if now - instant(run["created_at"]) > dt.timedelta(days=10):
                continue
            report, artifact_id = download(run, kind, token)
            day = validate(report, run, kind, now)
            if day in days:
                continue
            days.add(day)
            observations.append({"report": report, "run_id": run["id"], "sha": run["head_sha"],
                                 "artifact_id": artifact_id, "as_of": day})
            if len(observations) == 2:
                break
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            continue
    return sorted(observations, key=lambda x: x["as_of"], reverse=True)


def metrics(value):
    if not isinstance(value, dict):
        return None
    # Official normalized observed-zero rows have position=None (undefined).
    row = dict(value)
    if row.get("impressions") == 0 and row.get("position") is None:
        row["position"] = 0
    try:
        return safe_metrics(row)
    except (ValueError, TypeError):
        return None


def operator_query(query):
    return bool(re.search(r"(?:^|\s)-?site\s*:", unicodedata.normalize("NFKC", str(query)).lower()))


def findings_for(report, kind):
    from autonomous_operations_triage import new_finding, good_path
    findings, summary = [], []
    period = report["date_windows"]["last_28"]
    def add(site, code, path, message, evidence):
        if not good_path(path):
            return
        f = new_finding("P3", code, path, message,
                        "原本・公開状態・次回の同条件観測を照合。SEO/商品は自動変更しない", evidence=evidence)
        slug = site["property"].rstrip("/").rsplit("/", 1)[-1]
        f.update(id=code + ":" + slug + ":" + path, site=site["property"], site_name=site["name"],
                 period=period, observation="FIRST_OBSERVATION", auto_fix_allowed=False)
        findings.append(f)
    for site in report["sites"]:
        state = {"site": site["property"], "name": site["name"], "period": period,
                 "source_status": site.get("status"), "index_pass": None, "index_observed": None}
        if site.get('status') not in ('OBSERVED', 'NO_ROWS'):
            add(site, 'GSC_SITE_DATA_UNKNOWN', '/', 'サイトのAPI結果に欠落・権限・取得の要確認項目',
                'source status=' + str(site.get('status')) + '。検索表示0や未登録とは断定しない')
        if kind == "aggregate":
            windows = site.get("windows", {})
            for label, minimum, decrement in (("28", 100, 50), ("7", 50, 30)):
                current = windows.get("last_" + label, {})
                prior = windows.get("prior_" + label, {})
                a = metrics(current.get("metrics")) if current.get("status") == "OBSERVED" else None
                b = metrics(prior.get("metrics")) if prior.get("status") == "OBSERVED" else None
                if a is not None and b is not None and b["impressions"] >= minimum:
                    drop = b["impressions"] - a["impressions"]
                    if drop >= decrement and (label == "7" or drop >= b["impressions"] * .5):
                        add(site, "GSC_IMPRESSIONS_DROP_" + label, "/", "検索表示の大幅減少候補",
                            f"{label}日: {b['impressions']}→{a['impressions']}。確定OBSERVED。運用閾値であり有意差ではない")
                        findings[-1]['period'] = report['date_windows']['last_' + label]
                        findings[-1]['prior_period'] = report['date_windows']['prior_' + label]
            observed = windows.get("last_28", {})
            state["metrics"] = metrics(observed.get("metrics")) if observed.get("status") == "OBSERVED" else None
            for row in site.get("top_pages", [])[:5]:
                m = metrics(row)
                if not m:
                    continue
                path = row.get("path")
                if m["impressions"] >= 30 and 11 <= m["position"] <= 20:
                    add(site, "GSC_RANK_11_20", path, "11〜20位の改善調査候補（検索意図は別途確認）",
                        f"28日表示={m['impressions']} / 平均順位={m['position']}")
                if m["impressions"] >= 50 and 4 <= m["position"] <= 30 and m["ctr"] < .02:
                    add(site, "GSC_LOW_CTR", path, "検索表示に対してクリックが少ない候補",
                        f"28日表示={m['impressions']} / クリック={m['clicks']}。少標本で購入率は判定しない")
        else:
            analytics = site.get("analytics", {})
            queries = analytics.get("queries_28d", {})
            rows = queries.get("rows", []) if queries.get("status") in ("OBSERVED_ROWS", "TOP_ROWS_LIMIT_POSSIBLE") else []
            state["returned_query_rows"] = {"operator": sum(operator_query(r.get("key")) for r in rows),
                                              "natural": sum(not operator_query(r.get("key")) for r in rows)}
            state["query_coverage"] = "RETURNED_ROWS_ONLY_ANONYMIZED_OR_OMITTED_TERMS_UNKNOWN"
            pairs = analytics.get("query_pages_28d", {})
            if pairs.get("status") in ("OBSERVED_ROWS", "TOP_ROWS_LIMIT_POSSIBLE"):
                for row in pairs.get("rows", [])[:1000]:
                    if operator_query(row.get("key")) or safe_page(row.get("page"), site["property"]) != row.get("path"):
                        continue
                    m = metrics(row)
                    if not m or m["impressions"] < 30:
                        continue
                    # Deliberately narrow hypotheses, not a general intent classifier.
                    expected = next((path for word, path in (("ティッシュ", "/categories/tissue/"),
                        ("洗濯洗剤", "/categories/laundry/"), ("トイレットペーパー", "/categories/toilet-paper/"))
                        if word in row.get("key", "")), None) if site["name"] == "日用品" else None
                    if expected and row.get("path") != expected:
                        add(site, "GSC_QUERY_PAGE_MISMATCH", row.get("path"), "検索語と表示ページの不一致候補",
                            "返却された自然語×ページ30表示以上。期待カテゴリ=" + expected + "。匿名化分は不明")
            inspections = site.get("inspection", [])
            observed = [i for i in inspections if i.get("status") == "OBSERVED_SNAPSHOT"]
            state.update(index_observed=len(observed), index_pass=sum(i.get("verdict") == "PASS" for i in observed),
                         inspection_unavailable=len(inspections) - len(observed))
            if state['inspection_unavailable']:
                add(site, 'GSC_INSPECTION_DATA_UNKNOWN', '/', '保存済み登録状態のAPI取得に欠落',
                    '未取得=' + str(state['inspection_unavailable']) + '。未登録とは区別し再取得を確認')
            for item in observed:
                path = item.get("path")
                public = item.get("public", {}).get("status")
                if item.get("verdict") in ("FAIL", "NEUTRAL"):
                    add(site, "GSC_INDEX_REVIEW", path, "Google保存済み登録状態の確認候補（ライブテストではない）",
                        "verdict=" + str(item.get("verdict")) + " / public=" + str(public) + "。未取得とは区別。原因未確定")
                expected = site["property"] + str(path).lstrip("/")
                if any(item.get(k) and item[k] != expected for k in ("google_canonical", "user_canonical")):
                    add(site, "GSC_CANONICAL_REVIEW", path, "canonical不一致候補", "Google/指定canonicalと対象URLを照合。自動書換しない")
                if (item.get("robots_txt_state") == "DISALLOWED" or item.get("indexing_state") in ("BLOCKED_BY_META_TAG", "BLOCKED_BY_HTTP_HEADER")
                        or item.get("page_fetch_state") not in (None, "", "SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED")):
                    add(site, "GSC_CRAWL_REVIEW", path, "クロール・登録制限の確認候補", "保存済みrobots/indexing/fetch状態に要確認項目。公開HTMLと照合")
        summary.append(state)
    return {f["id"]: f for f in findings}, summary


def assess(observations, kind):
    if not observations:
        return {"status": "UNKNOWN", "reason": "NO_FRESH_VERIFIED_MAIN_ARTIFACT", "findings": [], "sites": [], "receipts": []}
    latest = observations[0]
    current, summary = findings_for(latest["report"], kind)
    previous = observations[1] if len(observations) > 1 else None
    independent = previous and previous["run_id"] != latest["run_id"] and previous["as_of"] < latest["as_of"]
    prior = findings_for(previous["report"], kind)[0] if independent else {}
    for key, finding in current.items():
        if key in prior:
            finding.update(severity="P2", observation="REPEATED_DISTINCT_DATES")
        finding["evidence"] += f" / run={latest['run_id']}"
    return {"status": "FRESH", "sites": summary, "findings": list(current.values()),
            "receipts": [{k: o[k] for k in ("run_id", "sha", "artifact_id", "as_of")} for o in observations]}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    result = {"source": SOURCE, "generated_at_utc": now.isoformat(), "sources": {},
              "policy": "Operational heuristics, not statistical significance. Sources/windows stay independent; queries never added to site totals; URL Inspection is saved state, not live test.",
              "automatic_code_change": False}
    for kind in CONFIG:
        try:
            result["sources"][kind] = assess(collect(kind, os.environ.get("GITHUB_TOKEN", ""), now), kind)
        except Exception:
            result["sources"][kind] = assess([], kind)
    root = Path("audit-results"); root.mkdir(exist_ok=True)
    (root / "gsc-operations-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("Official GSC evidence adapter: " + ", ".join(k + "=" + v["status"] for k, v in result["sources"].items()))


if __name__ == "__main__":
    main()
