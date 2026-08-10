# RB-008 - Post-Deployment Validation

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-008 |
| Title | Post-deployment validation |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Validate that a completed NKP deployment matches the approved plan.

## Scope

Covers verification commands, kubeconfig capture, cluster state review, and UAT
evidence packaging.

## Preconditions

- Deployment phase reached terminal state.
- Target system is reachable.
- Generated artifacts and approval references are available.

## Required Role/RBAC

Deployment operator, reviewer, and target-system owner where needed.

## Required Inputs

- Environment config and hash.
- Run ID.
- Approval ID.
- Target environment.

## Dependencies

- NKP CLI.
- Target cluster/API reachability.
- Local `.zt` run state.

## Risk/Impact

Validation is intended to be read-only. Misleading validation can overstate UAT
or production readiness.

## Point Of No Return

There is no target-changing point of no return in this runbook. If validation
requires a corrective change, stop and use failed-deployment recovery.

## Procedure

1. Run the framework `verify` phase.
2. Capture kubeconfig state if approved.
3. Compare target state with generated artifacts.
4. Record warnings or exceptions.
5. Capture evidence using [UAT-EVIDENCE.md](../uat/UAT-EVIDENCE.md).
6. Mark scenario outcome.

## Validation

- Verify phase succeeds or exceptions are documented.
- Target observations match the plan.
- Evidence record is complete.

## Expected Result

Deployment has a clear acceptance result and handover evidence.

## Failure Conditions

- Verify phase fails.
- Target state differs from expected state.
- Evidence is incomplete.

## Recovery/Rollback

Use [RB-007](RB-007-failed-deployment-recovery.md) for discrepancies.

## Evidence To Capture

- Verify output.
- Kubeconfig state reference if allowed.
- Target state summary.
- Acceptance result.
- Exceptions and owners.

## Audit Requirements

Keep validation evidence with the original deployment record.

## Escalation

Escalate validation failures that affect deployment acceptance.

## References

- [Lab Evidence Template](../lab-evidence-template.md)
- [UAT Evidence](../uat/UAT-EVIDENCE.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Verify output | CLI/dashboard run | Yes |
| Acceptance result | UAT record | Yes |
| Exceptions | Change/UAT record | Conditional |
