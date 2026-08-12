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
- CI validation for every committed environment file and duplicate identity values.
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
- Apply gates that require current plan review and release-channel governance.
- Production readiness view for review, backup, drift, channel, and verification status.
- External validation evidence records for reviewed Prism authorization,
  registry access, identity provider, Postgres, Vault, and deployment UAT proof.
- Restore plan generation from backup manifests with component inventory, active-lock warnings, JSON metadata, change records, and approval-gated manual authorization jobs.
- Runs, artifacts, health checks, and append-only audit visibility from `.zt`.
- Artifact viewer and diff workflow for generated plans, reports, logs, state, and configs.
- Local connection, RBAC, database, integration, approval policy, source, inventory, network, provider, and secret-backend settings.
- Optional file-backed console sessions for local restarts.
- Enterprise integration contracts and health probes for Postgres, Vault, OIDC, and session-store consistency.
- Authenticated dashboard health probes for Prism Central and registry endpoints when runtime credentials are present.

## Required Production Hardening

Before exposing this console beyond a trusted operator workstation:

- Keep all committed environment files passing CI validation before live apply.
- Keep generated shell scripts produced by the Python renderer; do not hand-edit
  command lines with unquoted environment values.
- Set `ZT_BOOTSTRAP_TOKEN` whenever the dashboard is bound outside localhost
  before the first admin account exists.
- Keep local console account passwords at least 12 characters, or set
  `ZT_MIN_PASSWORD_LENGTH` to match the organization's workstation policy.
- Keep local login throttling enabled for workstation use. Defaults are five
  failed attempts and a 300-second lockout; tune with `ZT_LOGIN_MAX_FAILURES`
  and `ZT_LOGIN_LOCKOUT_SECONDS`.
- Set `ZT_COOKIE_SECURE=true` whenever the dashboard is served through HTTPS or
  an HTTPS-terminating reverse proxy so browser cookies are marked `Secure`.
- Move from memory sessions to file-backed local sessions for workstation restarts, or to Postgres-backed sessions for shared operator consoles when `psycopg` or `psycopg2` is installed in the dashboard runtime.
- Enable `audit_mirror=postgres` for shared operator consoles that need central
  audit search while retaining the local append-only `.zt` audit log.
- Connect OIDC/SAML or enterprise SSO to a real identity provider.
- For built-in OIDC login, map provider identities to active local RBAC
  accounts. Configure `ZT_OIDC_CLIENT_SECRET` for HS256 providers; RS256
  providers are validated through provider JWKS metadata with 2048-bit minimum
  RSA keys.
- Connect console state to Postgres if multi-user operation is required.
- Encrypt or externalize all secrets; do not store raw credentials in the repo or database.
- Connect Vault or an equivalent external secret backend. The console can
  resolve HashiCorp Vault KV key presence with `VAULT_TOKEN`, while secret
  values remain hidden.
- Review and tune role separation for authoring, approving, and executing deployment changes.
- Confirm approval policy, release-channel gates, and plan-review controls are
  enabled for production channels.
- Keep restore file-copy execution manual. Use the dashboard restore approval
  workflow only as authorization evidence until automated copy, conflict, and
  post-restore verification controls are implemented.
- Run deployment jobs from an isolated Linux or WSL runner with pinned NKP
  bundles, least-privilege credentials, and controlled network access.
- Treat dashboard authenticated API health probes as readiness signals; still verify live deployment permissions before apply.
- Record external validation evidence references for production channels after
  Prism authorization and deployment UAT have been reviewed. Store evidence
  pointers and summaries only; never paste tokens, passwords, or secret values.

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
- Production SSO still requires deployment-specific provider configuration,
  claim mapping, and external validation evidence even though HS256 and
  RS256/JWKS token validation are implemented.
- No external Postgres service is connected in this repository; Postgres-backed dashboard sessions require deployment-specific database provisioning and runtime driver installation.
- No external Vault service is connected in this repository; HashiCorp Vault KV
  key-presence checks require deployment-specific Vault provisioning and a
  runtime `VAULT_TOKEN`.
- No live Prism Central authorization validation against a real NKP lab yet.
- No end-to-end deployment proof against a real NKP lab yet.
  The console can now record reviewed external evidence for these items, but
  the evidence must still come from deployment-specific lab or production runs.
