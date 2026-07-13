# Production Persistence

The local console currently stores runtime state under `.zt`. That is suitable
for an operator workstation, lab validation, and development. The
`session_store=file` setting persists local console sessions under
`.zt/settings/sessions.json` so restarts do not require memory-only sessions.
Production multi-user use should move durable shared state into Postgres.

Recommended Postgres-backed objects:

- Console accounts and role assignments.
- Sessions or session references for shared multi-user operation.
- Jobs, approvals, retries, and cancellations.
- Audit events.
- Plan review decisions.
- Environment metadata indexes.
- Health snapshots and integration probe results.

Secrets should not be stored in Postgres. Store only references to Vault or an
equivalent external secret backend.

Migration approach:

1. Keep environment YAML as the deployment source of truth.
2. Add a storage interface around `.zt` reads/writes.
3. Implement a Postgres backend for jobs, audit, approvals, and reviews.
4. Keep generated artifacts on disk or object storage with database metadata.
5. Add backup and restore procedures for both database state and generated
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
