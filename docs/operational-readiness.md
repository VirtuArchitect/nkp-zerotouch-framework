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
- Safe action execution: validate, prepare, generate, verify, backup, runs.
- Runs, artifacts, and audit visibility from `.zt`.
- Local connection, RBAC, and database settings.

## Required Production Hardening

Before exposing this console beyond a trusted operator workstation:

- Replace local sessions with durable server-side session storage.
- Add CSRF protection to all POST forms.
- Enforce RBAC permissions on routes and actions.
- Add OIDC/SAML or enterprise SSO integration.
- Move console state to Postgres if multi-user operation is required.
- Encrypt or externalize all secrets; do not store raw credentials in the repo or database.
- Add per-action audit events with user identity, timestamp, target environment, and result.
- Add role separation for authoring, approving, and executing deployment changes.
- Add backup/restore procedures for `.zt` state and future database state.
- Add health checks for Prism Central, registry, bundle mount, DNS, NTP, proxy, and disk space.

## Recommended Operating Model

Use the console for day-to-day preparation, review, and non-destructive actions.
Keep live apply operations deliberate and controlled:

1. Create or edit an environment profile.
2. Run `validate`.
3. Run `prepare`.
4. Run `generate`.
5. Review generated artifacts and runbooks.
6. For air-gapped environments, run registry planning and approved image push.
7. Execute live deploy from a prepared runner with approved credentials.
8. Capture kubeconfig.
9. Run `verify`.
10. Capture a run summary and archive artifacts.

## Current Gaps

- No enforced route-level RBAC yet.
- No production SSO integration yet.
- No Postgres persistence yet.
- No live Prism Central authentication validation yet.
- No end-to-end deployment proof against a real NKP lab yet.
- No approval workflow for destructive or live apply actions yet.

