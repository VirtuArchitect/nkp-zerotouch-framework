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

## Dashboard Console

Run the local console with Docker Compose:

```bash
docker compose up --build dashboard
```

Open:

```text
http://localhost:8080
```

The dashboard only exposes safe actions. Apply/destructive operations remain CLI-only.

Without Compose:

```bash
docker build -t nkp-zerotouch-framework:dev .
docker run --rm -p 8080:8080 \
  -e ZT_DASHBOARD_HOST=0.0.0.0 \
  -v "$PWD:/workspace" \
  -v C:/Share:/mnt/c/Share:ro \
  --entrypoint python \
  nkp-zerotouch-framework:dev dashboard/app.py 8080
```
