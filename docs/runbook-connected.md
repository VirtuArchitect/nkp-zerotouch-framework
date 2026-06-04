# Connected Runbook

1. Copy `configs/environments/connected.example.yaml`.
2. Replace Prism Central, subnet, image, endpoint IP, and SSH settings.
3. Run `validate`.
4. Run `prepare`.
5. Run `secrets` with a local secrets file.
6. Run `generate`.
7. Review `.zt/environments/<name>/generated/deploy.sh`.
8. Run `deploy` without apply.
9. Run `deploy -Apply` only after replacing placeholders.
10. Run `verify`.
