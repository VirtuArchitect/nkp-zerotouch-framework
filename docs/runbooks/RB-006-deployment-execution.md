# RB-006 - Deployment Execution

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-006 |
| Title | Deployment execution |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Execute an approved NKP deployment phase against a controlled target.

## Scope

Covers guarded deploy execution from generated artifacts. Registry, upgrade,
destroy, and rollback are covered by separate runbooks.

## Preconditions

- Pre-deployment validation passed.
- Generated artifacts are reviewed.
- Approval binds to the exact config hash and generated plan.

## Required Role/RBAC

Deployment operator plus approver. Target-system access must be limited to the
approved environment.

## Required Inputs

- Environment config and hash.
- Generated artifact path.
- Approval ID.
- Target environment.

## Dependencies

- NKP CLI.
- Generated `.zt` workspace.
- Prism Central and target network reachability.

## Risk/Impact

Deployment execution can create or modify NKP and Nutanix infrastructure.

## Point Of No Return

The point of no return is the first command that runs generated deployment
logic in apply mode, including `deploy --apply`.

## Procedure

1. Confirm validation and generated artifact evidence.
2. Confirm approval and maintenance window.
3. Recompute config hash.
4. Confirm no generated artifact drift.
5. Execute only the approved deployment command.
6. Monitor output and target-side task status.
7. Run post-deployment validation.

## Validation

- Deployment command reaches expected terminal state.
- Target-side state matches generated plan.
- Evidence includes approval, config, command, and target output.

## Expected Result

The approved deployment completes with evidence for UAT or change acceptance.

## Failure Conditions

- Config hash differs from approval.
- Generated artifacts changed after approval.
- Command fails or exits unknown.

## Recovery/Rollback

Use [RB-007](RB-007-failed-deployment-recovery.md). Do not rerun until target
state is understood.

## Evidence To Capture

- Approval ID.
- Config hash.
- Generated artifact path.
- Command transcript.
- Target-side tasks.

## Audit Requirements

Keep approval, config, generated artifacts, run output, and target evidence
together.

## Escalation

Escalate partial or unknown target state immediately.

## References

- [Pre-Deployment Validation](RB-004-pre-deployment-validation.md)
- [Post-Deployment Validation](RB-008-post-deployment-validation.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Approval | Dashboard/change record | Yes |
| Command transcript | CLI/dashboard run | Yes |
| Target task | NKP/Nutanix target | Yes |
