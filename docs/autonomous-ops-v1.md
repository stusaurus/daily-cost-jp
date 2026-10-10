# Autonomous Operations v1 — Safe Pilot

Status: experiment only. No automatic production code changes.

## Goals
- Detect failures without daily human prompting.
- Persist evidence and retry safely.
- Require deterministic tests before any change is proposed.
- Keep human approval for product matching, pricing, affiliate links, design and deployment logic.

## Existing safeguards to preserve
- scripts/product_quality.py
- scripts/validate_product_quality.py
- scripts/validate_generated_site.py
- npm test and Python unittest suite
- Existing scheduled update and X posting workflows

## Pilot acceptance criteria
1. Run read-only audit on schedule and on manual dispatch.
2. Test internal links, page status, product quality, and existing test suites.
3. Save dated machine-readable report and a human-readable summary.
4. Failed checks must produce an actionable result; never claim success from an AI response alone.
5. No secrets in logs; least-privilege permissions.
6. Retry transient network failures with bounded attempts.
7. No deploy, push, product substitution or pricing edits from the audit workflow.
8. Promote only after manual review of at least three successful runs and one simulated failure.

## Next implementation
Inventory current workflows and test commands, then implement a non-mutating GitHub Actions workflow on this branch. Avoid duplicate schedules and preserve the production workflows.

## Revenue optimization loop (every 3 days)

- Schedule every 3 days, with manual trigger available; persist last successful evaluation timestamp so runs cannot silently skip periods.
- Compare trailing 3/7/28 day windows with prior comparable periods, taking data freshness and reporting delays into account.
- Revenue source of truth: verified affiliate conversion/commission report when connected. GA4 affiliate_click is only an outbound click, not a sale. If no verified report, mark revenue as UNKNOWN, never zero.
- Diagnose funnel in order: measurement health -> impressions -> organic visits -> product availability -> outbound clicks -> verified orders/commission.
- Treat low traffic and insufficient sample size as INSUFFICIENT_EVIDENCE; avoid speculative automatic changes.
- Keep an experiment log with hypothesis, baseline, change, guardrails, result and rollback decision. Do not repeat failed experiments without new evidence.
- Safe auto-changes require allowlist, deterministic tests, preview, rollback and bounded change frequency. Pricing, product matching, affiliate attribution, tracking and material design changes require human approval.
- AI API optional, disabled by default until explicit budget ceiling, credentials, and privacy review are set. Use deterministic checks first.
- Never weaken product quality rules to increase clicks or apparent revenue.
- Report succinctly: revenue VERIFIED_ZERO / VERIFIED_POSITIVE / UNKNOWN, likely bottleneck, evidence, action taken, next check.

## Initial optimization KPI: affiliate clicks (owner decision)

Until traffic and outbound clicks reach useful volume, prioritize growth in qualified affiliate clicks over verified commission. Do not require affiliate dashboard login for the pilot.

- Primary metric: GA4 event_name=affiliate_click, excluding operator_test=1. Keep operator_test=0 and (not set) separately reported because neither guarantees non-owner traffic.
- Do not add auxiliary events product_result_click or same_product_rakuten_click to affiliate_click; they may describe the same interaction.
- Review rolling three-day totals every three days, alongside sessions, affiliate clicks per session, landing pages, conversion_source and 7/28-day baselines.
- Triage bands for three-day affiliate clicks: 0 = check instrumentation/link failures and traffic; 1-4 = inspect traffic and CTAs; 5-9 = identify effective entry points; 10+ = evaluate repeatable successes. Bands are investigation triggers, not statistical proof.
- Never optimize for fabricated or self-generated clicks. No bot clicking or artificial traffic.
- Owner's '100 clicks = 1 yen' is a planning placeholder only; do not report this as observed revenue or a credible conversion rate.
- Require sufficient evidence before changes, preserve all product-quality gates, and log each experiment and measured outcome.

## Detailed decision engine v1 (design, not deployed)

### Cadence and time semantics
- Evaluate every 3 calendar days in Asia/Tokyo; use complete JST days only and record evaluation_id/window_start/window_end.
- Use the same GA4 property, filters, and source dimensions for each comparison. Account for GA4 data latency by marking fresh/incomplete days and delaying decisions when necessary.
- Keep independent daily health checks for broken links, empty catalogs, workflow failure and measurement issues; do not wait three days to detect critical faults.

### Data contracts and truth labels
- Required: GA4 affiliate_click count by date, landing page, conversion_source, operator_test; sessions by landing page/source and device; data freshness; site version and deploy timestamp.
- Optional: Search Console page impressions, clicks, CTR, position; category/product inventory and valid outbound link count.
- Never join GSC search queries directly to GA4 users or assert purchase conversion from affiliate_click.
- If GA4 permission/data unavailable, state DATA_UNAVAILABLE and skip performance modifications; do not interpret missing as zero.
- Classify operator_test=1 as excluded; operator_test=0 as provisional; (not set) as uncertain. Report each bucket separately and do not silently treat uncertain as verified human clicks.
- Track click events and unique clicking sessions separately where technically available. Clicks/session is an intensity measure, not a purchase conversion rate.

### Root cause order
1. Instrumentation and pipeline health: event emitted once, no duplicates, no test pollution, no stale data.
2. Exposure: organic impressions, landing-page sessions, trends by page and device.
3. Discoverability: titles, snippets, query-to-page intent, indexing/canonical, Search Console coverage.
4. Engagement: mobile usability, page speed, internal navigation and CTA visibility.
5. Offer fit: valid products, stock, verified shipping-inclusive unit price, trustworthy comparisons.
6. Attribution and destination: affiliate URLs valid, no broken redirects, source tags intact.
7. Unknown: insufficient evidence -> observe and gather more data.

### Experiment policy
- One primary hypothesis per target page per evaluation; max 2 concurrent experiments across the pilot site.
- Prioritize using expected benefit x confidence / effort and risk, based on available evidence; do not invent precise predicted gains.
- Baseline: trailing 28 complete days plus 7-day trend; preserve seasonal/day-of-week context and note sparse samples.
- Freeze evaluation window for an experiment before deployment. Avoid simultaneous changes to title, layout, CTA and product ranking on the same page.
- Observe for at least 7 complete days after a change (extend for sparse traffic); three-day checkpoints monitor, not automatically declare wins.
- Success requires non-test affiliate clicks improve relative to eligible sessions, no decline in product-quality checks, no significant technical regression, and adequate sample size. If too few sessions, mark inconclusive.
- Maintain experiment_id, issue, evidence, hypothesis, changed files, test results, deploy SHA, pre/post metrics, status, rollback SHA, and next review date.
- Prevent repeated experiments by fingerprinting page + hypothesis + intervention; retry only with material new evidence.

### Automation permissions
- Phase A: read-only audit and reports; no deploy.
- Phase B: prepare draft pull requests with limited permissions, no auto merge.
- Phase C: auto merge only allowlisted noncommercial changes after deterministic QA, human-reviewed policy and rollback rehearsal.
- Never automatically change product eligibility filters, prices, affiliate links, GA4 identifiers, security settings, secrets, or legal copy.
- Set workflow permissions explicitly, avoid pull_request_target for untrusted code, pin trusted dependencies/actions and limit concurrency. Use idempotent checkpoints and bounded retries.
- Keep API spend capped and report cost per run. No LLM token use required for Phase A.

### Notification contract
Report every evaluation: status (HEALTHY/NEEDS_ATTENTION/INSUFFICIENT_DATA/DATA_UNAVAILABLE), qualified click count and trend, top bottleneck with evidence, exact action taken or proposed, verification outcome, next review.
Notify immediately on broken tracking, invalid affiliate links, failed quality gate, or workflow outage; do not manufacture positive results.

### Promotion gates
- Confirm GA4 read permissions and valid historical data.
- Run at least 3 scheduled cycles without missed windows, plus a simulated GA4 outage and one failed test.
- Validate a reversible improvement on one landing page before expanding to more categories and repositories.
