# Production Readiness Boundary

Current release marker: `v0.1.0`.

This project targets production-assessable documentation maturity, not a blanket
production-ready claim.

## Valid Claims

- The repository is an MVP/community automation framework for NKP ZeroTouch
  deployment preparation and guarded local execution.
- The public demo is simulated and does not provision infrastructure.
- Connected, proxied, and air-gapped deployment modes are modeled.
- Apply-class actions require explicit operator review and approval.

## Claims That Require More Evidence

Do not claim broadly production-validated status without environment-specific
evidence for live NKP deployment execution, registry push, upgrade or destroy,
backup/restore, proxy/air-gapped transfer controls, enterprise integrations,
monitoring, incident response, and support ownership.

## Operational Status Table

| Operational status | Status |
|---|---|
| Architecture documented | PASS |
| Installation documented | PASS |
| Security boundaries documented | PASS |
| UAT procedure available | PASS |
| UAT executed | LAB/PARTIAL |
| Operator runbooks | PASS |
| Recovery tested | PARTIAL |
| Production validated | NO |
| Vendor supported | NO |

## Maturity Levels

| Level | Meaning |
|---|---|
| L0 Experimental | Code/demo exists |
| L1 Documented | Architecture, installation, and limitations documented |
| L2 Testable | Defined test cases and acceptance criteria |
| L3 UAT-ready | Repeatable UAT plan, expected results, and evidence requirements |
| L4 Operator-controlled | Runbooks, rollback, escalation, RBAC, and operational controls |
| L5 Production-assessable | Security, DR, monitoring, lifecycle, governance, and formal acceptance evidence |

Target documentation maturity for this repository is L5
production-assessable. Current evidence must still be evaluated per deployment.

## Unsupported or Out-of-Scope Claims

- Nutanix-supported status.
- Production-ready status from static demo evidence.
- Unapproved apply, upgrade, destroy, or rollback.
- Infrastructure success from local-only validation.
- Registry or air-gapped integrity without checksum and transfer records.

## Review Cadence

Review this boundary before releases, before live UAT, after failures, and after
adding new apply-class behavior.
