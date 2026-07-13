# Security Documentation

This folder is for defensive security notes related to the NKP ZeroTouch
Framework.

The framework handles infrastructure configuration, generated deployment
artifacts, local state, and optional secret material. Treat changes in these
areas as security-sensitive:

- `configs/secrets/`
- `scripts/`
- `tools/`
- `dashboard/`
- `.github/workflows/`
- Container build files

Primary references:

- `../../SECURITY.md` for reporting and supported security expectations.
- `../../SECURITY_REVIEW.md` for review checklist guidance.
- `../../PENTEST_SCOPE_TEMPLATE.md` for assessment scoping.
- `../public-readiness.md` for public repository readiness.

Included security references:

- `threat-model.md`
- `dependency-risk.md`
- `security-reviews/`
- `incident-notes/`
