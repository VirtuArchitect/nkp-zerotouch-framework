# ADR-0004: Use Local Dashboard Governance Before Production SSO

## Status

Accepted

## Context

The dashboard needs local governance for lab and operator workstation use before enterprise SSO and durable shared sessions are fully implemented.

## Decision

Use local RBAC, CSRF-protected forms, audit events, approval policy, environment locks, plan review records, and change records as the baseline dashboard governance model. Treat OIDC and server-side session storage as productionization layers rather than prerequisites for local use.

## Consequences

The console can support controlled local workflows now. Internet-exposed or multi-user production use still requires completed OIDC token exchange, durable session storage, and operational controls described in `docs/production-persistence.md`.
