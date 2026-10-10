# GA4 read-only pilot: one-time Google Cloud setup

Status: NOT CONNECTED. Do not merge or enable automatic publication on the strength of this document.

## Prerequisites
- Google Cloud project with billing/cost alerts configured if applicable
- Google Analytics Data API enabled in that project
- GA4 numeric **property ID** (not G- measurement ID)
- Permissions to administer GA4 property access and Google Cloud IAM
- GitHub repository stusaurus/daily-cost-jp

## Secure identity setup
1. In Google Cloud IAM, create a dedicated service account for this pilot, with **no project-wide Editor/Owner** role.
2. In GA4 Admin > Property access management, grant the service account email **Viewer** on the intended property only.
3. Create a Workload Identity Pool and OIDC provider for issuer `https://token.actions.githubusercontent.com`.
4. Map `google.subject=assertion.sub`, `attribute.repository=assertion.repository`, `attribute.ref=assertion.ref`, and `attribute.environment=assertion.environment` as supported by the provider configuration.
5. Set provider condition restricting `assertion.repository == 'stusaurus/daily-cost-jp'`; restrict the service account's Workload Identity User principal binding to that repository and the dedicated `ga4-readonly-pilot` environment. Verify GitHub OIDC claim shape and provider mapping before enabling.
6. In GitHub Settings > Environments, create `ga4-readonly-pilot`; require a reviewer for initial runs where the plan supports it. Limit deployment branches to the reviewed branch or main as appropriate.
7. Set GitHub Actions **variables** (not passwords): `GA4_PROPERTY_ID` (numeric), `GCP_WIF_PROVIDER` (full provider resource name), `GCP_SERVICE_ACCOUNT` (service-account email). Do not paste service-account JSON keys into the repository or chat.
8. Once this workflow exists on the default branch, use Actions > GA4 Click Export Pilot > Run workflow. A workflow on an experiment branch alone may not appear in the manual-run UI.
9. Inspect the run and `ga4-clicks-raw` artifact. If authentication fails, verify pool provider, principal binding, environment and GA4 Viewer permission. Stop rather than broadening IAM roles.

## Important limitations
- The export is raw event counts. It does **not** remove `operator_test`, does **not** establish complete zero-click days, and does **not** provide session counts.
- Never feed this raw output directly to `evaluate_affiliate_clicks.py`; that evaluator expects verified complete daily records with test clicks and sessions.
- Keep auto-merge, product selection changes, affiliate URL edits and production write access disabled until separate verified tests and safety controls exist.
- Initial authenticated run is intentionally manual, not scheduled.
