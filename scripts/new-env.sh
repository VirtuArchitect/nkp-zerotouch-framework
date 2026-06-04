#!/usr/bin/env bash
set -euo pipefail

name="${1:?usage: scripts/new-env.sh <name> [connected|proxied|air-gapped]}"
type="${2:-connected}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$type" in
  connected|proxied|air-gapped) ;;
  *) echo "Unsupported type: $type" >&2; exit 2 ;;
esac

source_config="$repo_root/configs/environments/$type.example.yaml"
target_config="$repo_root/configs/environments/$name.yaml"
source_secrets="$repo_root/configs/secrets/lab-${type//-/}.secrets.example.yaml"
target_secrets="$repo_root/configs/secrets/$name.secrets.yaml"

if [[ -f "$target_config" ]]; then
  echo "Environment config already exists: $target_config" >&2
  exit 1
fi

cp "$source_config" "$target_config"
[[ -f "$source_secrets" ]] && cp "$source_secrets" "$target_secrets"

echo "Created environment config: $target_config"
echo "Created local secrets file: $target_secrets"
echo "Edit both files before running validate/apply phases."
