# Public Readiness Checklist

Before making this repository public:

- Run `scripts/security-scan.ps1` or `scripts/security-scan.sh`.
- Confirm `git status --short` does not show `.zt/`, `dist/`, bundles, kubeconfigs, or real secrets.
- Confirm all committed configs use placeholder endpoints.
- Confirm no NKP bundle binaries, image bundles, generated image lists, or proprietary artifacts are committed.
- Confirm real deployment configs are either private or sanitized.
- Confirm `docs/demo/` is safe for public review; it is published to the
  `gh-pages` branch by `.github/workflows/pages.yml`.
- Review `SECURITY.md`.
- Add a GitHub repository description that states this is an unofficial automation framework.

This repository is not affiliated with or supported by Nutanix.
