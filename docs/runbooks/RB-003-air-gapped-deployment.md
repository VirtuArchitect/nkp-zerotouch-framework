# RB-003 - Air-Gapped Deployment

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-003 |
| Title | Air-gapped deployment |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Run an NKP deployment flow in a disconnected environment using local bundles,
local registries, and approved transfer evidence.

## Scope

Covers air-gapped validation, offline bundle use, local registry planning,
guarded deployment execution, and verification.

## Preconditions

- `environment.type` is `air-gapped`.
- Air-gapped NKP bundle exists locally.
- Bundle checksums and transfer record are available.

## Required Role/RBAC

Deployment operator, registry administrator, transfer owner, and approver.

## Required Inputs

- Air-gapped environment YAML.
- NKP air-gapped bundle path.
- Bundle checksum and approval ID.

## Dependencies

- Local registry.
- Transferred NKP bundle.
- Prism Central and target networks inside the disconnected environment.

## Risk/Impact

Air-gapped deployment has high artifact integrity risk.

## Point Of No Return

The point of no return is the first local registry push that imports NKP bundle
content into the target registry, or any `deploy --apply` action.

## Procedure

1. Verify bundle checksum and transfer record.
2. Validate the air-gapped config.
3. Prepare and generate artifacts.
4. Review generated registry and deployment scripts.
5. Obtain approval.
6. Push to the local registry if required.
7. Run guarded deployment.
8. Verify cluster and capture evidence.

## Validation

- Bundle paths and checksums match.
- Local registry is reachable.
- Generated artifacts reference local sources only.

## Expected Result

Air-gapped deployment completes using approved local artifacts.

## Failure Conditions

- Bundle checksum mismatch.
- Missing bundle content.
- Registry push failure.
- Partial deployment state.

## Recovery/Rollback

Use [RB-007](RB-007-failed-deployment-recovery.md) and
[RB-010](RB-010-rollback-abort.md).

## Evidence To Capture

- Bundle path and checksum.
- Transfer approval.
- Config hash.
- Registry push output.
- Deployment output.
- Target verification.

## Audit Requirements

Keep transfer, checksum, registry, deployment, and target evidence together.

## Escalation

Escalate if artifact integrity is uncertain or registry state is partially
changed.

## References

- [Air-gapped runbook](../runbook-air-gapped.md)
- [Offline Bundle Preparation](RB-005-offline-bundle-preparation.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Bundle checksum | Transfer record | Yes |
| Registry push | CLI/dashboard run | Conditional |
| Target verification | NKP/Nutanix target | Yes |
