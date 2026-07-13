# Threat Model

This threat model covers the NKP ZeroTouch Framework as a local operator
console, CLI workflow, generated-artifact workspace, and static public demo.

## Security Boundaries

| Boundary | Trusted Inputs | Untrusted or Sensitive Inputs | Controls |
| --- | --- | --- | --- |
| Repository | Sanitized examples, docs, templates, tests | Real secrets, kubeconfigs, NKP bundles, generated state | `.gitignore`, security scans, public-readiness checklist |
| CLI runner | Operator commands, committed scripts | Environment YAML, local bundles, registry credentials, Prism credentials | Schema validation, explicit apply flags, generated scripts, run capture |
| Local `.zt` state | Generated plans, job records, audit events | Kubeconfig, local secrets, logs, backup artifacts | Local-only storage, path allowlists, restore planning, no repo commits |
| Dashboard | Authenticated local users | Form input, query parameters, job commands, artifact paths | RBAC, CSRF, cookie sessions, route permissions, path restrictions |
| Live apply | Reviewed plans and approved jobs | Prism Central, registry, NKP bundle, kubeconfig | Plan review, release-channel approvals, locks, change records |
| Static demo | Demo-only data under `docs/demo/` | Browser users and public traffic | No backend, no credentials, no apply behavior |

## Primary Assets

- Prism Central credentials and endpoint details.
- Registry credentials, CA policy, namespace, and image bundle metadata.
- NKP bundle paths and generated deploy scripts.
- Kubeconfig and verification reports.
- `.zt` job, audit, approval, lock, backup, and restore-plan records.
- Dashboard RBAC accounts, password hashes, sessions, and CSRF tokens.

## Threats and Mitigations

| Threat | Impact | Mitigations |
| --- | --- | --- |
| Committing real credentials or kubeconfig | Public credential exposure | Security scans, `.gitignore`, placeholder examples, public-readiness checklist |
| Path traversal through artifact views | Local file disclosure | Artifact allowlists, resolved-path checks, route tests |
| Unreviewed live apply | Cluster changes without approval | Explicit `--apply`, plan review, release-channel approvals, active locks |
| Stale approval after generated artifacts change | Applying a plan different from the reviewed plan | Plan hashes and stale-review warnings |
| Concurrent operations on one environment | State corruption or overlapping deployment actions | Environment locks for prepare/generate/apply-class jobs |
| CSRF against authenticated local console | Unintended state-changing request | CSRF token generation and validation on POST forms |
| Weak local account governance | Unauthorized console use | Password hashing, route-level RBAC, bootstrap exposure guard |
| Public demo mistaken for live console | Unsafe assumptions about provisioning | Demo disclaimer, static demo boundary ADR, no backend calls |
| Restore from stale or incomplete backups | Loss of local state or misleading recovery | Manual restore plans, manifest metadata, lock warnings, current-backup requirement |
| Dependency or build-chain compromise | Executing unsafe code in CI or operator runner | Dependency review, pinned workflow actions where practical, package smoke checks |

## Production Exposure Requirements

Before exposing the dashboard beyond a trusted operator workstation:

1. Require SSO/OIDC or another enterprise identity provider.
2. Move shared sessions and multi-user state to a durable backend.
3. Externalize secrets to Vault or an equivalent secret manager.
4. Run the console and apply runner on controlled hosts with least-privilege
   Prism and registry credentials.
5. Keep apply approvals, plan review, locks, audit events, backup evidence, and
   verification checks enabled for production release channels.

## Review Triggers

Update this model when changing:

- Authentication, sessions, RBAC, approval policy, or audit behavior.
- Artifact viewing, diffing, backup, restore, path handling, or generated files.
- CLI apply, upgrade, destroy, registry push, or shell-command generation.
- CI/CD, release, GitHub Pages, containers, or dependency handling.
- External integrations such as Prism Central, registry, Vault, Postgres, or
  OIDC.
