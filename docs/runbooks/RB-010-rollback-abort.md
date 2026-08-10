# RB-010 - Rollback/Abort

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-010 |
| Title | Rollback/abort |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Abort or roll back NKP deployment work after an unsafe condition, failed phase,
or rejected validation result.

## Scope

Covers controlled abort and rollback decision-making. It does not promise a
universal automatic rollback for every target state.

## Preconditions

- Original config, generated artifacts, and run transcript are preserved.
- Target state is inspected.
- Rollback option is known or explicitly unknown.

## Required Role/RBAC

Deployment operator, approver, and target-system owner.

## Required Inputs

- Original run ID.
- Failure/rejection reason.
- Target-state assessment.
- Rollback or abort plan.
- Approval ID.

## Dependencies

- Target-system access.
- Local `.zt` state.
- Backup/restore artifacts where available.

## Risk/Impact

Rollback and abort actions can be more destructive than the original deployment
if target state is misunderstood.

## Point Of No Return

The rollback point of no return is any abort, delete, restore, or destroy action
that modifies partially deployed target resources.

## Procedure

1. Stop dependent work.
2. Preserve logs and artifacts.
3. Confirm target-state assessment.
4. Decide whether abort, rollback, remediation, or no-action is safest.
5. Obtain approval for target-changing action.
6. Execute only the approved abort/rollback step.
7. Validate final target state.
8. Record residual risks.

## Validation

- Target state is documented after abort/rollback.
- No dependent phase remains active.
- Residual resources or exceptions are listed.

## Expected Result

The deployment is safely stopped, rolled back, or left in a documented accepted
state.

## Failure Conditions

- Target-state assessment is incomplete.
- Rollback command fails.
- Residual resources remain without owner.

## Recovery/Rollback

Escalate to platform/vendor support. Avoid further automated changes until
state is understood.

## Evidence To Capture

- Original run and failure.
- Target-state assessment.
- Rollback/abort approval.
- Command output.
- Final validation output.

## Audit Requirements

The rollback record must link the original run, recovery decision, approval, and
final target state.

## Escalation

Escalate critical or unknown rollback states immediately.

## References

- [Failed Deployment Recovery](RB-007-failed-deployment-recovery.md)
- [Upgrade Destroy Policy](../upgrade-destroy-policy.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Target-state assessment | NKP/Nutanix target | Yes |
| Approval | Change record | Conditional |
| Final validation | CLI/dashboard run | Yes |
