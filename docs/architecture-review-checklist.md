# Architecture Review Checklist

Use this checklist for changes that affect state, generated artifacts, provider contracts, dashboard authorization, or apply semantics.

## Scope

Run this checklist when a change touches:

- `.zt` state layout or migration behavior.
- Generated plans, scripts, reports, or backup manifests.
- Provider contracts or environment schema.
- Plan review, approvals, change records, release channels, or locks.
- Dashboard authorization, sessions, CSRF, audit events, or settings.
- CLI apply, upgrade, destroy, restore, or registry behavior.

## Review Questions

- Does the change preserve environment YAML as source of intent?
- Does generated state remain local or explicitly documented as durable shared state?
- Are old generated artifacts, reviews, backups, and jobs still readable?
- Do plan hashes change when apply-relevant artifacts change?
- Does the production gate block stale, missing, or warning evidence?
- Are secrets kept out of Git, logs, review artifacts, and test fixtures?
- Are filesystem paths constrained to expected repo or `.zt` boundaries?
- Are apply-class actions still explicit, audited, approved, and lock-protected?
- Are connected, proxied, and air-gapped modes considered?
- Are rollback and restore consequences documented?

## Required Evidence

Include links or command output for:

- Relevant tests.
- Smoke test of the changed workflow.
- Security review notes from `SECURITY_REVIEW.md` when triggered.
- Code review notes from `CODE_REVIEW.md` when reviewing someone else's change.
- Any ADR that explains a new architecture decision.

## Related Guidance

- `SECURITY_REVIEW.md`
- `CODE_REVIEW.md`
- `docs/architecture.md`
- `docs/architecture/data-flow.md`
- `docs/architecture/deployment-boundaries.md`
- `docs/restore-controls.md`
