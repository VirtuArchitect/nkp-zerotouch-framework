# Phases

The framework runs NKP deployment work in explicit phases. Infrastructure-changing actions are guarded and dry-run oriented by default.

## validate

Checks environment type, bundle type, bundle contents, mode-specific settings, and local tools.
It also writes structured preflight evidence under `.zt/preflight/<environment>.json`,
including the validation summary and redacted endpoint reachability metadata.

## prepare

Creates the local `.zt/environments/<name>/` workspace and stages `nkp` and `kubectl` from the configured bundle.

## generate

Creates generated environment artifacts:

- `cluster-values.yaml`
- `nkp.env`
- `deploy.sh`
- `deploy.ps1`
- `state/generate.json`

The generated `deploy.sh` uses `nkp create cluster nutanix --dry-run` by default.

## registry

Creates registry planning output.

For `connected` and `proxied`, this records that mirroring is optional.

For `air-gapped`, this also generates `registry.sh`, which uses `nkp push bundle` and expects credentials from:

- `ZT_REGISTRY_USERNAME`
- `ZT_REGISTRY_PASSWORD`

## deploy

Creates a deploy plan and does not execute infrastructure changes by default.

PowerShell:

```powershell
.\scripts\zt.ps1 deploy -Config .\configs\environments\connected.example.yaml
```

Bash:

```bash
./scripts/zt.sh deploy --config ./configs/environments/connected.example.yaml
```

Execution requires `-Apply` or `--apply`.

## verify

Writes local verification reports:

- `reports/verification-summary.md`
- `reports/component-health.json`
- `reports/verification-evidence.json`

This verifies local staged artifacts and generated state. When
`state/kubeconfig` exists, it also captures live `kubectl` and NKP query output
under `logs/verify-kubectl.log`. The structured evidence manifest records the
local checks, live verification status, command list, log path, and redacted
kubeconfig metadata when available.

## kubeconfig

Captures a post-deploy kubeconfig into local environment state:

- `state/kubeconfig`
- `state/kubeconfig.json`

The metadata file records capture time, source path, target path, file size, and
SHA256 hash. It does not include kubeconfig contents.

## secrets

Loads local secrets and writes only redacted state. Real secrets are ignored by Git.

## backup

Exports state, generated files, and reports into a timestamped local backup.

## upgrade

Generates an upgrade plan. Apply is guarded.

## destroy

Generates a destroy plan. Apply requires explicit confirmation.

## ci

Runs local syntax and example smoke checks.

## runs

Captures a timestamped run summary under `.zt/runs/`.

## evidence

Creates a timestamped evidence pack under `.zt/evidence/` for lab review and
change evidence. The pack includes preflight metadata, generated plans, reports,
logs, selected redacted state files, run summaries, an `evidence-manifest.json`,
and an archive when native archive tooling is available.

The evidence pack excludes raw `state/kubeconfig` and local secret values.
Operators should still review generated plans, logs, endpoint metadata, and
cluster topology before sharing the pack outside the lab.

## lab-evidence

Captures redacted live lab connectivity and authorization evidence under
`.zt/lab-evidence/`.

The phase probes Prism Central from the environment config or
`NUTANIX_PC_ENDPOINT`, and optionally probes Prism Element from
`NUTANIX_PE_ENDPOINT` or `--prism-element` / `-PrismElement`. Credentials must
come from runtime environment variables:

- `NUTANIX_PC_USERNAME`
- `NUTANIX_PC_PASSWORD`
- `NUTANIX_PE_USERNAME`
- `NUTANIX_PE_PASSWORD`

The evidence records TCP reachability, authenticated API status, HTTP status
codes, probe names, and credential environment variable names only. It does not
record usernames, passwords, tokens, or response bodies.

Use `--write-external-validation` or `-WriteExternalValidation` to create a
redacted `prism-authorization` external validation record when authentication
succeeds.
