# NKP ZeroTouch Runbooks

Current release marker: `v0.1.0`.

Target maturity: operator-controlled / deployment-controlled.

Current maturity: MVP/community automation framework with a simulated public
demo, local CLI phases, local dashboard governance, and guarded apply-class
execution paths. Production claims require environment-specific UAT evidence.

## Control Matrix

| ID | Operation | Risk | Approval | Point of no return | Evidence | Status |
|---|---|---:|---|---|---|---|
| [RB-001](RB-001-connected-deployment.md) | Connected deployment | High | Required for apply | `registry` or `deploy --apply` | Required | Draft |
| [RB-002](RB-002-proxied-deployment.md) | Proxied deployment | High | Required for apply | Proxy-bound `registry` or `deploy --apply` | Required | Draft |
| [RB-003](RB-003-air-gapped-deployment.md) | Air-gapped deployment | High | Required for apply | Offline registry push or `deploy --apply` | Required | Draft |
| [RB-004](RB-004-pre-deployment-validation.md) | Pre-deployment validation | Medium | Review required | None; validation is non-mutating | Required | Draft |
| [RB-005](RB-005-offline-bundle-preparation.md) | Offline bundle preparation | Medium | Required for transfer | Signed/approved transfer package | Required | Draft |
| [RB-006](RB-006-deployment-execution.md) | Deployment execution | Critical | Required | Any apply-class command | Required | Draft |
| [RB-007](RB-007-failed-deployment-recovery.md) | Failed deployment recovery | Critical | Required for rerun/remediation | Recovery command against target state | Required | Draft |
| [RB-008](RB-008-post-deployment-validation.md) | Post-deployment validation | Medium | Review required | None; validation is read-only | Required | Draft |
| [RB-009](RB-009-upgrade-update-artifacts.md) | Upgrade/update artifacts | High | Required | Upgrade apply or artifact replacement | Required | Draft |
| [RB-010](RB-010-rollback-abort.md) | Rollback/abort | Critical | Required except emergency stop | Abort/rollback against partial state | Required | Draft |

## Standard Runbook Format

Each runbook uses this structure:

1. Metadata
2. Purpose
3. Scope
4. Preconditions
5. Required role/RBAC
6. Required inputs
7. Dependencies
8. Risk/impact
9. Point of no return
10. Procedure
11. Validation
12. Expected result
13. Failure conditions
14. Recovery/rollback
15. Evidence to capture
16. Audit requirements
17. Escalation
18. References
19. Evidence mapping

Use [RUNBOOK-TEMPLATE.md](RUNBOOK-TEMPLATE.md) for new runbooks.

## Related Legacy Guides

- [Connected runbook](../runbook-connected.md)
- [Proxied runbook](../runbook-proxied.md)
- [Air-gapped runbook](../runbook-air-gapped.md)
