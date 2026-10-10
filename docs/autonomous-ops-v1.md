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
