#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "zt_config.py"


def run_tool(*args):
    result = subprocess.run([sys.executable, str(TOOL), *args], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_connected_context():
    data = json.loads(run_tool("context", "--config", "configs/environments/connected.example.yaml"))
    assert data["environmentType"] == "connected"
    assert data["clusterName"] == "nkp-mgmt-connected"
    assert data["controlPlaneEndpointIp"] == "10.10.10.50"


def test_invalid_environment_type():
    data = json.loads(run_tool("validate", "--config", "tests/fixtures/invalid-env.yaml"))
    assert data["valid"] is False
    assert any("environment.type" in item for item in data["errors"])
