# Scripts

This folder contains local developer and operator entry points for the NKP
ZeroTouch Framework.

Primary commands:

- `zt.ps1` / `zt.sh`: phase runner for validation, preparation, generation,
  registry planning, deployment planning, verification, backup, upgrade, destroy,
  run capture, and CI checks.
- `new-env.ps1` / `new-env.sh`: create a new environment config from examples.
- `package.ps1` / `package.sh`: create distributable framework archives.
- `security-scan.ps1` / `security-scan.sh`: scan for committed secrets and
  unsafe large bundle artifacts.

Common PowerShell flow:

```powershell
.\scripts\zt.ps1 validate -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 prepare -Config .\configs\environments\connected.example.yaml
.\scripts\zt.ps1 generate -Config .\configs\environments\connected.example.yaml
```

Common Bash flow:

```bash
./scripts/zt.sh validate --config ./configs/environments/connected.example.yaml
./scripts/zt.sh prepare --config ./configs/environments/connected.example.yaml
./scripts/zt.sh generate --config ./configs/environments/connected.example.yaml
```

Live apply and destructive operations are intentionally guarded. Review generated
plans and runbooks before using `--apply` or `--confirm-destroy`.

