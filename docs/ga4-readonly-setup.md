# GA4 read-only pilot — verified setup and safe first run

## Status (2026-10-10)
- Google Cloud project `daily-cost-analytics` created; Analytics Data API enabled (user-provided screenshots).
- GA4 property: `552907444`; service account `daily-cost-ga4-reader@daily-cost-analytics.iam.gserviceaccount.com`.
- GA4 property **Viewer** permission granted by owner (user confirmation; actual API read not yet verified).
- Workload Identity Pool `github-actions-pool`, provider `github-actions`, verified in Cloud Shell.
- Provider mapping: `google.subject=assertion.sub`, `attribute.repository=assertion.repository`.
- Provider condition: `assertion.repository == 'stusaurus/daily-cost-jp' && assertion.ref == 'refs/heads/main'`.
- Service account role `roles/iam.workloadIdentityUser` granted to matching repository principalSet; Cloud Shell returned `Updated IAM policy`.
- GitHub environment `ga4-readonly-pilot` exists and allows only `main` branch; user screenshot verified.
- **Actual GA4 authenticated export NOT YET EXECUTED.** No revenue conclusions or site edits permitted.

## First authenticated smoke test
1. Ensure this branch's CI tests pass and the read-only pilot is merged into `main`. A `workflow_dispatch` workflow must be present on the default branch to appear in Actions.
2. No GitHub Secrets or variables to enter for this pilot; property ID, provider resource and service account email are non-secret constants in the workflow. **Never upload a service-account JSON key.**
3. On GitHub: Actions → **GA4 Click Export Pilot** → **Run workflow**, branch **main**. The export job runs only on manual dispatch, with environment `ga4-readonly-pilot` and `id-token: write`. Pull-request jobs only run offline tests without Google credentials.
4. Inspect the run. Confirm **Authenticate to Google (read-only)** and **Export raw GA4 click events** both succeeded.
5. Download the `ga4-clicks-raw` artifact only from a successful run. It intentionally contains `RAW_UNVERIFIED` values, not qualified clicks or commissions. Empty rows are **not evidence of zero clicks**.
6. If authentication fails, inspect only the error summary, avoid sharing tokens or logs that contain credentials. Common causes: IAM Service Account Credentials API not enabled, insufficient GA4 Viewer access, WIF provider or environment constraints.
7. Do not run on a PR branch, relax branch restrictions, assign project Editor/Admin, enable deployment credentials, or auto-merge changes to resolve an authentication error.

## Boundaries
- This pilot is **read-only**. It cannot update product data, affiliate URLs, website code, or GA4 configuration.
- The raw export does not filter `operator_test`, does not establish completeness of zero-click days, and has no GA4 sessions denominator.
- Never feed it straight into `evaluate_affiliate_clicks.py`; that evaluator requires verified complete daily records with test clicks and session counts.
- Independent 3-day optimization and automatic production edits remain **disabled**.
