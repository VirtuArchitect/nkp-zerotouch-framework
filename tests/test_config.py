#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "zt_config.py"


def run_tool(*args):
    result = subprocess.run([sys.executable, str(TOOL), *args], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _make_bundle(root):
    version = "v2.17.0"
    bundle = root / "bundle" / f"nkp-{version}"
    for directory in ["cli", "container-images", "application-repositories", "image-artifacts"]:
        (bundle / directory).mkdir(parents=True, exist_ok=True)
    for path in [
        bundle / "cli" / "nkp",
        bundle / "kubectl",
        bundle / f"konvoy-bootstrap-image-{version}.tar",
        bundle / f"nkp-image-builder-image-{version}.tar",
        bundle / "application-repositories" / f"kommander-applications-{version}.tar.gz",
        bundle / "container-images" / f"konvoy-image-bundle-{version}.tar",
        bundle / "container-images" / f"kommander-image-bundle-{version}.tar",
        bundle / "image-artifacts" / "nkp-rocky-9.qcow2",
    ]:
        path.write_text("placeholder", encoding="utf-8")
    return bundle


def test_connected_context():
    data = json.loads(run_tool("context", "--config", "configs/environments/connected.example.yaml"))
    assert data["environmentType"] == "connected"
    assert data["clusterName"] == "nkp-mgmt-connected"
    assert data["controlPlaneEndpointIp"] == "10.10.10.50"


def test_invalid_environment_type():
    data = json.loads(run_tool("validate", "--config", "tests/fixtures/invalid-env.yaml"))
    assert data["valid"] is False
    assert any("environment.type" in item for item in data["errors"])


def test_schema_rejects_invalid_numeric_types(tmp_path):
    config = tmp_path / "bad-types.yaml"
    config.write_text(
        """
environment:
  name: bad-types
  type: connected
nkp:
  version: v2.17.1
nutanix:
  prismCentralEndpoint: https://pc.example.com:9440
  clusterName: pe-cluster
cluster:
  name: bad-types
  kubernetesVersion: v1.32.3
  controlPlaneReplicas: zero
  workerReplicas: -1
registry:
  pushConcurrency: 0
""",
        encoding="utf-8",
    )

    data = json.loads(run_tool("validate", "--config", str(config)))
    assert data["valid"] is False
    assert any("controlPlaneReplicas" in item for item in data["errors"])
    assert any("workerReplicas" in item for item in data["errors"])
    assert any("pushConcurrency" in item for item in data["errors"])


def test_schema_rejects_unsafe_environment_name(tmp_path):
    config = tmp_path / "unsafe-name.yaml"
    config.write_text(
        """
environment:
  name: ../bad
  type: connected
nkp:
  version: v2.17.1
nutanix:
  prismCentralEndpoint: https://pc.example.com:9440
  clusterName: pe-cluster
cluster:
  name: unsafe-name
  kubernetesVersion: v1.32.3
""",
        encoding="utf-8",
    )

    data = json.loads(run_tool("validate", "--config", str(config)))
    assert data["valid"] is False
    assert any("environment.name" in item for item in data["errors"])


def test_render_generate_quotes_shell_sensitive_values(tmp_path):
    config = tmp_path / "quoted.yaml"
    generated = tmp_path / "generated"
    state = tmp_path / "state"
    reports = tmp_path / "reports"
    config.write_text(
        """
environment:
  name: quoted-env
  type: connected
nkp:
  version: v2.17.1
  bundleType: standard
  bundlePath: /tmp/nkp bundle/nkp-v2.17.1
nutanix:
  prismCentralEndpoint: https://pc.example.com:9440
  clusterName: pe cluster
  subnetName: vlan 10
  imageName: image $(touch SHOULD_NOT_EXIST)
cluster:
  name: cluster name
  kubernetesVersion: v1.32.3
  sshUsername: user; touch SHOULD_NOT_EXIST
""",
        encoding="utf-8",
    )

    run_tool(
        "render-generate",
        "--config",
        str(config),
        "--generated-dir",
        str(generated),
        "--state-dir",
        str(state),
        "--reports-dir",
        str(reports),
    )
    deploy_script = (generated / "deploy.sh").read_text(encoding="utf-8")
    env_file = (generated / "nkp.env").read_text(encoding="utf-8")
    generate_state = json.loads((state / "generate.json").read_text(encoding="utf-8"))
    assert "'image $(touch SHOULD_NOT_EXIST)'" in deploy_script
    assert "'user; touch SHOULD_NOT_EXIST'" in deploy_script
    assert "ZT_BUNDLE_PATH='/tmp/nkp bundle/nkp-v2.17.1'" in env_file
    assert generate_state["dryRunCommand"].endswith("--dry-run --output yaml --output-directory ./generated")
    assert "--dry-run" not in generate_state["applyCommand"]
    assert 'if [[ "$apply_mode" == "true" ]]; then' in deploy_script


def test_bash_generate_uses_nkp_v217_nutanix_flags():
    scratch = ROOT / ".zt-test"
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.rmtree(ROOT / ".zt" / "environments" / "v217-test", ignore_errors=True)
    bundle = _make_bundle(scratch)
    config = scratch / "airgapped.yaml"
    environment_root = scratch / "env"
    generated_root = ROOT / ".zt" / "environments" / "v217-test"
    bundle_config_path = bundle.relative_to(ROOT).as_posix()
    environment_config_root = environment_root.relative_to(ROOT).as_posix()
    config.write_text(
        f"""
environment:
  name: v217-test
  type: air-gapped
  root: {environment_config_root}
nkp:
  version: v2.17.0
  bundleType: air-gapped
  bundlePath: {bundle_config_path}
nutanix:
  prismCentralEndpoint: pc.example.com
  clusterName: pe-cluster
  subnetName: vlan-10
  imageName: nkp-node-image
cluster:
  name: nkp-v217-test
  kubernetesVersion: v1.32.3
  controlPlaneReplicas: 3
  workerReplicas: 3
  podCidr: 192.168.0.0/16
  serviceCidr: 10.96.0.0/12
registry:
  endpoint: registry.example.com/nkp
  namespace: nkp
advanced: {{}}
""",
        encoding="utf-8",
    )

    relative_config = config.relative_to(ROOT).as_posix()
    subprocess.run(["bash", "scripts/zt.sh", "prepare", "--config", relative_config], cwd=ROOT, check=True)
    subprocess.run(["bash", "scripts/zt.sh", "generate", "--config", relative_config], cwd=ROOT, check=True)

    deploy_script = (generated_root / "generated" / "deploy.sh").read_text(encoding="utf-8")
    generate_state = json.loads((generated_root / "state" / "generate.json").read_text(encoding="utf-8"))
    assert "--control-plane-vm-image nkp-node-image" in deploy_script
    assert "--worker-vm-image nkp-node-image" in deploy_script
    assert "--vm-image" not in deploy_script
    assert "--bundle" in deploy_script
    assert "--registry-mirror-url registry.example.com/nkp" in deploy_script
    assert "--registry-mirror-username" in deploy_script
    assert "--registry-mirror-password" in deploy_script
    assert "--dry-run" in generate_state["dryRunCommand"]
    assert "--dry-run" not in generate_state["applyCommand"]


def test_bash_registry_uses_nkp_v217_push_bundle():
    scratch = ROOT / ".zt-test"
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.rmtree(ROOT / ".zt" / "environments" / "v217-registry", ignore_errors=True)
    bundle = _make_bundle(scratch)
    config = scratch / "registry.yaml"
    environment_root = scratch / "env"
    generated_root = ROOT / ".zt" / "environments" / "v217-registry"
    bundle_config_path = bundle.relative_to(ROOT).as_posix()
    environment_config_root = environment_root.relative_to(ROOT).as_posix()
    config.write_text(
        f"""
environment:
  name: v217-registry
  type: air-gapped
  root: {environment_config_root}
nkp:
  version: v2.17.0
  bundleType: air-gapped
  bundlePath: {bundle_config_path}
nutanix:
  prismCentralEndpoint: pc.example.com
  clusterName: pe-cluster
  subnetName: vlan-10
  imageName: nkp-node-image
cluster:
  name: nkp-v217-registry
  kubernetesVersion: v1.32.3
  controlPlaneReplicas: 3
  workerReplicas: 3
  podCidr: 192.168.0.0/16
  serviceCidr: 10.96.0.0/12
registry:
  endpoint: registry.example.com/nkp
  namespace: nkp
advanced: {{}}
""",
        encoding="utf-8",
    )

    relative_config = config.relative_to(ROOT).as_posix()
    subprocess.run(["bash", "scripts/zt.sh", "prepare", "--config", relative_config], cwd=ROOT, check=True)
    subprocess.run(["bash", "scripts/zt.sh", "registry", "--config", relative_config], cwd=ROOT, check=True)

    registry_script = (generated_root / "generated" / "registry.sh").read_text(encoding="utf-8")
    assert "nkp push bundle" in registry_script
    assert "--bundle" in registry_script
    assert "push image-bundle" not in registry_script
    assert "--image-bundle" not in registry_script


def test_secret_env_exports_nkp_expected_prism_variables():
    output = run_tool("secret-env", "--secrets", "configs/secrets/lab-airgapped.secrets.example.yaml")
    assert "export NUTANIX_USER=" in output
    assert "export NUTANIX_PASSWORD=" in output
    assert "export NUTANIX_PC_USERNAME=" in output


def test_secret_env_shell_quotes_values(tmp_path):
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(json.dumps({
        "prismCentral": {"username": "admin user", "password": "$(touch SHOULD_NOT_EXIST)"},
        "registry": {"username": "registry", "password": 'pass"word'},
    }), encoding="utf-8")

    output = run_tool("secret-env", "--secrets", str(secrets))
    assert "export NUTANIX_USER='admin user'" in output
    assert "export NUTANIX_PASSWORD='$(touch SHOULD_NOT_EXIST)'" in output
    assert 'export ZT_REGISTRY_PASSWORD=' in output
