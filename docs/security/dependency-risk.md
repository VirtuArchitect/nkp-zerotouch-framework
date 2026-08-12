# Dependency Risk

The framework is intentionally dependency-light. New runtime dependencies should
be added only when they remove meaningful risk or enable a security-sensitive
feature that cannot be implemented correctly with the standard toolchain.

## Current Dependency Posture

- Dashboard runtime uses Python standard-library HTTP handling.
- CLI wrappers use PowerShell and Bash entrypoints.
- Tests use `pytest`.
- CI uses GitHub Actions, ShellCheck, Python, PowerShell parsing, security
  scans, package smoke checks, and container syntax smoke checks.
- Public demo uses static HTML, CSS, and JavaScript with no package manager.

## Dependency Review Checklist

Before adding a dependency:

1. Confirm the feature cannot be implemented safely with existing tools.
2. Prefer maintained libraries with clear release history and security response.
3. Check license compatibility with the repository license.
4. Pin or constrain versions where the package manager supports it.
5. Add tests for the dependency-backed behavior.
6. Add failure-mode handling when the dependency is missing or misconfigured.
7. Document any operator installation or runtime impact.
8. Run security scans and package smoke checks before merge.

## High-Sensitivity Dependency Areas

| Area | Risk | Requirement |
| --- | --- | --- |
| OIDC/JWT validation | Accepting forged identities or tokens | Use a maintained JWT/JWKS implementation; validate issuer, audience, state, nonce, expiry, and signature |
| Secret backends | Exposing credentials or tokens | Keep secrets out of Git and local logs; validate required env vars |
| HTTP clients | SSRF, TLS, auth leakage | Restrict endpoints to configured targets; avoid logging credentials |
| YAML/config parsing | Unsafe parsing or schema bypass | Use safe parsers and schema validation |
| Shell execution | Injection or unintended apply | Keep generated scripts quoted and apply-gated |
| CI/CD actions | Build-chain compromise | Prefer official actions, minimal permissions, and scanner-compatible token use |

## Current Known Dependency Decision

OIDC authorization-code login now supports signed HS256 and RS256/JWKS
`id_token` validation in the dependency-light baseline. The built-in validator
checks issuer, audience, state, nonce, expiry, signature, local RBAC mapping,
JWKS key ID selection, and 2048-bit minimum RSA signing keys without adding a
runtime dependency.

Production SSO still requires deployment-specific identity provider
configuration, claim mapping, secret handling, durable sessions, and external
validation evidence. If broader JWT algorithms, encrypted tokens, advanced key
rotation behavior, or IdP-specific profile handling become required, add a
reviewed JWT/OIDC library and include tests for invalid issuer, invalid
audience, expired tokens, unknown key IDs, algorithm confusion, and missing role
mapping.
