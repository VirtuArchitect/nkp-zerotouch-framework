# Operations

These phases complete the local operational lifecycle around NKP deployment.

## secrets

Loads a local secrets file and writes only a redacted summary to `.zt`.

PowerShell:

```powershell
.\scripts\zt.ps1 secrets -Config .\configs\environments\connected.example.yaml -Secrets .\configs\secrets\lab-connected.secrets.example.yaml
```

Bash:

```bash
./scripts/zt.sh secrets --config ./configs/environments/connected.example.yaml --secrets ./configs/secrets/lab-connected.secrets.example.yaml
```

Real `*.secrets.yaml` files are ignored by Git.

## backup

Copies generated state, reports, and generated plans to a timestamped backup folder under the environment workspace.

## upgrade

Generates an upgrade plan. Live execution is intentionally guarded until the target bundle and real environment details are confirmed.

## destroy

Generates a destroy plan. Live execution requires explicit confirmation flags and still refuses placeholder endpoints.

## ci

Runs local syntax and smoke checks.

PowerShell:

```powershell
.\scripts\zt.ps1 ci -Config .\configs\environments\connected.example.yaml
```

Bash:

```bash
./scripts/zt.sh ci --config ./configs/environments/connected.example.yaml
```

## runs

Captures a timestamped summary of the current environment state.

```powershell
.\scripts\zt.ps1 runs -Config .\configs\environments\connected.example.yaml
```

Output:

```text
.zt/runs/<timestamp>/
  summary.json
  summary.md
```
