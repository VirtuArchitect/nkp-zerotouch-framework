# RB-007 - Failed Deployment Recovery

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-007 |
| Title | Failed deployment recovery |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Recover from failed, cancelled, or unknown NKP deployment phases.

## Scope

Covers failed registry, deploy, upgrade, destroy, and verification flows.

## Preconditions

- Failed run, command transcript, or dashboard run ID is known.
- Generated artifacts and config hash are available.
- Target-side state can be inspected.

## Required Role/RBAC

Deployment operator, approver, and target-system owner for remediation.

## Required Inputs

- Run ID or transcript.
- Config path and hash.
- Generated artifact path.
- Error text and timestamp.

## Dependencies

- Local `.zt` state.
- CLI/dashboard run records.
- Target Nutanix and NKP visibility.

## Risk/Impact

Blind rerun can create duplicates, overwrite state, or hide partial deployment.

## Point Of No Return

The recovery point of no return is any remediation, rollback, rerun, or destroy
command that changes target state after the failure.

## Procedure

1. Stop dependent phases.
2. Preserve logs, `.zt` state, generated artifacts, and config.
3. Identify the last completed phase.
4. Inspect target-side resources.
5. Classify the failure.
6. Choose recovery: fix inputs, resume, roll back, abort, or escalate.
7. Obtain approval for any target-changing recovery.
8. Capture final evidence.

## Validation

- Completed and incomplete actions are documented.
- Target-side state is known or explicitly classified unknown.
- Recovery decision is approved.

## Expected Result

Failure is closed with a defensible target-state assessment.

## Failure Conditions

- Target state cannot be determined.
- Logs or generated artifacts are missing.
- Rerun idempotency cannot be proven.

## Recovery/Rollback

Use [RB-010](RB-010-rollback-abort.md) for rollback/abort decisions.

## Evidence To Capture

- Original run ID.
- Error output.
- Config hash.
- Target-side state.
- Recovery decision and approval.

## Audit Requirements

Recovery evidence must link original failure, assessment, approval, and final
state.

## Escalation

Escalate immediately when infrastructure state is unknown or partially changed.

## References

- [Rollback/Abort](RB-010-rollback-abort.md)
- [UAT Evidence](../uat/UAT-EVIDENCE.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Failure transcript | CLI/dashboard run | Yes |
| Target state | NKP/Nutanix target | Yes |
| Recovery approval | Change record | Conditional |
