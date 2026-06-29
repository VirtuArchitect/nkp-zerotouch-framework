# Deployment Boundaries

This document defines where the framework expects code to run and what each boundary is allowed to do.

## Operator Workstation

The operator workstation is the default development and lab execution boundary. It contains the repository checkout, local config examples, `.zt` generated state, secrets files, and the local dashboard.

Use this boundary for:

- Editing environment YAML.
- Running validation and generation.
- Reviewing plans and dashboard evidence.
- Capturing run history and backups.
- Testing connected, proxied, or air-gapped assumptions before using a controlled runner.

## Container Runner

The container runner packages the dashboard and CLI dependencies for repeatable local execution. It is useful when operators want a consistent Python and shell environment without installing everything directly on the host.

Use this boundary for:

- Running the dashboard through Docker Compose.
- Mounting repository state into a controlled local container.
- Exercising safe phases and dashboard review workflows.

The container does not remove the need for real NKP bundle paths, registry access, Prism Central settings, credentials, approvals, or operator review before apply-class actions.

## Air-Gapped Runner

The air-gapped runner boundary assumes the deployment host has no internet path. Required bundles, mirrored artifacts, registry endpoints, certificates, and credentials must already be available locally.

Use this boundary for:

- Validating air-gapped bundle paths.
- Generating registry mirror plans.
- Running guarded `registry --apply` only after review.
- Running guarded deploy or upgrade steps after artifacts and approvals are in place.

Air-gapped workflows should keep generated evidence, registry plans, and verification reports local unless export is explicitly approved.

## Infrastructure Boundary

The framework treats registry push, cluster deploy, upgrade, destroy, and restore as infrastructure-changing operations. Those actions are outside the safe planning boundary and require:

- Explicit apply flags.
- Valid environment configuration.
- Real credentials supplied outside Git.
- Plan review.
- Approval policy satisfaction.
- Change records and audit evidence.

## Public Demo Boundary

The GitHub Pages demo is static. It is safe for public review because it does not call the CLI, read local `.zt` state, authenticate users, or connect to Nutanix infrastructure.

Use the demo to explain intended operator experience, not to validate real deployment behavior.
