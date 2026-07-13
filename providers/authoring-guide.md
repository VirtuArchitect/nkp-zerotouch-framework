# Provider Authoring Guide

Provider folders define the contract between environment intent and generated NKP deployment artifacts.

## Required Provider README Sections

Each provider README should include:

- Status: implemented baseline, partial, design placeholder, or deprecated.
- Supported environment types: `connected`, `proxied`, `air-gapped`, or a narrower subset.
- Required YAML fields and defaults.
- Required credentials and secret backend keys.
- Bundle, registry, proxy, certificate, and runner expectations.
- Generated artifacts and where they are written under `.zt`.
- Safe phases and apply-class phases.
- Verification evidence and production gate expectations.
- Rollback, backup, restore, upgrade, and destroy boundaries.

## Implementation Contract

Provider behavior should preserve the framework control model:

1. Validate inputs before preparing local state.
2. Generate reviewable artifacts before apply.
3. Keep secret values outside Git and generated review artifacts.
4. Record plan hashes when an approval is saved.
5. Block apply when identity, drift, review, verification, lock, or release-channel gates fail.
6. Emit verification evidence that the dashboard can classify as pass, warn, or fail.

## Mode Differences

Connected providers may assume upstream reachability and public registries.

Proxied providers must document proxy and no-proxy handling for Prism Central, registries, service networks, API VIPs, and node access.

Air-gapped providers must document local bundle requirements, registry mirroring, CA/insecure policy, existing-tag behavior, and offline evidence handling.

## Test Expectations

Provider changes should include:

- Parser or schema coverage for new fields.
- Validation tests for missing or invalid required values.
- Generated artifact checks for shell quoting and dry-run defaults.
- Dashboard gate tests when provider output changes plan, verification, or drift behavior.
