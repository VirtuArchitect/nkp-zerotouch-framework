# Self-Hosted CI

GitHub-hosted runners cannot access local NKP bundles under `C:\Share`.

Use a self-hosted runner when CI should validate real bundles or perform lab deployment smoke tests.

Runner requirements:

- Linux or WSL
- Python with PyYAML
- Bash
- PowerShell if testing `zt.ps1`
- access to NKP bundle mount paths
- access to Prism Central and registry for live tests

Suggested labels:

```text
self-hosted
nkp
linux
airgap
```

Keep live apply jobs manual/approval-gated.
