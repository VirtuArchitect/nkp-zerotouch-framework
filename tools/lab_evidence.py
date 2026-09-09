#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import socket
import ssl
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]
ZT_ROOT = ROOT / ".zt"
SENSITIVE_VALUE_PATTERN = re.compile(r"(?i)\b(password|passwd|token|secret|private[_-]?key)\s*[:=]\s*\S+")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_key(value):
    key = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-").lower()
    return key or "unknown"


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
    return current


def normalize_endpoint(endpoint):
    endpoint = str(endpoint or "").strip().rstrip("/")
    if endpoint and "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return endpoint


def endpoint_host_port(endpoint, default_port):
    value = endpoint if "://" in endpoint else f"tcp://{endpoint}"
    parsed = urlparse(value)
    host = parsed.hostname
    port = parsed.port or default_port
    if not host:
        raise ValueError("host missing")
    return host, port


def tcp_probe(endpoint, default_port=9440):
    result = {
        "status": "warn",
        "detail": "not configured",
    }
    if not endpoint:
        return result
    try:
        host, port = endpoint_host_port(endpoint, default_port)
        with socket.create_connection((host, port), timeout=5):
            pass
        result.update({"status": "pass", "detail": f"{host}:{port}"})
    except Exception as exc:
        result.update({"status": "fail", "detail": str(exc)})
    return result


def auth_headers(username, password):
    if not username or not password:
        return {}
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def http_request(endpoint, path, method="GET", username="", password="", body=None):
    url = normalize_endpoint(endpoint) + path
    headers = {
        "Accept": "application/json",
        "User-Agent": "nkp-zerotouch-lab-evidence/1.0",
    }
    headers.update(auth_headers(username, password))
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context() if url.startswith("https://") else None
    started = time.time()
    try:
        with urlopen(request, timeout=10, context=context) as response:
            payload = response.read(4096)
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "status": "pass" if response.status < 400 else "warn",
                "httpStatus": response.status,
                "detail": "authenticated request completed" if username else "request completed",
                "elapsedMs": elapsed_ms,
                "bytesSampled": len(payload),
            }
    except HTTPError as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        detail = "authentication rejected" if exc.code in {401, 403} else f"HTTP {exc.code}"
        return {
            "status": "fail" if exc.code in {401, 403} else "warn",
            "httpStatus": exc.code,
            "detail": detail,
            "elapsedMs": elapsed_ms,
            "bytesSampled": 0,
        }
    except (URLError, TimeoutError, OSError) as exc:
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "status": "fail",
            "httpStatus": None,
            "detail": str(getattr(exc, "reason", exc)),
            "elapsedMs": elapsed_ms,
            "bytesSampled": 0,
        }


def first_passing_probe(endpoint, username, password, candidates):
    if not username or not password:
        return {
            "status": "warn",
            "detail": "credentials not configured in runtime environment",
            "httpStatus": None,
            "attempted": False,
            "candidate": "",
        }
    attempts = []
    for candidate in candidates:
        result = http_request(
            endpoint,
            candidate["path"],
            method=candidate.get("method", "GET"),
            username=username,
            password=password,
            body=candidate.get("body"),
        )
        result["candidate"] = candidate["name"]
        attempts.append(result)
        if result["status"] == "pass":
            result["attempted"] = True
            result["attempts"] = summarize_attempts(attempts)
            return result
    result = attempts[-1] if attempts else {"status": "warn", "detail": "no probes configured", "httpStatus": None}
    result["attempted"] = bool(attempts)
    result["attempts"] = summarize_attempts(attempts)
    return result


def summarize_attempts(attempts):
    return [
        {
            "candidate": item.get("candidate", ""),
            "status": item.get("status", "warn"),
            "httpStatus": item.get("httpStatus"),
            "detail": item.get("detail", ""),
            "elapsedMs": item.get("elapsedMs"),
        }
        for item in attempts
    ]


def target_record(name, kind, endpoint, username_env, password_env, candidates):
    username = os.environ.get(username_env, "") or os.environ.get("NUTANIX_USER", "")
    password = os.environ.get(password_env, "") or os.environ.get("NUTANIX_PASSWORD", "")
    endpoint = normalize_endpoint(endpoint)
    tcp = tcp_probe(endpoint)
    auth = first_passing_probe(endpoint, username, password, candidates) if endpoint else {
        "status": "warn",
        "detail": "endpoint not configured",
        "httpStatus": None,
        "attempted": False,
        "candidate": "",
    }
    return {
        "name": name,
        "kind": kind,
        "endpoint": endpoint,
        "tcp": tcp,
        "authenticatedApi": auth,
        "credentialSource": {
            "usernameEnv": username_env if username else "",
            "passwordEnv": password_env if password else "",
            "fallbackSupported": True,
            "valuesRecorded": False,
        },
        "tlsVerification": "skipped-for-lab-self-signed-endpoints",
    }


def create_external_validation(area, environment, status, summary, evidence_ref):
    if SENSITIVE_VALUE_PATTERN.search(summary) or SENSITIVE_VALUE_PATTERN.search(evidence_ref):
        raise ValueError("external validation records must not contain secret values")
    record_id = f"ev-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    record = {
        "id": record_id,
        "area": area,
        "environment": environment or "global",
        "status": status,
        "summary": summary[:1000],
        "evidenceRef": evidence_ref[:500],
        "validatedAt": utc_now(),
        "recordedAt": utc_now(),
        "recordedBy": "lab-evidence-phase",
        "recordedRole": "automation",
    }
    path = ZT_ROOT / "external-validations" / f"{record_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def build_evidence(config_path, prism_element):
    config = load_yaml(config_path)
    env_name = str(dotted_get(config, "environment.name", Path(config_path).stem))
    env_type = str(dotted_get(config, "environment.type", ""))
    cluster_name = str(dotted_get(config, "cluster.name", ""))
    prism_central = os.environ.get("NUTANIX_PC_ENDPOINT", "") or str(dotted_get(config, "nutanix.prismCentralEndpoint", ""))
    prism_element = os.environ.get("NUTANIX_PE_ENDPOINT", "") or prism_element

    pc_candidates = [
        {"name": "Prism Central v3 clusters list", "method": "POST", "path": "/api/nutanix/v3/clusters/list", "body": {"kind": "cluster"}},
        {"name": "Prism v2 cluster", "method": "GET", "path": "/PrismGateway/services/rest/v2.0/cluster/"},
        {"name": "Prism root", "method": "GET", "path": "/"},
    ]
    pe_candidates = [
        {"name": "Prism Element v2 cluster", "method": "GET", "path": "/PrismGateway/services/rest/v2.0/cluster/"},
        {"name": "Prism Element v2 hosts", "method": "GET", "path": "/PrismGateway/services/rest/v2.0/hosts/"},
        {"name": "Prism root", "method": "GET", "path": "/"},
    ]

    targets = [
        target_record("Prism Central", "prism-central", prism_central, "NUTANIX_PC_USERNAME", "NUTANIX_PC_PASSWORD", pc_candidates)
    ]
    if prism_element:
        targets.append(target_record("Prism Element", "prism-element", prism_element, "NUTANIX_PE_USERNAME", "NUTANIX_PE_PASSWORD", pe_candidates))

    pass_count = sum(1 for target in targets if target["tcp"]["status"] == "pass" and target["authenticatedApi"]["status"] == "pass")
    warn_count = sum(1 for target in targets if target["tcp"]["status"] == "pass" and target["authenticatedApi"]["status"] != "pass")
    fail_count = len(targets) - pass_count - warn_count
    status = "pass" if pass_count == len(targets) else ("warn" if pass_count else "fail")
    return {
        "capturedAt": utc_now(),
        "config": str(config_path),
        "environment": env_name,
        "type": env_type,
        "cluster": cluster_name,
        "status": status,
        "summary": {
            "targets": len(targets),
            "authenticatedTargets": pass_count,
            "reachableButUnauthenticatedTargets": warn_count,
            "failedTargets": fail_count,
            "secretValuesRecorded": False,
        },
        "targets": targets,
    }


def write_summary(path, evidence):
    lines = [
        "# Lab Evidence Summary",
        "",
        f"Environment: `{evidence['environment']}`",
        f"Status: `{evidence['status']}`",
        "",
        "| Target | TCP | Authenticated API | Probe |",
        "| --- | --- | --- | --- |",
    ]
    for target in evidence["targets"]:
        lines.append(
            f"| {target['name']} | {target['tcp']['status']} | "
            f"{target['authenticatedApi']['status']} | {target['authenticatedApi'].get('candidate', '')} |"
        )
    lines.extend([
        "",
        "Credentials were supplied from runtime environment variables only. Secret values are not recorded in this evidence.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Capture redacted lab connectivity and authorization evidence.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--prism-element", default="")
    parser.add_argument("--write-external-validation", action="store_true")
    args = parser.parse_args(argv)

    evidence = build_evidence(Path(args.config), args.prism_element)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    evidence_dir = ZT_ROOT / "lab-evidence" / f"{safe_key(evidence['environment'])}-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "lab-evidence.json"
    summary_path = evidence_dir / "README.md"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    write_summary(summary_path, evidence)

    external_paths = []
    if args.write_external_validation and evidence["summary"]["authenticatedTargets"] > 0:
        target_names = ", ".join(
            target["name"] for target in evidence["targets"] if target["authenticatedApi"]["status"] == "pass"
        )
        external_paths.append(create_external_validation(
            "prism-authorization",
            evidence["environment"],
            "pass" if evidence["status"] == "pass" else "warn",
            f"Lab evidence phase authenticated to {target_names}.",
            str(evidence_path),
        ))

    print(json.dumps({
        "status": evidence["status"],
        "environment": evidence["environment"],
        "evidencePath": str(evidence_path),
        "summaryPath": str(summary_path),
        "externalValidationRecords": [str(path) for path in external_paths],
    }, indent=2))
    return 0 if evidence["status"] in {"pass", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
