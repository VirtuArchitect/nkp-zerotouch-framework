# Implementation Status

This maps the public-readiness and real-deployment tasks to the repository features.

| Task | Status | Implementation |
| --- | --- | --- |
| Replace placeholder configs | Supported | `scripts/new-env.*`, runbooks, config reference |
| Create real secrets files | Supported | `secrets` phase, ignored `*.secrets.yaml`, local `.zt/.../secrets/secrets.env` |
| Test Prism connectivity | Partially automated | `validate` checks endpoint shape/reachability; dashboard health can probe Prism API authentication with runtime credentials |
| Test registry connectivity | Partially automated | `validate` checks endpoint shape/reachability; dashboard health can probe registry `/v2/` authentication and `registry -Apply` performs real push |
| Run air-gapped registry apply | Supported | guarded `registry -Apply` / `--apply` |
| Run NKP deploy apply | Supported | guarded `deploy -Apply` / `--apply` |
| Capture kubeconfig into state | Implemented | `kubeconfig` phase writes `.zt/environments/<name>/state/kubeconfig` and redacted `kubeconfig.json` metadata |
| Strengthen live verification | Partially automated | `verify` runs `kubectl get nodes/pods` and NKP queries when kubeconfig exists |
| Confirm generated NKP flags | Supported | generated `deploy.sh` and runbooks are review points |
| Decide upgrade/destroy automation | Guarded | plan-first `upgrade` and `destroy` phases |
| Add real CI strategy | Implemented baseline | GitHub Actions syntax/helper/security/package checks and all-environment config validation |
| Create first real profile | Supported | `scripts/new-env.*` |
| Dashboard / console | Implemented | `dashboard/app.py`, `docs/dashboard.md` |
| Live demo | Implemented | GitHub Pages prototype under `docs/demo/`, published to `gh-pages` by `.github/workflows/pages.yml` |
| CSRF protection | Implemented | authenticated POST forms receive and validate CSRF tokens |
| Route-level RBAC | Implemented baseline | routes are mapped to permissions and enforced for local roles |
| Audit events | Implemented baseline | append-only `.zt/audit/events.jsonl` for logins, settings, jobs, approvals, and environment changes |
| Health checks | Implemented baseline | console health page for runner, tools, bundles, Prism, registry, credential variables, authenticated API probes, and enterprise integration probes |
| Artifact viewer | Implemented | generated plans, reports, logs, and allowed config/docs files can be opened from the console |
| Artifact diff/review | Implemented baseline | allowed artifacts can be compared from the console before operational use |
| Formal plan review | Implemented baseline | console records per-environment approve/reject status under `.zt` |
| Setup wizard | Implemented baseline | guided first-run setup page links source, connection, inventory, network, secrets, environment, and preflight tasks |
| Lifecycle/readiness | Implemented baseline | environment table shows lifecycle state and readiness score |
| Kubeconfig console visibility | Implemented baseline | kubeconfig page shows capture status, metadata evidence, and command guidance |
| Provider catalog | Implemented baseline | provider contracts live under `providers/` and are visible in Settings > Providers |
| API layer | Implemented baseline | authenticated JSON endpoints for status, environments, jobs, logs, locks, change records, and production readiness |
| Environment locking | Implemented baseline | environment locks are created for prepare, generate, registry, deploy, upgrade, and destroy jobs |
| Plan hashing | Implemented baseline | plan review stores hashes and reports stale reviews when generated artifacts change |
| Change records | Implemented baseline | apply requests create local change records with job ID, requester, plan hashes, and rollback notes |
| Drift detection | Implemented baseline | console reports stale reviews, YAML-after-prepare changes, missing generate, and missing verification |
| Backup/restore UI | Implemented baseline | console lists backup manifests; restore remains manual and controlled |
| Release channels | Implemented baseline | configurable dev/lab/pilot/production channel metadata |
| Release channel enforcement | Implemented baseline | apply jobs use the higher of action approval count or release-channel approval count |
| Plan review enforcement | Implemented baseline | apply requests are blocked when review is missing, rejected, or stale |
| Change record detail | Implemented baseline | change records have detail pages with job link, hashes, requester, status, and rollback notes |
| Restore planning | Implemented baseline | console generates guarded restore plans and JSON metadata from backup manifests, including component inventory and lock warnings |
| Lock cleanup | Implemented baseline | stale locks can be cleared while active locks remain protected |
| Production readiness gate | Implemented baseline | console reports plan review, backup, drift, channel, and verification readiness |
| Dashboard route tests | Implemented baseline | pytest route/API smoke coverage for dashboard pages and JSON endpoints |
| OIDC login flow | Partial | readiness route validates discovery metadata and required endpoints; full authorization-code token exchange remains future work |
| Vault secret validation | Implemented baseline | runtime secret key presence checks and Vault health probe metadata |
| Environment uniqueness checks | Implemented baseline | environment create/edit blocks duplicate names, cluster names, API VIPs, and registry namespaces |
| CI environment identity checks | Implemented baseline | `tools/zt_config.py validate-all` validates committed environment files and blocks duplicate identity values |
| Approval policy | Implemented baseline | per-action approval thresholds, self-approval prevention, production Admin option |
| Enterprise integrations | Probed baseline | Postgres TCP, Vault health, OIDC discovery, and session-store consistency checks under Settings > Integrations, Health, and Preflight |
| File session store | Implemented baseline | `session_store=file` persists console sessions under `.zt/settings/sessions.json`; memory remains the default local mode |
| Kubeconfig capture | Implemented | `kubeconfig` phase |
| Registry push enhancements | Implemented | CA, insecure, concurrency, existing-tag behavior |
| Containerized runner | Implemented | `Dockerfile`, `Containerfile`, `docs/container-runner.md` |
| Self-hosted CI option | Documented | `docs/self-hosted-ci.md` |
| Better tests | Implemented baseline | parser tests, smoke tests, invalid fixture |
| Release automation | Implemented | tag workflow creates artifact and GitHub release |
| Public polish | Implemented baseline | `SECURITY.md`, `CONTRIBUTING.md`, architecture/public-readiness docs, security threat model, dependency-risk guidance |

Live infrastructure changes still require real Prism Central, registry, network, and credential values.
