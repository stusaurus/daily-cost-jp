#!/usr/bin/env python3
"""Maintain ONE rolling GitHub Issue for the autonomous read-only ops queue.

Only the authorized main-branch workflow can write issue text. This does not
create commits, PRs, deployment events or external affiliate requests.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "stusaurus/daily-cost-jp"
ISSUE_TITLE = "【自動運営】日用品サイトの改善判断（最新）"
MARKER = "<!-- daily-cost-autonomous-operations-v1 -->"
TAG_RE = re.compile(r"<!-- findings-hash:([a-f0-9]{20}) -->")
API = "https://api.github.com/repos/" + REPO


def should_update(existing, fingerprint, now=None):
    if not isinstance(existing, dict):
        return True
    body = existing.get("body", "")
    old = TAG_RE.search(body) if isinstance(body, str) else None
    if not old or old.group(1) != fingerprint:
        return True
    try:
        updated = dt.datetime.fromisoformat(existing["updated_at"].replace("Z", "+00:00"))
        now = now or dt.datetime.now(dt.timezone.utc)
        return now - updated >= dt.timedelta(days=7)
    except (KeyError, ValueError, TypeError, AttributeError):
        return True


def render_issue(report, run_url):
    """No arbitrary raw product names, URLs or query text enter GitHub issue."""
    from autonomous_operations_triage import markdown
    key = report["fingerprint"]
    if not re.fullmatch(r"[0-9a-f]{20}", key):
        raise ValueError("Untrusted findings fingerprint")
    if not run_url.startswith("https://github.com/" + REPO + "/actions/runs/"):
        raise ValueError("Unexpected run URL")
    return ("\n".join([
        MARKER,
        f"<!-- findings-hash:{key} -->",
        "# 日用品サイト：自動運営の改善キュー",
        "",
        "このIssueは自動分析が管理する**1件の継続レポート**です。",
        "同じ問題で新しいIssueを繰り返し作成しません。",
        "最後に更新された検証：[GitHub Actions](" + run_url + ")",
        "",
        markdown(report),
        "",
        "### 次の自動化段階",
        "",
        "ここでは検出・優先順位付け・安全な調査候補整理まで。",
        "コード修正PRやデプロイの自動許可はまだ有効化していません。",
        "改善を行う場合は別PRの差分、商品判定、楽天リンク、PC/スマホQAの確認が必要です。",
        "",
    ]))


def github_request(path, token, method="GET", payload=None):
    if not isinstance(token, str) or not token:
        raise ValueError("Missing GitHub workflow token")
    url = API + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url, method=method, data=data, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DailyCost-AutoOperations/1.0",
    })
    with urlopen(request, timeout=20) as response:
        body = response.read(250_000)
    return json.loads(body)


def sync_issue(report, token, run_id, ref, repository):
    if ref != "refs/heads/main" or repository != REPO:
        raise ValueError("Only main branch of the exact repository can publish ops issues")
    if not isinstance(report, dict) or report.get("source") != "daily-cost autonomous operations triage v1":
        raise ValueError("Unexpected operations report source")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{6,20}", run_id):
        raise ValueError("Invalid GitHub Actions run ID")
    url = f"https://github.com/{REPO}/actions/runs/{run_id}"
    body = render_issue(report, url)
    data = github_request("/issues?state=open&per_page=100", token)
    if not isinstance(data, list):
        raise ValueError("Invalid existing-issue listing")
    matches = [issue for issue in data if isinstance(issue, dict) and
               "pull_request" not in issue and issue.get("title") == ISSUE_TITLE and
               MARKER in (issue.get("body") or "")]
    if len(matches) > 1:
        raise ValueError("Duplicate rolling issues need manual cleanup; refuse creating more")
    if matches:
        issue = matches[0]
        if not should_update(issue, report["fingerprint"]):
            return {"status": "UNCHANGED", "url": issue.get("html_url", "")}
        response = github_request(f"/issues/{issue['number']}", token, "PATCH", {"body": body})
        return {"status": "UPDATED", "url": response.get("html_url", "")}
    # Keep the issue tracker silent when the entire queue is healthy.
    if not report.get("findings"):
        return {"status": "NO_ISSUE_NEEDED", "url": None}
    response = github_request("/issues", token, "POST", {"title": ISSUE_TITLE, "body": body})
    return {"status": "CREATED", "url": response.get("html_url", "")}


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        print("Rolling issue sync disabled outside main")
        return
    report = json.loads(Path("audit-results/autonomous-operations.json").read_text(encoding="utf-8"))
    result = sync_issue(report, os.environ.get("GITHUB_TOKEN", ""),
                        os.environ.get("GITHUB_RUN_ID", ""),
                        os.environ.get("GITHUB_REF", ""),
                        os.environ.get("GITHUB_REPOSITORY", ""))
    print("Autonomous operations rolling issue: " + result["status"])
    if result.get("url"):
        print("Issue URL: " + result["url"])


if __name__ == "__main__":
    main()
