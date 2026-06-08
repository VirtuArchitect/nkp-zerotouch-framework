# Testing Documentation

This folder contains test strategy and repeatable validation guidance for the
NKP ZeroTouch Framework.

Primary test entry points:

- `../../tests/smoke.ps1`
- `../../tests/smoke.sh`
- `../../tests/test_config.py`
- `../../scripts/security-scan.ps1`
- `../../scripts/security-scan.sh`

Recommended baseline before opening a pull request:

```powershell
.\tests\smoke.ps1 -Config .\configs\environments\connected.example.yaml
python -m pytest .\tests
.\scripts\security-scan.ps1
```

```bash
./tests/smoke.sh ./configs/environments/connected.example.yaml
python -m pytest ./tests
./scripts/security-scan.sh
```

See also:

- `../../TESTING_GUIDE.md`
- `smoke-tests.md`

