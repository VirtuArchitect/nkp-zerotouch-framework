# ADR-0003: Keep The Public Demo Static

## Status

Accepted

## Context

The project needs a public demo that shows the operator experience without exposing local runners, secrets, `.zt` state, Prism Central, registries, or NKP tooling.

## Decision

Serve the public demo from static GitHub Pages assets under `docs/demo/`. The demo may mirror dashboard screens and workflow states, but it must not call the CLI, mutate state, authenticate users, or connect to infrastructure.

## Consequences

The public demo is safe to inspect and share, but it is not proof of real deployment behavior. Runtime behavior must be verified through the local dashboard, CLI smoke tests, generated artifacts, and CI.
