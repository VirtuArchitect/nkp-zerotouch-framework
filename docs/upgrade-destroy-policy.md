# Upgrade and Destroy Policy

Upgrade and destroy are intentionally guarded.

## Upgrade

`upgrade` generates an operator-reviewed plan. Apply requires:

- real Prism Central endpoint
- target bundle path
- a current backup
- successful validation
- explicit `-Apply` or `--apply`

Live upgrade command sequencing should be confirmed in a lab before production use.

## Destroy

`destroy` generates an operator-reviewed plan. Apply requires:

- real Prism Central endpoint
- explicit `-Apply -ConfirmDestroy` or `--apply --confirm-destroy`
- manual review of generated plan

For production environments, keep destroy as a manual, break-glass workflow.
