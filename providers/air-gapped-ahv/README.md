# Air-Gapped AHV Provider

Status: implemented baseline through the Nutanix AHV command path.

This provider profile models AHV deployments where the target environment has
no internet path and requires local NKP bundles plus a private registry.

Additional inputs:

- Air-gapped NKP bundle path.
- Registry endpoint and namespace.
- Registry credentials supplied through runtime environment variables or a
  configured secret backend.
- Optional registry CA, insecure TLS policy, push concurrency, and existing-tag
  behavior.

The registry phase generates a plan and guarded `nkp push bundle` script.
