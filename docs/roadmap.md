# Roadmap

This roadmap captures public follow-up issues that should stay visible even when there are no open GitHub issues.

## Issue-Ready Backlog

### Add ADRs for architecture-sensitive changes

Status: implemented baseline in `docs/architecture/decisions/`.

Create initial architecture decision records under `docs/architecture/decisions/` for current baseline choices:

- Local `.zt` state instead of a central database by default.
- Plan-first apply model.
- Static public demo boundary.
- Local dashboard RBAC and approval model.

Acceptance criteria:

- At least three accepted ADRs are added.
- ADRs reference the relevant docs for state, boundaries, and approval behavior.
- Future public contract changes are expected to add or update ADRs.

### Complete OIDC authorization-code login flow

The implementation status currently marks OIDC login as partial. Discovery
metadata readiness is validated in the console; complete the full
authorization-code token exchange and session mapping flow after approving a
JWT/JWKS-capable runtime dependency.

Acceptance criteria:

- OIDC discovery is validated before login.
- Authorization-code callback validates state, nonce, issuer, audience, and token expiry.
- OIDC identity maps to local roles without storing provider secrets in Git.
- Tests cover success, invalid state, invalid issuer, and missing role mapping.

### Add provider implementation guides

Status: implemented baseline in `providers/authoring-guide.md`.

Provider folders define current extension boundaries, but new contributors need a repeatable implementation guide.

Acceptance criteria:

- A provider authoring guide describes required fields, templates, generated artifacts, verification evidence, and rollback boundaries.
- Existing provider README files link to the guide.
- The guide explains how connected, proxied, and air-gapped modes differ.

### Add data-flow diagrams to the README

Status: implemented baseline in `README.md`.

The README now explains the mental model in prose. Add a compact architecture diagram or link block near the top for visual readers.

Acceptance criteria:

- README includes a compact flow or direct architecture callout.
- The flow distinguishes CLI, dashboard, `.zt` state, and live demo boundaries.
- The diagram does not imply the public demo provisions infrastructure.

### Strengthen restore execution controls

Status: documented baseline in `docs/restore-controls.md`.

Restore planning exists, but restore execution remains intentionally manual. Define the next control layer before adding any automated restore apply behavior.

Acceptance criteria:

- Restore execution requirements are documented.
- Approval, evidence, rollback, and dry-run behavior are specified.
- No restore apply automation is added without tests and security review.

### Publish an architecture review checklist

Status: implemented baseline in `docs/architecture-review-checklist.md`.

Create a checklist for reviewing future changes that affect state, generated artifacts, provider contracts, dashboard authorization, or apply semantics.

Acceptance criteria:

- Checklist links to `SECURITY_REVIEW.md`, `CODE_REVIEW.md`, and architecture docs.
- Checklist calls out generated artifact compatibility and local-state migration concerns.
- Pull request template links to the checklist.

### Add security operations documentation

Status: implemented baseline in `docs/security/`.

Create the security documentation needed to review public and production-facing
changes consistently.

Acceptance criteria:

- Threat model documents assets, trust boundaries, threats, and mitigations.
- Dependency-risk guidance explains when new runtime dependencies are justified.
- Security review and incident note folders include sanitized note templates.
