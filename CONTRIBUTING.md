# Contributing

Thanks for improving NKP ZeroTouch Framework.

## Development Checks

Run before opening a pull request:

```bash
bash tests/smoke.sh configs/environments/connected.example.yaml
bash scripts/security-scan.sh
```

PowerShell:

```powershell
.\tests\smoke.ps1 -Config .\configs\environments\connected.example.yaml
.\scripts\security-scan.ps1
```

## Safety

Do not commit:

- real secrets
- kubeconfigs
- NKP bundles
- generated `.zt` state
- internal customer/environment details

Apply/destructive phases must remain explicit and guarded.
