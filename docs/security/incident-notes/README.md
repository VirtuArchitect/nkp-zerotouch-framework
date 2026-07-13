# Incident Notes

Use this folder for sanitized notes when a security-relevant event affects the
framework, its demo, its CI/CD path, or its local operator workflow.

## Incident Note Format

```text
# Incident Note: <short title>

Date:
Status: investigating | contained | resolved | informational

## Summary

What happened, without secrets or private infrastructure details.

## Impact

Affected branches, workflows, artifacts, credentials, or users.

## Response

Containment, remediation, validation, and follow-up actions.

## Evidence

Links to public PRs, commits, workflow runs, or sanitized local evidence.
```

Never commit real tokens, passwords, kubeconfigs, private hostnames, customer
data, or unredacted logs.
