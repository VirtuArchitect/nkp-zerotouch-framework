# Security Reviews

Use this folder to capture security review notes for changes that touch
authentication, authorization, sessions, secrets, file handling, shell
execution, CI/CD, containers, or external integrations.

## Suggested Review Note Format

```text
# Security Review: <change title>

Date: YYYY-MM-DD
Reviewer:
Change:

## Scope

- Files or features reviewed.
- Threat model areas affected.

## Findings

- Finding, severity, and resolution.

## Checks

- Security scans.
- Tests.
- Smoke checks.

## Residual Risk

- Known limitations or external dependencies.
```

Do not include real secrets, kubeconfigs, private endpoints, customer data, or
proprietary lab evidence in committed review notes.
