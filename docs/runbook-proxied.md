# Proxied Runbook

1. Copy `configs/environments/proxied.example.yaml`.
2. Configure `environment.proxy`.
3. Set Prism, Nutanix, cluster, and SSH fields.
4. Run `validate`, `prepare`, `secrets`, and `generate`.
5. Review generated proxy flags in `deploy.sh`.
6. Run `deploy -Apply` only after endpoint and credential validation.
7. Run `verify`.
