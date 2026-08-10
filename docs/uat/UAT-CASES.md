# NKP ZeroTouch UAT Cases

Current release marker: `v0.1.0`.

Use these cases to test repeatable operator behavior.

| ID | Case | Required result | Evidence |
|---|---|---|---|
| UAT-001 | Connected config validation | Validation pass or accepted warnings | Config hash and validation output |
| UAT-002 | Proxied config validation | Proxy/no-proxy checks reviewed | Config hash, proxy review, validation output |
| UAT-003 | Air-gapped config validation | Bundle and registry requirements verified | Config hash, bundle checksum, validation output |
| UAT-004 | Prepare workspace | `.zt` workspace created for approved config | Prepare output and workspace path |
| UAT-005 | Generate artifacts | Reviewable artifacts created | Generated files and config hash |
| UAT-006 | Point-of-no-return review | Operator identifies apply boundary | Approval or tabletop record |
| UAT-007 | Registry planning/execution | Registry action is approved or simulated | Registry output or simulation marker |
| UAT-008 | Deployment execution | Deploy action is approved or simulated | Command output and target/simulation evidence |
| UAT-009 | Post-deployment validation | Verify output captured | Verify output and acceptance result |
| UAT-010 | Failed deployment recovery | Failure is classified before rerun | Failure transcript and recovery decision |
| UAT-011 | Rollback/abort | Abort or rollback path is documented | Decision record and final state |
| UAT-012 | Dashboard governance | Approval/audit/run records are visible | Dashboard record or screenshot |

## Outcome Values

- Pass: objective completed and evidence is complete.
- Pass with exception: objective completed with accepted exception.
- Partial: useful evidence exists but objective is incomplete.
- Fail: remediation required before readiness claim.
- Not tested: intentionally deferred with owner and reason.

## Rules

- Do not convert a simulated demo result into infrastructure proof.
- Do not run apply-class actions without approval.
- Do not rerun failed deployment actions until target state is understood.
- Do not call UAT complete while evidence is missing.
