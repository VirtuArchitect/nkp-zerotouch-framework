# Validation

`validate` is the preflight phase for the framework. It checks the config shape, selected environment type, local NKP bundle contents, and the tools needed for later deployment phases.

## Run

PowerShell:

```powershell
.\scripts\zt.ps1 validate -Config .\configs\environments\air-gapped.example.yaml
```

Linux or WSL:

```bash
./scripts/zt.sh validate --config ./configs/environments/air-gapped.example.yaml
```

## Strict Mode

Strict mode treats warnings as failures.

PowerShell:

```powershell
.\scripts\zt.ps1 validate -Config .\configs\environments\air-gapped.example.yaml -Strict
```

Linux or WSL:

```bash
./scripts/zt.sh validate --config ./configs/environments/air-gapped.example.yaml --strict
```

## Current Checks

- `environment.name`
- `environment.type`
- `nkp.version`
- `nkp.bundleType`
- `nkp.bundlePath`
- NKP CLI binary
- `kubectl`
- Konvoy bootstrap image
- NKP image builder image
- Kommander application repository
- Konvoy and Kommander image bundles
- image artifact directory
- Prism Central endpoint placeholder/TCP reachability
- air-gapped registry config and TCP reachability
- proxied HTTP/HTTPS proxy config
- local tools: `ssh`, `docker`, `podman`, `openssl`
