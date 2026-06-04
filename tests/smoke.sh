#!/usr/bin/env bash
set -euo pipefail

config="${1:-./configs/environments/connected.example.yaml}"
python_bin="${PYTHON_BIN:-python3}"

bash -n ./scripts/zt.sh
"$python_bin" ./tools/zt_config.py validate --config "$config" >/dev/null
./scripts/zt.sh validate --config "$config"
./scripts/zt.sh prepare --config "$config"
./scripts/zt.sh generate --config "$config"
./scripts/zt.sh registry --config "$config"
./scripts/zt.sh deploy --config "$config"
./scripts/zt.sh verify --config "$config"
./scripts/zt.sh runs --config "$config"
echo "Bash smoke test completed."
