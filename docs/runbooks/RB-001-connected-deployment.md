# RB-001 - Connected Deployment

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-001 |
| Title | Connected deployment |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Run an NKP deployment flow when the deployment host can reach upstream
registries, repositories, Prism Central, and required internet endpoints.

## Scope

Covers connected validation, preparation, generation, registry planning,
guarded deployment execution, and verification.

## Preconditions

- `environment.type` is `connected`.
- NKP standard bundle or CLI path is available.
- Prism Central endpoint and credentials are approved for UAT.

## Required Role/RBAC

Deployment operator for validate/prepare/generate; approver and target-system
operator for apply-class phases.

## Required Inputs

- Connected environment YAML.
- NKP bundle path or CLI version.
- Approval ID for apply-class phases.

## Dependencies

- Internet and registry reachability.
- Prism Central reachability.
- Local `.zt` workspace.

## Risk/Impact

Connected deployment can create or modify cluster resources and consume registry
and infrastructure capacity.

## Point Of No Return

The point of no return is the first approved `registry` push that modifies a
registry or any `deploy --apply` action that sends changes toward the target.

## Procedure

1. Run `validate`.
2. Run `prepare`.
3. Run `generate` and review generated artifacts.
4. Confirm approval for apply-class actions.
5. Run `registry` only if required.
6. Run guarded `deploy`.
7. Run `verify` and capture evidence.

## Validation

- Validation returns pass or accepted warnings.
- Generated artifacts match approved inputs.
- Verification records are captured.

## Expected Result

Connected deployment completes with traceable config, approval, run, and target
evidence.

## Failure Conditions

- Endpoint reachability fails.
- Generated artifacts differ from reviewed inputs.
- Apply-class command is requested without approval.

## Recovery/Rollback

Use [RB-007](RB-007-failed-deployment-recovery.md) and
[RB-010](RB-010-rollback-abort.md). Do not rerun blindly.

## Evidence To Capture

- Config path and hash.
- NKP version and bundle path.
- Approval ID.
- CLI/dashboard output.
- Target verification output.

## Audit Requirements

Bind approval to the exact config hash and generated artifacts.

## Escalation

Escalate when deployment starts but target state cannot be verified.

## References

- [Connected runbook](../runbook-connected.md)
- [Phases](../phases.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Config hash | Environment YAML | Yes |
| Approval | Dashboard/change record | Apply only |
| Target verification | NKP/Nutanix target | Yes |
