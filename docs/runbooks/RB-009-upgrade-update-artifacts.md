# RB-009 - Upgrade/Update Artifacts

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-009 |
| Title | Upgrade/update artifacts |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Update NKP deployment artifacts, framework code, bundle references, or upgrade
plans with compatibility and rollback evidence.

## Scope

Covers artifact refresh, bundle update, generated upgrade planning, and guarded
upgrade execution.

## Preconditions

- Current version and target version are known.
- Current state is backed up or exported where applicable.
- Compatibility notes are reviewed.

## Required Role/RBAC

Deployment operator, approver, artifact owner, and target-system owner for
upgrade apply.

## Required Inputs

- Current and target versions.
- Bundle/artifact references and checksums.
- Existing config hash.
- Approval ID.

## Dependencies

- NKP bundle/artifacts.
- Local `.zt` state.
- Registry if image updates are required.

## Risk/Impact

Upgrade can change cluster behavior, deployed artifacts, registry state, and
recovery options.

## Point Of No Return

The point of no return is replacing approved artifacts in the deployment path,
pushing upgraded registry content, or running an upgrade apply command.

## Procedure

1. Record current versions and artifact checksums.
2. Prepare target artifacts and checksums.
3. Generate or review upgrade plan.
4. Confirm rollback/abort path.
5. Obtain approval.
6. Apply artifact update or upgrade only for the approved plan.
7. Run post-update validation.

## Validation

- Target artifacts match approved checksums.
- Upgrade plan matches approved inputs.
- Post-update validation succeeds.

## Expected Result

Artifacts or target deployment are updated with traceable evidence.

## Failure Conditions

- Version mismatch.
- Checksum mismatch.
- Upgrade plan drift.
- Partial target upgrade.

## Recovery/Rollback

Use [RB-010](RB-010-rollback-abort.md). Do not replace rollback artifacts before
the update is accepted.

## Evidence To Capture

- Current and target versions.
- Artifact checksums.
- Upgrade plan.
- Approval ID.
- Validation output.
- Rollback reference.

## Audit Requirements

Retain current and target artifact evidence until the upgrade is accepted.

## Escalation

Escalate if upgrade state is partial or rollback feasibility is unclear.

## References

- [Upgrade Destroy Policy](../upgrade-destroy-policy.md)
- [Post-Deployment Validation](RB-008-post-deployment-validation.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Version/checksum | Artifact records | Yes |
| Upgrade plan | Generated artifacts | Yes |
| Validation | CLI/dashboard run | Yes |
