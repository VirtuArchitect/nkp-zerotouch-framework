# Dashboard

The dashboard is a local console for inspecting `.zt` state and running safe phases.

Run:

```powershell
python .\dashboard\app.py 8080
```

Open:

```text
http://127.0.0.1:8080
```

Dashboard-safe actions:

- `validate`
- `prepare`
- `generate`
- `verify`
- `backup`
- `runs`

Apply/destructive actions remain CLI-only:

- `registry -Apply`
- `deploy -Apply`
- `destroy -Apply -ConfirmDestroy`

Deployment readiness sections:

- `Sources`: NKP bundle paths, source path, Git URL/ref, version pin, and checksum metadata.
- `Inventory`: AHV or future bare-metal node inventory, BMC details, boot mode, and OS image notes.
- `Network`: management/workload CIDRs, API VIP, ingress range, DNS, NTP, proxy, and IP assignment mode.
- `Preflight`: console-level readiness matrix across sources, inventory, network, connections, secrets, and provider.
- `Pipeline`: visual ZeroTouch flow from source intake through validation, preparation, generation, registry, deploy, verify, and operate.
- `Jobs`: run history and the future live-log/retry/cancel surface.

Settings sections:

- `Providers`: default provider intent and runner type.
- `Secrets`: metadata for local-file or external secret backends. Secret values are not stored by the dashboard.
