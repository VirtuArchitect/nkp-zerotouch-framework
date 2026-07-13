# NKP Lab Evidence Template

Use this template to capture the first end-to-end lab proof for a real NKP
deployment.

## Environment

- Environment name:
- Environment type:
- NKP version:
- Bundle type:
- Runner:
- Prism Central:
- Registry:
- Date:

## Evidence Checklist

- `validate` output captured.
- `prepare` output captured.
- `generate` output captured.
- Generated deploy plan reviewed.
- Plan review approved in the console.
- Registry plan or push evidence captured when required.
- Deploy apply job and approval evidence captured.
- Kubeconfig captured into `.zt/environments/<name>/state/kubeconfig`.
- Kubeconfig metadata captured in `.zt/environments/<name>/state/kubeconfig.json`.
- `verify` output captured.
- Run summary captured under `.zt/runs`.

## Sanitized Attachments

- Generated `deploy-plan.md`.
- Generated `registry-plan.md` when applicable.
- Verification summary.
- Job log excerpts.
- Screenshots of console lifecycle/readiness state.

Do not include credentials, kubeconfig contents, private IP details that cannot
be shared, or proprietary bundle contents.
