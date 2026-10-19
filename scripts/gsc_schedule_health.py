#!/usr/bin/env python3
"""Read GitHub schedule receipts, independently of successful manual GSC runs."""
import datetime as dt
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

# The diagnostic was merged Oct 19 after its due time; its first eligible
# scheduled receipt is Oct 26. Manual Oct 19 success does not replace it.
WORKFLOWS = {"gsc-six-sites.yml": 0, "gsc-six-sites-diagnostics.yml": 45}
FIRST_DIAGNOSTIC = dt.datetime(2026, 10, 26, 0, 45, tzinfo=dt.timezone.utc)
GRACE = dt.timedelta(hours=24)


def evaluate(now, minute, runs, first_expected=None):
    if first_expected is not None and now < first_expected:
        return {"status": "NOT_YET_DUE", "expected_after_utc": first_expected.isoformat(),
                "grace_hours": 24, "run_id": None, "conclusion": None}
    due = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=minute, second=0, microsecond=0)
    if due > now:
        due -= dt.timedelta(days=7)
    eligible = [r for r in runs if r.get("event") == "schedule" and r.get("head_branch") == "main"
                and due <= dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) <= now]
    latest = max(eligible, key=lambda r: r["created_at"], default=None)
    if latest and latest.get("status") == "completed":
        status = "HEALTHY" if latest.get("conclusion") == "success" else "FAILED_SCHEDULE"
    elif now < due + GRACE:
        status = "WAITING_WITHIN_24H_GRACE"
    else:
        status = "SCHEDULE_NOT_COMPLETED" if latest else "MISSING_SCHEDULE"
    return {"status": status, "expected_after_utc": due.isoformat(),
            "grace_hours": 24, "run_id": latest.get("id") if latest else None,
            "conclusion": latest.get("conclusion") if latest else None}


def read_runs(workflow):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    # Fixed host/repo/workflow; never send GitHub credentials to public site probes.
    url = "https://api.github.com/repos/stusaurus/daily-cost-jp/actions/workflows/" + workflow + "/runs?event=schedule&branch=main&per_page=10"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise ValueError("invalid run list")
    return data["workflow_runs"]


def main():
    now = dt.datetime.now(dt.timezone.utc)
    results = {}
    for workflow, minute in WORKFLOWS.items():
        try:
            first = FIRST_DIAGNOSTIC if workflow == "gsc-six-sites-diagnostics.yml" else None
            runs = [] if first is not None and now < first else read_runs(workflow)
            results[workflow] = evaluate(now, minute, runs, first)
        except Exception:
            results[workflow] = {"status": "UNAVAILABLE", "reason": "GITHUB_RUN_HISTORY_UNAVAILABLE"}
    report = {"checked_at": now.isoformat(), "workflows": results,
              "limitation": "This watchdog also uses GitHub schedules; it cannot detect a platform-wide outage while itself not running. Notifications depend on repository watcher settings."}
    output = Path("audit-results")
    output.mkdir(exist_ok=True)
    (output / "gsc-schedule-health.json").write_text(json.dumps(report, indent=2))
    summary = "\n## GSC schedule receipts (manual runs excluded)\n\n" + "\n".join("- " + w + ": **" + d["status"] + "**" for w, d in results.items()) + "\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(summary)
    print(summary)
    bad = [w for w, d in results.items() if d["status"] not in ("HEALTHY", "WAITING_WITHIN_24H_GRACE", "NOT_YET_DUE")]
    if bad:
        print("::error::GSC schedule missing, failed or unknown: " + ", ".join(bad))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
