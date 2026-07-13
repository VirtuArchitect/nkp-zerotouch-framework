#!/usr/bin/env python3
import argparse
import json
import re
import shlex
import sys
import time
from pathlib import Path

import yaml

try:
    import jsonschema
except ImportError:
    jsonschema = None


ENV_TYPES = {"connected", "proxied", "air-gapped"}
BUNDLE_TYPES = {"standard", "air-gapped"}
PROVIDER_TYPES = {"nutanix-ahv", "air-gapped-ahv", "proxied-ahv", "bare-metal"}
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "configs" / "schema" / "environment.schema.json"


class RawShell(str):
    pass


def load_yaml(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return data


def dotted_get(data, dotted_path, default=""):
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    if current is None:
        return default
    if isinstance(current, (dict, list)):
        return json.dumps(current, separators=(",", ":"))
    return str(current)


def require(errors, data, dotted_path):
    value = dotted_get(data, dotted_path)
    if value == "":
        errors.append(f"{dotted_path} is required")
    return value


def load_schema():
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def schema_errors(data):
    if jsonschema is None or not hasattr(jsonschema, "Draft202012Validator"):
        return fallback_schema_errors(data)
    validator = jsonschema.Draft202012Validator(load_schema())
    return [format_schema_error(error) for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path))]


def format_schema_error(error):
    location = ".".join(str(part) for part in error.absolute_path)
    prefix = f"{location}: " if location else ""
    return f"{prefix}{error.message}"


def fallback_schema_errors(data):
    errors = []
    environment_name = raw_dotted_get(data, "environment.name")
    if environment_name is not None:
        if not isinstance(environment_name, str):
            errors.append("environment.name must be a string")
        elif not ENVIRONMENT_NAME_PATTERN.fullmatch(environment_name):
            errors.append("environment.name must contain only letters, numbers, underscores, and hyphens")
    integer_minimums = {
        "cluster.controlPlaneReplicas": 1,
        "cluster.workerReplicas": 0,
        "cluster.controlPlaneEndpointPort": 1,
        "registry.pushConcurrency": 1,
    }
    for path, minimum in integer_minimums.items():
        value = raw_dotted_get(data, path)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path} must be an integer")
        elif value < minimum:
            errors.append(f"{path} must be greater than or equal to {minimum}")
    boolean_paths = ["registry.insecure", "cluster.selfManaged", "cluster.fips"]
    for path in boolean_paths:
        value = raw_dotted_get(data, path)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{path} must be a boolean")
    return errors


def raw_dotted_get(data, dotted_path):
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def validate_config(data):
    errors = schema_errors(data)
    warnings = []

    env_type = require(errors, data, "environment.type")
    provider = dotted_get(data, "environment.provider", "nutanix-ahv")
    env_name = require(errors, data, "environment.name")
    version = require(errors, data, "nkp.version")
    bundle_type = dotted_get(data, "nkp.bundleType")
    bundle_path = dotted_get(data, "nkp.bundlePath")

    if env_type and env_type not in ENV_TYPES:
        errors.append(f"environment.type must be one of: {', '.join(sorted(ENV_TYPES))}")
    if bundle_type and bundle_type not in BUNDLE_TYPES:
        errors.append(f"nkp.bundleType must be one of: {', '.join(sorted(BUNDLE_TYPES))}")
    if provider and provider not in PROVIDER_TYPES:
        errors.append(f"environment.provider must be one of: {', '.join(sorted(PROVIDER_TYPES))}")
    if env_name and not ENVIRONMENT_NAME_PATTERN.fullmatch(env_name):
        message = "environment.name must contain only letters, numbers, underscores, and hyphens"
        if message not in errors:
            errors.append(message)

    require(errors, data, "nutanix.prismCentralEndpoint")
    require(errors, data, "nutanix.clusterName")
    require(errors, data, "cluster.name")
    require(errors, data, "cluster.kubernetesVersion")

    if env_type == "air-gapped":
        if bundle_type != "air-gapped":
            errors.append("air-gapped environments must use nkp.bundleType: air-gapped")
        require(errors, data, "nkp.bundlePath")
        require(errors, data, "registry.endpoint")
        require(errors, data, "registry.namespace")
    elif env_type in {"connected", "proxied"} and bundle_type == "air-gapped":
        warnings.append(f"{env_type} environment is using an air-gapped bundle")

    if env_type == "proxied":
        require(errors, data, "environment.proxy.httpProxy")
        require(errors, data, "environment.proxy.httpsProxy")

    if version and bundle_path and not bundle_path.endswith(f"nkp-{version}"):
        warnings.append("nkp.bundlePath does not end with nkp.version; verify bundle/version alignment")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def identity_values(data, config_path):
    return {
        "config": str(Path(config_path)),
        "environment": dotted_get(data, "environment.name"),
        "cluster": dotted_get(data, "cluster.name"),
        "api_vip": dotted_get(data, "cluster.controlPlaneEndpointIp"),
        "registry_namespace": dotted_get(data, "registry.namespace"),
    }


def identity_errors(items):
    fields = [
        ("environment", "Environment name"),
        ("cluster", "Cluster name"),
        ("api_vip", "API endpoint VIP"),
        ("registry_namespace", "Registry namespace"),
    ]
    errors = []
    for key, label in fields:
        seen = {}
        for item in items:
            value = str(item.get(key, "")).strip()
            if not value:
                continue
            seen.setdefault(value.lower(), []).append(item)
        for matches in seen.values():
            if len(matches) > 1:
                configs = ", ".join(Path(match["config"]).name for match in matches)
                errors.append(f"{label} '{matches[0].get(key)}' is duplicated in {configs}")
    return errors


def validate_all_configs(directory):
    base = Path(directory)
    files = sorted(list(base.glob("*.yaml")) + list(base.glob("*.yml")))
    results = []
    identities = []
    errors = []
    for path in files:
        data = load_yaml(path)
        result = validate_config(data)
        results.append({
            "config": str(path),
            "valid": result["valid"],
            "errors": result["errors"],
            "warnings": result["warnings"],
        })
        identities.append(identity_values(data, path))
        errors.extend(f"{path.name}: {error}" for error in result["errors"])
    errors.extend(identity_errors(identities))
    return {"valid": not errors, "errors": errors, "configs": results}


def context(data, config_path):
    root = {
        "environmentName": dotted_get(data, "environment.name"),
        "environmentType": dotted_get(data, "environment.type"),
        "environmentProvider": dotted_get(data, "environment.provider", "nutanix-ahv"),
        "bundleType": dotted_get(data, "nkp.bundleType"),
        "bundlePath": dotted_get(data, "nkp.bundlePath"),
        "nkpVersion": dotted_get(data, "nkp.version"),
        "prismCentralEndpoint": dotted_get(data, "nutanix.prismCentralEndpoint"),
        "prismElementCluster": dotted_get(data, "nutanix.clusterName"),
        "subnetName": dotted_get(data, "nutanix.subnetName"),
        "imageName": dotted_get(data, "nutanix.imageName"),
        "clusterName": dotted_get(data, "cluster.name"),
        "kubernetesVersion": dotted_get(data, "cluster.kubernetesVersion"),
        "controlPlaneReplicas": dotted_get(data, "cluster.controlPlaneReplicas", "3"),
        "workerReplicas": dotted_get(data, "cluster.workerReplicas", "3"),
        "podCidr": dotted_get(data, "cluster.podCidr", "192.168.0.0/16"),
        "serviceCidr": dotted_get(data, "cluster.serviceCidr", "10.96.0.0/12"),
        "controlPlaneEndpointIp": dotted_get(data, "cluster.controlPlaneEndpointIp"),
        "controlPlaneEndpointPort": dotted_get(data, "cluster.controlPlaneEndpointPort", "6443"),
        "sshPublicKeyFile": dotted_get(data, "cluster.sshPublicKeyFile"),
        "sshUsername": dotted_get(data, "cluster.sshUsername"),
        "ntpServers": dotted_get(data, "cluster.ntpServers"),
        "loadBalancerIpRange": dotted_get(data, "cluster.loadBalancerIpRange"),
        "selfManaged": dotted_get(data, "cluster.selfManaged", "false"),
        "fips": dotted_get(data, "cluster.fips", "false"),
        "storageContainer": dotted_get(data, "nutanix.storageContainer"),
        "project": dotted_get(data, "nutanix.project"),
        "registryEndpoint": dotted_get(data, "registry.endpoint"),
        "registryNamespace": dotted_get(data, "registry.namespace"),
        "registryInsecure": dotted_get(data, "registry.insecure", "false"),
        "registryCaCert": dotted_get(data, "registry.caCert"),
        "registryPushConcurrency": dotted_get(data, "registry.pushConcurrency", "1"),
        "registryOnExistingTag": dotted_get(data, "registry.onExistingTag", "overwrite"),
        "httpProxy": dotted_get(data, "environment.proxy.httpProxy"),
        "httpsProxy": dotted_get(data, "environment.proxy.httpsProxy"),
        "noProxy": dotted_get(data, "environment.proxy.noProxy"),
        "configPath": str(Path(config_path).resolve()),
    }
    return root


def is_truthy(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def shell_join(args):
    return " ".join(str(arg) if isinstance(arg, RawShell) else shlex.quote(str(arg)) for arg in args)


def shell_export(key, value):
    return f"export {key}={shlex.quote(str(value))}"


def build_nkp_command(ctx, dry_run=True):
    args = [
        "./bin/nkp",
        "create",
        "cluster",
        "nutanix",
        "--cluster-name",
        ctx["clusterName"],
        "--endpoint",
        ctx["prismCentralEndpoint"],
        "--kubernetes-version",
        ctx["kubernetesVersion"],
        "--control-plane-replicas",
        ctx["controlPlaneReplicas"],
        "--worker-replicas",
        ctx["workerReplicas"],
        "--control-plane-vm-image",
        ctx["imageName"],
        "--worker-vm-image",
        ctx["imageName"],
        "--control-plane-prism-element-cluster",
        ctx["prismElementCluster"],
        "--worker-prism-element-cluster",
        ctx["prismElementCluster"],
        "--control-plane-subnets",
        ctx["subnetName"],
        "--worker-subnets",
        ctx["subnetName"],
        "--kubernetes-pod-network-cidr",
        ctx["podCidr"],
        "--kubernetes-service-cidr",
        ctx["serviceCidr"],
    ]
    if ctx["environmentType"] == "air-gapped":
        args.append("--airgapped")
    if ctx["registryEndpoint"]:
        args.extend([
            "--registry-mirror-url",
            ctx["registryEndpoint"],
            RawShell("${ZT_REGISTRY_USERNAME:+--registry-mirror-username}"),
            RawShell("${ZT_REGISTRY_USERNAME:-}"),
            RawShell("${ZT_REGISTRY_PASSWORD:+--registry-mirror-password}"),
            RawShell("${ZT_REGISTRY_PASSWORD:-}"),
        ])
    if ctx["environmentType"] == "proxied":
        if ctx["httpProxy"]:
            args.extend(["--http-proxy", ctx["httpProxy"]])
        if ctx["httpsProxy"]:
            args.extend(["--https-proxy", ctx["httpsProxy"]])
    if ctx["bundlePath"]:
        args.extend([
            "--bootstrap-cluster-image",
            f"{ctx['bundlePath']}/konvoy-bootstrap-image-{ctx['nkpVersion']}.tar",
            "--bundle",
            f"{ctx['bundlePath']}/container-images/konvoy-image-bundle-{ctx['nkpVersion']}.tar,{ctx['bundlePath']}/container-images/kommander-image-bundle-{ctx['nkpVersion']}.tar",
        ])
    optional_pairs = [
        ("controlPlaneEndpointIp", "--control-plane-endpoint-ip"),
        ("controlPlaneEndpointPort", "--control-plane-endpoint-port"),
        ("sshPublicKeyFile", "--ssh-public-key-file"),
        ("sshUsername", "--ssh-username"),
        ("loadBalancerIpRange", "--kubernetes-service-load-balancer-ip-range"),
        ("storageContainer", "--csi-storage-container"),
        ("registryCaCert", "--registry-mirror-cacert"),
    ]
    for key, flag in optional_pairs:
        if ctx[key]:
            args.extend([flag, ctx[key]])
    if ctx["ntpServers"]:
        try:
            ntp_servers = ",".join(json.loads(ctx["ntpServers"]))
        except json.JSONDecodeError:
            ntp_servers = ctx["ntpServers"]
        args.extend(["--ntp-servers", ntp_servers])
    if ctx["project"]:
        args.extend(["--control-plane-pc-project", ctx["project"], "--worker-pc-project", ctx["project"]])
    if is_truthy(ctx["selfManaged"]):
        args.append("--self-managed")
    if is_truthy(ctx["fips"]):
        args.append("--fips")
    if dry_run:
        args.extend(["--dry-run", "--output", "yaml", "--output-directory", "./generated"])
    return shell_join(args)


def render_generate(config_path, generated_dir, state_dir, reports_dir, deploy_ps=False):
    data = load_yaml(config_path)
    ctx = context(data, config_path)
    generated = Path(generated_dir)
    state = Path(state_dir)
    reports = Path(reports_dir)
    for path in [generated, state, reports]:
        path.mkdir(parents=True, exist_ok=True)

    cluster_values = {
        "environment": {"name": ctx["environmentName"], "type": ctx["environmentType"]},
        "nkp": {"version": ctx["nkpVersion"], "bundleType": ctx["bundleType"]},
        "nutanix": {
            "prismCentralEndpoint": ctx["prismCentralEndpoint"],
            "prismElementCluster": ctx["prismElementCluster"],
            "subnetName": ctx["subnetName"],
            "imageName": ctx["imageName"],
        },
        "cluster": {
            "name": ctx["clusterName"],
            "kubernetesVersion": ctx["kubernetesVersion"],
            "controlPlaneReplicas": ctx["controlPlaneReplicas"],
            "workerReplicas": ctx["workerReplicas"],
            "podCidr": ctx["podCidr"],
            "serviceCidr": ctx["serviceCidr"],
        },
        "registry": {"endpoint": ctx["registryEndpoint"], "namespace": ctx["registryNamespace"]},
    }
    cluster_config_path = generated / "cluster-values.yaml"
    cluster_config_path.write_text(yaml.safe_dump(cluster_values, sort_keys=False), encoding="utf-8")

    env_path = generated / "nkp.env"
    env_values = {
        "ZT_ENVIRONMENT_NAME": ctx["environmentName"],
        "ZT_ENVIRONMENT_TYPE": ctx["environmentType"],
        "ZT_NKP_VERSION": ctx["nkpVersion"],
        "ZT_CLUSTER_NAME": ctx["clusterName"],
        "ZT_BUNDLE_TYPE": ctx["bundleType"],
        "ZT_BUNDLE_PATH": ctx["bundlePath"],
        "ZT_REGISTRY_ENDPOINT": ctx["registryEndpoint"],
    }
    env_path.write_text("\n".join(shell_export(key, value) for key, value in env_values.items() if value) + "\n", encoding="utf-8")

    dry_run_command = build_nkp_command(ctx, dry_run=True)
    apply_command = build_nkp_command(ctx, dry_run=False)
    deploy_script_path = generated / "deploy.sh"
    deploy_script_path.write_text(
        "\n".join([
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'cd "$(dirname "$0")/.."',
            "if [[ -f ./secrets/secrets.env ]]; then",
            "  # shellcheck disable=SC1091",
            "  source ./secrets/secrets.env",
            "fi",
            'apply_mode="${ZT_APPLY:-false}"',
            'if [[ "${1:-}" == "--apply" ]]; then',
            '  apply_mode="true"',
            "fi",
            'if [[ "$apply_mode" == "true" ]]; then',
            f"  {apply_command}",
            "else",
            f"  {dry_run_command}",
            "fi",
            "",
        ]),
        encoding="utf-8",
    )
    try:
        deploy_script_path.chmod(deploy_script_path.stat().st_mode | 0o111)
    except OSError:
        pass

    files = [str(cluster_config_path), str(env_path), str(deploy_script_path)]
    if deploy_ps:
        deploy_ps_path = generated / "deploy.ps1"
        ps_dry_run_command = dry_run_command.replace("'", "''")
        ps_apply_command = apply_command.replace("'", "''")
        deploy_ps_path.write_text(
            "\n".join([
                "param([switch]$Apply)",
                "Set-StrictMode -Version Latest",
                '$ErrorActionPreference = "Stop"',
                'Set-Location (Join-Path $PSScriptRoot "..")',
                'Write-Host "Run deploy.sh from Linux or WSL for NKP Linux binaries."',
                'if ($Apply) {',
                f"    Write-Host '{ps_apply_command}'",
                '} else {',
                f"    Write-Host '{ps_dry_run_command}'",
                '}',
                "",
            ]),
            encoding="utf-8",
        )
        files.append(str(deploy_ps_path))

    state_payload = {"generatedAt": utc_stamp(), "files": files, "dryRunCommand": dry_run_command, "applyCommand": apply_command}
    generate_state = state / "generate.json"
    generate_state.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
    return {"files": files, "state": str(generate_state), "dryRunCommand": dry_run_command, "applyCommand": apply_command}


def build_registry_command(ctx):
    konvoy_bundle = f"{ctx['bundlePath']}/container-images/konvoy-image-bundle-{ctx['nkpVersion']}.tar"
    kommander_bundle = f"{ctx['bundlePath']}/container-images/kommander-image-bundle-{ctx['nkpVersion']}.tar"
    args = [
        "./bin/nkp",
        "push",
        "bundle",
        "--bundle",
        konvoy_bundle,
        "--bundle",
        kommander_bundle,
        "--to-registry",
        ctx["registryEndpoint"],
    ]
    if ctx["registryCaCert"]:
        args.extend(["--to-registry-ca-cert-file", ctx["registryCaCert"]])
    if is_truthy(ctx["registryInsecure"]):
        args.append("--to-registry-insecure-skip-tls-verify")
    if ctx["registryPushConcurrency"]:
        args.extend(["--image-push-concurrency", ctx["registryPushConcurrency"]])
    if ctx["registryOnExistingTag"]:
        args.extend(["--on-existing-tag", ctx["registryOnExistingTag"]])
    args.extend([
        "--force-oci-media-types",
        "--to-registry-username",
        RawShell('"$ZT_REGISTRY_USERNAME"'),
        "--to-registry-password",
        RawShell('"$ZT_REGISTRY_PASSWORD"'),
    ])
    return shell_join(args), konvoy_bundle, kommander_bundle


def render_registry(config_path, generated_dir, state_dir):
    data = load_yaml(config_path)
    ctx = context(data, config_path)
    generated = Path(generated_dir)
    state = Path(state_dir)
    generated.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)

    plan_path = generated / "registry-plan.md"
    script_path = generated / "registry.sh"
    script_value = None
    if ctx["environmentType"] != "air-gapped":
        plan_path.write_text(
            f"# Registry Plan\n\nEnvironment `{ctx['environmentName']}` is `{ctx['environmentType']}`.\n\nNo mandatory image mirroring is required.\n",
            encoding="utf-8",
        )
    else:
        command, konvoy_bundle, kommander_bundle = build_registry_command(ctx)
        plan_path.write_text(
            "\n".join([
                "# Registry Plan",
                "",
                f"Environment: `{ctx['environmentName']}`",
                f"Registry: `{ctx['registryEndpoint']}`",
                f"Namespace: `{ctx['registryNamespace']}`",
                "",
                "Bundles:",
                "",
                f"- `{konvoy_bundle}`",
                f"- `{kommander_bundle}`",
                "",
                "The generated script uses nkp push bundle. Provide credentials through environment variables before running it:",
                "",
                "- ZT_REGISTRY_USERNAME",
                "- ZT_REGISTRY_PASSWORD",
                "",
            ]),
            encoding="utf-8",
        )
        script_path.write_text(
            "\n".join([
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'cd "$(dirname "$0")/.."',
                "if [[ -f ./secrets/secrets.env ]]; then",
                "  # shellcheck disable=SC1091",
                "  source ./secrets/secrets.env",
                "fi",
                ': "${ZT_REGISTRY_USERNAME:?Set ZT_REGISTRY_USERNAME}"',
                ': "${ZT_REGISTRY_PASSWORD:?Set ZT_REGISTRY_PASSWORD}"',
                command,
                "",
            ]),
            encoding="utf-8",
        )
        try:
            script_path.chmod(script_path.stat().st_mode | 0o111)
        except OSError:
            pass
        script_value = str(script_path)

    registry_state = state / "registry.json"
    registry_state.write_text(json.dumps({"generatedAt": utc_stamp(), "registryPlan": str(plan_path), "registryScript": script_value}, indent=2) + "\n", encoding="utf-8")
    return {"registryPlan": str(plan_path), "registryScript": script_value, "state": str(registry_state)}


def utc_stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def render_secret_env(secrets_path):
    secrets = load_yaml(secrets_path)
    values = {
        "NUTANIX_USER": dotted_get(secrets, "prismCentral.username"),
        "NUTANIX_PASSWORD": dotted_get(secrets, "prismCentral.password"),
        "NUTANIX_PC_USERNAME": dotted_get(secrets, "prismCentral.username"),
        "NUTANIX_PC_PASSWORD": dotted_get(secrets, "prismCentral.password"),
        "ZT_REGISTRY_USERNAME": dotted_get(secrets, "registry.username"),
        "ZT_REGISTRY_PASSWORD": dotted_get(secrets, "registry.password"),
        "ZT_PROXY_USERNAME": dotted_get(secrets, "proxy.username"),
        "ZT_PROXY_PASSWORD": dotted_get(secrets, "proxy.password"),
        "ZT_SSH_PRIVATE_KEY": dotted_get(secrets, "ssh.privateKeyPath"),
        "ZT_SSH_USERNAME": dotted_get(secrets, "ssh.username"),
    }
    return "\n".join(shell_export(key, value) for key, value in values.items() if value) + "\n"


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--config", required=True)

    validate_all = sub.add_parser("validate-all")
    validate_all.add_argument("--directory", default=str(Path("configs") / "environments"))

    get = sub.add_parser("get")
    get.add_argument("--config", required=True)
    get.add_argument("--path", required=True)

    ctx = sub.add_parser("context")
    ctx.add_argument("--config", required=True)

    env = sub.add_parser("secret-env")
    env.add_argument("--secrets", required=True)

    generate = sub.add_parser("render-generate")
    generate.add_argument("--config", required=True)
    generate.add_argument("--generated-dir", required=True)
    generate.add_argument("--state-dir", required=True)
    generate.add_argument("--reports-dir", required=True)
    generate.add_argument("--deploy-ps", action="store_true")

    registry = sub.add_parser("render-registry")
    registry.add_argument("--config", required=True)
    registry.add_argument("--generated-dir", required=True)
    registry.add_argument("--state-dir", required=True)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            print(json.dumps(validate_config(load_yaml(args.config)), indent=2))
        elif args.command == "validate-all":
            result = validate_all_configs(args.directory)
            print(json.dumps(result, indent=2))
            if not result["valid"]:
                return 1
        elif args.command == "get":
            print(dotted_get(load_yaml(args.config), args.path))
        elif args.command == "context":
            print(json.dumps(context(load_yaml(args.config), args.config), indent=2))
        elif args.command == "secret-env":
            print(render_secret_env(args.secrets), end="")
        elif args.command == "render-generate":
            print(json.dumps(render_generate(args.config, args.generated_dir, args.state_dir, args.reports_dir, args.deploy_ps), indent=2))
        elif args.command == "render-registry":
            print(json.dumps(render_registry(args.config, args.generated_dir, args.state_dir), indent=2))
    except Exception as exc:
        print(f"zt_config error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
