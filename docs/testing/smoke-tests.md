# Smoke Tests

Use these smoke tests to confirm that the framework is still operational after
changes.

## Connected Config Validation

Name: Connected environment validation

Purpose: Confirm that the connected example parses and validates.

Prerequisites:

- Python is available.
- Repository dependencies are installed.

Steps:

```powershell
.\tests\smoke.ps1 -Config .\configs\environments\connected.example.yaml
```

```bash
./tests/smoke.sh ./configs/environments/connected.example.yaml
```

Expected result:

- Exit code `0`
- Validation summary shows no failures

## Dashboard Console

Name: Container dashboard reachability

Purpose: Confirm that the Docker console starts and exposes the local UI.

Prerequisites:

- Docker Desktop or Docker Engine is running.

Steps:

```powershell
docker compose up -d --build dashboard
Invoke-WebRequest -UseBasicParsing http://localhost:18080
```

Expected result:

- HTTP status `200`
- Dashboard renders the environment table and safe action buttons

## Security Scan

Name: Repository security scan

Purpose: Catch accidentally committed secrets or unsafe artifacts.

Steps:

```powershell
.\scripts\security-scan.ps1
```

```bash
./scripts/security-scan.sh
```

Expected result:

- Exit code `0`
- No committed secrets or blocked bundle artifacts are detected

