# RB-005 - Offline Bundle Preparation

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-005 |
| Title | Offline bundle preparation |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Prepare and verify NKP offline bundles before transfer into a disconnected or
controlled environment.

## Scope

Covers bundle inventory, checksum capture, transfer packaging, and handoff to
air-gapped deployment. It does not perform deployment.

## Preconditions

- Target NKP version is approved.
- Source bundle location is trusted.
- Transfer process and destination owner are known.

## Required Role/RBAC

Artifact owner, transfer owner, registry owner where applicable, and approver.

## Required Inputs

- NKP bundle path.
- Expected NKP version.
- Destination environment.
- Transfer ticket.

## Dependencies

- Local checksum tooling.
- Approved transfer media or artifact repository.
- Air-gapped deployment runbook.

## Risk/Impact

Incorrect or untracked offline bundles can compromise deployment integrity.

## Point Of No Return

The point of no return is the signed or approved transfer package. Corrections
after that require a new package and transfer record.

## Procedure

1. Inventory bundle contents.
2. Record NKP version and bundle type.
3. Compute checksums.
4. Confirm destination requirements.
5. Transfer through the approved process.
6. Verify checksum after transfer.
7. Hand off to [RB-003](RB-003-air-gapped-deployment.md).

## Validation

- Source and destination checksums match.
- Bundle type matches the target environment.
- Transfer record is complete.

## Expected Result

The offline bundle is ready for air-gapped registry/deployment use.

## Failure Conditions

- Checksum mismatch.
- Missing bundle content.
- Wrong NKP version.
- Transfer record is incomplete.

## Recovery/Rollback

Reject the bundle and produce a corrected package.

## Evidence To Capture

- Bundle version.
- Bundle path.
- Checksums.
- Transfer ticket.
- Destination verification output.

## Audit Requirements

Keep source and destination checksum evidence with the transfer approval.

## Escalation

Escalate checksum mismatch or missing content to the artifact owner.

## References

- [Air-gapped Deployment](RB-003-air-gapped-deployment.md)
- [Environment Types](../environment-types.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Source checksum | Staging host | Yes |
| Destination checksum | Air-gapped host | Yes |
| Transfer approval | Transfer ticket | Yes |
