# Prepare

`prepare` creates the local ZeroTouch workspace for an environment after validation succeeds.

## Run

PowerShell:

```powershell
.\scripts\zt.ps1 prepare -Config .\configs\environments\air-gapped.example.yaml
```

Linux or WSL:

```bash
./scripts/zt.sh prepare --config ./configs/environments/air-gapped.example.yaml
```

## Output

The command creates:

```text
.zt/
  environments/
    <environment-name>/
      bin/
      generated/
      logs/
      state/
```

`bin/` contains staged NKP tools from the configured bundle:

- `nkp`
- `kubectl`

`state/` contains framework metadata:

- `environment.json`
- `staged-tools.json`

The `.zt/` folder is local generated output and is ignored by Git.
