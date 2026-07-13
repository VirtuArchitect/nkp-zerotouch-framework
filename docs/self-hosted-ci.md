# Self-Hosted CI

GitHub-hosted runners cannot access local NKP bundles under `C:\Share`.

Use a self-hosted runner when CI should validate real bundles or perform lab deployment smoke tests.

The repository includes a manual GitHub Actions workflow named `Self-hosted lab
smoke`. It is dispatched from the Actions tab and runs only in the canonical
`VirtuArchitect/nkp-zerotouch-framework` repository on runners labeled
`self-hosted` and `nkp`.

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

## Manual Lab Workflow

Use `Self-hosted lab smoke` for non-apply lab evidence:

1. Select an environment file under `configs/environments/`.
2. Select `bash` or `powershell`.
3. Leave `run_verify` enabled when the runner has a valid kubeconfig and NKP
   tools; disable it for config-only smoke checks.

The workflow runs:

- `validate`
- `prepare`
- `generate`
- optional `verify`

It uploads local evidence from `.zt/preflight`, `.zt/environments/*/reports`,
`.zt/environments/*/generated`, `.zt/environments/*/state/*.json`, `.zt/jobs`,
and `.zt/runs`.

The workflow deliberately does not run `registry --apply`, `deploy --apply`,
`upgrade --apply`, `destroy --apply`, or any automated restore copy-back.
Keep live apply jobs manual/approval-gated.

## Safety Notes

- Do not commit real secrets or local secrets files.
- Use environment variables or runner-level secret stores for Prism, registry,
  Vault, and OIDC credentials.
- Review uploaded artifacts before sharing them outside the lab. Evidence files
  should contain metadata and redacted state, but generated plans may still
  reveal environment names, VIPs, registry endpoints, and cluster topology.
- Run the workflow only on trusted self-hosted runners with access to the
  intended NKP bundles and network targets.
