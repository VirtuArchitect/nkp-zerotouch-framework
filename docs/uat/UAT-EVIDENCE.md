# NKP ZeroTouch UAT Evidence

Current release marker: `v0.1.0`.

Capture one evidence record per UAT case, deployment run, failure recovery, or
rollback/abort exercise.

## Environment Evidence

- Repository version and commit.
- NKP version.
- Environment type.
- Environment config path and hash.
- Bundle type, path, and checksum where applicable.
- Registry endpoint where applicable.
- Prism Central endpoint.

## Governance Evidence

- Operator.
- Reviewer/approver.
- Approval ID.
- Change or UAT record.
- Point-of-no-return acknowledgment.
- Accepted warnings or exceptions.

## Execution Evidence

- CLI command or dashboard action.
- Run ID where available.
- Generated artifact path.
- Command output.
- Apply/dry-run mode marker.

## Target Evidence

- NKP verify output.
- Prism Central or cluster observation.
- Registry content confirmation where applicable.
- Explicit simulated-demo or local-only marker when no real target is touched.

## Recovery Evidence

- Failure classification.
- Last known completed phase.
- Target-state assessment.
- Recovery or rollback decision.
- Residual risks and owners.

## Acceptance Summary

Record outcome, evidence location, reviewer, approval or exception, and
production-readiness boundary impact.
