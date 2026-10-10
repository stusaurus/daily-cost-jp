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
