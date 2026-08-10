# RB-002 - Proxied Deployment

Current release marker: `v0.1.0`.

## Metadata

| Field | Value |
|---|---|
| Runbook ID | RB-002 |
| Title | Proxied deployment |
| Version | 1.0 |
| Owner | Platform operations |
| Approver | Platform lead |
| Classification | Internal operational procedure |
| Status | Draft |

## Purpose

Run an NKP deployment flow where external access is mediated by corporate proxy
and no-proxy rules.

## Scope

Covers proxied validation, preparation, generation, registry interaction,
deployment execution, and verification.

## Preconditions

- `environment.type` is `proxied`.
- Proxy and no-proxy values are reviewed.
- Registry access through the proxy is confirmed.

## Required Role/RBAC

Deployment operator plus proxy/network owner review for proxy-sensitive
changes.

## Required Inputs

- Proxied environment YAML.
- Proxy URL and no-proxy list.
- Registry endpoint and approval ID.

## Dependencies

- Proxy service.
- Registry service.
- Prism Central.

## Risk/Impact

Incorrect proxy or no-proxy values can break deployment or make validation
misleading.

## Point Of No Return

The point of no return is a proxy-bound `registry` push or `deploy --apply`
that begins modifying registry state or target infrastructure.

## Procedure

1. Validate the proxied config.
2. Confirm proxy/no-proxy behavior with the network owner.
3. Prepare and generate artifacts.
4. Review proxy exports.
5. Obtain approval.
6. Run registry/deploy only for the approved config.
7. Run verification.

## Validation

- Validation covers proxy-required fields.
- Generated artifacts include expected proxy/no-proxy values.
- Target verification succeeds.

## Expected Result

Proxied deployment completes with approved proxy routing and traceable evidence.

## Failure Conditions

- Proxy authentication fails.
- No-proxy rules route target traffic incorrectly.
- Registry or deployment state is unclear.

## Recovery/Rollback

Use [RB-007](RB-007-failed-deployment-recovery.md). Stop before rerun when proxy
or target state is uncertain.

## Evidence To Capture

- Config hash.
- Proxy/no-proxy review.
- Approval ID.
- Registry and deployment output.
- Verification output.

## Audit Requirements

Record proxy routing assumptions and owner approval with the deployment record.

## Escalation

Escalate to network/proxy owners for proxy failures or ambiguous routing.

## References

- [Proxied runbook](../runbook-proxied.md)
- [Environment Types](../environment-types.md)
- [Runbook Index](README.md)

## Evidence Mapping

| Evidence | Source | Required |
|---|---|---|
| Proxy review | Network/change record | Yes |
| Config hash | Environment YAML | Yes |
| Verification | NKP/Nutanix target | Yes |
