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
- `/api/production-readiness`
- `/api/external-validations`

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

## External Validation Evidence

The console records reviewed external validation metadata under
`.zt/external-validations/`. These records provide a source-controlled workflow
for operator-attested proof that cannot be produced by the repository alone,
including Prism authorization, registry authorization, identity-provider
readiness, Postgres service readiness, Vault service readiness, and deployment
UAT results.

Production readiness requires passing Prism authorization and deployment UAT
external validation records for production-channel environments. Records store
status, scope, summary, evidence reference, timestamp, and recorder metadata
only. They must not contain passwords, tokens, kubeconfig contents, or secret
values.

## Apply Gates

Apply requests are blocked when:

- Plan review is missing, rejected, or stale.
- A production environment is missing required backup evidence.
- A production environment is missing required external validation evidence.
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

OIDC metadata is probed for discovery readiness. The built-in login callback
completes authorization-code exchange for HS256 `id_token` responses, validates
nonce, issuer, audience, and expiry, then maps the identity to an active local
RBAC account. Keep the client secret in `ZT_OIDC_CLIENT_SECRET`; do not save it
in integration settings. RSA/JWKS identity providers remain fail-closed until a
reviewed JWT crypto dependency is added.

Postgres can be used for dashboard sessions when `session_store=postgres`, a
password-free DSN is saved, and optional `psycopg` or `psycopg2` is installed in
the dashboard runtime. Store any required database password in
`ZT_POSTGRES_PASSWORD`, not in the saved DSN.

Postgres can also mirror audit event metadata when `audit_mirror=postgres`.
The console still writes the local append-only `.zt/audit/events.jsonl` record
first, then mirrors event, actor, role, target, status, timestamp, and JSON
detail fields to `zt_console_audit_events`.

HashiCorp Vault can be used as a dashboard secret-presence backend. Save only
Vault URL, namespace, and path metadata under Settings > Secrets, provide
`VAULT_TOKEN` in the runtime environment, and use the console to confirm
required keys exist without rendering secret values.
