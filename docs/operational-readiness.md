# Operational Readiness

This framework is targeted at operations teams deploying Nutanix Kubernetes
Platform across connected, proxied, and air-gapped environments.

## Required Inputs

Before live deployment, operations teams must provide:

- Real Prism Central endpoint and credentials.
- Nutanix cluster, subnet, project, image, and storage container names.
- Cluster sizing, Kubernetes version, CIDR ranges, endpoint IP, and SSH details.
- Standard or air-gapped NKP bundle path mounted into the runner.
- Registry endpoint, namespace, CA policy, and credentials for air-gapped use.
- Proxy settings for proxied environments.
- Approved NTP, DNS, certificate, firewall, and routing details.
- Kubeconfig capture location after deployment.

## Current Console Capabilities

- Local login/logout with password-hashed RBAC accounts.
- Local account and role management.
- Environment create, edit, and delete.
- Environment identity safeguards for duplicate names, cluster names, API VIPs, and registry namespaces.
- CSRF protection on authenticated POST forms.
- Route-level RBAC for operations, settings, jobs, approvals, artifacts, audit, and health.
- Safe action execution through background jobs: validate, prepare, generate, verify, backup, runs.
- Apply action requests through approval-gated jobs.
- Job approval, reject, cancel, retry, detail, and captured log views.
- Guided setup wizard for first-run source, connection, inventory, network, secrets, environment, and preflight work.
- Lifecycle and readiness status for each environment.
- Formal plan review status before apply approval.
- Kubeconfig capture visibility for post-deploy verification.
- Environment locks to prevent overlapping operations.
- Change records for apply requests.
- Plan hashes to detect artifact changes after review.
- Drift detection for stale plans, changed YAML, and missing verification evidence.
- Backup manifest browsing and release-channel metadata.
- Authenticated JSON endpoints for future automation and frontend decoupling.
- Runs, artifacts, health checks, and append-only audit visibility from `.zt`.
- Artifact viewer and diff workflow for generated plans, reports, logs, state, and configs.
- Local connection, RBAC, database, integration, approval policy, source, inventory, network, provider, and secret-backend settings.
- Enterprise integration contracts and health probes for Postgres, Vault, OIDC, and session-store consistency.

## Required Production Hardening

Before exposing this console beyond a trusted operator workstation:

- Move from memory sessions to file or Postgres-backed durable session storage.
- Connect OIDC/SAML or enterprise SSO to a real identity provider.
- Complete OIDC authorization-code token exchange for production login.
- Connect console state to Postgres if multi-user operation is required.
- Encrypt or externalize all secrets; do not store raw credentials in the repo or database.
- Connect Vault or an equivalent external secret backend.
- Review and tune role separation for authoring, approving, and executing deployment changes.
- Add backup/restore procedures for `.zt` state and future database state.
- Extend health checks from TCP and credential-environment validation to authenticated Prism Central and registry API validation.

## Recommended Operating Model

Use the console for day-to-day preparation, review, and non-destructive actions.
Keep live apply operations deliberate and controlled:

1. Create or edit an environment profile.
2. Run `validate`.
3. Run `prepare`.
4. Run `generate`.
5. Review generated artifacts, compare diffs, and approve runbooks.
6. For air-gapped environments, run registry planning and approved image push.
7. Request live deploy from the controlled CLI window.
8. Obtain required approval under the configured approval policy.
9. Let the approved job run from the prepared runner with approved credentials.
10. Capture kubeconfig.
11. Run `verify`.
12. Capture a run summary and archive artifacts.

## Current Gaps

- No production SSO provider connected yet.
- No external Postgres service connected yet.
- No external Vault service connected yet.
- No live Prism Central authentication validation yet.
- No end-to-end deployment proof against a real NKP lab yet.
