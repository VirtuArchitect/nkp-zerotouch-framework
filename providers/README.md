# Providers

Provider folders describe deployment target contracts used by the ZeroTouch
framework. The current generator is implemented for Nutanix AHV, while this
directory defines extension boundaries for additional target types.

Each provider should document:

- Supported environment types.
- Required environment YAML fields.
- Required credentials and secret backend keys.
- Validation and preflight checks.
- Generate, registry, deploy, verify, upgrade, and destroy behavior.

Provider-specific implementation can move here once the shell entrypoints are
split into reusable provider modules.
