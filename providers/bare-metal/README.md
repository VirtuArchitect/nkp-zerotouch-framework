# Bare Metal Provider

Status: design placeholder.

This provider is reserved for a future NKP bare-metal workflow.

Required design items before implementation:

- Supported NKP bare-metal command path and version matrix.
- Node inventory schema, including roles, NICs, disks, BMC endpoints, and boot
  mode.
- Image/PXE or ISO preparation flow.
- BMC credential and power-control integration.
- Network admission checks for management, workload, API VIP, and ingress
  ranges.

Until these items are implemented, bare metal should remain provider intent
only and should not be used for live apply.
