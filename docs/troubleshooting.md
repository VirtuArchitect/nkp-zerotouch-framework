# Troubleshooting

## Bundle Not Found

Use Linux/WSL style paths in config, such as `/mnt/c/Share/...`. PowerShell converts these paths for local validation.

## Placeholder Endpoint Warnings

Example configs intentionally use `.example.com`. Apply phases refuse placeholder endpoints.

## Missing Podman or OpenSSL

These are warnings unless your chosen workflow requires them.

## NKP Binary Will Not Run on Windows

The NKP bundle contains Linux AMD64 binaries. Use WSL or a Linux runner for live NKP commands.

## Secrets Not Found

Copy a `configs/secrets/*.secrets.example.yaml` file to `*.secrets.yaml` or pass `-Secrets` / `--secrets`.
