# Dashboard

The dashboard is a local console for inspecting `.zt` state, creating deployment jobs, and approval-gating live apply phases.

Run:

```powershell
python .\dashboard\app.py 8080
```

Open:

```text
http://127.0.0.1:8080
```

Dashboard-safe actions:

- `validate`: creates and immediately starts a safe job
- `prepare`: creates and immediately starts a safe job
- `generate`: creates and immediately starts a safe job
- `verify`: creates and immediately starts a safe job
- `backup`: creates and immediately starts a safe job
- `runs`: creates and immediately starts a safe job
- `evidence`: creates and immediately starts a safe job

Apply/destructive actions use the controlled CLI window and require approval:

- `registry -Apply`
- `deploy -Apply`
- `upgrade -Apply`
- `destroy -Apply -ConfirmDestroy`

Job and approval model:

- Safe jobs are written under `.zt/jobs/<job-id>/` and start immediately.
- Apply jobs are written with `pending_approval` status.
- Users with approval permission can approve or reject apply jobs from `Jobs`.
- Job detail pages show the validated command, status, approval metadata, and captured log output.
- Active job detail pages auto-refresh while queued, running, or waiting for approval.
- Running jobs can be cancelled; failed, rejected, cancelled, or completed jobs can be retried.
- Approval thresholds are configured under `Approval Policy`.
- Authenticated POST forms include CSRF protection.
- Route access is RBAC-gated by role permissions.
- Bootstrap and RBAC-created local account passwords must be at least 12
  characters by default. Set `ZT_MIN_PASSWORD_LENGTH` to tune this local policy.
- Repeated failed local login or bootstrap-token attempts are rate-limited.
  Defaults are five failures and a 300-second lockout; tune with
  `ZT_LOGIN_MAX_FAILURES` and `ZT_LOGIN_LOCKOUT_SECONDS`.
- Login cookies include a `Max-Age` matching the server-side session TTL. Set
  `ZT_COOKIE_SECURE=true` when serving the dashboard through HTTPS so session
  and OIDC handoff cookies are marked `Secure`.
- Mutations are written to an append-only audit log under `.zt/audit/events.jsonl`.

Deployment readiness sections:

- `Sources`: NKP bundle paths, source path, Git URL/ref, version pin, and checksum metadata.
- `Inventory`: AHV or future bare-metal node inventory, BMC details, boot mode, and OS image notes.
- `Network`: management/workload CIDRs, API VIP, ingress range, DNS, NTP, proxy, and IP assignment mode.
- `Preflight`: console-level readiness matrix plus latest `.zt/preflight/` validation evidence across sources, inventory, network, connections, integration probes, uniqueness checks, secrets, and provider.
- `UAT`: maps documented UAT cases to local evidence records, evidence packs, jobs, backups, and run history without treating partial evidence coverage as completed UAT. The public demo mirrors this view with simulated UAT readiness data.
- `Pipeline`: visual ZeroTouch flow from source intake through validation, preparation, generation, registry, deploy, verify, and operate.
- `Jobs`: execution queue, approval controls, job detail pages, and captured live logs.
- `Health`: runner, tool, bundle, Prism, registry, credential environment variables, enterprise integration probes, and state-path readiness.
- `Artifacts`: generated file browser, viewer, and diff workflow for plans, logs, reports, state, and configs.
- `Evidence Packs`: review page for `.zt/evidence/` manifests, redaction status, archive paths, and pack metadata created by the `evidence` phase. The public demo mirrors this view with simulated evidence-pack data.
- `/api/preflight`: authenticated JSON view of console preflight checks and structured validation evidence.
- `/api/evidence`: authenticated JSON view of generated evidence pack manifests and archive metadata.
- `/api/uat`: authenticated JSON view of documented UAT cases and their local evidence coverage signals.
- `/api/production-readiness`: authenticated JSON view of the same production gate checks shown in the console.

Settings sections:

- `Providers`: default provider intent and runner type.
- `Secrets`: metadata for local-file or external secret backends. Secret values are not stored by the dashboard.
- `Integrations`: Postgres, Vault, OIDC, and session-store integration metadata with endpoint/discovery health probes. File-backed sessions are active for local restarts; Postgres session storage is contract-only until a reviewed backend is implemented. Postgres DSNs must not include passwords; the console rejects password-bearing DSNs and redacts any previously saved value before rendering it. OIDC handoff now issues short-lived signed state/nonce cookies and the callback validates the signed handoff before failing closed until signed token validation is implemented.

Environment safeguards:

- New environment creation rewrites copied template identity fields so operators do not accidentally create another `lab-connected` target.
- Environment create/edit workflows block duplicate environment names, cluster names, API VIPs, and registry namespaces before YAML is saved.
