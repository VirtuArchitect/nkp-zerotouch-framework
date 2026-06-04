# Air-Gapped Runbook

1. Copy `configs/environments/air-gapped.example.yaml`.
2. Configure the air-gapped bundle path and registry.
3. Configure registry CA or insecure behavior.
4. Run `validate`.
5. Run `prepare`.
6. Run `secrets`.
7. Run `registry` and review `registry.sh`.
8. Run `registry -Apply` only after credentials and registry are ready.
9. Run `generate`.
10. Run `deploy -Apply` only after generated commands are reviewed.
11. Run `verify`.
