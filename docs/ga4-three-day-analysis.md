# GA4 Three-Day Read-Only Analysis (pilot)

## Purpose
Report actual GA4 `affiliate_click` events for `stusaurus.github.io/daily-cost-jp/` without mixing in local/development, other domains, or known operator test events. No automatic editing, fake clicks or commission assumptions.

## Current setup
- GA4 property ID: `552907444`.
- Workload Identity Federation: GitHub `stusaurus/daily-cost-jp` **main** only.
- GitHub Environment: `ga4-readonly-pilot`, main only, no JSON keys.
- Existing `scripts/report_daily_clicks.py` validates `pageLocation` and partitions operator (1), non-operator (0), and unknown. The three-day script reuses this production classifier.

## Schedule and dates
The workflow runs a lightweight **date check every day at 10:27 JST**. Only once every 3 JST calendar days does it request Google credentials and read GA4, anchored to 2026-10-10. An initial read-only report also runs automatically when this new workflow is first merged into main (workflow-file push). Manual runs always permit a read-only report. For example, the next automatic evaluation dates after 2026-10-10 are **2026-10-13** and **2026-10-16**, subject to GitHub's scheduled workflow availability.

Every execution analyzes three complete dates **four, three, and two days before** the run in Asia/Tokyo. This gives GA4 extra processing time; the property timezone must be checked before treating dates as an exact coverage guarantee.

## Output
GitHub Actions > GA4 Three-Day Read-Only Analysis > selected run:
- **Summary**: short Japanese count table without downloading files.
- **Artifact** `ga4-three-day-report`: aggregated JSON and Markdown retained for 30 days.

Click buckets:
- `production_operator`: explicitly `operator_test=1`, **exclude** from ordinary click metric.
- `production_non_operator`: explicitly `operator_test=0`, **provisional** only (not proof of a unique independent shopper).
- `production_unknown`: missing/unknown flag, **do not** assume independent visitor.
- `development`, `other_site`, `unscoped`: excluded from production.
- Sessions: independent GA4 report scoped to matching hostname and `/daily-cost-jp/` paths. This is a site activity proxy, not a verified purchase conversion rate.

The script checks GA4 metadata to see if event-scoped custom dimension `operator_test` is registered. The Google Analytics Data API only exposes `customEvent:operator_test` after the dimension has been registered. If it is unavailable, clicks remain in the **unknown** bucket and the result is **DATA_LIMITED**, not falsely counted as non-operator.

A day missing from the sessions report is `null` (unknown), never zero. Truncated or thresholded GA4 reports cause a failed job. The successful metrics remain **provisional**: GA4 may later revise numbers.

## Safety boundary
- Read-only API scope and short-lived OIDC credentials.
- On PRs only offline tests run. Authenticated reports are restricted to main via GitHub environment and GCP provider condition.
- No write token, no GitHub commit, no website rebuild/deploy, no changes to product matching or prices.
- A successful GitHub run means the code and API completed, not that true revenue increased.
- Status bands `NEEDS_ATTENTION` and `OBSERVE` are **investigation priorities**, never permission to auto-edit pages.

## First rollout
1. Require the full PR CI suite and synthetic tests to pass.
2. Merge the read-only workflow; verify the initial automatically triggered main-branch report. If it is skipped due to GitHub scheduling, trigger manually on main.
3. Inspect `operator_test_custom_dimension_registered` and `summary.status` before interpreting the click counts. If `DATA_LIMITED`, do not auto-fix measurement settings without review.
4. Observe the next scheduled run and verify no duplicates or missed windows. Expand to autonomous suggestions only after the metrics are reliable.
