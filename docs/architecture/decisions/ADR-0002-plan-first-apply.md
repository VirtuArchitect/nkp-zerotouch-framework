# ADR-0002: Use Plan-First Apply Gates

## Status

Accepted

## Context

NKP registry pushes, deploys, upgrades, destroys, and restores can change live infrastructure. Operators need reviewable evidence and approval records before apply-class actions run.

## Decision

Generate artifacts before apply, require plan review for apply-class actions, store plan hashes with approvals, create change records for apply requests, and keep destructive actions behind explicit flags and approval policy.

## Consequences

The workflow is slower than direct execution, but it gives operators auditability, stale-review detection, approval gates, and safer rollback decision points. Tests must cover gate behavior whenever generated artifact shape, review records, or apply semantics change.
