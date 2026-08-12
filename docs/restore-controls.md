# Restore Controls

Restore remains plan-first and manual by default. The dashboard can create an
approval-gated restore authorization job from clean restore metadata, but that
job does not copy files or mutate environment state. Do not add automated
restore apply behavior until copy semantics, conflict handling, and post-restore
verification controls are implemented and reviewed.

## Restore Execution Requirements

Before restore execution is automated, the framework must require:

- A selected backup manifest with environment, timestamp, source paths, and operator-visible contents.
- A generated restore plan that lists every file or state folder to be restored.
- A current backup before restore begins.
- Environment identity checks proving the target config and state directory match.
- No active lock for the target environment.
- Approval policy for restore authorization jobs.
- A change record linking requester, approvals, backup manifest, restore plan, and rollback notes.
- Audit events for plan generation, approval, execution start, success, failure, and cancellation.

## Dry-Run Behavior

Restore dry run should show:

- Files and directories that would be copied.
- Current files that would be overwritten.
- Missing backup components.
- Required post-restore checks.
- Commands an operator must run before any live apply resumes.

The dashboard restore plan generator records available backup components, file
counts, active lock status, target identity evidence, dry-run file impact,
blocking signals, a restore-specific change record, and JSON metadata for audit.
When the metadata has no blocking signals, an operator can request restore
approval. The approved job records the authorization and required follow-up
checks, then exits without copying files.

## Execution Boundary

Automated restore must not:

- Restore secrets from committed files.
- Overwrite active locks.
- Restore into an environment with unresolved identity conflicts.
- Resume deployment apply automatically.
- Hide failed or partial restore state.

## Required Verification

After restore, operators should rerun:

1. Preflight.
2. Drift detection.
3. Plan review.
4. Verification.
5. Backup.

Automated restore execution still needs implementation, tests, and security
review before it moves beyond approval-gated manual authorization.
