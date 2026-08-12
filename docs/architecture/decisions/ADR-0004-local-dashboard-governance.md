# ADR-0004: Use Local Dashboard Governance Before Production SSO

## Status

Accepted

## Context

The dashboard needs local governance for lab and operator workstation use before enterprise SSO and durable shared sessions are fully connected in a target environment.

## Decision

Use local RBAC, CSRF-protected forms, audit events, approval policy, environment locks, plan review records, and change records as the baseline dashboard governance model. Treat OIDC provider configuration and server-side session storage as productionization layers rather than prerequisites for local use.

## Consequences

The console can support controlled local workflows now. Internet-exposed or multi-user production use still requires deployment-specific OIDC provider configuration, durable session storage, external validation evidence, and operational controls described in `docs/production-persistence.md`.
