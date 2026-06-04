# Environment Types

The framework uses `environment.type` to select the deployment workflow. Each workflow shares the same high-level phases, but resolves artifacts differently.

## connected

Use this when the deployment workstation and target cluster nodes can reach the required public endpoints directly.

Expected behavior:

- Use the standard NKP bundle when a local bundle is supplied.
- Pull images from public registries.
- Fetch required application repositories online.
- Skip local registry mirroring unless explicitly requested.

## proxied

Use this when internet access is available only through an HTTP/HTTPS proxy.

Expected behavior:

- Use the standard NKP bundle when a local bundle is supplied.
- Export proxy variables before invoking NKP tooling.
- Validate `httpProxy`, `httpsProxy`, and `noProxy`.
- Pull external images through the proxy path.

## air-gapped

Use this when the environment has no internet route.

Expected behavior:

- Require a local air-gapped NKP bundle path.
- Require a local registry endpoint.
- Load or mirror image bundles before cluster creation.
- Use bundled CLI and application repository artifacts.

## Bundle Types

Use `nkp.bundleType` to describe the local NKP artifact:

- `standard`: extracted from `nkp-bundle_v2.17.1_linux_amd64.tar.gz`, suitable for `connected` and `proxied` workflows.
- `air-gapped`: extracted from `nkp-air-gapped-bundle_v2.17.1_linux_amd64.tar.gz`, required for `air-gapped` workflows.

## Shared Deployment Phases

1. `validate`: check config, required tools, connectivity, and mode-specific inputs.
2. `prepare`: stage binaries, registry credentials, image bundles, and generated configs.
3. `deploy`: create or upgrade NKP management/workload clusters.
4. `verify`: check cluster readiness, NKP components, and application health.
