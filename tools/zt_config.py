#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

import yaml


ENV_TYPES = {"connected", "proxied", "air-gapped"}
BUNDLE_TYPES = {"standard", "air-gapped"}
PROVIDER_TYPES = {"nutanix-ahv", "air-gapped-ahv", "proxied-ahv", "bare-metal"}


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


def validate_config(data):
    errors = []
    warnings = []

    env_type = require(errors, data, "environment.type")
    provider = dotted_get(data, "environment.provider", "nutanix-ahv")
    require(errors, data, "environment.name")
    version = require(errors, data, "nkp.version")
    bundle_type = dotted_get(data, "nkp.bundleType")
    bundle_path = dotted_get(data, "nkp.bundlePath")

    if env_type and env_type not in ENV_TYPES:
        errors.append(f"environment.type must be one of: {', '.join(sorted(ENV_TYPES))}")
    if bundle_type and bundle_type not in BUNDLE_TYPES:
        errors.append(f"nkp.bundleType must be one of: {', '.join(sorted(BUNDLE_TYPES))}")
    if provider and provider not in PROVIDER_TYPES:
        errors.append(f"environment.provider must be one of: {', '.join(sorted(PROVIDER_TYPES))}")

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
    return "\n".join(f'export {key}="{value}"' for key, value in values.items() if value) + "\n"


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--config", required=True)

    get = sub.add_parser("get")
    get.add_argument("--config", required=True)
    get.add_argument("--path", required=True)

    ctx = sub.add_parser("context")
    ctx.add_argument("--config", required=True)

    env = sub.add_parser("secret-env")
    env.add_argument("--secrets", required=True)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            print(json.dumps(validate_config(load_yaml(args.config)), indent=2))
        elif args.command == "get":
            print(dotted_get(load_yaml(args.config), args.path))
        elif args.command == "context":
            print(json.dumps(context(load_yaml(args.config), args.config), indent=2))
        elif args.command == "secret-env":
            print(render_secret_env(args.secrets), end="")
    except Exception as exc:
        print(f"zt_config error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
