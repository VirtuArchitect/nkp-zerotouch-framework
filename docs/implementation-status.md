# Implementation Status

This maps the public-readiness and real-deployment tasks to the repository features.

| Task | Status | Implementation |
| --- | --- | --- |
| Replace placeholder configs | Supported | `scripts/new-env.*`, runbooks, config reference |
| Create real secrets files | Supported | `secrets` phase, ignored `*.secrets.yaml`, local `.zt/.../secrets/secrets.env` |
| Test Prism connectivity | Partially automated | `validate` checks endpoint shape/reachability; real auth requires environment values |
| Test registry connectivity | Partially automated | `validate` checks endpoint shape/reachability; `registry -Apply` performs real push |
| Run air-gapped registry apply | Supported | guarded `registry -Apply` / `--apply` |
| Run NKP deploy apply | Supported | guarded `deploy -Apply` / `--apply` |
| Capture kubeconfig into state | Convention defined | place kubeconfig at `.zt/environments/<name>/state/kubeconfig` |
| Strengthen live verification | Partially automated | `verify` runs `kubectl get nodes/pods` when kubeconfig exists |
| Confirm generated NKP flags | Supported | generated `deploy.sh` and runbooks are review points |
| Decide upgrade/destroy automation | Guarded | plan-first `upgrade` and `destroy` phases |
| Add real CI strategy | Implemented baseline | GitHub Actions syntax/helper/security/package checks |
| Create first real profile | Supported | `scripts/new-env.*` |
| Dashboard / console | Implemented | `dashboard/app.py`, `docs/dashboard.md` |
| CSRF protection | Implemented | authenticated POST forms receive and validate CSRF tokens |
| Route-level RBAC | Implemented baseline | routes are mapped to permissions and enforced for local roles |
| Audit events | Implemented baseline | append-only `.zt/audit/events.jsonl` for logins, settings, jobs, approvals, and environment changes |
| Health checks | Implemented baseline | console health page for runner, tools, bundles, Prism, registry, credential variables, and enterprise integration probes |
| Artifact viewer | Implemented | generated plans, reports, logs, and allowed config/docs files can be opened from the console |
| Artifact diff/review | Implemented baseline | allowed artifacts can be compared from the console before operational use |
| Formal plan review | Implemented baseline | console records per-environment approve/reject status under `.zt` |
| Setup wizard | Implemented baseline | guided first-run setup page links source, connection, inventory, network, secrets, environment, and preflight tasks |
| Lifecycle/readiness | Implemented baseline | environment table shows lifecycle state and readiness score |
| Kubeconfig console visibility | Implemented baseline | kubeconfig page shows capture status and command guidance |
| Provider catalog | Implemented baseline | provider contracts live under `providers/` and are visible in Settings > Providers |
| Environment uniqueness checks | Implemented baseline | environment create/edit blocks duplicate names, cluster names, API VIPs, and registry namespaces |
| Approval policy | Implemented baseline | per-action approval thresholds, self-approval prevention, production Admin option |
| Enterprise integrations | Probed baseline | Postgres TCP, Vault health, OIDC discovery, and session-store consistency checks under Settings > Integrations, Health, and Preflight |
| Kubeconfig capture | Implemented | `kubeconfig` phase |
| Registry push enhancements | Implemented | CA, insecure, concurrency, existing-tag behavior |
| Containerized runner | Implemented | `Dockerfile`, `Containerfile`, `docs/container-runner.md` |
| Self-hosted CI option | Documented | `docs/self-hosted-ci.md` |
| Better tests | Implemented baseline | parser tests, smoke tests, invalid fixture |
| Release automation | Implemented | tag workflow creates artifact and GitHub release |
| Public polish | Implemented baseline | `SECURITY.md`, `CONTRIBUTING.md`, architecture/public-readiness docs |

Live infrastructure changes still require real Prism Central, registry, network, and credential values.
