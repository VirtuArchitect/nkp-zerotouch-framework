# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Added

- GitHub Pages live demo for the NKP ZeroTouch Framework.
- Clickable static prototype covering environment inventory, profile design,
  ZeroTouch phases, governance gates, and generated artifacts.

## [0.1.0] - 2026-06-04

### Added

- Multi-environment NKP ZeroTouch workflow for `connected`, `proxied`, and `air-gapped` deployments.
- Phases: `validate`, `prepare`, `generate`, `registry`, `deploy`, `verify`, `secrets`, `backup`, `upgrade`, `destroy`, `runs`, and `ci`.
- Real YAML parsing helper with custom config validation.
- Standard and air-gapped NKP bundle discovery.
- Local `.zt` workspace generation with staged `nkp` and `kubectl`.
- Guarded dry-run deploy behavior with explicit apply flags.
- Air-gapped registry plan/script generation.
- Redacted secrets handling with local untracked environment injection.
- Local smoke tests and package scripts.
- GitHub Actions CI and release packaging workflows.
- Connected, proxied, and air-gapped runbooks.
- Local dashboard/console with safe phase actions.
- Kubeconfig capture phase and stronger live verification.
- Registry push options for CA, insecure TLS skip, concurrency, and existing tag policy.
- Dockerfile and Containerfile for container runner use.
- Self-hosted CI guidance.
- Parser tests, invalid config fixture, and smoke tests.
- GitHub release workflow.
- Public-readiness, architecture, security, and contribution docs.
