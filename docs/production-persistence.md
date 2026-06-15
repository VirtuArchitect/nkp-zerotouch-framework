# Production Persistence

The local console currently stores runtime state under `.zt`. That is suitable
for an operator workstation, lab validation, and development. Production
multi-user use should move durable shared state into Postgres.

Recommended Postgres-backed objects:

- Console accounts and role assignments.
- Sessions or session references.
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
