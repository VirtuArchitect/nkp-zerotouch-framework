# RB-XXX - Title

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-XXX |
| Title | Title |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Describe the controlled operational outcome.

## Scope

State which environment modes, CLI phases, dashboard actions, and target systems
are covered.

## Preconditions

- Environment config is reviewed.
- Required bundle, registry, proxy, and Prism Central details are available.

## Required Role/RBAC

State the minimum operator, approver, host, registry, and target-system access.

## Required Inputs

- Environment config.
- Bundle or artifact reference.
- Approval ID where applicable.

## Dependencies

- NKP bundle and CLI.
- Local `.zt` workspace.
- Prism Central and deployment target reachability.

## Risk/Impact

Describe infrastructure, registry, credential, generated-state, and evidence
impact.

## Point Of No Return

State the exact command, flag, dashboard action, or handoff where the operation
crosses from preparation into target modification.

## Procedure

1. Validate inputs.
2. Review generated plan/artifacts.
3. Obtain approval where required.
4. Execute only the approved phase.
5. Capture evidence.

## Validation

State the expected post-action checks.

## Expected Result

Describe the successful final state.

## Failure Conditions

State conditions that require stop, recovery, or escalation.

## Recovery/Rollback

Describe recovery steps or reference another runbook.

## Evidence To Capture

- Operator.
- Timestamp.
- Config path and hash.
- Approval ID.
- Command and output.

## Audit Requirements

Keep approvals, command output, generated artifacts, and target evidence with
the UAT or change record.

## Escalation

Escalate when target state is unknown, partial, or inconsistent.

## References

- [Runbook Index](README.md)
- [UAT Evidence](../uat/UAT-EVIDENCE.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Config hash | Environment YAML | Yes |
| Approval | Dashboard/change record | Conditional |
| Command output | CLI/dashboard run | Yes |
