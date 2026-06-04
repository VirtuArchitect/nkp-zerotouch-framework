#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if git grep -n -E 'BEGIN .*PRIVATE KEY|client-key-data:|token:[[:space:]]*[^[:space:]]+|secret:[[:space:]]*[^[:space:]]+' -- ':!dist/**' ':!.zt/**' ':!.git/**' ':!*.md' ':!.gitignore' ':!scripts/security-scan.*'; then
  echo "Security scan found possible sensitive content." >&2
  exit 1
fi

if git grep -n -E 'password:[[:space:]]*[^[:space:]]+' -- ':!dist/**' ':!.zt/**' ':!.git/**' ':!*.md' ':!.gitignore' ':!scripts/security-scan.*' | grep -viE 'change-?me|changeme|ZT_REGISTRY_PASSWORD|NUTANIX_PC_PASSWORD|passwordConfigured'; then
  echo "Security scan found possible non-placeholder password content." >&2
  exit 1
fi

echo "Security scan passed."
