# Enterprise Controls

This document summarizes the operational controls added around the ZeroTouch
deployment flow.

## API Layer

Authenticated JSON endpoints are available for automation and future UI
decoupling:

- `/api/status`
- `/api/environments`
- `/api/jobs`
- `/api/jobs/log?id=<job-id>`
- `/api/locks`
- `/api/change-records`

## Environment Locking

The console records a lock under `.zt/locks/` while prepare, generate, registry,
deploy, upgrade, or destroy jobs run for an environment. This prevents
overlapping operations against the same target.

## Plan Hashing

Plan review decisions store SHA256 hashes for generated deploy and registry
plans/scripts. If generated artifacts change after approval, the console reports
the review as stale.

## Change Records

Apply requests create change records under `.zt/change-records/` with:

- Job ID.
- Environment.
- Action.
- Requester.
- Plan hashes.
- Rollback notes.
- Job completion status.

## Drift Detection

The Drift page highlights:

- Missing generation.
- Generated plan changes after approval.
- Environment YAML changes after prepare.
- Missing verification reports.

## Release Channels

Release channels define promotion lanes such as `dev`, `lab`, `pilot`, and
`production`. Production channels should require plan review, backup evidence,
and elevated approvals.

Apply jobs use the higher of the action approval threshold and the configured
release-channel approval threshold.

## Apply Gates

Apply requests are blocked when:

- Plan review is missing, rejected, or stale.
- A production environment is missing required backup evidence.
- Drift detection reports blocking signals.
- The environment has an active lock.

## Restore Planning

The Restore page generates a restore plan from backup manifests and keeps the
actual copy-back procedure manual and deliberate.

## Secret and Identity Checks

The console checks required runtime secret keys by presence and uses those
values for optional authenticated health probes. Prism Central is probed through
the configured endpoint with `NUTANIX_PC_USERNAME` and `NUTANIX_PC_PASSWORD`.
Registry readiness is probed through `/v2/` with `ZT_REGISTRY_USERNAME` and
`ZT_REGISTRY_PASSWORD`.

OIDC metadata is probed for discovery readiness, while full authorization-code
login remains a future production integration item.
