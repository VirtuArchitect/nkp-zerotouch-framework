# ADR-0001: Keep Local State As The Default Runtime Store

## Status

Accepted

## Context

The framework must support operator workstations, lab runners, and air-gapped environments before it assumes shared infrastructure. Generated plans, logs, backups, reviews, jobs, and audit events also need to remain inspectable without a central service.

## Decision

Use `.zt/` as the default runtime state store. Keep environment YAML in `configs/environments/` as deployment intent, and keep generated state, jobs, audit events, reviews, reports, and backups under ignored local paths.

## Consequences

Local state keeps the framework portable and reviewable in disconnected environments. Multi-user production deployments still need a storage interface and a durable backend such as Postgres for sessions, jobs, approvals, reviews, and audit indexes.
