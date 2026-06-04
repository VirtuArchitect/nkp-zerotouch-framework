# Security Policy

## Supported Versions

The current development version is tracked in `VERSION`.

## Reporting Issues

Do not open public issues containing credentials, kubeconfigs, registry tokens, internal hostnames, private IP plans, or proprietary NKP bundle contents.

## Secret Handling

Real secrets must stay in local ignored files:

```text
configs/secrets/*.secrets.yaml
.zt/
```

The repository should never contain:

- Prism Central passwords
- registry passwords
- proxy passwords
- SSH private keys
- kubeconfigs
- NKP bundle binaries or image bundles
