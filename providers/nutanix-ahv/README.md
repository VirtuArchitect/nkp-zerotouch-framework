# Nutanix AHV Provider

Status: implemented baseline.

This provider targets NKP clusters on Nutanix AHV through Prism Central.

Supported modes:

- connected
- proxied
- air-gapped

Primary inputs:

- Prism Central endpoint and credentials.
- Prism Element cluster, subnet, image, project, and storage container.
- NKP bundle path and version.
- Cluster name, Kubernetes version, replica counts, pod CIDR, and service CIDR.
- Optional registry mirror metadata for proxied and air-gapped workflows.

Current implementation lives in `scripts/zt.ps1`, `scripts/zt.sh`, and
`tools/zt_config.py`.
