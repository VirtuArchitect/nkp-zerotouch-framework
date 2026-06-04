#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-validate}"
config_path=""
strict="false"
failures=0
warnings=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    validate|prepare|deploy|verify)
      command_name="$1"
      shift
      ;;
    --config|-c)
      config_path="${2:-}"
      shift 2
      ;;
    --strict)
      strict="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

check() {
  local status="$1"
  local message="$2"

  case "$status" in
    PASS) printf '[PASS] %s\n' "$message" ;;
    WARN)
      warnings=$((warnings + 1))
      printf '[WARN] %s\n' "$message"
      ;;
    FAIL)
      failures=$((failures + 1))
      printf '[FAIL] %s\n' "$message"
      ;;
    INFO) printf '[INFO] %s\n' "$message" ;;
  esac
}

yaml_scalar() {
  local key="$1"
  grep -m 1 -E "^[[:space:]]*${key}:[[:space:]]*" "$config_path" \
    | sed -E "s/^[[:space:]]*${key}:[[:space:]]*[\"']?([^\"'[:space:]]+)['\"]?[[:space:]]*$/\1/" || true
}

required_scalar() {
  local name="$1"
  local value="$2"

  if [[ -z "$value" ]]; then
    check FAIL "$name is required."
  else
    check PASS "$name is set."
  fi
}

allowed_value() {
  local name="$1"
  local value="$2"
  shift 2
  local allowed=("$@")

  if [[ -z "$value" ]]; then
    check FAIL "$name is required."
    return
  fi

  for candidate in "${allowed[@]}"; do
    if [[ "$value" == "$candidate" ]]; then
      check PASS "$name is '$value'."
      return
    fi
  done

  check FAIL "$name '$value' is unsupported. Expected one of: ${allowed[*]}."
}

path_exists() {
  local display_path="$1"
  local local_path="$2"
  local description="$3"

  if [[ -z "$display_path" ]]; then
    check FAIL "$description path is required."
    return 1
  fi

  if [[ -e "$local_path" ]]; then
    check PASS "$description found: $display_path"
    return 0
  fi

  check FAIL "$description not found: $display_path"
  return 1
}

command_available() {
  local command_name="$1"
  local required="${2:-false}"

  if command -v "$command_name" >/dev/null 2>&1; then
    check PASS "Tool available: $command_name"
  elif [[ "$required" == "true" ]]; then
    check FAIL "Required tool missing from PATH: $command_name"
  else
    check WARN "Optional tool missing from PATH: $command_name"
  fi
}

tcp_endpoint() {
  local endpoint="$1"
  local name="$2"

  if [[ -z "$endpoint" ]]; then
    check WARN "$name endpoint is not configured."
    return
  fi

  if [[ "$endpoint" == *".example.com"* ]]; then
    check WARN "$name uses placeholder endpoint: $endpoint"
    return
  fi

  check INFO "$name reachability check is scaffolded for: $endpoint"
}

bundle_file() {
  local bundle_path="$1"
  local relative_path="$2"
  local description="$3"

  path_exists "$bundle_path/$relative_path" "$bundle_path/$relative_path" "$description" || true
}

validate_bundle() {
  local bundle_path="$1"
  local bundle_type="$2"
  local version="$3"

  if ! path_exists "$bundle_path" "$bundle_path" "NKP bundle"; then
    return
  fi

  bundle_file "$bundle_path" "cli/nkp" "nkp CLI"
  bundle_file "$bundle_path" "kubectl" "kubectl"
  bundle_file "$bundle_path" "konvoy-bootstrap-image-${version}.tar" "Konvoy bootstrap image"
  bundle_file "$bundle_path" "nkp-image-builder-image-${version}.tar" "NKP image builder image"
  bundle_file "$bundle_path" "application-repositories/kommander-applications-${version}.tar.gz" "Kommander application repository"
  bundle_file "$bundle_path" "container-images/konvoy-image-bundle-${version}.tar" "Konvoy image bundle"
  bundle_file "$bundle_path" "container-images/kommander-image-bundle-${version}.tar" "Kommander image bundle"

  if [[ -d "$bundle_path/image-artifacts" ]]; then
    local artifact_count
    artifact_count="$(find "$bundle_path/image-artifacts" -type f | wc -l | tr -d ' ')"
    check PASS "Image artifact files discovered: $artifact_count"
  else
    check FAIL "Image artifacts directory missing: $bundle_path/image-artifacts"
  fi

  case "$bundle_type" in
    standard) check PASS "Standard bundle workflow selected." ;;
    air-gapped) check PASS "Air-gapped bundle workflow selected." ;;
  esac
}

prepare_workspace() {
  local environment_name="$1"
  local environment_type="$2"
  local bundle_type="$3"
  local bundle_path="$4"
  local nkp_version="$5"
  local prism_endpoint="$6"
  local registry_endpoint="$7"
  local registry_namespace="$8"

  local repo_root
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local environment_root="$repo_root/.zt/environments/$environment_name"
  local bin_dir="$environment_root/bin"
  local generated_dir="$environment_root/generated"
  local logs_dir="$environment_root/logs"
  local state_dir="$environment_root/state"

  printf '\n'
  check INFO "Preparing ZeroTouch workspace for '$environment_name'."

  mkdir -p "$bin_dir" "$generated_dir" "$logs_dir" "$state_dir"
  check PASS "Directory ready: $environment_root"
  check PASS "Directory ready: $bin_dir"
  check PASS "Directory ready: $generated_dir"
  check PASS "Directory ready: $logs_dir"
  check PASS "Directory ready: $state_dir"

  if [[ -n "$bundle_path" ]]; then
    cp -f "$bundle_path/cli/nkp" "$bin_dir/nkp"
    cp -f "$bundle_path/kubectl" "$bin_dir/kubectl"
    chmod +x "$bin_dir/nkp" "$bin_dir/kubectl"
    check PASS "Staged nkp CLI to $bin_dir/nkp"
    check PASS "Staged kubectl to $bin_dir/kubectl"
  else
    check WARN "No bundlePath was configured; skipping local tool staging."
  fi

  local metadata_path="$state_dir/environment.json"
  cat >"$metadata_path" <<EOF
{
  "preparedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "environment": {
    "name": "$environment_name",
    "type": "$environment_type"
  },
  "nkp": {
    "version": "$nkp_version",
    "bundleType": "$bundle_type",
    "bundlePath": "$bundle_path"
  },
  "nutanix": {
    "prismCentralEndpoint": "$prism_endpoint"
  },
  "registry": {
    "endpoint": "$registry_endpoint",
    "namespace": "$registry_namespace"
  },
  "paths": {
    "config": "$(cd "$(dirname "$config_path")" && pwd)/$(basename "$config_path")",
    "environmentRoot": "$environment_root",
    "bin": "$bin_dir",
    "generated": "$generated_dir",
    "logs": "$logs_dir",
    "state": "$state_dir"
  }
}
EOF
  check PASS "Wrote environment metadata: $metadata_path"

  local manifest_path="$state_dir/staged-tools.json"
  printf '[\n' >"$manifest_path"
  local first="true"
  for tool_name in nkp kubectl; do
    local tool_path="$bin_dir/$tool_name"
    if [[ -f "$tool_path" ]]; then
      if [[ "$first" == "false" ]]; then
        printf ',\n' >>"$manifest_path"
      fi
      first="false"
      local size_bytes
      size_bytes="$(wc -c <"$tool_path" | tr -d ' ')"
      printf '  { "name": "%s", "path": "%s", "sizeBytes": %s }\n' "$tool_name" "$tool_path" "$size_bytes" >>"$manifest_path"
    fi
  done
  printf ']\n' >>"$manifest_path"
  check PASS "Wrote staged tool manifest: $manifest_path"

  printf '\nPrepare summary: workspace ready at %s\n' "$environment_root"
}

if [[ -z "$config_path" ]]; then
  echo "Missing required --config path." >&2
  exit 2
fi

if [[ ! -f "$config_path" ]]; then
  echo "Config file not found: $config_path" >&2
  exit 1
fi

case "$command_name" in
  validate|prepare)
    environment_name="$(yaml_scalar name)"
    environment_type="$(yaml_scalar type)"
    bundle_type="$(yaml_scalar bundleType)"
    bundle_path="$(yaml_scalar bundlePath)"
    nkp_version="$(yaml_scalar version)"
    prism_endpoint="$(yaml_scalar prismCentralEndpoint)"
    registry_endpoint="$(yaml_scalar endpoint)"
    registry_namespace="$(yaml_scalar namespace)"
    http_proxy="$(yaml_scalar httpProxy)"
    https_proxy="$(yaml_scalar httpsProxy)"

    check INFO "ZeroTouch command: validate"
    check INFO "Config: $config_path"

    required_scalar "environment.name" "$environment_name"
    allowed_value "environment.type" "$environment_type" connected proxied air-gapped
    required_scalar "nkp.version" "$nkp_version"

    if [[ -n "$bundle_type" ]]; then
      allowed_value "nkp.bundleType" "$bundle_type" standard air-gapped
    else
      check WARN "nkp.bundleType is not set; bundle discovery will be skipped."
    fi

    if [[ "$environment_type" == "air-gapped" && "$bundle_type" != "air-gapped" ]]; then
      check FAIL "Air-gapped environments must use nkp.bundleType: air-gapped."
    elif [[ "$environment_type" =~ ^(connected|proxied)$ && "$bundle_type" == "air-gapped" ]]; then
      check WARN "$environment_type environment is using an air-gapped bundle."
    fi

    if [[ -n "$bundle_path" ]]; then
      validate_bundle "$bundle_path" "$bundle_type" "$nkp_version"
    elif [[ "$environment_type" == "air-gapped" ]]; then
      check FAIL "nkp.bundlePath is required for air-gapped environments."
    else
      check WARN "nkp.bundlePath is not set; online tooling must provide NKP binaries."
    fi

    tcp_endpoint "$prism_endpoint" "Prism Central"

    if [[ "$environment_type" == "air-gapped" ]]; then
      required_scalar "registry.endpoint" "$registry_endpoint"
      required_scalar "registry.namespace" "$registry_namespace"
      tcp_endpoint "$registry_endpoint" "Registry"
    fi

    if [[ "$environment_type" == "proxied" ]]; then
      required_scalar "environment.proxy.httpProxy" "$http_proxy"
      required_scalar "environment.proxy.httpsProxy" "$https_proxy"
    fi

    command_available ssh true
    command_available docker false
    command_available podman false
    command_available openssl false

    if [[ "$strict" == "true" && "$warnings" -gt 0 ]]; then
      check FAIL "Strict mode treats warnings as failures."
    fi

    printf '\nValidation summary: %s failure(s), %s warning(s).\n' "$failures" "$warnings"

    if [[ "$failures" -gt 0 ]]; then
      exit 1
    fi

    if [[ "$command_name" == "prepare" ]]; then
      prepare_workspace "$environment_name" "$environment_type" "$bundle_type" "$bundle_path" "$nkp_version" "$prism_endpoint" "$registry_endpoint" "$registry_namespace"
    fi
    ;;
  deploy|verify)
    echo "Command '$command_name' is scaffolded. Mode-specific implementation comes next."
    ;;
  *)
    echo "Unsupported command '$command_name'." >&2
    exit 2
    ;;
esac
