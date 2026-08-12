# Production Persistence

The local console currently stores runtime state under `.zt`. That is suitable
for an operator workstation, lab validation, and development. The
`session_store=file` setting persists local console sessions under
`.zt/settings/sessions.json` so restarts do not require memory-only sessions.
The `session_store=postgres` setting stores console session records in Postgres
when Postgres is enabled, a password-free DSN is saved under Settings >
Integrations, and optional `psycopg` or `psycopg2` is installed in the dashboard
runtime. If the database account requires a password, provide it through
`ZT_POSTGRES_PASSWORD`; do not embed it in the saved DSN. Production multi-user
use should move durable shared state into Postgres.

Current Postgres-backed objects:

- Console sessions in `zt_console_sessions`.
- Optional audit event mirror records in `zt_console_audit_events`.
- External validation records remain local JSON metadata under
  `.zt/external-validations/`.

Recommended future Postgres-backed objects:

- Console accounts and role assignments.
- Jobs, approvals, retries, and cancellations.
- Plan review decisions.
- Environment metadata indexes.
- Health snapshots and integration probe results.
- External validation metadata after a schema and retention model are accepted.

Secrets should not be stored in Postgres or embedded in dashboard integration
settings. Store only references to Vault or an equivalent external secret
backend. The dashboard rejects Postgres DSNs that include a password and redacts
any previously saved password-bearing DSN before rendering the integrations
page.

Migration approach:

1. Keep environment YAML as the deployment source of truth.
2. Use Postgres-backed sessions for shared console deployments that need durable
   server-side login state.
3. Enable the Postgres audit mirror for deployments that require central audit
   search while keeping `.zt/audit/events.jsonl` as the local append-only log.
4. Add a storage interface around remaining `.zt` reads/writes.
5. Implement a Postgres backend for jobs, approvals, and reviews.
6. Keep generated artifacts on disk or object storage with database metadata.
7. Add backup and restore procedures for both database state and generated
   artifacts.

## Production Readiness Checklist

Before production use, confirm:

- Environment files pass `tools/zt_config.py validate` with the JSON schema
  dependency installed.
- Generated `deploy.sh`, `registry.sh`, and `secrets.env` files come from the
  renderer and preserve shell quoting.
- The first dashboard admin is created through localhost or with
  `ZT_BOOTSTRAP_TOKEN` set for exposed binds.
- Secrets are sourced from Vault or an equivalent external backend; committed
  files contain placeholders only.
- Apply, registry, upgrade, and destroy workflows are approval-gated and backed
  by change records.
- Backups cover `.zt` state, generated artifacts, future database state, and
  the operator run evidence needed for audit.
- Live runners are isolated, patched, and granted only the Prism Central,
  registry, bundle, SSH, and network access required for the target environment.
- Production-channel environments have passing external validation evidence
  records for Prism authorization and deployment UAT, with links to reviewed
  evidence packs, tickets, or runbook outputs.
