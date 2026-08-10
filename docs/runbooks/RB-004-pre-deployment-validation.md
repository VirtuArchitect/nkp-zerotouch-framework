# RB-004 - Pre-Deployment Validation

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-004 |
| Title | Pre-deployment validation |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Validate NKP environment inputs before generated artifacts or apply-class
commands are trusted.

## Scope

Covers schema validation, duplicate identity checks, mode-specific checks,
bundle discovery, endpoint reachability, and readiness review.

## Preconditions

- Environment YAML is available.
- Secrets are referenced through the approved local process.
- Bundle, proxy, registry, and target values are filled where required.

## Required Role/RBAC

Deployment operator. Approver review is required before accepting warnings for
UAT.

## Required Inputs

- Environment YAML.
- Secrets reference where applicable.
- Bundle or CLI path.
- Target endpoint list.

## Dependencies

- `tools/zt_config.py`.
- `scripts/zt.*`.
- Schema files under `configs/schema/`.

## Risk/Impact

Validation is non-mutating, but accepting warnings can move weak inputs toward
deployment.

## Point Of No Return

There is no infrastructure point of no return in this runbook. It must finish
before registry, deploy, upgrade, or destroy phases.

## Procedure

1. Run validation for the selected environment.
2. Review errors and warnings.
3. Confirm duplicate identity checks pass.
4. Confirm mode-specific checks.
5. Record accepted warnings.
6. Stop if any blocking error remains.

## Validation

- Validation returns valid or warnings accepted by the approver.
- Blocking errors are resolved.
- Evidence includes config hash and validation output.

## Expected Result

The environment is ready for preparation and artifact generation.

## Failure Conditions

- Schema errors remain.
- Endpoint checks fail unexpectedly.
- Bundle or registry requirements are missing.
- Warnings are accepted without owner or reason.

## Recovery/Rollback

Correct inputs and rerun validation. Do not proceed to apply-class actions.

## Evidence To Capture

- Config path and hash.
- Validation command output.
- Accepted warnings and approver.
- Endpoint/bundle checks.

## Audit Requirements

Attach validation output to the UAT or change record before deployment.

## Escalation

Escalate unresolved validation failures to the platform owner for that domain.

## References

- [Validation](../validation.md)
- [UAT Cases](../uat/UAT-CASES.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Validation result | CLI/dashboard | Yes |
| Accepted warnings | Change/UAT record | Conditional |
| Config hash | Environment YAML | Yes |
