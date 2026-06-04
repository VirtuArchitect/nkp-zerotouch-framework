# nkp-zerotouch-framework

ZeroTouch framework for deploying Nutanix Kubernetes Platform (NKP) across multiple environment types.

The framework is designed so `air-gapped` is one supported deployment mode, not the only mode.

## Supported Environment Types

| Type | Use when | Artifact source |
| --- | --- | --- |
| `connected` | Deployment hosts can reach the internet and upstream registries. | Public registries and online repositories. |
| `proxied` | Deployment hosts reach external services through a corporate proxy. | Public registries through proxy settings. |
| `air-gapped` | Deployment hosts have no internet path. | Local NKP bundle, local registry, and mirrored artifacts. |

## NKP Bundle Types

| Bundle type | Example local path | Intended modes |
| --- | --- | --- |
| `standard` | `/mnt/c/Share/nkp-bundle_v2.17.1_linux_amd64/nkp-v2.17.1` | `connected`, `proxied` |
| `air-gapped` | `/mnt/c/Share/nkp-air-gapped-bundle_v2.17.1_linux_amd64/nkp-v2.17.1` | `air-gapped` |

## Repository Layout

```text
configs/
  environments/        # Example environment definitions
  schema/              # Config contract for validation and tooling
docs/                  # Design notes and runbooks
scripts/               # ZeroTouch entrypoints
templates/             # NKP config templates by environment type
```

## Quick Start

1. Copy one of the examples from `configs/environments/`.
2. Edit cluster, Prism Central, registry, network, and deployment settings.
3. Validate the selected environment type:

```powershell
.\scripts\zt.ps1 validate -Config .\configs\environments\air-gapped.example.yaml
```

For Linux or WSL:

```bash
./scripts/zt.sh validate --config ./configs/environments/air-gapped.example.yaml
```

Validation discovers NKP bundle contents, checks mode-specific requirements, and reports pass/warn/fail results. See `docs/validation.md` for the current preflight checks.

Prepare a local workspace after validation succeeds:

```powershell
.\scripts\zt.ps1 prepare -Config .\configs\environments\air-gapped.example.yaml
```

See `docs/prepare.md` for workspace output and staged files.

The main phase sequence is:

```powershell
.\scripts\zt.ps1 validate -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 prepare  -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 generate -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 registry -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 deploy   -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 verify   -Config .\configs\environments\connected.example.yaml
```

See `docs/phases.md` for details.

Additional operational phases are available for secrets, backup, upgrade planning, guarded destroy planning, and CI smoke checks. See `docs/operations.md`.

## Documentation

- `docs/config-reference.md`
- `docs/runbook-connected.md`
- `docs/runbook-proxied.md`
- `docs/runbook-air-gapped.md`
- `docs/troubleshooting.md`

## Tests and Packaging

```powershell
.\tests\smoke.ps1 -Config .\configs\environments\connected.example.yaml
.\scripts\package.ps1 -Version dev
```

```bash
./tests/smoke.sh ./configs/environments/connected.example.yaml
./scripts/package.sh dev
```

## NKP Bundle Note

The NKP 2.17.1 bundles contain Linux AMD64 binaries. Run NKP deployment steps from Linux or WSL when using the bundled `nkp` and `kubectl` binaries.
