# Phases

The framework runs NKP deployment work in explicit phases. Infrastructure-changing actions are guarded and dry-run oriented by default.

## validate

Checks environment type, bundle type, bundle contents, mode-specific settings, and local tools.

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
- `reports/component-health.json` from PowerShell

Today this verifies local staged artifacts and generated state. Cluster-live checks are the next layer once real kubeconfig output is wired in.

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
