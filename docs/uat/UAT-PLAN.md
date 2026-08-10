# NKP ZeroTouch UAT Plan

Current release marker: `v0.1.0`.

This plan defines controlled UAT for the NKP ZeroTouch Framework. It separates
simulated demo proof, local CLI proof, lab proof, controlled UAT, and
production validation.

## Maturity Target

Target maturity: operator-controlled / deployment-controlled.

Current maturity: MVP/community automation framework with a simulated public
demo, local CLI phases, local dashboard governance, and guarded apply-class
execution paths.

Production claims require environment-specific UAT evidence and organization
acceptance.

## UAT Objectives

- Prove environment YAML can be validated for connected, proxied, and
  air-gapped modes.
- Prove preparation and generation produce reviewable artifacts.
- Prove approvals and point-of-no-return boundaries are understood.
- Prove evidence records can support handoff or production assessment.

## Required UAT Stages

1. Documentation review.
2. Environment config review.
3. Pre-deployment validation.
4. Prepare and generate artifacts.
5. Approval and point-of-no-return review.
6. Controlled execution or approved simulation.
7. Post-deployment validation.
8. Failed-deployment recovery exercise.
9. Rollback/abort tabletop or lab run.
10. Evidence package review.

## Evidence Classes

| Evidence class | Meaning | Production claim allowed |
|---|---|---|
| Simulated demo | Static/demo UI proof | No |
| Local CLI | Local validation/generation proof | No |
| Lab | Controlled non-production target proof | Lab-scoped only |
| Controlled UAT | Approved representative environment proof | Scenario-scoped only |
| Production validation | Accepted production-like target proof | Scope-specific |

## Exit Criteria

Controlled UAT is complete when required runbooks are reviewed, UAT cases have
outcomes, evidence is retained, point-of-no-return approvals are captured, and
production-readiness gaps are recorded.
