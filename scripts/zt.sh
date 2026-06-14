#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-validate}"
config_path=""
strict="false"
apply="false"
secrets_path=""
target_bundle=""
confirm_destroy="false"
kubeconfig_source=""
failures=0
warnings=0
python_bin="${PYTHON_BIN:-}"

if [[ -z "$python_bin" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  elif command -v python.exe >/dev/null 2>&1; then
    python_bin="python.exe"
  else
    echo "Python is required. Set PYTHON_BIN or install python3." >&2
    exit 2
  fi
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    validate|prepare|generate|registry|deploy|verify|kubeconfig|secrets|backup|upgrade|destroy|runs|ci)
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
    --apply)
      apply="true"
      shift
      ;;
    --secrets)
      secrets_path="${2:-}"
      shift 2
      ;;
    --target-bundle)
      target_bundle="${2:-}"
      shift 2
      ;;
    --confirm-destroy)
      confirm_destroy="true"
      shift
      ;;
    --kubeconfig)
      kubeconfig_source="${2:-}"
      shift 2
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
  local path="$key"
  case "$key" in
    name) path="environment.name" ;;
    type) path="environment.type" ;;
    version) path="nkp.version" ;;
    bundleType) path="nkp.bundleType" ;;
    bundlePath) path="nkp.bundlePath" ;;
    prismCentralEndpoint) path="nutanix.prismCentralEndpoint" ;;
    endpoint) path="registry.endpoint" ;;
    namespace) path="registry.namespace" ;;
    httpProxy) path="environment.proxy.httpProxy" ;;
    httpsProxy) path="environment.proxy.httpsProxy" ;;
  esac
  "$python_bin" ./tools/zt_config.py get --config "$config_path" --path "$path"
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
  local secrets_dir="$environment_root/secrets"

  printf '\n'
  check INFO "Preparing ZeroTouch workspace for '$environment_name'."

  mkdir -p "$bin_dir" "$generated_dir" "$logs_dir" "$state_dir" "$secrets_dir"
  check PASS "Directory ready: $environment_root"
  check PASS "Directory ready: $bin_dir"
  check PASS "Directory ready: $generated_dir"
  check PASS "Directory ready: $logs_dir"
  check PASS "Directory ready: $state_dir"
  check PASS "Directory ready: $secrets_dir"

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
    "state": "$state_dir",
    "secrets": "$secrets_dir"
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

section_scalar() {
  local section="$1"
  local key="$2"
  "$python_bin" ./tools/zt_config.py get --config "$config_path" --path "$section.$key"
}

context_paths() {
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  environment_root="$repo_root/.zt/environments/$environment_name"
  bin_dir="$environment_root/bin"
  generated_dir="$environment_root/generated"
  logs_dir="$environment_root/logs"
  state_dir="$environment_root/state"
  reports_dir="$environment_root/reports"
  secrets_dir="$environment_root/secrets"
}

assert_prepared() {
  context_paths
  if [[ ! -f "$state_dir/environment.json" ]]; then
    echo "Prepare has not completed for '$environment_name'. Run prepare first." >&2
    exit 1
  fi
  check PASS "Prepared workspace found: $environment_root"
}

load_context() {
  environment_name="$(section_scalar environment name)"
  environment_type="$(section_scalar environment type)"
  bundle_type="$(section_scalar nkp bundleType)"
  bundle_path="$(section_scalar nkp bundlePath)"
  nkp_version="$(section_scalar nkp version)"
  prism_endpoint="$(section_scalar nutanix prismCentralEndpoint)"
  prism_cluster="$(section_scalar nutanix clusterName)"
  subnet_name="$(section_scalar nutanix subnetName)"
  image_name="$(section_scalar nutanix imageName)"
  cluster_name="$(section_scalar cluster name)"
  kubernetes_version="$(section_scalar cluster kubernetesVersion)"
  control_plane_replicas="$(section_scalar cluster controlPlaneReplicas)"
  worker_replicas="$(section_scalar cluster workerReplicas)"
  pod_cidr="$(section_scalar cluster podCidr)"
  service_cidr="$(section_scalar cluster serviceCidr)"
  control_plane_endpoint_ip="$(section_scalar cluster controlPlaneEndpointIp)"
  control_plane_endpoint_port="$(section_scalar cluster controlPlaneEndpointPort)"
  ssh_public_key_file="$(section_scalar cluster sshPublicKeyFile)"
  ssh_username="$(section_scalar cluster sshUsername)"
  ntp_servers="$(section_scalar cluster ntpServers)"
  load_balancer_ip_range="$(section_scalar cluster loadBalancerIpRange)"
  self_managed="$(section_scalar cluster selfManaged)"
  fips="$(section_scalar cluster fips)"
  storage_container="$(section_scalar nutanix storageContainer)"
  project="$(section_scalar nutanix project)"
  registry_endpoint="$(section_scalar registry endpoint)"
  registry_namespace="$(section_scalar registry namespace)"
  registry_ca_cert="$(section_scalar registry caCert)"
  registry_insecure="$(section_scalar registry insecure)"
  registry_push_concurrency="$(section_scalar registry pushConcurrency)"
  registry_on_existing_tag="$(section_scalar registry onExistingTag)"
  http_proxy="$(section_scalar proxy httpProxy)"
  https_proxy="$(section_scalar proxy httpsProxy)"
  context_paths
}

generate_assets() {
  load_context
  assert_prepared
  mkdir -p "$generated_dir" "$state_dir" "$reports_dir"

  local airgap_flag=""
  [[ "$environment_type" == "air-gapped" ]] && airgap_flag=" --airgapped"
  local registry_flags=""
  [[ -n "$registry_endpoint" ]] && registry_flags=" --registry-mirror-url $registry_endpoint \${ZT_REGISTRY_USERNAME:+--registry-mirror-username \$ZT_REGISTRY_USERNAME} \${ZT_REGISTRY_PASSWORD:+--registry-mirror-password \$ZT_REGISTRY_PASSWORD}"
  local proxy_flags=""
  [[ "$environment_type" == "proxied" && -n "$http_proxy" ]] && proxy_flags="$proxy_flags --http-proxy $http_proxy"
  [[ "$environment_type" == "proxied" && -n "$https_proxy" ]] && proxy_flags="$proxy_flags --https-proxy $https_proxy"
  local bundle_flags=""
  if [[ -n "$bundle_path" ]]; then
    bundle_flags=" --bootstrap-cluster-image $bundle_path/konvoy-bootstrap-image-$nkp_version.tar --bundle $bundle_path/container-images/konvoy-image-bundle-$nkp_version.tar,$bundle_path/container-images/kommander-image-bundle-$nkp_version.tar"
  fi
  local advanced_flags=""
  [[ -n "$control_plane_endpoint_ip" ]] && advanced_flags="$advanced_flags --control-plane-endpoint-ip $control_plane_endpoint_ip"
  [[ -n "$control_plane_endpoint_port" ]] && advanced_flags="$advanced_flags --control-plane-endpoint-port $control_plane_endpoint_port"
  [[ -n "$ssh_public_key_file" ]] && advanced_flags="$advanced_flags --ssh-public-key-file $ssh_public_key_file"
  [[ -n "$ssh_username" ]] && advanced_flags="$advanced_flags --ssh-username $ssh_username"
  [[ -n "$load_balancer_ip_range" ]] && advanced_flags="$advanced_flags --kubernetes-service-load-balancer-ip-range $load_balancer_ip_range"
  [[ -n "$ntp_servers" ]] && advanced_flags="$advanced_flags --ntp-servers ${ntp_servers//[\[\]\"]/}"
  [[ -n "$storage_container" ]] && advanced_flags="$advanced_flags --csi-storage-container $storage_container"
  [[ -n "$project" ]] && advanced_flags="$advanced_flags --control-plane-pc-project $project --worker-pc-project $project"
  [[ "$self_managed" == "true" || "$self_managed" == "True" ]] && advanced_flags="$advanced_flags --self-managed"
  [[ "$fips" == "true" || "$fips" == "True" ]] && advanced_flags="$advanced_flags --fips"
  [[ -n "$registry_ca_cert" ]] && advanced_flags="$advanced_flags --registry-mirror-cacert $registry_ca_cert"

  local nkp_command="./bin/nkp create cluster nutanix --cluster-name $cluster_name --endpoint $prism_endpoint --kubernetes-version $kubernetes_version --control-plane-replicas $control_plane_replicas --worker-replicas $worker_replicas --control-plane-vm-image $image_name --worker-vm-image $image_name --control-plane-prism-element-cluster $prism_cluster --worker-prism-element-cluster $prism_cluster --control-plane-subnets $subnet_name --worker-subnets $subnet_name --kubernetes-pod-network-cidr $pod_cidr --kubernetes-service-cidr $service_cidr$airgap_flag$registry_flags$proxy_flags$bundle_flags$advanced_flags --dry-run --output yaml --output-directory ./generated"

  cat >"$generated_dir/cluster-values.yaml" <<EOF
environment:
  name: $environment_name
  type: $environment_type
nkp:
  version: $nkp_version
  bundleType: $bundle_type
cluster:
  name: $cluster_name
  kubernetesVersion: $kubernetes_version
EOF

  cat >"$generated_dir/nkp.env" <<EOF
ZT_ENVIRONMENT_NAME=$environment_name
ZT_ENVIRONMENT_TYPE=$environment_type
ZT_NKP_VERSION=$nkp_version
ZT_CLUSTER_NAME=$cluster_name
ZT_BUNDLE_TYPE=$bundle_type
ZT_BUNDLE_PATH=$bundle_path
ZT_REGISTRY_ENDPOINT=$registry_endpoint
EOF

  cat >"$generated_dir/deploy.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "\$(dirname "\$0")/.."
if [[ -f ./secrets/secrets.env ]]; then
  # shellcheck disable=SC1091
  source ./secrets/secrets.env
fi
$nkp_command
EOF
  chmod +x "$generated_dir/deploy.sh"

  cat >"$state_dir/generate.json" <<EOF
{
  "generatedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "dryRunCommand": "$nkp_command"
}
EOF

  check PASS "Generated cluster values: $generated_dir/cluster-values.yaml"
  check PASS "Generated environment file: $generated_dir/nkp.env"
  check PASS "Generated deploy script: $generated_dir/deploy.sh"
}

registry_assets() {
  load_context
  assert_prepared
  mkdir -p "$generated_dir" "$state_dir"

  if [[ "$environment_type" != "air-gapped" ]]; then
    cat >"$generated_dir/registry-plan.md" <<EOF
# Registry Plan

Environment \`$environment_name\` is \`$environment_type\`.

No mandatory image mirroring is required.
EOF
    check PASS "Generated registry plan: $generated_dir/registry-plan.md"
  else
    local konvoy_bundle="$bundle_path/container-images/konvoy-image-bundle-$nkp_version.tar"
    local kommander_bundle="$bundle_path/container-images/kommander-image-bundle-$nkp_version.tar"
    local registry_extra_flags=""
    [[ -n "$registry_ca_cert" ]] && registry_extra_flags="$registry_extra_flags  --to-registry-ca-cert-file \"$registry_ca_cert\" \\
"
    [[ "$registry_insecure" == "true" || "$registry_insecure" == "True" ]] && registry_extra_flags="$registry_extra_flags  --to-registry-insecure-skip-tls-verify \\
"
    [[ -n "$registry_push_concurrency" ]] && registry_extra_flags="$registry_extra_flags  --image-push-concurrency $registry_push_concurrency \\
"
    [[ -n "$registry_on_existing_tag" ]] && registry_extra_flags="$registry_extra_flags  --on-existing-tag $registry_on_existing_tag \\
"
    cat >"$generated_dir/registry-plan.md" <<EOF
# Registry Plan

Environment: \`$environment_name\`
Registry: \`$registry_endpoint\`
Namespace: \`$registry_namespace\`

Bundles:

- \`$konvoy_bundle\`
- \`$kommander_bundle\`
EOF
    cat >"$generated_dir/registry.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "\$(dirname "\$0")/.."
if [[ -f ./secrets/secrets.env ]]; then
  # shellcheck disable=SC1091
  source ./secrets/secrets.env
fi
: "\${ZT_REGISTRY_USERNAME:?Set ZT_REGISTRY_USERNAME}"
: "\${ZT_REGISTRY_PASSWORD:?Set ZT_REGISTRY_PASSWORD}"
./bin/nkp push bundle \\
  --bundle "$konvoy_bundle" \\
  --bundle "$kommander_bundle" \\
  --to-registry "$registry_endpoint" \\
${registry_extra_flags}  --force-oci-media-types \\
  --to-registry-username "\$ZT_REGISTRY_USERNAME" \\
  --to-registry-password "\$ZT_REGISTRY_PASSWORD"
EOF
    chmod +x "$generated_dir/registry.sh"
    check PASS "Generated registry plan: $generated_dir/registry-plan.md"
    check PASS "Generated registry script: $generated_dir/registry.sh"
  fi

  cat >"$state_dir/registry.json" <<EOF
{ "generatedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")", "registryPlan": "$generated_dir/registry-plan.md" }
EOF
  if [[ "$apply" == "true" ]]; then
    if [[ "$environment_type" != "air-gapped" ]]; then
      check INFO "Registry apply is optional for $environment_type; generated plan only."
      return
    fi
    if [[ "$registry_endpoint" == *".example.com"* ]]; then
      echo "Refusing registry apply because registry endpoint is still a placeholder." >&2
      exit 1
    fi
    mkdir -p "$logs_dir"
    "$generated_dir/registry.sh" >"$logs_dir/registry-push.log" 2>&1
    check PASS "Registry apply completed; log: $logs_dir/registry-push.log"
  fi
}

deploy_phase() {
  load_context
  assert_prepared
  if [[ ! -f "$generated_dir/deploy.sh" ]]; then
    echo "Generate has not completed for '$environment_name'. Run generate first." >&2
    exit 1
  fi
  cat >"$generated_dir/deploy-plan.md" <<EOF
# Deploy Plan

Environment: \`$environment_name\`
Cluster: \`$cluster_name\`
Mode: \`$environment_type\`

Generated script:

\`\`\`bash
$generated_dir/deploy.sh
\`\`\`
EOF
  check PASS "Generated deploy plan: $generated_dir/deploy-plan.md"
  if [[ "$apply" != "true" ]]; then
    check INFO "Dry-run mode. Re-run with --apply to execute the generated deploy script."
    return
  fi
  if [[ "$prism_endpoint" == *".example.com"* ]]; then
    echo "Refusing apply because Prism Central endpoint is still a placeholder." >&2
    exit 1
  fi
  mkdir -p "$logs_dir"
  "$generated_dir/deploy.sh" >"$logs_dir/deploy.log" 2>&1
  check PASS "Deploy apply completed; log: $logs_dir/deploy.log"
}

verify_phase() {
  load_context
  assert_prepared
  mkdir -p "$reports_dir"
  local report_path="$reports_dir/verification-summary.md"
  {
    echo "# Verification Summary"
    echo
    echo "Environment: \`$environment_name\`"
    echo "Cluster: \`$cluster_name\`"
    echo
    [[ -f "$state_dir/generate.json" ]] && echo "- pass: generated config - generate.json" || echo "- warn: generated config - generate.json"
    [[ -f "$bin_dir/nkp" ]] && echo "- pass: nkp binary - $bin_dir/nkp" || echo "- fail: nkp binary - $bin_dir/nkp"
    [[ -f "$bin_dir/kubectl" ]] && echo "- pass: kubectl binary - $bin_dir/kubectl" || echo "- fail: kubectl binary - $bin_dir/kubectl"
    [[ -f "$state_dir/kubeconfig" ]] && echo "- pass: kubeconfig - $state_dir/kubeconfig" || echo "- warn: kubeconfig - $state_dir/kubeconfig"
  } >"$report_path"
  if [[ -f "$state_dir/kubeconfig" && -f "$bin_dir/kubectl" ]]; then
    mkdir -p "$logs_dir"
    "$bin_dir/kubectl" --kubeconfig "$state_dir/kubeconfig" get nodes -o wide >"$logs_dir/verify-kubectl.log" 2>&1
    "$bin_dir/kubectl" --kubeconfig "$state_dir/kubeconfig" get nodes >>"$logs_dir/verify-kubectl.log" 2>&1
    "$bin_dir/kubectl" --kubeconfig "$state_dir/kubeconfig" get pods -A >>"$logs_dir/verify-kubectl.log" 2>&1
    "$bin_dir/kubectl" --kubeconfig "$state_dir/kubeconfig" get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded >>"$logs_dir/verify-kubectl.log" 2>&1 || true
    "$bin_dir/nkp" get clusters -A --kubeconfig "$state_dir/kubeconfig" >>"$logs_dir/verify-kubectl.log" 2>&1 || true
    "$bin_dir/nkp" get appdeployments -A --kubeconfig "$state_dir/kubeconfig" >>"$logs_dir/verify-kubectl.log" 2>&1 || true
    check PASS "Live kubectl verification log: $logs_dir/verify-kubectl.log"
  fi
  check PASS "Wrote verification report: $report_path"
}

kubeconfig_phase() {
  load_context
  assert_prepared
  if [[ -z "$kubeconfig_source" ]]; then
    echo "Kubeconfig path is required. Use --kubeconfig <path>." >&2
    exit 2
  fi
  if [[ ! -f "$kubeconfig_source" ]]; then
    echo "Kubeconfig not found: $kubeconfig_source" >&2
    exit 1
  fi
  cp "$kubeconfig_source" "$state_dir/kubeconfig"
  check PASS "Captured kubeconfig: $state_dir/kubeconfig"
}

secrets_phase() {
  load_context
  assert_prepared
  mkdir -p "$state_dir" "$generated_dir" "$secrets_dir"
  local resolved_secrets="$secrets_path"
  [[ -z "$resolved_secrets" ]] && resolved_secrets="$repo_root/configs/secrets/$environment_name.secrets.yaml"
  if [[ ! -f "$resolved_secrets" ]]; then
    echo "Secrets file not found: $resolved_secrets. Copy one of configs/secrets/*.example.yaml and remove .example." >&2
    exit 1
  fi
  cat >"$state_dir/secrets.json" <<EOF
{
  "loadedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "source": "$resolved_secrets",
  "redacted": true
}
EOF
  "$python_bin" ./tools/zt_config.py secret-env --secrets "$resolved_secrets" >"$secrets_dir/secrets.env"
  cat >"$generated_dir/secrets.env.example" <<'EOF'
# Source this file pattern with real values in your shell. Do not commit real secrets.
export NUTANIX_USER="admin"
export NUTANIX_PASSWORD="change-me"
export NUTANIX_PC_USERNAME="admin"
export NUTANIX_PC_PASSWORD="change-me"
export ZT_REGISTRY_USERNAME="registry-user"
export ZT_REGISTRY_PASSWORD="change-me"
EOF
  check PASS "Recorded redacted secrets summary: $state_dir/secrets.json"
  check PASS "Rendered local secret environment file: $secrets_dir/secrets.env"
  check PASS "Wrote shell secrets example: $generated_dir/secrets.env.example"
}

backup_phase() {
  load_context
  assert_prepared
  local stamp
  stamp="$(date -u +"%Y%m%d-%H%M%S")"
  local backup_dir="$environment_root/backup/$stamp"
  mkdir -p "$backup_dir"
  for dir_name in state generated reports; do
    if [[ -d "$environment_root/$dir_name" ]]; then
      cp -a "$environment_root/$dir_name" "$backup_dir/$dir_name"
      check PASS "Backed up $dir_name"
    fi
  done
  cat >"$backup_dir/backup-manifest.json" <<EOF
{ "createdAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")", "environment": "$environment_name", "backup": "$backup_dir" }
EOF
  check PASS "Backup ready: $backup_dir"
}

upgrade_phase() {
  load_context
  assert_prepared
  mkdir -p "$generated_dir"
  cat >"$generated_dir/upgrade-plan.md" <<EOF
# Upgrade Plan

Environment: $environment_name
Current NKP version: $nkp_version
Target bundle: $target_bundle

Planned flow:

1. Run backup.
2. Validate target bundle.
3. Run NKP upgrade commands from Linux or WSL.
4. Run verify.
EOF
  check PASS "Generated upgrade plan: $generated_dir/upgrade-plan.md"
  if [[ "$apply" != "true" ]]; then
    check INFO "Dry-run mode. Re-run with --apply after validating the target bundle."
    return
  fi
  [[ -z "$target_bundle" ]] && { echo "target bundle is required for upgrade apply." >&2; exit 1; }
  [[ "$prism_endpoint" == *".example.com"* ]] && { echo "Refusing upgrade apply because Prism Central endpoint is still a placeholder." >&2; exit 1; }
  check WARN "Live upgrade execution is intentionally not automated yet; plan has been generated for operator review."
}

destroy_phase() {
  load_context
  assert_prepared
  mkdir -p "$generated_dir"
  cat >"$generated_dir/destroy-plan.md" <<EOF
# Destroy Plan

Environment: $environment_name
Cluster: $cluster_name

Command:

\`\`\`bash
./bin/nkp delete cluster --cluster-name $cluster_name
\`\`\`

Destroy requires both --apply and --confirm-destroy.
EOF
  check PASS "Generated destroy plan: $generated_dir/destroy-plan.md"
  if [[ "$apply" != "true" || "$confirm_destroy" != "true" ]]; then
    check INFO "Dry-run mode. Destruction requires --apply --confirm-destroy."
    return
  fi
  [[ "$prism_endpoint" == *".example.com"* ]] && { echo "Refusing destroy apply because Prism Central endpoint is still a placeholder." >&2; exit 1; }
  check WARN "Live destroy execution is guarded; run the generated plan manually from a prepared Linux/WSL runner."
}

runs_phase() {
  load_context
  assert_prepared
  local stamp
  stamp="$(date -u +"%Y%m%d-%H%M%S")"
  local run_dir="$repo_root/.zt/runs/$stamp"
  mkdir -p "$run_dir"
  cat >"$run_dir/summary.json" <<EOF
{
  "capturedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "environment": "$environment_name",
  "type": "$environment_type",
  "cluster": "$cluster_name"
}
EOF
  {
    echo "# Run Summary"
    echo
    echo "Environment: $environment_name"
    echo "Cluster: $cluster_name"
    echo
    for file_name in environment.json staged-tools.json generate.json registry.json secrets.json; do
      [[ -f "$state_dir/$file_name" ]] && echo "- present: $file_name" || echo "- missing: $file_name"
    done
  } >"$run_dir/summary.md"
  check PASS "Captured run summary: $run_dir"
}

ci_phase() {
  check INFO "Running local CI smoke checks."
  bash -n ./scripts/zt.sh
  check PASS "Bash syntax parsed."
  for example in ./configs/environments/*.example.yaml; do
    ./scripts/zt.sh validate --config "$example" >/dev/null
  done
  check PASS "Example config validation completed."
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

    schema_result="$("$python_bin" ./tools/zt_config.py validate --config "$config_path")"
    while IFS= read -r schema_error; do
      [[ -n "$schema_error" ]] && check FAIL "Schema: $schema_error"
    done < <("$python_bin" -c 'import json,sys; data=json.loads(sys.stdin.read()); print("\n".join(data.get("errors", [])))' <<<"$schema_result")
    while IFS= read -r schema_warning; do
      [[ -n "$schema_warning" ]] && check WARN "Schema: $schema_warning"
    done < <("$python_bin" -c 'import json,sys; data=json.loads(sys.stdin.read()); print("\n".join(data.get("warnings", [])))' <<<"$schema_result")

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
  generate)
    generate_assets
    ;;
  registry)
    registry_assets
    ;;
  deploy)
    deploy_phase
    ;;
  verify)
    verify_phase
    ;;
  kubeconfig)
    kubeconfig_phase
    ;;
  secrets)
    secrets_phase
    ;;
  backup)
    backup_phase
    ;;
  upgrade)
    upgrade_phase
    ;;
  destroy)
    destroy_phase
    ;;
  runs)
    runs_phase
    ;;
  ci)
    ci_phase
    ;;
  *)
    echo "Unsupported command '$command_name'." >&2
    exit 2
    ;;
esac
