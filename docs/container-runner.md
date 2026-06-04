# Container Runner

Build:

```bash
docker build -t nkp-zerotouch-framework:dev .
```

Run with local configs and bundles mounted:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -v /mnt/c/Share:/mnt/c/Share:ro \
  nkp-zerotouch-framework:dev \
  validate --config configs/environments/connected.example.yaml
```

For live NKP deployment, prefer a Linux VM or WSL runner with direct access to Docker/Podman, Prism Central, registry, SSH keys, and bundle paths.
