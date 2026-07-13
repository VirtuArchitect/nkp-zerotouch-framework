#!/usr/bin/env python3
import difflib
import html
import hashlib
import json
import os
import re
import secrets
import signal
import shlex
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
ZT = ROOT / ".zt"
SETTINGS = ZT / "settings"
JOBS = ZT / "jobs"
AUDIT = ZT / "audit"
LOCKS = ZT / "locks"
CHANGE_RECORDS = ZT / "change-records"
ENV_DIR = ROOT / "configs" / "environments"
SESSIONS = {}
try:
    SESSION_TTL_SECONDS = int(os.environ.get("ZT_SESSION_TTL_SECONDS", "43200"))
except ValueError:
    SESSION_TTL_SECONDS = 43200
SAFE_ACTIONS = {"validate", "prepare", "generate", "verify", "backup", "runs"}
ACTION_ORDER = ["validate", "prepare", "generate", "verify", "backup", "runs"]
CLI_APPLY_ACTIONS = {"registry", "deploy", "upgrade", "destroy"}
CLI_ALLOWED_ACTIONS = CLI_APPLY_ACTIONS
VIEW_PATHS = {
    "environments": "/",
    "setup": "/setup",
    "cli": "/cli",
    "runs": "/runs",
    "artifacts": "/artifacts",
    "health": "/health",
    "kubeconfig": "/kubeconfig",
    "plan-review": "/plan-review",
    "change-records": "/change-records",
    "locks": "/locks",
    "drift": "/drift",
    "backups": "/backups",
    "restore": "/restore",
    "production-readiness": "/production-readiness",
    "release-channels": "/release-channels",
    "sources": "/sources",
    "inventory": "/inventory",
    "network": "/network",
    "preflight": "/preflight",
    "pipeline": "/pipeline",
    "jobs": "/jobs",
    "actions": "/actions",
    "audit": "/audit",
    "approval-policy": "/approval-policy",
    "connections": "/settings/connections",
    "new-environment": "/settings/new-environment",
    "providers": "/settings/providers",
    "secrets": "/settings/secrets",
    "rbac": "/settings/rbac",
    "database": "/settings/database",
    "integrations": "/settings/integrations",
    "about": "/about",
}


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, separators=(",", ":")) + "\n")


def env_configs():
    return sorted(ENV_DIR.glob("*.yaml"))


def resolve_env_config(raw_path):
    if not raw_path:
        raise ValueError("Missing environment config path.")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    env_root = ENV_DIR.resolve()
    if resolved.parent != env_root or resolved.suffix not in {".yaml", ".yml"}:
        raise ValueError("Environment config path is outside configs/environments.")
    if not resolved.exists():
        raise ValueError(f"Environment config not found: {resolved.name}")
    return resolved


def load_env_yaml(config):
    if yaml is None:
        raise RuntimeError("PyYAML is required to edit environment files.")
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Environment config must be a YAML mapping.")
    return data


def write_env_yaml(config, data):
    if yaml is None:
        raise RuntimeError("PyYAML is required to edit environment files.")
    config.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def nested_get(data, path, default=""):
    cursor = data
    for key in path:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key, default)
    if cursor is None:
        return default
    return cursor


def nested_set(data, path, value):
    cursor = data
    for key in path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[path[-1]] = value


def int_or_original(value):
    try:
        return int(value)
    except ValueError:
        return value


def env_state(name):
    base = ZT / "environments" / name
    return {
        "base": base,
        "state": read_json(base / "state" / "environment.json"),
        "generate": read_json(base / "state" / "generate.json"),
        "registry": read_json(base / "state" / "registry.json"),
        "secrets": read_json(base / "state" / "secrets.json"),
        "verification": base / "reports" / "verification-summary.md",
    }


def recent_run_summaries(limit=25):
    runs = sorted((ZT / "runs").glob("*/summary.md")) if (ZT / "runs").exists() else []
    return list(reversed(runs[-limit:]))


def file_count(path, pattern="*"):
    if not path.exists():
        return 0
    return len([p for p in path.rglob(pattern) if p.is_file()])


def mtime_label(path):
    if not path.exists():
        return "n/a"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))


def metric_card(label, value, foot, href=None):
    content = (
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-foot">{html.escape(foot)}</div>'
    )
    if href and value > 0:
        return f'<a class="metric metric-link" href="{html.escape(href)}">{content}</a>'
    return f'<div class="metric disabled">{content}</div>'


def pct(value, total):
    if total <= 0:
        return 0
    return int(round((value / total) * 100))


def form_value(form, name, default=""):
    return form.get(name, [default])[0].strip()


def safe_key(value):
    key = value.strip().lower().replace(" ", "-")
    return "".join(ch for ch in key if ch.isalnum() or ch in {"-", "_"})


def password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return {"salt": salt, "passwordHash": digest, "algorithm": "pbkdf2_sha256", "iterations": 120000}


def verify_password(password, account):
    salt = account.get("salt", "")
    expected = account.get("passwordHash", "")
    if not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(account.get("iterations", 120000))).hex()
    return secrets.compare_digest(digest, expected)


def cookie_value(headers, name):
    raw = headers.get("Cookie", "")
    for part in raw.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def default_rbac():
    return {
        "settings": {"enabled": "false", "provider": "local", "admin": "admin"},
        "roles": [
            {"name": "Admin", "permissions": "settings, environments, safe-actions, audit, jobs, approve, apply, sources, inventory, network, preflight, pipeline, artifacts, runs, health, approval-policy, integrations, rbac"},
            {"name": "Environment Author", "permissions": "environments, sources, inventory, network, preflight, pipeline, artifacts, runs, health"},
            {"name": "Deployment Operator", "permissions": "environments, safe-actions, artifacts, jobs, sources, inventory, network, preflight, pipeline, runs, health, apply"},
            {"name": "Approver", "permissions": "runs, artifacts, audit, jobs, approve, preflight, pipeline, health"},
            {"name": "Auditor", "permissions": "runs, artifacts, audit, jobs, preflight, pipeline, health"},
        ],
        "accounts": [],
    }


def has_password_accounts():
    rbac = load_rbac()
    return any(account.get("passwordHash") for account in rbac.get("accounts", []))


def is_local_host(host):
    return host in {"127.0.0.1", "localhost", "::1"}


def bootstrap_token_required(host=None):
    bind_host = host if host is not None else os.environ.get("ZT_DASHBOARD_HOST", "127.0.0.1")
    return not is_local_host(bind_host) or bool(os.environ.get("ZT_BOOTSTRAP_TOKEN"))


def assert_bootstrap_safe(host):
    if has_password_accounts():
        return
    if bootstrap_token_required(host) and not os.environ.get("ZT_BOOTSTRAP_TOKEN"):
        raise RuntimeError("Refusing dashboard startup on a non-local bind without ZT_BOOTSTRAP_TOKEN while no admin account exists.")


def load_rbac():
    data = read_json(SETTINGS / "rbac.json") or default_rbac()
    if "settings" not in data:
        data = {"settings": data, "roles": default_rbac()["roles"], "accounts": []}
    data.setdefault("settings", default_rbac()["settings"])
    data.setdefault("roles", default_rbac()["roles"])
    data.setdefault("accounts", [])
    return data


def load_setting(name, defaults):
    data = read_json(SETTINGS / f"{name}.json") or {}
    merged = dict(defaults)
    merged.update(data)
    return merged


def save_setting(name, data):
    data["savedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(SETTINGS / f"{name}.json", data)


def session_store_mode():
    mode = load_setting("integrations", default_integrations()).get("session_store", "memory")
    return mode if mode in {"memory", "file"} else "memory"


def session_file():
    return SETTINGS / "sessions.json"


def session_expired(session, now=None):
    expires_at = float(session.get("expiresAt", 0) or 0)
    return bool(expires_at and expires_at <= (now or time.time()))


def load_persisted_sessions():
    data = read_json(session_file()) or {}
    sessions = data.get("sessions", {}) if isinstance(data, dict) else {}
    now = time.time()
    active = {token: session for token, session in sessions.items() if isinstance(session, dict) and not session_expired(session, now)}
    if active != sessions:
        write_json(session_file(), {"sessions": active, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return active


def save_persisted_sessions(sessions):
    write_json(session_file(), {"sessions": sessions, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def get_session(token):
    if not token:
        return None
    if session_store_mode() == "file":
        return load_persisted_sessions().get(token)
    session = SESSIONS.get(token)
    if session and session_expired(session):
        SESSIONS.pop(token, None)
        return None
    return session


def save_session(token, session):
    session.setdefault("createdAt", time.time())
    session["expiresAt"] = session.get("expiresAt") or (time.time() + SESSION_TTL_SECONDS)
    if session_store_mode() == "file":
        sessions = load_persisted_sessions()
        sessions[token] = session
        save_persisted_sessions(sessions)
        return
    SESSIONS[token] = session


def delete_session(token):
    if not token:
        return
    SESSIONS.pop(token, None)
    if session_file().exists():
        sessions = load_persisted_sessions()
        if token in sessions:
            sessions.pop(token, None)
            save_persisted_sessions(sessions)


def bool_label(value):
    return "yes" if str(value).lower() in {"1", "true", "yes", "on"} else "no"


def path_status(raw_path):
    if not raw_path:
        return "warn", "not configured"
    candidate = Path(raw_path)
    return ("ok", "available") if candidate.exists() else ("warn", "not found")


def preflight_checks():
    sources = load_setting("sources", default_sources())
    inventory = load_setting("inventory", default_inventory())
    network = load_setting("network", default_network())
    secrets_cfg = load_setting("secrets", default_secrets())
    providers = load_setting("providers", default_providers())
    connections = read_json(SETTINGS / "connections.json") or {}
    checks = []

    for label, raw_path in [
        ("Standard NKP bundle", sources.get("standard_bundle")),
        ("Air-gapped NKP bundle", sources.get("airgapped_bundle")),
        ("NKP source path", sources.get("source_path")),
    ]:
        status, note = path_status(raw_path)
        checks.append({"area": "Sources", "check": label, "status": status, "note": note})

    checks.append({"area": "Sources", "check": "Pinned version", "status": "ok" if sources.get("version") else "warn", "note": sources.get("version") or "not pinned"})
    checks.append({"area": "Inventory", "check": "Node inventory", "status": "ok" if inventory.get("nodes") else "warn", "note": inventory.get("nodes") or "not configured"})
    checks.append({"area": "Inventory", "check": "BMC access", "status": "ok" if inventory.get("bmc_network") else "warn", "note": inventory.get("bmc_network") or "not configured"})
    checks.append({"area": "Network", "check": "API endpoint VIP", "status": "ok" if network.get("api_vip") else "warn", "note": network.get("api_vip") or "not configured"})
    checks.append({"area": "Network", "check": "DNS servers", "status": "ok" if network.get("dns_servers") else "warn", "note": network.get("dns_servers") or "not configured"})
    checks.append({"area": "Network", "check": "NTP servers", "status": "ok" if network.get("ntp_servers") else "warn", "note": network.get("ntp_servers") or "not configured"})
    prism_ok, prism_note = check_tcp_endpoint(connections.get("prism", ""), 9440)
    registry_ok, registry_note = check_tcp_endpoint(connections.get("registry", ""), 443)
    checks.append({"area": "Connections", "check": "Prism Central", "status": "ok" if prism_ok else "warn", "note": prism_note})
    checks.append({"area": "Connections", "check": "Registry", "status": "ok" if registry_ok else "warn", "note": registry_note})
    checks.append({"area": "Connections", "check": "Prism credentials", "status": "ok" if os.environ.get("NUTANIX_PC_USERNAME") and os.environ.get("NUTANIX_PC_PASSWORD") else "warn", "note": "environment variables present" if os.environ.get("NUTANIX_PC_USERNAME") and os.environ.get("NUTANIX_PC_PASSWORD") else "NUTANIX_PC_USERNAME/NUTANIX_PC_PASSWORD not set"})
    checks.append({"area": "Connections", "check": "Registry credentials", "status": "ok" if os.environ.get("ZT_REGISTRY_USERNAME") and os.environ.get("ZT_REGISTRY_PASSWORD") else "warn", "note": "environment variables present" if os.environ.get("ZT_REGISTRY_USERNAME") and os.environ.get("ZT_REGISTRY_PASSWORD") else "ZT_REGISTRY_USERNAME/ZT_REGISTRY_PASSWORD not set"})
    checks.append({"area": "Secrets", "check": "Secrets backend", "status": "ok" if secrets_cfg.get("backend") not in {"local-file", ""} else "warn", "note": secrets_cfg.get("backend", "local-file")})
    checks.append({"area": "Provider", "check": "Default provider", "status": "ok", "note": providers.get("default_provider", "nutanix-ahv")})
    for name, status, note in integration_checks():
        checks.append({"area": "Integrations", "check": name, "status": status, "note": note})
    uniqueness = environment_uniqueness_issues()
    if uniqueness:
        for issue in uniqueness:
            checks.append({"area": "Uniqueness", "check": "Environment identity", "status": "warn", "note": issue})
    else:
        checks.append({"area": "Uniqueness", "check": "Environment identity", "status": "ok", "note": "no duplicate names, clusters, VIPs, or namespaces"})
    return checks


def default_sources():
    return {
        "version": "v2.17.1",
        "standard_bundle": "/mnt/c/Share/nkp-bundle_v2.17.1_linux_amd64/nkp-v2.17.1",
        "airgapped_bundle": "/mnt/c/Share/nkp-air-gapped-bundle_v2.17.1_linux_amd64/nkp-v2.17.1",
        "source_path": "/mnt/c/Share/nkp-bundle_v2.17.1_linux_amd64/nkp-v2.17.1",
        "git_url": "",
        "git_ref": "v2.17.1",
        "checksum": "",
    }


def default_inventory():
    return {
        "mode": "nutanix-ahv",
        "nodes": "",
        "bmc_network": "",
        "bmc_provider": "ipmi",
        "boot_mode": "uefi",
        "os_image": "",
        "notes": "",
    }


def default_network():
    return {
        "management_cidr": "",
        "workload_cidr": "",
        "api_vip": "",
        "ingress_range": "",
        "dns_servers": "",
        "ntp_servers": "",
        "proxy": "",
        "ip_mode": "static",
    }


def default_secrets():
    return {
        "backend": "local-file",
        "vault_url": "",
        "namespace": "",
        "secret_path": "kv/nkp/zerotouch",
        "rotation_policy": "manual",
    }


def default_providers():
    return {
        "default_provider": "nutanix-ahv",
        "enabled_providers": "nutanix-ahv, air-gapped-ahv, proxied-ahv",
        "runner_type": "container",
        "runner_notes": "Use WSL or Linux VM for live NKP binaries.",
    }


def default_approval_policy():
    return {
        "deploy_approvals": "1",
        "registry_approvals": "1",
        "upgrade_approvals": "1",
        "destroy_approvals": "2",
        "prevent_self_approval": "true",
        "production_requires_admin": "true",
    }


def default_release_channels():
    return {
        "default_channel": "lab",
        "channels": "dev:0, lab:1, pilot:1, production:2",
        "production_requires_plan_review": "true",
        "production_requires_backup": "true",
    }


def default_integrations():
    return {
        "session_store": "memory",
        "postgres_enabled": "false",
        "postgres_dsn": "",
        "oidc_enabled": "false",
        "oidc_issuer": "",
        "oidc_client_id": "",
        "oidc_redirect_uri": "http://localhost:18080/login/oidc/callback",
        "vault_enabled": "false",
        "vault_addr": "",
        "vault_mount": "kv",
        "vault_secret_path": "nkp/zerotouch",
    }


def permission_catalog():
    return {
        "Admin": {
            "settings", "environments", "safe-actions", "audit", "jobs", "approve", "apply",
            "sources", "inventory", "network", "preflight", "pipeline", "artifacts", "runs",
            "health", "approval-policy", "integrations", "rbac",
        },
        "Operator": {
            "environments", "safe-actions", "artifacts", "jobs", "sources", "inventory",
            "network", "preflight", "pipeline", "runs", "health",
        },
        "Auditor": {"runs", "artifacts", "audit", "jobs", "preflight", "pipeline", "health"},
        "Deployment Reviewer": {"runs", "artifacts", "audit", "jobs", "approve", "preflight", "pipeline", "health"},
    }


ROUTE_PERMISSIONS = [
    ("/settings/rbac", "rbac"),
    ("/settings/database", "settings"),
    ("/settings/integrations", "integrations"),
    ("/settings/providers", "settings"),
    ("/settings/secrets", "settings"),
    ("/settings/connections", "settings"),
    ("/settings/new-environment", "environments"),
    ("/environment", "environments"),
    ("/setup", "environments"),
    ("/kubeconfig", "artifacts"),
    ("/plan-review", "artifacts"),
    ("/change-records", "jobs"),
    ("/locks", "jobs"),
    ("/drift", "preflight"),
    ("/backups", "artifacts"),
    ("/restore", "artifacts"),
    ("/production-readiness", "preflight"),
    ("/release-channels", "approval-policy"),
    ("/api", "health"),
    ("/sources", "sources"),
    ("/inventory", "inventory"),
    ("/network", "network"),
    ("/preflight", "preflight"),
    ("/pipeline", "pipeline"),
    ("/jobs", "jobs"),
    ("/artifacts", "artifacts"),
    ("/runs", "runs"),
    ("/actions", "safe-actions"),
    ("/audit", "audit"),
    ("/approval-policy", "approval-policy"),
    ("/health", "health"),
    ("/cli", "apply"),
    ("/action", "safe-actions"),
]


def route_permission(path):
    if path in {"/", "/environments", "/about", "/logout", "/assets/veridian-mark-teal.svg"}:
        return None
    for prefix, permission in ROUTE_PERMISSIONS:
        if path.startswith(prefix):
            return permission
    return None


def csrf_token(user):
    if not user:
        return ""
    token = user.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        user["csrf"] = token
    return token


def csrf_field(user):
    token = csrf_token(user)
    return f'<input type="hidden" name="csrf_token" value="{html.escape(token)}">' if token else ""


def inject_csrf_fields(body, user):
    token_field = csrf_field(user)
    if not token_field:
        return body
    return re.sub(r'(<form\b[^>]*method="post"[^>]*>)', r'\1' + token_field, body)


def audit_event(event, user=None, target="", status="info", detail=None):
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "status": status,
        "user": (user or {}).get("username", "anonymous"),
        "role": (user or {}).get("role", ""),
        "target": target,
        "detail": detail or {},
    }
    append_jsonl(AUDIT / "events.jsonl", entry)


def recent_audit_events(limit=100):
    path = AUDIT / "events.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))


def check_tcp_endpoint(endpoint, default_port=443, timeout=2):
    if not endpoint or ".example.com" in endpoint:
        return False, "not configured"
    host = endpoint.replace("https://", "").replace("http://", "").split("/")[0]
    if ":" in host:
        name, raw_port = host.rsplit(":", 1)
        port = int(raw_port) if raw_port.isdigit() else default_port
    else:
        name, port = host, default_port
    try:
        import socket

        with socket.create_connection((name, port), timeout=timeout):
            return True, f"reachable {name}:{port}"
    except Exception as exc:
        return False, str(exc)


def http_probe(url, headers=None, timeout=3):
    if not url or ".example.com" in url:
        return "warn", "not configured"
    try:
        request = Request(url, headers=headers or {}, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return "ok", f"HTTP {response.status}"
    except Exception as exc:
        return "warn", str(exc)


def postgres_status(settings):
    if settings.get("postgres_enabled") != "true":
        return "warn", "disabled"
    dsn = settings.get("postgres_dsn", "")
    if not dsn:
        return "warn", "DSN missing"
    parsed = urlparse(dsn)
    host = parsed.hostname
    if not host:
        return "warn", "DSN host missing"
    endpoint = f"{host}:{parsed.port or 5432}"
    reachable, note = check_tcp_endpoint(endpoint, 5432)
    return ("ok" if reachable else "warn"), note


def oidc_status(settings):
    if settings.get("oidc_enabled") != "true":
        return "warn", "disabled"
    issuer = settings.get("oidc_issuer", "").rstrip("/")
    client_id = settings.get("oidc_client_id", "")
    if not issuer or not client_id:
        return "warn", "issuer/client ID missing"
    status, note = http_probe(f"{issuer}/.well-known/openid-configuration")
    return status, f"discovery {note}"


def vault_status(settings):
    if settings.get("vault_enabled") != "true":
        return "warn", "disabled"
    addr = settings.get("vault_addr", "").rstrip("/")
    if not addr:
        return "warn", "Vault address missing"
    headers = {}
    token = os.environ.get("VAULT_TOKEN", "")
    if token:
        headers["X-Vault-Token"] = token
    status, note = http_probe(f"{addr}/v1/sys/health", headers=headers)
    return status, f"health {note}"


def integration_checks():
    settings = load_setting("integrations", default_integrations())
    postgres = postgres_status(settings)
    oidc = oidc_status(settings)
    vault = vault_status(settings)
    session_store = settings.get("session_store", "memory")
    session_status = "ok" if session_store != "postgres" or settings.get("postgres_enabled") == "true" else "warn"
    session_note = f"{session_store}" if session_status == "ok" else "postgres session store requires Postgres"
    return [
        ("Postgres", postgres[0], postgres[1]),
        ("OIDC", oidc[0], oidc[1]),
        ("Vault", vault[0], vault[1]),
        ("Session store", session_status, session_note),
    ]


def environment_inventory(extra=None, exclude=None):
    rows = []
    exclude_path = Path(exclude).resolve() if exclude else None
    for config in env_configs():
        if exclude_path and config.resolve() == exclude_path:
            continue
        try:
            data = load_env_yaml(config)
        except Exception:
            continue
        rows.append({
            "config": config,
            "environment": str(nested_get(data, ["environment", "name"], config.stem)).strip(),
            "cluster": str(nested_get(data, ["cluster", "name"], "")).strip(),
            "api_vip": str(nested_get(data, ["cluster", "controlPlaneEndpointIp"], "")).strip(),
            "registry_namespace": str(nested_get(data, ["registry", "namespace"], "")).strip(),
        })
    if extra:
        rows.append(extra)
    return rows


def environment_uniqueness_issues(extra=None, exclude=None):
    fields = [
        ("environment", "Environment name"),
        ("cluster", "Cluster name"),
        ("api_vip", "API endpoint VIP"),
        ("registry_namespace", "Registry namespace"),
    ]
    issues = []
    rows = environment_inventory(extra=extra, exclude=exclude)
    for key, label in fields:
        seen = {}
        for row in rows:
            value = row.get(key, "")
            if not value:
                continue
            normalized = value.lower()
            seen.setdefault(normalized, []).append(row)
        for value, matches in seen.items():
            if len(matches) > 1:
                configs = ", ".join(match["config"].name for match in matches)
                issues.append(f"{label} '{matches[0].get(key)}' is duplicated in {configs}.")
    return issues


def prepared_config_path(state):
    raw_path = ((state.get("state") or {}).get("paths") or {}).get("config", "")
    return Path(raw_path) if raw_path else None


def same_config_path(left, right):
    if not left or not right:
        return False
    if Path(left).name == Path(right).name:
        return True
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return False


def environment_identity_issues(config, data, state):
    env_name = str(data.get("environmentName") or config.stem)
    current = {
        "config": config,
        "environment": env_name,
        "cluster": str(data.get("clusterName", "")).strip(),
        "api_vip": str(data.get("controlPlaneEndpointIp", "")).strip(),
        "registry_namespace": str(data.get("registryNamespace", "")).strip(),
    }
    issues = environment_uniqueness_issues(extra=current, exclude=config)
    state_config = prepared_config_path(state)
    if state_config and not same_config_path(state_config, config):
        issues.append(f"State was prepared from {state_config.name}, not {config.name}.")
    state_env = ((state.get("state") or {}).get("environment") or {}).get("name", "")
    if state_env and state_env != env_name:
        issues.append(f"State environment name '{state_env}' does not match config environment name '{env_name}'.")
    return issues


def verification_status(state):
    if not state["verification"].exists():
        return False, "verification missing"
    health_path = state["base"] / "reports" / "component-health.json"
    health = read_json(health_path)
    if isinstance(health, list):
        issues = [
            f"{item.get('name', 'check')}: {item.get('status', 'unknown')}"
            for item in health
            if str(item.get("status", "")).lower() not in {"pass", "ok"}
        ]
        if issues:
            return False, "; ".join(issues[:4])
        return True, "verification checks passed"
    try:
        text = state["verification"].read_text(encoding="utf-8-sig", errors="replace").lower()
    except OSError:
        return False, "verification report unreadable"
    if re.search(r"(^|\n)-\s*(warn|fail|failed|error):", text):
        return False, "verification report contains warnings or failures"
    return True, "verification report available"


def artifact_files():
    roots = [ZT, ROOT / "docs", ROOT / "configs"]
    files = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".yaml", ".yml", ".md", ".txt", ".log", ".sh", ".ps1"}:
                files.append(path)
    return sorted(files, key=lambda item: str(item.relative_to(ROOT) if ROOT in item.parents else item))


def environment_lifecycle(name, state):
    verification_ok, _ = verification_status(state)
    if verification_ok:
        return "Verified", "ok"
    if state["verification"].exists():
        return "Verification Warning", "warn"
    if (state["base"] / "state" / "kubeconfig").exists():
        return "Kubeconfig Captured", "ok"
    if state["generate"]:
        return "Generated", "ok"
    if state["state"]:
        return "Prepared", "ok"
    return "Draft", "warn"


def environment_readiness(data, state):
    verification_ok, _ = verification_status(state)
    checks = [
        bool(data.get("environmentName")),
        data.get("environmentType") in {"connected", "proxied", "air-gapped"},
        bool(data.get("nkpVersion")),
        bool(data.get("bundlePath")),
        bool(data.get("prismEndpoint")) and ".example.com" not in str(data.get("prismEndpoint", "")),
        bool(data.get("clusterName")),
        bool(data.get("registryEndpoint")) and ".example.com" not in str(data.get("registryEndpoint", "")),
        bool(state["state"]),
        bool(state["generate"]),
        verification_ok,
    ]
    passed = sum(1 for item in checks if item)
    return passed, len(checks), pct(passed, len(checks))


def review_path(env_name):
    return ZT / "environments" / env_name / "state" / "plan-review.json"


def load_plan_review(env_name):
    return read_json(review_path(env_name)) or {"status": "pending", "reviewedBy": "", "reviewedAt": "", "note": ""}


def file_sha256(path):
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_hashes(env_name):
    base = ZT / "environments" / env_name / "generated"
    return {
        "deployPlan": file_sha256(base / "deploy-plan.md"),
        "deployScript": file_sha256(base / "deploy.sh"),
        "registryPlan": file_sha256(base / "registry-plan.md"),
        "registryScript": file_sha256(base / "registry.sh"),
    }


def plan_review_status(env_name, state):
    review = load_plan_review(env_name)
    if not state["generate"] and not (state["base"] / "generated" / "deploy-plan.md").exists():
        return "not generated", "warn"
    reviewed_hashes = review.get("planHashes") or {}
    current_hashes = plan_hashes(env_name)
    if review.get("status") == "approved" and not reviewed_hashes:
        return "legacy review missing hashes", "warn"
    if review.get("status") == "approved" and reviewed_hashes and reviewed_hashes != current_hashes:
        return "stale review", "warn"
    if review.get("status") == "approved":
        return "approved", "ok"
    if review.get("status") == "rejected":
        return "rejected", "warn"
    return "pending review", "warn"


def provider_catalog():
    base = ROOT / "providers"
    providers = []
    for path in sorted(base.glob("*/README.md")) if base.exists() else []:
        providers.append({"name": path.parent.name, "readme": path})
    return providers


def lock_path(env_name):
    return LOCKS / f"{safe_key(env_name)}.json"


def active_lock(env_name):
    lock = read_json(lock_path(env_name))
    if not lock:
        return None
    job_id = lock.get("jobId", "")
    if job_id:
        job = read_job(job_id)
        if job and job.get("status") in {"queued", "running", "pending_approval", "cancel_requested"}:
            return lock
    try:
        lock_path(env_name).unlink(missing_ok=True)
    except OSError:
        pass
    return None


def acquire_lock(env_name, job):
    if not env_name:
        return True, ""
    existing = active_lock(env_name)
    if existing:
        return False, f"Environment is locked by job {existing.get('jobId', 'unknown')}."
    write_json(lock_path(env_name), {
        "environment": env_name,
        "jobId": job.get("id", ""),
        "action": job.get("action", ""),
        "lockedBy": job.get("requestedBy", ""),
        "lockedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return True, ""


def release_lock(env_name, job_id):
    lock = read_json(lock_path(env_name))
    if lock and lock.get("jobId") == job_id:
        lock_path(env_name).unlink(missing_ok=True)


def change_record_path(record_id):
    return CHANGE_RECORDS / f"{safe_key(record_id)}.json"


def create_change_record(job, user):
    env_name = job.get("environment", "")
    record_id = f"cr-{job.get('id', secrets.token_hex(4))}"
    record = {
        "id": record_id,
        "jobId": job.get("id", ""),
        "environment": env_name,
        "action": job.get("action", ""),
        "requestedBy": (user or {}).get("username", "unknown"),
        "requestedRole": (user or {}).get("role", ""),
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "open",
        "planHashes": plan_hashes(env_name),
        "rollbackNotes": "Run backup before apply. Use generated plan and NKP runbooks for rollback decision points.",
    }
    write_json(change_record_path(record_id), record)
    return record


def list_change_records(limit=100):
    if not CHANGE_RECORDS.exists():
        return []
    records = [read_json(path) for path in CHANGE_RECORDS.glob("*.json")]
    return sorted([record for record in records if record], key=lambda item: item.get("createdAt", ""), reverse=True)[:limit]


def update_change_record_for_job(job_id, status):
    if not CHANGE_RECORDS.exists():
        return
    for path in CHANGE_RECORDS.glob("*.json"):
        record = read_json(path)
        if record and record.get("jobId") == job_id:
            record["status"] = "closed" if status == "succeeded" else status
            record["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_json(path, record)


def drift_status(config):
    data = read_json_from_context(config)
    env_name = str(data.get("environmentName") or config.stem)
    state = env_state(env_name)
    review = load_plan_review(env_name)
    current = plan_hashes(env_name)
    reviewed = review.get("planHashes") or {}
    issues = []
    if not state["generate"]:
        issues.append("generate has not run")
    if review.get("status") == "approved" and reviewed and reviewed != current:
        issues.append("generated plan changed after approval")
    env_state_file = state["base"] / "state" / "environment.json"
    if config.exists() and env_state_file.exists() and config.stat().st_mtime > env_state_file.stat().st_mtime:
        issues.append("environment YAML changed after prepare")
    identity_issues = environment_identity_issues(config, data, state)
    issues.extend(identity_issues)
    verification_ok, verification_detail = verification_status(state)
    if not verification_ok:
        issues.append(verification_detail)
    return env_name, ("warn" if issues else "ok"), issues or ["no drift indicators detected"]


def release_channel_map():
    settings = load_setting("release-channels", default_release_channels())
    channels = {}
    for item in settings.get("channels", "").split(","):
        name, _, approvals = item.strip().partition(":")
        if not name:
            continue
        try:
            channels[safe_key(name)] = int(approvals or "0")
        except ValueError:
            channels[safe_key(name)] = 0
    return channels


def env_channel(data):
    channel = str(data.get("releaseChannel") or data.get("channel") or "").strip()
    if channel:
        return safe_key(channel)
    settings = load_setting("release-channels", default_release_channels())
    return safe_key(settings.get("default_channel", "lab"))


def backup_exists(env_name):
    return any((item["data"].get("environment") == env_name or env_name in str(item["path"])) for item in backup_manifests())


def production_gate(config):
    data = read_json_from_context(config)
    env_name = str(data.get("environmentName") or config.stem)
    channel = env_channel(data)
    state = env_state(env_name)
    review_label, review_status = plan_review_status(env_name, state)
    _, drift_state, drift_issues = drift_status(config)
    identity_issues = environment_identity_issues(config, data, state)
    verification_ok, verification_detail = verification_status(state)
    channels = load_setting("release-channels", default_release_channels())
    checks = []
    checks.append(("Environment identity", not identity_issues, "; ".join(identity_issues) if identity_issues else "config and state identity match"))
    if channel == "production":
        checks.append(("Plan review", review_status == "ok", review_label))
        checks.append(("Backup evidence", not (channels.get("production_requires_backup") == "true") or backup_exists(env_name), "backup found" if backup_exists(env_name) else "backup missing"))
    else:
        checks.append(("Plan review", review_status == "ok", review_label))
        checks.append(("Backup evidence", True, "not required for non-production"))
    checks.append(("Drift", drift_state == "ok", "; ".join(drift_issues)))
    checks.append(("Verification", verification_ok, verification_detail))
    ok = all(item[1] for item in checks)
    return env_name, channel, ok, checks


def apply_gate(config, action):
    env_name, channel, ok, checks = production_gate(config)
    state = env_state(env_name)
    review_label, review_status = plan_review_status(env_name, state)
    reasons = []
    if action in {"deploy", "registry", "upgrade", "destroy"}:
        if review_status != "ok":
            reasons.append(f"plan review is {review_label}")
    if channel == "production" and not ok:
        reasons.extend(f"{name}: {detail}" for name, passed, detail in checks if not passed)
    if active_lock(env_name):
        reasons.append(f"environment locked by job {active_lock(env_name).get('jobId', 'unknown')}")
    return not reasons, reasons


def environment_next_action(config):
    data = read_json_from_context(config)
    env_name = str(data.get("environmentName") or config.stem)
    state = env_state(env_name)
    identity_issues = environment_identity_issues(config, data, state)
    review_label, review_status = plan_review_status(env_name, state)
    _, drift_state, drift_issues = drift_status(config)
    _, _, gate_ok, gate_checks = production_gate(config)
    detail_href = f"/environment/view?config={quote(str(config))}"

    if identity_issues:
        return "Resolve identity", detail_href, "warn", "; ".join(identity_issues)
    if not state["state"]:
        return "Prepare workspace", detail_href, "warn", "Stage NKP inputs and create local state."
    if not state["generate"]:
        return "Generate artifacts", detail_href, "warn", "Create registry, deploy, and reviewable plans."
    if review_status != "ok":
        return "Review plan", "/plan-review", "warn", review_label
    if drift_state != "ok":
        return "Resolve drift", "/drift", "warn", "; ".join(drift_issues)
    if not gate_ok:
        failed = [f"{name}: {detail}" for name, passed, detail in gate_checks if not passed]
        return "Clear production gate", "/production-readiness", "warn", "; ".join(failed)
    if not (state["base"] / "state" / "kubeconfig").exists():
        return "Request deploy", "/cli", "ok", "Apply gate is clear; submit controlled CLI deploy."
    verification_ok, verification_detail = verification_status(state)
    if not verification_ok:
        return "Verify cluster", detail_href, "warn", "Run verification and capture deployment evidence."
    return "Capture run summary", "/runs", "ok", "Environment has deployment evidence."


def backup_manifests():
    manifests = []
    for path in (ZT / "environments").glob("*/backup/*/backup-manifest.json") if (ZT / "environments").exists() else []:
        manifests.append({"path": path, "data": read_json(path) or {}})
    return sorted(manifests, key=lambda item: str(item["data"].get("createdAt", "")), reverse=True)


def environment_for_config(config):
    data = read_json_from_context(config)
    return str(data.get("environmentName") or Path(config).stem)


def health_checks():
    sources = load_setting("sources", default_sources())
    connections = read_json(SETTINGS / "connections.json") or {}
    checks = []
    checks.append(("Runner OS", "ok", os.name))
    checks.append(("Dashboard state", "ok" if ZT.exists() or ROOT.exists() else "warn", str(ZT)))
    checks.append(("Workspace writable", "ok" if os.access(ROOT, os.W_OK) else "warn", str(ROOT)))
    for tool in ["docker", "podman", "kubectl", "bash", "pwsh"]:
        checks.append((f"Tool: {tool}", "ok" if shutil.which(tool) else "warn", shutil.which(tool) or "not found"))
    for label, path in [("Standard bundle", sources.get("standard_bundle")), ("Air-gapped bundle", sources.get("airgapped_bundle"))]:
        status, note = path_status(path or "")
        checks.append((label, status, note))
    prism_ok, prism_note = check_tcp_endpoint(connections.get("prism", ""), 9440)
    checks.append(("Prism Central", "ok" if prism_ok else "warn", prism_note))
    reg_ok, reg_note = check_tcp_endpoint(connections.get("registry", ""), 443)
    checks.append(("Registry", "ok" if reg_ok else "warn", reg_note))
    checks.append(("Prism credentials", "ok" if os.environ.get("NUTANIX_PC_USERNAME") and os.environ.get("NUTANIX_PC_PASSWORD") else "warn", "environment variables present" if os.environ.get("NUTANIX_PC_USERNAME") and os.environ.get("NUTANIX_PC_PASSWORD") else "NUTANIX_PC_USERNAME/NUTANIX_PC_PASSWORD not set"))
    checks.append(("Registry credentials", "ok" if os.environ.get("ZT_REGISTRY_USERNAME") and os.environ.get("ZT_REGISTRY_PASSWORD") else "warn", "environment variables present" if os.environ.get("ZT_REGISTRY_USERNAME") and os.environ.get("ZT_REGISTRY_PASSWORD") else "ZT_REGISTRY_USERNAME/ZT_REGISTRY_PASSWORD not set"))
    for name, status, note in integration_checks():
        checks.append((f"Integration: {name}", status, note))
    return checks


def resolve_artifact(raw_path):
    if not raw_path:
        raise ValueError("Missing artifact path.")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    allowed_roots = [ZT.resolve(), (ROOT / "docs").resolve(), (ROOT / "configs").resolve(), (ROOT / "providers").resolve()]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError("Artifact path is outside allowed artifact roots.")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError("Artifact file not found.")
    return resolved


def create_environment(name, env_type):
    if not name.replace("-", "").replace("_", "").isalnum():
        return 2, "", "Environment name may contain only letters, numbers, hyphens, and underscores."
    if env_type not in {"connected", "proxied", "air-gapped"}:
        return 2, "", "Unsupported environment type."

    bash_path = shutil.which("bash")
    pwsh_path = shutil.which("pwsh") or shutil.which("powershell")
    if bash_path and (ROOT / "scripts" / "new-env.sh").exists():
        command = [bash_path, str(ROOT / "scripts" / "new-env.sh"), name, env_type]
    elif pwsh_path and (ROOT / "scripts" / "new-env.ps1").exists():
        command = [
            pwsh_path,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "new-env.ps1"),
            "-Name",
            name,
            "-Type",
            env_type,
        ]
    else:
        return 127, "", "No supported shell runner found for environment creation."

    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        return completed.returncode, completed.stdout, completed.stderr
    except OSError as exc:
        return 127, "", f"Failed to create environment: {exc}"


def action_command(action, config):
    bash_path = shutil.which("bash")
    pwsh_path = shutil.which("pwsh") or shutil.which("powershell")

    if bash_path and (ROOT / "scripts" / "zt.sh").exists():
        return [bash_path, str(ROOT / "scripts" / "zt.sh"), action, "--config", str(config)]
    if pwsh_path and (ROOT / "scripts" / "zt.ps1").exists():
        return [
            pwsh_path,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "zt.ps1"),
            action,
            "-Config",
            str(config),
        ]
    return None


def cli_command(action, config, apply=False, confirm_destroy=False):
    command = action_command(action, config)
    if not command:
        return None
    if command[0] == shutil.which("bash"):
        if apply:
            command.append("--apply")
        if confirm_destroy:
            command.append("--confirm-destroy")
    else:
        if apply:
            command.append("-Apply")
        if confirm_destroy:
            command.append("-ConfirmDestroy")
    return command


def command_label(command):
    if not command:
        return "runner unavailable"
    return " ".join(shlex.quote(str(part)) for part in command)


def run_action(action, config):
    command = action_command(action, config)
    if not command:
        return 127, "", "No supported shell runner found. Install bash, PowerShell, or run the dashboard container image."

    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", (exc.stderr or "") + "\nAction timed out after 300 seconds."
    except OSError as exc:
        return 127, "", f"Failed to start action runner: {exc}"


def parse_cli_command(command_text, fallback_config):
    tokens = shlex.split(command_text, posix=os.name != "nt")
    if not tokens:
        raise ValueError("Enter a ZeroTouch command.")

    script_index = next((idx for idx, token in enumerate(tokens) if token.endswith("zt.sh") or token.endswith("zt.ps1")), None)
    if script_index is not None:
        tokens = tokens[script_index + 1 :]

    action = tokens[0] if tokens else ""
    if action not in CLI_ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported CLI apply action: {action}.")

    config = fallback_config
    apply = False
    confirm_destroy = False
    idx = 1
    while idx < len(tokens):
        token = tokens[idx]
        if token in {"--config", "-c", "-Config"}:
            if idx + 1 >= len(tokens):
                raise ValueError(f"{token} requires a config path.")
            config = tokens[idx + 1]
            idx += 2
            continue
        if token in {"--apply", "-Apply"}:
            apply = True
            idx += 1
            continue
        if token in {"--confirm-destroy", "-ConfirmDestroy"}:
            confirm_destroy = True
            idx += 1
            continue
        raise ValueError(f"Unsupported CLI argument: {token}.")

    if action in CLI_APPLY_ACTIONS and not apply:
        raise ValueError(f"{action} requires --apply in the CLI window.")
    if action == "destroy" and not confirm_destroy:
        raise ValueError("destroy requires --confirm-destroy in the CLI window.")

    return action, resolve_env_config(config), apply, confirm_destroy


def run_cli_action(action, config, apply=False, confirm_destroy=False):
    command = cli_command(action, config, apply=apply, confirm_destroy=confirm_destroy)
    if not command:
        return 127, "", "No supported shell runner found."

    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", (exc.stderr or "") + "\nCLI command timed out after 600 seconds."
    except OSError as exc:
        return 127, "", f"Failed to start CLI runner: {exc}"


def role_permissions(role_name):
    permissions = set(permission_catalog().get(role_name, set()))
    rbac = load_rbac()
    for role in rbac.get("roles", []):
        if role.get("name") == role_name:
            permissions.update(safe_key(item) for item in role.get("permissions", "").replace(";", ",").split(",") if item.strip())
    return permissions


def has_permission(user, permission):
    if not user:
        return False
    return permission in role_permissions(user.get("role", "Operator"))


def job_dir(job_id):
    return JOBS / job_id


def job_meta_path(job_id):
    return job_dir(job_id) / "job.json"


def job_log_path(job_id):
    return job_dir(job_id) / "output.log"


def read_job(job_id):
    safe_id = safe_key(job_id)
    if not safe_id or safe_id != job_id:
        return None
    return read_json(job_meta_path(safe_id))


def write_job(job):
    path = job_meta_path(job["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, job)


def list_jobs(limit=50):
    if not JOBS.exists():
        return []
    jobs = []
    for meta in JOBS.glob("*/job.json"):
        job = read_json(meta)
        if job:
            jobs.append(job)
    return sorted(jobs, key=lambda item: item.get("createdAt", ""), reverse=True)[:limit]


def update_job(job_id, **updates):
    job = read_job(job_id)
    if not job:
        return None
    job.update(updates)
    job["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_job(job)
    return job


def append_job_log(job_id, text):
    path = job_log_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def run_job_background(job_id):
    job = read_job(job_id)
    if not job:
        return
    command = job.get("command", [])
    env_name = job.get("environment", "")
    lock_required = job.get("action") in {"prepare", "generate", "registry", "deploy", "upgrade", "destroy"}
    if lock_required:
        locked, reason = acquire_lock(env_name, job)
        if not locked:
            update_job(job_id, status="failed", exitCode=423, finishedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            append_job_log(job_id, f"[lock denied] {reason}\n")
            return
    update_job(job_id, status="running", startedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    append_job_log(job_id, f"$ {job.get('commandLabel', command_label(command))}\n")
    try:
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        update_job(job_id, pid=process.pid)
        assert process.stdout is not None
        for line in process.stdout:
            append_job_log(job_id, line)
        code = process.wait(timeout=10)
        latest = read_job(job_id) or {}
        status = "cancelled" if latest.get("status") == "cancel_requested" else ("succeeded" if code == 0 else "failed")
        update_job(job_id, status=status, exitCode=code, finishedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        update_change_record_for_job(job_id, status)
        append_job_log(job_id, f"\n[exit code {code}]\n")
    except Exception as exc:
        update_job(job_id, status="failed", exitCode=127, finishedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        update_change_record_for_job(job_id, "failed")
        append_job_log(job_id, f"\n[job runner error] {exc}\n")
    finally:
        if lock_required:
            release_lock(env_name, job_id)


def start_job(job_id):
    thread = threading.Thread(target=run_job_background, args=(job_id,), daemon=True)
    thread.start()


def create_job(action, config, command, requested_by, kind="safe", approval_required=False):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job_id = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{secrets.token_hex(3)}"
    job = {
        "id": job_id,
        "kind": kind,
        "action": action,
        "config": str(config),
        "environment": environment_for_config(config) if config else "",
        "status": "pending_approval" if approval_required else "queued",
        "requestedBy": requested_by.get("username", "unknown") if requested_by else "unknown",
        "requestedRole": requested_by.get("role", "") if requested_by else "",
        "approvalRequired": approval_required,
        "requiredApprovals": approval_requirement_for_config(action, config) if approval_required else 0,
        "approvals": [],
        "createdAt": now,
        "updatedAt": now,
        "command": command,
        "commandLabel": command_label(command),
    }
    write_job(job)
    append_job_log(job_id, "[pending approval]\n" if approval_required else "[queued]\n")
    if not approval_required:
        start_job(job_id)
    return job


def job_status_chip(status):
    return "ok" if status in {"succeeded", "running"} else "warn"


def approval_requirement(action):
    policy = load_setting("approval-policy", default_approval_policy())
    key = f"{action}_approvals"
    try:
        return max(1, int(policy.get(key, "1")))
    except ValueError:
        return 1


def approval_requirement_for_config(action, config):
    base = approval_requirement(action)
    if not config:
        return base
    data = read_json_from_context(config)
    channel = env_channel(data)
    return max(base, release_channel_map().get(channel, 0))


def approval_policy_allows(user, job):
    policy = load_setting("approval-policy", default_approval_policy())
    if policy.get("prevent_self_approval", "true") == "true" and job.get("requestedBy") == user.get("username"):
        return False, "Requester cannot approve their own apply job."
    if policy.get("production_requires_admin", "true") == "true" and "prod" in job.get("environment", "").lower() and user.get("role") != "Admin":
        return False, "Production-like environments require Admin approval."
    return True, ""


def job_approval_count(job):
    return len({approval.get("user") for approval in job.get("approvals", []) if approval.get("user")})


def job_controls(job, user, compact=False, include_open=True):
    controls = []
    if include_open:
        controls.append(f'<a class="button-link" href="/jobs/view?id={html.escape(job["id"])}">Open</a>')
    if job.get("status") == "pending_approval" and has_permission(user, "approve"):
        controls.append(f'<form method="post" action="/jobs/approve"><input type="hidden" name="job_id" value="{html.escape(job["id"])}"><button>{"Approve" if compact else "Approve and run"}</button></form>')
        controls.append(f'<form method="post" action="/jobs/reject"><input type="hidden" name="job_id" value="{html.escape(job["id"])}"><button class="button-danger">Reject</button></form>')
    if job.get("status") in {"running", "queued", "pending_approval"}:
        controls.append(f'<form method="post" action="/jobs/cancel"><input type="hidden" name="job_id" value="{html.escape(job["id"])}"><button class="button-danger">Cancel</button></form>')
    if job.get("status") in {"failed", "cancelled", "rejected", "succeeded"} and has_permission(user, "jobs"):
        controls.append(f'<form method="post" action="/jobs/retry"><input type="hidden" name="job_id" value="{html.escape(job["id"])}"><button>Retry</button></form>')
    return " ".join(controls)


def page(title, body, active="environments", user=None):
    body = inject_csrf_fields(body, user)

    def nav_class(key):
        return "nav-item active" if key == active else "nav-item"

    nav = f"""
    <div class="nav-label">Operations</div>
    <a class="{nav_class('environments')}" href="{VIEW_PATHS['environments']}"><span class="nav-dot"></span>Environments</a>
    <a class="{nav_class('jobs')}" href="{VIEW_PATHS['jobs']}">Jobs</a>
    <a class="{nav_class('runs')}" href="{VIEW_PATHS['runs']}">Runs</a>
    <div class="nav-label">Readiness</div>
    <a class="{nav_class('setup')}" href="{VIEW_PATHS['setup']}">Setup Wizard</a>
    <a class="{nav_class('preflight')}" href="{VIEW_PATHS['preflight']}">Preflight</a>
    <a class="{nav_class('drift')}" href="{VIEW_PATHS['drift']}">Drift</a>
    <a class="{nav_class('production-readiness')}" href="{VIEW_PATHS['production-readiness']}">Production Gate</a>
    <a class="{nav_class('health')}" href="{VIEW_PATHS['health']}">Health</a>
    <div class="nav-label">Artifacts</div>
    <a class="{nav_class('artifacts')}" href="{VIEW_PATHS['artifacts']}">Artifacts</a>
    <a class="{nav_class('plan-review')}" href="{VIEW_PATHS['plan-review']}">Plan Review</a>
    <a class="{nav_class('kubeconfig')}" href="{VIEW_PATHS['kubeconfig']}">Kubeconfig</a>
    <a class="{nav_class('backups')}" href="{VIEW_PATHS['backups']}">Backups</a>
    <a class="{nav_class('restore')}" href="{VIEW_PATHS['restore']}">Restore</a>
    <div class="nav-label">Deployment</div>
    <a class="{nav_class('sources')}" href="{VIEW_PATHS['sources']}">Sources</a>
    <a class="{nav_class('inventory')}" href="{VIEW_PATHS['inventory']}">Inventory</a>
    <a class="{nav_class('network')}" href="{VIEW_PATHS['network']}">Network</a>
    <a class="{nav_class('pipeline')}" href="{VIEW_PATHS['pipeline']}">Pipeline</a>
    <a class="{nav_class('cli')}" href="{VIEW_PATHS['cli']}">CLI</a>
    <a class="{nav_class('locks')}" href="{VIEW_PATHS['locks']}">Locks</a>
    <div class="nav-label">Governance</div>
    <a class="{nav_class('actions')}" href="{VIEW_PATHS['actions']}">Safe Actions</a>
    <a class="{nav_class('change-records')}" href="{VIEW_PATHS['change-records']}">Change Records</a>
    <a class="{nav_class('approval-policy')}" href="{VIEW_PATHS['approval-policy']}">Approval Policy</a>
    <a class="{nav_class('release-channels')}" href="{VIEW_PATHS['release-channels']}">Release Channels</a>
    <a class="{nav_class('audit')}" href="{VIEW_PATHS['audit']}">Audit Trail</a>
    <div class="nav-label">Settings</div>
    <a class="{nav_class('connections')}" href="{VIEW_PATHS['connections']}">Connections</a>
    <a class="{nav_class('new-environment')}" href="{VIEW_PATHS['new-environment']}">New Environment</a>
    <a class="{nav_class('providers')}" href="{VIEW_PATHS['providers']}">Providers</a>
    <a class="{nav_class('secrets')}" href="{VIEW_PATHS['secrets']}">Secrets</a>
    <a class="{nav_class('rbac')}" href="{VIEW_PATHS['rbac']}">RBAC</a>
    <a class="{nav_class('database')}" href="{VIEW_PATHS['database']}">Database</a>
    <a class="{nav_class('integrations')}" href="{VIEW_PATHS['integrations']}">Integrations</a>
    <div class="nav-label">System</div>
    <a class="{nav_class('about')}" href="{VIEW_PATHS['about']}">About</a>
"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="icon" type="image/svg+xml" href="/assets/veridian-mark-teal.svg">
  <script>
    (() => {{
      try {{
        const storedTheme = localStorage.getItem("zt-theme");
        if (storedTheme === "light") document.documentElement.dataset.theme = "light";
      }} catch (error) {{}}
    }})();
  </script>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #030712;
      --panel: #111827;
      --panel-2: #172033;
      --panel-3: #111827;
      --ink: #f1f5f9;
      --muted: #9ca3af;
      --muted-2: #6b7280;
      --line: #263244;
      --line-strong: #344256;
      --nav: #030712;
      --nav-2: #080d1a;
      --topbar-bg: rgba(3,7,18,.82);
      --heading: #f1f5f9;
      --brand-text: #f1f5f9;
      --nav-item-text: #9ca3af;
      --nav-label-text: #4b5563;
      --nav-hover-text: #e5e7eb;
      --operator-text: #d1d5db;
      --control-text: #d1d5db;
      --control-hover-text: #e5f5ff;
      --table-hover: rgba(255,255,255,.025);
      --input-bg: #111827;
      --input-label: #9ca3af;
      --pre-bg: #030712;
      --pre-text: #dbeafe;
      --notice-bg: rgba(3,78,162,.08);
      --notice-border: rgba(3,78,162,.3);
      --notice-text: #bfdbfe;
      --scrollbar-track: #111827;
      --scrollbar-thumb: #374151;
      --scrollbar-thumb-hover: #4b5563;
      --badge-connected-text: #93c5fd;
      --badge-connected-bg: rgba(3,78,162,.18);
      --badge-connected-border: rgba(3,78,162,.3);
      --badge-proxied-text: #c4b5fd;
      --badge-proxied-bg: rgba(91,33,182,.22);
      --badge-proxied-border: rgba(124,58,237,.28);
      --badge-airgapped-text: #fcd34d;
      --badge-airgapped-bg: rgba(234,179,8,.12);
      --badge-airgapped-border: rgba(234,179,8,.28);
      --danger-text: #fca5a5;
      --danger-hover-text: #fecaca;
      --accent: #034ea2;
      --accent-2: #21c2f8;
      --accent-soft: rgba(3, 78, 162, .16);
      --good: #00b388;
      --good-soft: rgba(0, 179, 136, .14);
      --warn: #eab308;
      --warn-soft: rgba(234, 179, 8, .14);
      --bad: #ef4444;
      --bad-soft: rgba(239, 68, 68, .14);
      --shadow: none;
    }}
    :root[data-theme="light"] {{
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --panel-2: #edf2f7;
      --panel-3: #f8fafc;
      --ink: #111827;
      --muted: #4b5563;
      --muted-2: #6b7280;
      --line: #d6deea;
      --line-strong: #b9c5d6;
      --nav: #ffffff;
      --nav-2: #f8fafc;
      --topbar-bg: rgba(255,255,255,.9);
      --heading: #111827;
      --brand-text: #111827;
      --nav-item-text: #374151;
      --nav-label-text: #4b5563;
      --nav-hover-text: #0f172a;
      --operator-text: #1f2937;
      --control-text: #1f2937;
      --control-hover-text: #034ea2;
      --table-hover: rgba(3,78,162,.045);
      --input-bg: #ffffff;
      --input-label: #374151;
      --pre-bg: #0f172a;
      --pre-text: #e5f0ff;
      --notice-bg: #eaf2ff;
      --notice-border: #b7cdf2;
      --notice-text: #0f3d75;
      --scrollbar-track: #e5e7eb;
      --scrollbar-thumb: #9ca3af;
      --scrollbar-thumb-hover: #6b7280;
      --badge-connected-text: #0f4c9a;
      --badge-connected-bg: #e7f0ff;
      --badge-connected-border: #b7cdf2;
      --badge-proxied-text: #5b21b6;
      --badge-proxied-bg: #f1eafe;
      --badge-proxied-border: #d8c8fb;
      --badge-airgapped-text: #7a4f00;
      --badge-airgapped-bg: #fff5cc;
      --badge-airgapped-border: #ecd27a;
      --danger-text: #b91c1c;
      --danger-hover-text: #7f1d1d;
      --accent-soft: rgba(3, 78, 162, .1);
      --good: #047857;
      --good-soft: rgba(4, 120, 87, .12);
      --warn: #9a6700;
      --warn-soft: rgba(154, 103, 0, .12);
      --bad: #b91c1c;
      --bad-soft: rgba(185, 28, 28, .1);
      --shadow: 0 14px 36px rgba(15, 23, 42, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 Inter, "Segoe UI", Roboto, Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: var(--accent-2); text-decoration: none; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: var(--scrollbar-track); }}
    ::-webkit-scrollbar-thumb {{ background: var(--scrollbar-thumb); border-radius: 999px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--scrollbar-thumb-hover); }}
    .shell {{ display: grid; grid-template-columns: 256px minmax(0, 1fr); min-height: 100vh; }}
    .sidebar {{
      background: var(--nav);
      color: #f8fafc;
      padding: 0 12px 16px;
      border-right: 1px solid var(--line);
      position: sticky; top: 0; height: 100vh; overflow-y: auto;
    }}
    .brand {{ min-height: 64px; display: flex; align-items: center; gap: 12px; margin: 0 -12px 12px; padding: 0 16px; border-bottom: 1px solid var(--line); }}
    .brand-mark {{
      width: 34px; height: 34px; border-radius: 8px;
      display: grid; place-items: center;
      background: #1a6b6b;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.12);
    }}
    .brand-mark img {{ width: 34px; height: 34px; display: block; border-radius: 8px; }}
    .brand-title {{ font-size: 14px; font-weight: 800; color: var(--brand-text); letter-spacing: 0; }}
    .brand-subtitle {{ color: #6b7280; font-size: 12px; margin-top: 1px; }}
    .nav-label {{ color: var(--nav-label-text); font-size: 11px; font-weight: 760; text-transform: uppercase; margin: 20px 12px 8px; letter-spacing: .04em; }}
    .nav-item {{
      display: flex; align-items: center; gap: 10px;
      min-height: 38px; padding: 0 12px; border-radius: 8px;
      color: var(--nav-item-text); font-weight: 650; text-decoration: none;
      border: 1px solid transparent;
      transition: background .15s ease, color .15s ease, border-color .15s ease;
    }}
    .nav-item:hover {{ background: var(--panel); color: var(--nav-hover-text); border-color: transparent; }}
    .nav-item.active {{ background: var(--accent); color: #fff; border-color: transparent; }}
    .nav-dot {{ width: 8px; height: 8px; border-radius: 50%; background: transparent; }}
    .nav-item.active .nav-dot {{ background: var(--accent-2); }}
    .content {{ min-width: 0; }}
    .topbar {{
      min-height: 64px; background: var(--topbar-bg);
      border-bottom: 1px solid var(--line);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 24px;
      position: sticky; top: 0; z-index: 5; backdrop-filter: blur(10px);
    }}
    .topbar h1 {{ margin: 0; font-size: 18px; font-weight: 700; letter-spacing: 0; color: var(--heading); }}
    .topbar-meta {{ display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 12px; flex-wrap: wrap; justify-content: flex-end; }}
    .operator-pill {{ display: inline-flex; align-items: center; gap: 8px; min-height: 28px; padding: 0 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); color: var(--operator-text); font-weight: 700; }}
    .operator-pill::before {{ content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--good); }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 24px 28px 42px; }}
    h2 {{ margin: 0; font-size: 16px; }}
    .section-head {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 24px 0 12px; }}
    .section-copy {{ color: var(--muted); font-size: 12px; margin-top: 3px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 14px; }}
    .ops-strip {{ display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 1px; border: 1px solid var(--line); border-radius: 8px; background: var(--line); overflow: hidden; box-shadow: var(--shadow); margin-bottom: 18px; }}
    .ops-item {{ background: var(--panel); padding: 13px 15px; }}
    .ops-label {{ color: var(--muted); font-size: 11px; font-weight: 760; text-transform: uppercase; letter-spacing: .04em; }}
    .ops-value {{ margin-top: 5px; font-weight: 780; color: var(--heading); }}
    .metric {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
      padding: 17px; box-shadow: var(--shadow); position: relative; overflow: hidden;
    }}
    .metric::after {{ content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: var(--line-strong); }}
    .metric-link::after {{ background: var(--accent); }}
    .metric-link {{
      display: block; color: var(--ink);
      transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease;
    }}
    .metric-link:hover {{
      transform: translateY(-1px);
      border-color: var(--line-strong);
      box-shadow: 0 18px 42px rgba(3, 78, 162, .12);
    }}
    .metric.disabled {{ opacity: .72; }}
    .metric-label {{ color: var(--muted); font-size: 12px; font-weight: 650; }}
    .metric-value {{ margin-top: 8px; font-size: 28px; font-weight: 780; }}
    .metric-foot {{ margin-top: 4px; color: var(--muted); font-size: 12px; }}
    .panel {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
      box-shadow: var(--shadow); overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 13px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: 0; }}
    th {{
      background: var(--panel-2); color: var(--muted);
      font-size: 11px; font-weight: 780; text-transform: uppercase; letter-spacing: .035em;
      border-bottom: 1px solid var(--line-strong);
    }}
    tbody tr:hover {{ background: var(--table-hover); }}
    code, pre {{ font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; }}
    pre {{
      margin: 0; background: var(--pre-bg); color: var(--pre-text);
      padding: 16px; overflow: auto; border-radius: 8px;
      border: 1px solid var(--line);
    }}
    .env-name {{ font-weight: 750; }}
    .env-file {{ color: var(--muted); font-size: 12px; margin-top: 3px; white-space: nowrap; }}
    .badge {{
      display: inline-flex; align-items: center; gap: 6px;
      min-height: 24px; padding: 0 9px; border-radius: 999px;
      font-size: 12px; font-weight: 700; border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge.connected {{ color: var(--badge-connected-text); background: var(--badge-connected-bg); border-color: var(--badge-connected-border); }}
    .badge.proxied {{ color: var(--badge-proxied-text); background: var(--badge-proxied-bg); border-color: var(--badge-proxied-border); }}
    .badge.air-gapped {{ color: var(--badge-airgapped-text); background: var(--badge-airgapped-bg); border-color: var(--badge-airgapped-border); }}
    .chip {{ display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-weight: 650; }}
    .chip::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }}
    .chip.ok {{ color: var(--good); }}
    .chip.ok::before {{ background: var(--good); }}
    .chip.warn {{ color: var(--warn); }}
    .chip.warn::before {{ background: var(--warn); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 7px; min-width: 270px; }}
    .actions form {{ display: inline; }}
    .manage-actions {{ display: flex; flex-wrap: wrap; gap: 7px; min-width: 128px; }}
    button {{
      min-height: 32px; border: 1px solid var(--line); background: var(--panel-2);
      padding: 0 9px; border-radius: 6px; cursor: pointer;
      color: var(--control-text); font-weight: 700; font-size: 12px;
    }}
    button:hover {{ background: var(--accent-soft); border-color: rgba(33,194,248,.45); color: var(--control-hover-text); }}
    .button-link {{
      display: inline-flex; align-items: center; min-height: 32px;
      border: 1px solid var(--line); background: var(--panel-2);
      padding: 0 9px; border-radius: 6px; color: var(--control-text);
      font-weight: 700; font-size: 12px;
    }}
    .button-link:hover {{ background: var(--accent-soft); border-color: rgba(33,194,248,.45); color: var(--control-hover-text); }}
    .button-danger {{ border-color: rgba(239,68,68,.35); color: var(--danger-text); }}
    .button-danger:hover {{ background: var(--bad-soft); border-color: rgba(239,68,68,.45); color: var(--danger-hover-text); }}
    .run-list {{ list-style: none; margin: 0; padding: 0; }}
    .run-list li {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 11px 16px; border-bottom: 1px solid var(--line);
    }}
    .run-list li:last-child {{ border-bottom: 0; }}
    .muted {{ color: var(--muted); }}
    .notice {{
      margin-top: 16px; padding: 12px 14px; border-radius: 8px;
      border: 1px solid var(--notice-border); background: var(--notice-bg); color: var(--notice-text);
      font-size: 13px;
    }}
    .login-panel {{ max-width: 520px; margin: 38px auto 0; }}
    .login-panel .panel {{ box-shadow: 0 24px 70px rgba(0, 0, 0, .28); }}
    .settings-grid {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; }}
    .settings-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); }}
    .settings-card h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .settings-card p {{ margin: 0; color: var(--muted); }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 14px; }}
    .field label {{ display: block; color: var(--input-label); font-size: 12px; font-weight: 750; margin-bottom: 6px; text-transform: uppercase; }}
    .field input, .field select, .field textarea {{
      width: 100%; min-height: 36px; border: 1px solid var(--line); border-radius: 6px;
      padding: 0 10px; color: var(--ink); background: var(--input-bg);
    }}
    .field textarea {{ min-height: 96px; padding: 10px; resize: vertical; font: inherit; }}
    .pipeline {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; }}
    .pipeline-step {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }}
    .pipeline-step strong {{ display: block; margin-bottom: 6px; }}
    .pipeline-step .chip {{ font-size: 12px; }}
    .progress-track {{ height: 8px; min-width: 120px; border-radius: 999px; background: rgba(148,163,184,.18); overflow: hidden; margin-top: 6px; }}
    .progress-bar {{ height: 100%; background: linear-gradient(90deg, var(--accent), var(--good)); }}
    .action-group {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; }}
    .next-actions {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 12px; }}
    .next-action {{
      display: flex; justify-content: space-between; gap: 14px; align-items: center;
      padding: 14px; border: 1px solid var(--line); border-radius: 8px;
      background: var(--panel);
    }}
    .next-action strong {{ display: block; margin-bottom: 4px; }}
    .next-action .button-link {{ flex: 0 0 auto; }}
    .risk-low {{ color: var(--good); }}
    .risk-medium {{ color: var(--warn); }}
    .risk-high {{ color: var(--danger-text); }}
    .review-note {{ max-width: 380px; color: var(--muted); font-size: 12px; }}
    .terminal-window {{ background: #0b1220; color: #dbeafe; border-radius: 8px; border: 1px solid #253149; overflow: hidden; }}
    .terminal-bar {{ min-height: 36px; display: flex; align-items: center; gap: 8px; padding: 0 12px; background: #111827; border-bottom: 1px solid #253149; color: #93a4bd; font-size: 12px; font-weight: 700; }}
    .terminal-dot {{ width: 9px; height: 9px; border-radius: 50%; background: #64748b; }}
    .terminal-body {{ padding: 14px; }}
    .terminal-prompt {{ color: #5eead4; font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; margin-bottom: 8px; }}
    .terminal-input {{
      width: 100%; min-height: 160px; resize: vertical; border: 1px solid #334155; border-radius: 6px;
      background: #0f172a; color: #e5f0ff; padding: 12px;
      font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; font-size: 13px; line-height: 1.5;
    }}
    .terminal-help {{ color: #9fb1c8; margin-top: 10px; font-size: 12px; }}
    .result-layout {{ display: grid; gap: 16px; }}
    .back-link {{ display: inline-flex; align-items: center; margin-top: 16px; font-weight: 700; }}
    .theme-toggle {{ min-width: 76px; }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: none; }}
      .topbar {{ align-items: flex-start; flex-direction: column; gap: 10px; padding: 16px 20px; }}
      main {{ padding: 18px 16px 32px; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .ops-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .settings-grid, .form-grid {{ grid-template-columns: 1fr; }}
      .action-group, .detail-grid, .next-actions {{ grid-template-columns: 1fr; }}
      .actions {{ min-width: 270px; }}
      .manage-actions {{ min-width: 128px; }}
    }}
    @media (max-width: 620px) {{
      .summary-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark"><img src="/assets/veridian-mark-teal.svg" alt="Veridian"></div>
      <div>
        <div class="brand-title">NKP ZeroTouch</div>
        <div class="brand-subtitle">Framework</div>
      </div>
    </div>
{nav}
  </aside>
  <div class="content">
    <div class="topbar">
      <div>
        <h1>NKP ZeroTouch Framework</h1>
        <div class="section-copy">Nutanix Kubernetes Platform deployment console</div>
      </div>
      <div class="topbar-meta">
        <span class="badge connected">Console Online</span>
        <span class="operator-pill">{html.escape(user.get('username', 'operator session') if user else 'operator session')}</span>
        <button class="theme-toggle" type="button" data-theme-toggle><span data-theme-label>Light</span></button>
        <a class="button-link" href="/logout">Log out</a>
        <span>CLI apply requires approval</span>
      </div>
    </div>
    <main>{body}</main>
  </div>
</div>
<script>
  (() => {{
    const root = document.documentElement;
    const toggle = document.querySelector("[data-theme-toggle]");
    const label = document.querySelector("[data-theme-label]");
    const currentTheme = () => root.dataset.theme === "light" ? "light" : "dark";
    const render = () => {{
      if (!label) return;
      label.textContent = currentTheme() === "light" ? "Dark" : "Light";
    }};
    render();
    toggle?.addEventListener("click", () => {{
      const next = currentTheme() === "light" ? "dark" : "light";
      if (next === "light") root.dataset.theme = "light";
      else root.removeAttribute("data-theme");
      try {{ localStorage.setItem("zt-theme", next); }} catch (error) {{}}
      render();
    }});
  }})();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content, status=200, headers=None):
        content = inject_csrf_fields(content, self.current_user())
        user = self.current_user()
        if user:
            label = f"{user.get('username', 'operator')} ({user.get('role', 'Operator')})"
            content = content.replace('<span class="operator-pill">operator session</span>', f'<span class="operator-pill">{html.escape(label)}</span>')
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, payload, status=200):
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_redirect(self, location, headers=None):
        self.send_response(303)
        self.send_header("Location", location)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def current_user(self):
        token = cookie_value(self.headers, "zt_session")
        return get_session(token)

    def require_login(self, parsed):
        if parsed.path in {"/login", "/login/oidc", "/login/oidc/callback", "/assets/veridian-mark-teal.svg"}:
            return True
        if self.current_user():
            return True
        self.send_redirect("/login")
        return False

    def require_permission(self, parsed):
        permission = route_permission(parsed.path)
        user = self.current_user()
        if not permission or has_permission(user, permission):
            return True
        audit_event("permission_denied", user, parsed.path, "denied", {"permission": permission})
        self.send_html(page("Access Denied", f"<h2>Access denied</h2><div class='notice'>Your role does not have <code>{html.escape(permission)}</code> permission for this route.</div><a class='back-link' href='/'>Back to dashboard</a>", "about"), status=403)
        return False

    def require_csrf(self, form):
        user = self.current_user()
        expected = csrf_token(user)
        provided = form_value(form, "csrf_token")
        if expected and provided and secrets.compare_digest(expected, provided):
            return True
        audit_event("csrf_rejected", user, self.path, "denied")
        self.send_html(page("Request Rejected", "<h2>Request rejected</h2><div class='notice'>The form security token was missing or invalid. Reload the page and try again.</div><a class='back-link' href='/'>Back to dashboard</a>", "about"), status=403)
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self.require_login(parsed):
            return
        if not self.require_permission(parsed):
            return
        if parsed.path == "/assets/veridian-mark-teal.svg":
            asset = ROOT / "dashboard" / "assets" / "veridian-mark-teal.svg"
            if not asset.exists():
                self.send_html(page("Not Found", "<h2>Asset not found</h2>"), status=404)
                return
            encoded = asset.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if parsed.path == "/login":
            rbac = load_rbac()
            has_login_accounts = any(account.get("passwordHash") for account in rbac.get("accounts", []))
            heading = "Sign In" if has_login_accounts else "Create Admin Account"
            needs_bootstrap_token = (not has_login_accounts) and bootstrap_token_required()
            hint = "Use a local console account." if has_login_accounts else "No password-enabled accounts exist yet. Create the first local administrator account."
            token_row = ""
            if needs_bootstrap_token:
                token_row = '<tr><td>Bootstrap Token</td><td><div class="field"><input name="bootstrap_token" type="password"></div></td></tr>'
            body = f"""
<div class="login-panel">
<div class="section-head">
  <div>
    <h2>{heading}</h2>
    <div class="section-copy">{hint}</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/login">
    <table>
      <thead><tr><th>Field</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Username</td><td><div class="field"><input name="username" value="admin"></div></td></tr>
        <tr><td>Password</td><td><div class="field"><input name="password" type="password"></div></td></tr>
        {token_row}
        <tr><td></td><td><button>{'Sign in' if has_login_accounts else 'Create admin and sign in'}</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">This is local console authentication for operator workstations. Production use should move to OIDC/SSO and server-side session storage. <a href="/login/oidc">Check OIDC login readiness</a>.</div>
</div>
"""
            self.send_html(page("Login - NKP ZeroTouch Framework", body, "about"))
            return
        if parsed.path == "/login/oidc":
            settings = load_setting("integrations", default_integrations())
            status, note = oidc_status(settings)
            body = f"""
<div class="login-panel">
<div class="section-head">
  <div>
    <h2>OIDC Login</h2>
    <div class="section-copy">Enterprise identity provider handoff status.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Item</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>OIDC issuer</td><td>{html.escape(settings.get('oidc_issuer', '') or 'not configured')}</td></tr>
      <tr><td>Discovery</td><td><span class="chip {status}">{html.escape(note)}</span></td></tr>
      <tr><td>Client ID</td><td>{html.escape(settings.get('oidc_client_id', '') or 'not configured')}</td></tr>
    </tbody>
  </table>
</section>
<div class="notice">OIDC metadata is configured and probed here. Full authorization-code token exchange is the next implementation step before production SSO can replace local login.</div>
<a class="back-link" href="/login">Back to local login</a>
</div>
"""
            self.send_html(page("OIDC Login - NKP ZeroTouch Framework", body, "about"))
            return
        if parsed.path == "/logout":
            token = cookie_value(self.headers, "zt_session")
            audit_event("logout", self.current_user(), "session", "success")
            delete_session(token)
            self.send_redirect("/login", {"Set-Cookie": "zt_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            return
        if parsed.path.startswith("/api/"):
            if parsed.path == "/api/status":
                checks = health_checks()
                self.send_json({"status": "ok", "checks": [{"name": name, "status": status, "note": note} for name, status, note in checks]})
                return
            if parsed.path == "/api/environments":
                rows = []
                for config in env_configs():
                    data = read_json_from_context(config)
                    env_name = data.get("environmentName") or config.stem
                    state = env_state(env_name)
                    lifecycle, lifecycle_status = environment_lifecycle(env_name, state)
                    ready_passed, ready_total, ready_pct = environment_readiness(data, state)
                    rows.append({"name": env_name, "config": config.name, "type": data.get("environmentType", ""), "lifecycle": lifecycle, "lifecycleStatus": lifecycle_status, "readiness": {"passed": ready_passed, "total": ready_total, "percent": ready_pct}, "planReview": plan_review_status(env_name, state)[0]})
                self.send_json({"environments": rows})
                return
            if parsed.path == "/api/jobs":
                self.send_json({"jobs": list_jobs(100)})
                return
            if parsed.path == "/api/jobs/log":
                query = parse_qs(parsed.query)
                job_id = query.get("id", [""])[0]
                job = read_job(job_id)
                if not job:
                    self.send_json({"error": "job not found"}, status=404)
                    return
                log_path = job_log_path(job_id)
                self.send_json({"job": job, "log": log_path.read_text(encoding="utf-8") if log_path.exists() else ""})
                return
            if parsed.path == "/api/locks":
                locks = [read_json(path) for path in LOCKS.glob("*.json")] if LOCKS.exists() else []
                self.send_json({"locks": [lock for lock in locks if lock]})
                return
            if parsed.path == "/api/change-records":
                self.send_json({"changeRecords": list_change_records(100)})
                return
            self.send_json({"error": "not found"}, status=404)
            return
        if parsed.path == "/setup":
            sources = load_setting("sources", default_sources())
            connections = read_json(SETTINGS / "connections.json") or {}
            inventory = load_setting("inventory", default_inventory())
            network = load_setting("network", default_network())
            secrets_cfg = load_setting("secrets", default_secrets())
            checks = [
                ("Sources", "/sources", bool(sources.get("standard_bundle") or sources.get("airgapped_bundle")), "Register NKP bundle and source paths."),
                ("Connections", "/settings/connections", bool(connections.get("prism") or connections.get("registry")), "Add Prism Central and registry endpoints."),
                ("Inventory", "/inventory", bool(inventory.get("nodes") or inventory.get("mode")), "Document AHV or bare-metal target inventory."),
                ("Network", "/network", bool(network.get("api_vip") or network.get("dns_servers")), "Define VIP, DNS, NTP, proxy, and CIDR inputs."),
                ("Secrets", "/settings/secrets", secrets_cfg.get("backend") not in {"", "local-file"} or bool((ZT / "settings").exists()), "Choose local or external secret backend."),
                ("Environment", "/settings/new-environment", bool(env_configs()), "Create or edit deployment profiles."),
                ("Preflight", "/preflight", any(item["status"] == "ok" for item in preflight_checks()), "Review readiness warnings before generate/apply."),
            ]
            rows = "".join(
                f"<tr><td>{idx}</td><td><a href='{href}'>{html.escape(label)}</a></td><td><span class='chip {'ok' if ok else 'warn'}'>{'complete' if ok else 'pending'}</span></td><td>{html.escape(note)}</td></tr>"
                for idx, (label, href, ok, note) in enumerate(checks, 1)
            )
            done = sum(1 for _, _, ok, _ in checks if ok)
            body = f"""
<section class="summary-grid">
  {metric_card("Setup Progress", pct(done, len(checks)), "percent complete", "/setup")}
  {metric_card("Steps Complete", done, "of 7 setup steps", "/setup")}
  {metric_card("Preflight", sum(1 for item in preflight_checks() if item["status"] == "ok"), "checks passing", "/preflight")}
  {metric_card("Environments", len(env_configs()), "profiles available", "/")}
</section>
<div class="section-head">
  <div>
    <h2>Setup Wizard</h2>
    <div class="section-copy">Guided operator flow from source intake through preflight readiness.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Step</th><th>Area</th><th>Status</th><th>Operator Task</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
<div class="notice">Use this page for first-run setup. Once all steps are complete, run validate, prepare, generate, review artifacts, and request apply through the controlled CLI workflow.</div>
"""
            self.send_html(page("Setup Wizard - NKP ZeroTouch Framework", body, "setup"))
            return
        if parsed.path in ("/", "/environments"):
            rows = []
            next_action_cards = []
            env_total = 0
            ready_to_deploy = 0
            blocked_total = 0
            drift_total = 0
            report_total = 0
            for config in env_configs():
                data = read_json_from_context(config)
                name = data.get("environmentName") or config.stem
                env_type = data.get("environmentType", "unknown")
                channel = env_channel(data)
                state = env_state(name)
                report = state["verification"].exists()
                lifecycle_label, lifecycle_status = environment_lifecycle(name, state)
                ready_passed, ready_total, ready_pct = environment_readiness(data, state)
                review_label, review_status = plan_review_status(name, state)
                _, drift_state, drift_issues = drift_status(config)
                gate_ok, gate_reasons = apply_gate(config, "deploy")
                next_label, next_href, next_status, next_detail = environment_next_action(config)
                env_total += 1
                ready_to_deploy += 1 if gate_ok else 0
                blocked_total += 0 if gate_ok else 1
                drift_total += 1 if drift_state != "ok" else 0
                report_total += 1 if report else 0
                config_arg = quote(str(config))
                manage_buttons = (
                    f'<a class="button-link" href="/environment/view?config={config_arg}">Open</a> '
                    f'<a class="button-link" href="/environment/edit?config={config_arg}">Edit</a> '
                )
                if len(next_action_cards) < 4:
                    next_action_cards.append(
                        f"<div class='next-action'><div><strong>{html.escape(name)}</strong>"
                        f"<div class='env-file'>{html.escape(config.name)} &middot; {html.escape(next_detail[:140])}</div></div>"
                        f"<a class='button-link' href='{html.escape(next_href)}'>{html.escape(next_label)}</a></div>"
                    )
                gate_detail = "deploy gate clear" if gate_ok else "; ".join(gate_reasons[:2])
                drift_label = "clear" if drift_state == "ok" else "attention"
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='badge {html.escape(env_type)}'>{html.escape(env_type)}</span><div class='env-file'>channel {html.escape(channel)}</div></td>"
                    f"<td><span class='chip {lifecycle_status}'>{html.escape(lifecycle_label)}</span><div class='env-file'>readiness {ready_passed}/{ready_total}</div><div class='progress-track'><div class='progress-bar' style='width:{ready_pct}%'></div></div></td>"
                    f"<td><span class='chip {'ok' if gate_ok else 'warn'}'>{'ready' if gate_ok else 'blocked'}</span><div class='env-file'>{html.escape(gate_detail[:120])}</div></td>"
                    f"<td><span class='chip {drift_state}'>{html.escape(drift_label)}</span><div class='env-file'>{html.escape('; '.join(drift_issues)[:120])}</div></td>"
                    f"<td><span class='chip {review_status}'>{html.escape(review_label)}</span><div class='env-file'>{'report available' if report else 'report missing'}</div></td>"
                    f"<td><a class='button-link' href='{html.escape(next_href)}'>{html.escape(next_label)}</a><div class='env-file'>{html.escape(next_detail[:120])}</div></td>"
                    f"<td class='manage-actions'>{manage_buttons}</td></tr>"
                )
            runs = sorted((ZT / "runs").glob("*/summary.md")) if (ZT / "runs").exists() else []
            recent_runs = list(reversed(runs[-10:]))
            rbac = load_rbac()
            auth_mode = "Local RBAC" if any(account.get("passwordHash") for account in rbac.get("accounts", [])) else "Bootstrap"
            pending_approvals = sum(1 for job in list_jobs(200) if job.get("status") == "pending_approval")
            uniqueness_issues = environment_uniqueness_issues()
            uniqueness_notice = (
                "<div class='notice'><strong>Environment identity warning:</strong> "
                + " ".join(html.escape(issue) for issue in uniqueness_issues)
                + "</div>"
                if uniqueness_issues else ""
            )
            run_rows = "".join(
                f"<li><code>{html.escape(p.parent.name)}</code><span class='muted'>summary.md</span></li>"
                for p in recent_runs
            )
            body = f"""
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Runner</div><div class="ops-value">Docker / Local Shell</div></div>
  <div class="ops-item"><div class="ops-label">Deployment Modes</div><div class="ops-value">Connected / Proxied / Air-gapped</div></div>
  <div class="ops-item"><div class="ops-label">Authentication</div><div class="ops-value">{html.escape(auth_mode)}</div></div>
  <div class="ops-item"><div class="ops-label">Live Apply</div><div class="ops-value">CLI Approval Required</div></div>
</section>
<section class="summary-grid">
  {metric_card("Ready to Deploy", ready_to_deploy, "environments clear deploy gate", "/production-readiness")}
  {metric_card("Blocked", blocked_total, "environments need operator action", "/preflight")}
  {metric_card("Pending Approval", pending_approvals, "apply jobs awaiting review", "/jobs")}
  {metric_card("Drift Detected", drift_total, "environments with drift signals", "/drift")}
</section>
{uniqueness_notice}

<div class="section-head">
  <div>
    <h2>Recommended Next Actions</h2>
    <div class="section-copy">Highest-signal operator actions based on current state, review, drift, and production gate checks.</div>
  </div>
</div>
<section class="next-actions">{''.join(next_action_cards) or '<div class="next-action"><div><strong>No environments found</strong><div class="env-file">Create an environment profile to start the deployment flow.</div></div><a class="button-link" href="/settings/new-environment">Create</a></div>'}</section>

<div class="section-head">
  <div>
    <h2>Environments</h2>
    <div class="section-copy">Operational cockpit for connected, proxied, and air-gapped NKP deployment profiles.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Name</th><th>Type / Channel</th><th>Lifecycle / Readiness</th><th>Deploy Gate</th><th>Drift</th><th>Evidence</th><th>Next Action</th><th>Manage</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>

<div class="section-head">
  <div>
    <h2>Recent Runs</h2>
    <div class="section-copy">Latest framework executions captured under the local .zt workspace.</div>
  </div>
</div>
<section class="panel">
  <ul class="run-list">{run_rows or '<li><span class="muted">No run summaries yet.</span></li>'}</ul>
</section>
<div class="notice">Destructive and apply actions are intentionally CLI-only. This console exposes validation, preparation, generation, verification, backup, and run inspection workflows.</div>
"""
            self.send_html(page("NKP ZeroTouch Framework", body, "environments"))
            return
        if parsed.path == "/environment/view":
            query = parse_qs(parsed.query)
            try:
                config = resolve_env_config(query.get("config", [""])[0])
            except Exception as exc:
                self.send_html(page("Environment", f"<h2>Environment unavailable</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "environments"), status=400)
                return
            data = read_json_from_context(config)
            name = str(data.get("environmentName") or config.stem)
            env_type = str(data.get("environmentType") or "unknown")
            channel = env_channel(data)
            state = env_state(name)
            state_config = prepared_config_path(state)
            identity_issues = environment_identity_issues(config, data, state)
            lifecycle_label, lifecycle_status = environment_lifecycle(name, state)
            ready_passed, ready_total, ready_pct = environment_readiness(data, state)
            review_label, review_status = plan_review_status(name, state)
            _, drift_state, drift_issues = drift_status(config)
            _, _, gate_ok, gate_checks = production_gate(config)
            next_label, next_href, next_status, next_detail = environment_next_action(config)
            config_arg = quote(str(config))
            identity_status = "warn" if identity_issues else "ok"
            identity_detail = "; ".join(identity_issues) if identity_issues else "config and state identity match"
            state_config_display = str(state_config) if state_config else "not prepared"
            state_root_display = str(state["base"].relative_to(ROOT) if ROOT in state["base"].parents else state["base"])
            identity_rows = "".join(
                [
                    f"<tr><td>Config file</td><td><code>{html.escape(str(config.relative_to(ROOT)))}</code></td></tr>",
                    f"<tr><td>Environment name</td><td>{html.escape(name)}</td></tr>",
                    f"<tr><td>State directory</td><td><code>{html.escape(state_root_display)}</code></td></tr>",
                    f"<tr><td>Prepared from</td><td><code>{html.escape(state_config_display)}</code></td></tr>",
                    f"<tr><td>Identity status</td><td><span class='chip {identity_status}'>{html.escape(identity_detail)}</span></td></tr>",
                ]
            )
            actions = "".join(
                f'<form method="post" action="/action"><input type="hidden" name="action" value="{a}"><input type="hidden" name="config" value="{html.escape(str(config))}"><button>{a}</button></form>'
                for a in ACTION_ORDER
            )
            generated_root = state["base"] / "generated"
            artifact_candidates = [
                generated_root / "deploy-plan.md",
                generated_root / "deploy.sh",
                generated_root / "registry-plan.md",
                generated_root / "registry.sh",
                state["verification"],
                state["base"] / "state" / "kubeconfig",
            ]
            artifact_rows = "".join(
                f"<tr><td><code>{html.escape(path.name)}</code></td><td><span class='muted'>{html.escape(str(path.relative_to(ROOT)))}</span></td><td><a class='button-link' href='/artifacts/view?path={quote(str(path))}'>Open</a></td></tr>"
                for path in artifact_candidates if path.exists()
            )
            gate_rows = "".join(
                f"<tr><td>{html.escape(label)}</td><td><span class='chip {'ok' if passed else 'warn'}'>{'passed' if passed else 'blocked'}</span></td><td>{html.escape(detail)}</td></tr>"
                for label, passed, detail in gate_checks
            )
            recent_jobs = [job for job in list_jobs(100) if job.get("environment") == name][:8]
            job_rows = "".join(
                f"<tr><td><code>{html.escape(job.get('id', ''))}</code></td><td>{html.escape(job.get('action', ''))}</td><td><span class='chip {job_status_chip(job.get('status', 'queued'))}'>{html.escape(job.get('status', 'queued'))}</span></td><td><a class='button-link' href='/jobs/view?id={quote(job.get('id', ''))}'>Open</a></td></tr>"
                for job in recent_jobs
            )
            body = f"""
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Environment</div><div class="ops-value">{html.escape(name)}</div></div>
  <div class="ops-item"><div class="ops-label">Type / Channel</div><div class="ops-value">{html.escape(env_type)} / {html.escape(channel)}</div></div>
  <div class="ops-item"><div class="ops-label">Lifecycle</div><div class="ops-value"><span class="chip {lifecycle_status}">{html.escape(lifecycle_label)}</span></div></div>
  <div class="ops-item"><div class="ops-label">Next Action</div><div class="ops-value"><span class="chip {next_status}">{html.escape(next_label)}</span></div></div>
</section>
<section class="summary-grid">
  {metric_card("Readiness", ready_pct, f"{ready_passed}/{ready_total} checks complete", "/preflight")}
  {metric_card("Deploy Gate", 1 if gate_ok else 0, "clear" if gate_ok else "blocked", "/production-readiness")}
  {metric_card("Plan Review", 1 if review_status == "ok" else 0, review_label, "/plan-review")}
  {metric_card("Drift", 0 if drift_state == "ok" else 1, "; ".join(drift_issues)[:80], "/drift")}
</section>

<div class="section-head">
  <div>
    <h2>{html.escape(name)}</h2>
    <div class="section-copy">{html.escape(str(config.relative_to(ROOT)))} &middot; {html.escape(next_detail)}</div>
  </div>
  <a class="button-link" href="{html.escape(next_href)}">{html.escape(next_label)}</a>
</div>
<section class="detail-grid">
  <div class="settings-card">
    <h3>Deployment Profile</h3>
    <table><tbody>
      <tr><td>NKP version</td><td><code>{html.escape(str(data.get('nkpVersion', '')))}</code></td></tr>
      <tr><td>Cluster</td><td>{html.escape(str(data.get('clusterName', '')))}</td></tr>
      <tr><td>Prism</td><td>{html.escape(str(data.get('prismEndpoint', '')))}</td></tr>
      <tr><td>Registry</td><td>{html.escape(str(data.get('registryEndpoint', '')))}</td></tr>
    </tbody></table>
  </div>
  <div class="settings-card">
    <h3>Environment Identity</h3>
    <table><tbody>{identity_rows}</tbody></table>
  </div>
  <div class="settings-card">
    <h3>Safe Actions</h3>
    <div class="actions">{actions}</div>
    <p style="margin-top: 12px;">Safe actions run as tracked jobs and do not execute live apply operations.</p>
  </div>
  <div class="settings-card">
    <h3>Governance</h3>
    <p><span class="chip {'ok' if gate_ok else 'warn'}">{'Deploy gate clear' if gate_ok else 'Deploy gate blocked'}</span></p>
    <p style="margin-top: 10px;"><a href="/cli">CLI apply</a> &middot; <a href="/plan-review">Plan review</a> &middot; <a href="/change-records">Change records</a></p>
  </div>
</section>

<div class="section-head">
  <div>
    <h2>Production Gate</h2>
    <div class="section-copy">Release-channel checks that must be clear before apply work proceeds.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{gate_rows}</tbody></table></section>

<div class="section-head">
  <div>
    <h2>Artifacts</h2>
    <div class="section-copy">Generated plans, scripts, kubeconfig evidence, and verification summaries for this environment.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Artifact</th><th>Path</th><th>Open</th></tr></thead><tbody>{artifact_rows or '<tr><td colspan="3" class="muted">No generated artifacts found yet.</td></tr>'}</tbody></table></section>

<div class="section-head">
  <div>
    <h2>Recent Jobs</h2>
    <div class="section-copy">Latest tracked work for this deployment target.</div>
  </div>
  <span class="manage-actions"><a class="button-link" href="/environment/edit?config={config_arg}">Edit</a><a class="button-link button-danger" href="/environment/delete?config={config_arg}">Delete</a></span>
</div>
<section class="panel"><table><thead><tr><th>Job</th><th>Action</th><th>Status</th><th>Open</th></tr></thead><tbody>{job_rows or '<tr><td colspan="4" class="muted">No jobs have run for this environment yet.</td></tr>'}</tbody></table></section>
<a class="back-link" href="/">Back to environments</a>
"""
            self.send_html(page(f"{name} - NKP ZeroTouch Framework", body, "environments"))
            return
        if parsed.path == "/cli":
            config_options = []
            for config in env_configs():
                data = read_json_from_context(config)
                label = data.get("environmentName") or config.stem
                config_options.append(f'<option value="{html.escape(str(config))}">{html.escape(label)} - {html.escape(config.name)}</option>')
            default_config = str(env_configs()[0]) if env_configs() else ""
            runner_hint = "bash scripts/zt.sh" if shutil.which("bash") else "powershell scripts/zt.ps1"
            example_command = f"deploy --apply --config {default_config}"
            body = f"""
<div class="section-head">
  <div>
    <h2>CLI</h2>
    <div class="section-copy">Run approved ZeroTouch apply commands from inside a controlled console window.</div>
  </div>
</div>
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Command Mode</div><div class="ops-value">Controlled CLI</div></div>
  <div class="ops-item"><div class="ops-label">Apply Commands</div><div class="ops-value">registry / deploy / upgrade / destroy</div></div>
  <div class="ops-item"><div class="ops-label">Guardrails</div><div class="ops-value">Validated arguments only</div></div>
  <div class="ops-item"><div class="ops-label">Runner</div><div class="ops-value">{html.escape(runner_hint)}</div></div>
</section>
<section class="terminal-window">
  <form method="post" action="/cli/run">
    <div class="terminal-bar"><span class="terminal-dot"></span><span class="terminal-dot"></span><span class="terminal-dot"></span><span>ZeroTouch CLI</span></div>
    <div class="terminal-body">
      <div class="terminal-prompt">$ {html.escape(runner_hint)}</div>
      <textarea class="terminal-input" name="command" rows="6" spellcheck="false" aria-label="ZeroTouch apply command" autofocus>{html.escape(example_command)}</textarea>
      <div class="terminal-help">Allowed apply examples: <code>registry --apply --config &lt;file&gt;</code>, <code>deploy --apply --config &lt;file&gt;</code>, <code>upgrade --apply --config &lt;file&gt;</code>, <code>destroy --apply --confirm-destroy --config &lt;file&gt;</code>.</div>
      <div class="terminal-help">Fallback environment if <code>--config</code> is omitted:</div>
      <div class="field"><select name="config">{''.join(config_options)}</select></div>
      <div style="margin-top: 12px;"><button>Run apply command</button></div>
    </div>
  </form>
</section>
<div class="notice">This is a command window, but not an unrestricted shell. The server only executes approved ZeroTouch apply actions after parsing and validating the command.</div>
"""
            self.send_html(page("CLI - NKP ZeroTouch Framework", body, "cli"))
            return
        if parsed.path == "/environment/edit":
            query = parse_qs(parsed.query)
            try:
                config = resolve_env_config(query.get("config", [""])[0])
                data = load_env_yaml(config)
            except Exception as exc:
                self.send_html(page("Edit Environment", f"<h2>Edit unavailable</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "environments"), status=400)
                return
            body = f"""
<div class="section-head">
  <div>
    <h2>Edit Environment</h2>
    <div class="section-copy">Update core deployment settings for <code>{html.escape(config.name)}</code>.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/environment/edit/save">
    <input type="hidden" name="config" value="{html.escape(str(config))}">
    <table>
      <thead><tr><th>Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Environment name</td><td><div class="field"><input name="environment_name" value="{html.escape(str(nested_get(data, ['environment', 'name'])))}"></div></td></tr>
        <tr><td>Environment type</td><td><div class="field"><select name="environment_type">
          <option value="connected" {'selected' if nested_get(data, ['environment', 'type']) == 'connected' else ''}>connected</option>
          <option value="proxied" {'selected' if nested_get(data, ['environment', 'type']) == 'proxied' else ''}>proxied</option>
          <option value="air-gapped" {'selected' if nested_get(data, ['environment', 'type']) == 'air-gapped' else ''}>air-gapped</option>
        </select></div></td></tr>
        <tr><td>Release channel</td><td><div class="field"><select name="release_channel">
          <option value="dev" {'selected' if env_channel(read_json_from_context(config)) == 'dev' else ''}>dev</option>
          <option value="lab" {'selected' if env_channel(read_json_from_context(config)) == 'lab' else ''}>lab</option>
          <option value="pilot" {'selected' if env_channel(read_json_from_context(config)) == 'pilot' else ''}>pilot</option>
          <option value="production" {'selected' if env_channel(read_json_from_context(config)) == 'production' else ''}>production</option>
        </select></div></td></tr>
        <tr><td>Provider</td><td><div class="field"><select name="environment_provider">
          <option value="nutanix-ahv" {'selected' if nested_get(data, ['environment', 'provider'], 'nutanix-ahv') == 'nutanix-ahv' else ''}>nutanix-ahv</option>
          <option value="air-gapped-ahv" {'selected' if nested_get(data, ['environment', 'provider']) == 'air-gapped-ahv' else ''}>air-gapped-ahv</option>
          <option value="proxied-ahv" {'selected' if nested_get(data, ['environment', 'provider']) == 'proxied-ahv' else ''}>proxied-ahv</option>
          <option value="bare-metal" {'selected' if nested_get(data, ['environment', 'provider']) == 'bare-metal' else ''}>bare-metal</option>
        </select></div></td></tr>
        <tr><td>NKP version</td><td><div class="field"><input name="nkp_version" value="{html.escape(str(nested_get(data, ['nkp', 'version'])))}"></div></td></tr>
        <tr><td>Bundle type</td><td><div class="field"><select name="bundle_type">
          <option value="standard" {'selected' if nested_get(data, ['nkp', 'bundleType']) == 'standard' else ''}>standard</option>
          <option value="air-gapped" {'selected' if nested_get(data, ['nkp', 'bundleType']) == 'air-gapped' else ''}>air-gapped</option>
        </select></div></td></tr>
        <tr><td>Bundle path</td><td><div class="field"><input name="bundle_path" value="{html.escape(str(nested_get(data, ['nkp', 'bundlePath'])))}"></div></td></tr>
        <tr><td>Prism Central endpoint</td><td><div class="field"><input name="prism_endpoint" value="{html.escape(str(nested_get(data, ['nutanix', 'prismCentralEndpoint'])))}"></div></td></tr>
        <tr><td>Nutanix cluster</td><td><div class="field"><input name="nutanix_cluster" value="{html.escape(str(nested_get(data, ['nutanix', 'clusterName'])))}"></div></td></tr>
        <tr><td>Subnet</td><td><div class="field"><input name="subnet" value="{html.escape(str(nested_get(data, ['nutanix', 'subnetName'])))}"></div></td></tr>
        <tr><td>Image name</td><td><div class="field"><input name="image_name" value="{html.escape(str(nested_get(data, ['nutanix', 'imageName'])))}"></div></td></tr>
        <tr><td>Cluster name</td><td><div class="field"><input name="cluster_name" value="{html.escape(str(nested_get(data, ['cluster', 'name'])))}"></div></td></tr>
        <tr><td>Kubernetes version</td><td><div class="field"><input name="kubernetes_version" value="{html.escape(str(nested_get(data, ['cluster', 'kubernetesVersion'])))}"></div></td></tr>
        <tr><td>Control plane replicas</td><td><div class="field"><input name="control_plane_replicas" value="{html.escape(str(nested_get(data, ['cluster', 'controlPlaneReplicas'])))}"></div></td></tr>
        <tr><td>Worker replicas</td><td><div class="field"><input name="worker_replicas" value="{html.escape(str(nested_get(data, ['cluster', 'workerReplicas'])))}"></div></td></tr>
        <tr><td>Registry endpoint</td><td><div class="field"><input name="registry_endpoint" value="{html.escape(str(nested_get(data, ['registry', 'endpoint'])))}"></div></td></tr>
        <tr><td>Registry namespace</td><td><div class="field"><input name="registry_namespace" value="{html.escape(str(nested_get(data, ['registry', 'namespace'])))}"></div></td></tr>
        <tr><td></td><td><button>Save environment</button> <a class="button-link" href="/">Cancel</a></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">Advanced settings remain available by editing the YAML directly. This form updates common deployment fields only.</div>
"""
            self.send_html(page("Edit Environment - NKP ZeroTouch Framework", body, "environments"))
            return
        if parsed.path == "/environment/delete":
            query = parse_qs(parsed.query)
            try:
                config = resolve_env_config(query.get("config", [""])[0])
                data = load_env_yaml(config)
            except Exception as exc:
                self.send_html(page("Delete Environment", f"<h2>Delete unavailable</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "environments"), status=400)
                return
            env_name = str(nested_get(data, ["environment", "name"], config.stem))
            protected = config.name.endswith(".example.yaml")
            protected_notice = "<div class='notice'>Example environment templates are protected and cannot be deleted from the console.</div>" if protected else ""
            disabled = "disabled" if protected else ""
            body = f"""
<div class="section-head">
  <div>
    <h2>Delete Environment</h2>
    <div class="section-copy">Confirm deletion for <code>{html.escape(config.name)}</code>.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/environment/delete/confirm">
    <input type="hidden" name="config" value="{html.escape(str(config))}">
    <table>
      <thead><tr><th>Item</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Environment</td><td><code>{html.escape(env_name)}</code></td></tr>
        <tr><td>Config file</td><td><span class="muted">{html.escape(str(config.relative_to(ROOT)))}</span></td></tr>
        <tr><td>Confirmation</td><td><div class="field"><input name="confirm" placeholder="Type {html.escape(env_name)} to confirm"></div></td></tr>
        <tr><td>Delete local state</td><td><label><input type="checkbox" name="delete_state" value="yes"> also remove <code>.zt/environments/{html.escape(env_name)}</code></label></td></tr>
        <tr><td></td><td><button class="button-danger" {disabled}>Delete environment</button> <a class="button-link" href="/">Cancel</a></td></tr>
      </tbody>
    </table>
  </form>
</section>
{protected_notice}
"""
            self.send_html(page("Delete Environment - NKP ZeroTouch Framework", body, "environments"))
            return
        if parsed.path == "/runs":
            run_rows = "".join(
                f"<tr><td><code>{html.escape(p.parent.name)}</code></td><td>{html.escape(mtime_label(p))}</td><td><span class='muted'>{html.escape(str(p.relative_to(ROOT)))}</span></td></tr>"
                for p in recent_run_summaries()
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>Runs</h2>
    <div class="section-copy">Timestamped execution summaries captured by the framework.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Run ID</th><th>Updated</th><th>Summary</th></tr></thead>
    <tbody>{run_rows or '<tr><td colspan="3" class="muted">No run summaries yet.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Runs - NKP ZeroTouch Framework", body, "runs"))
            return
        if parsed.path == "/kubeconfig":
            rows = []
            for config in env_configs():
                data = read_json_from_context(config)
                name = data.get("environmentName") or config.stem
                state = env_state(name)
                kubeconfig = state["base"] / "state" / "kubeconfig"
                command = f".\\scripts\\zt.ps1 kubeconfig -Config .\\configs\\environments\\{config.name} -Kubeconfig <path>"
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='chip {'ok' if kubeconfig.exists() else 'warn'}'>{'Captured' if kubeconfig.exists() else 'Missing'}</span></td>"
                    f"<td><span class='muted'>{html.escape(str(kubeconfig.relative_to(ROOT) if ROOT in kubeconfig.parents else kubeconfig))}</span></td>"
                    f"<td><code>{html.escape(command)}</code></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Kubeconfig</h2>
    <div class="section-copy">Post-deploy handoff for cluster verification and ongoing NKP operations.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Status</th><th>State Path</th><th>Capture Command</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4" class="muted">No environments found.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">After deploy, capture kubeconfig into the environment state directory, then run verify to collect live cluster evidence.</div>
"""
            self.send_html(page("Kubeconfig - NKP ZeroTouch Framework", body, "kubeconfig"))
            return
        if parsed.path == "/backups":
            rows = []
            for item in backup_manifests():
                data = item["data"]
                path = item["path"]
                rows.append(
                    f"<tr><td><code>{html.escape(str(data.get('environment', path.parents[2].name)))}</code></td>"
                    f"<td>{html.escape(str(data.get('createdAt', 'n/a')))}</td>"
                    f"<td><span class='muted'>{html.escape(str(path.parent.relative_to(ROOT) if ROOT in path.parents else path.parent))}</span></td>"
                    f"<td><a class='button-link' href='/artifacts/view?path={quote(str(path))}'>Manifest</a></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Backups</h2>
    <div class="section-copy">Browse backup manifests created by the backup phase.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Created</th><th>Backup Path</th><th>Open</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4" class="muted">No backup manifests found. Run backup for an environment first.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">Restore remains a controlled manual workflow. Review the manifest, then restore selected state/generated/report folders deliberately.</div>
"""
            self.send_html(page("Backups - NKP ZeroTouch Framework", body, "backups"))
            return
        if parsed.path == "/restore":
            rows = []
            for item in backup_manifests():
                data = item["data"]
                path = item["path"]
                rows.append(
                    f"<tr><td><code>{html.escape(str(data.get('environment', path.parents[2].name)))}</code></td>"
                    f"<td>{html.escape(str(data.get('createdAt', 'n/a')))}</td>"
                    f"<td><span class='muted'>{html.escape(str(path.parent.relative_to(ROOT) if ROOT in path.parents else path.parent))}</span></td>"
                    f"<td><form method='post' action='/restore/plan'><input type='hidden' name='manifest' value='{html.escape(str(path))}'><button>Generate restore plan</button></form></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Restore Planning</h2>
    <div class="section-copy">Generate controlled restore plans from backup manifests. Actual restore remains manual.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Created</th><th>Backup Path</th><th>Plan</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4" class="muted">No backups available.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">Restore plans are written under <code>.zt/restore-plans/</code>. Review the plan before manually copying state back into place.</div>
"""
            self.send_html(page("Restore - NKP ZeroTouch Framework", body, "restore"))
            return
        if parsed.path == "/plan-review":
            rows = []
            for config in env_configs():
                data = read_json_from_context(config)
                name = data.get("environmentName") or config.stem
                state = env_state(name)
                review = load_plan_review(name)
                review_label, review_status = plan_review_status(name, state)
                hashes = plan_hashes(name)
                hash_note = "<br>".join(f"{html.escape(key)}: <code>{html.escape(value[:12] or 'n/a')}</code>" for key, value in hashes.items())
                plan = state["base"] / "generated" / "deploy-plan.md"
                plan_link = f'<a class="button-link" href="/artifacts/view?path={quote(str(plan))}">Open deploy plan</a>' if plan.exists() else '<span class="muted">Generate first</span>'
                has_plan = bool(state["generate"]) or plan.exists()
                controls = (
                    f'<form method="post" action="/plan-review/save"><input type="hidden" name="environment" value="{html.escape(name)}"><input type="hidden" name="decision" value="approved"><button>Approve</button></form>'
                    f'<form method="post" action="/plan-review/save"><input type="hidden" name="environment" value="{html.escape(name)}"><input type="hidden" name="decision" value="rejected"><button class="button-danger">Reject</button></form>'
                ) if has_plan else ""
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='chip {review_status}'>{html.escape(review_label)}</span></td>"
                    f"<td>{html.escape(review.get('reviewedBy', '') or 'n/a')}</td>"
                    f"<td>{html.escape(review.get('reviewedAt', '') or 'n/a')}</td>"
                    f"<td class='review-note'>{hash_note}</td>"
                    f"<td>{plan_link}</td><td><div class='actions'>{controls}</div></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Plan Review</h2>
    <div class="section-copy">Formal review gate for generated deployment plans before apply approval.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Status</th><th>Reviewer</th><th>Reviewed</th><th>Plan Hashes</th><th>Plan</th><th>Decision</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="7" class="muted">No environments found.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">Plan review records live under each environment state directory. Apply jobs still require approval through the Jobs workflow.</div>
"""
            self.send_html(page("Plan Review - NKP ZeroTouch Framework", body, "plan-review"))
            return
        if parsed.path == "/artifacts":
            artifact_rows = []
            for env_dir in sorted((ZT / "environments").glob("*")) if (ZT / "environments").exists() else []:
                if not env_dir.is_dir():
                    continue
                sample_links = []
                for artifact in sorted(list((env_dir / "generated").glob("*")) + list((env_dir / "reports").glob("*")) + list((env_dir / "logs").glob("*")))[:4]:
                    if artifact.is_file():
                        sample_links.append(f'<a class="button-link" href="/artifacts/view?path={quote(str(artifact))}">{html.escape(artifact.name)}</a>')
                links_html = "".join(sample_links) or '<span class="muted">No files yet</span>'
                artifact_rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(env_dir.name)}</div><div class='env-file'>{html.escape(str(env_dir.relative_to(ROOT)))}</div></td>"
                    f"<td>{file_count(env_dir / 'generated')}</td>"
                    f"<td>{file_count(env_dir / 'reports')}</td>"
                    f"<td>{file_count(env_dir / 'state')}</td>"
                    f"<td>{html.escape(mtime_label(env_dir))}</td>"
                    f"<td><div class='actions'>{links_html}</div></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Artifacts</h2>
    <div class="section-copy">Generated plans, reports, state files, and staged environment outputs.</div>
  </div>
  <a class="button-link" href="/artifacts/diff">Compare artifacts</a>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Generated</th><th>Reports</th><th>State</th><th>Updated</th><th>Open</th></tr></thead>
    <tbody>{''.join(artifact_rows) or '<tr><td colspan="6" class="muted">No environment artifacts found. Run prepare or generate first.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Artifacts - NKP ZeroTouch Framework", body, "artifacts"))
            return
        if parsed.path == "/artifacts/diff":
            query = parse_qs(parsed.query)
            files = artifact_files()
            options = []
            for artifact in files:
                label = str(artifact.relative_to(ROOT) if ROOT in artifact.parents else artifact)
                value = str(artifact)
                options.append(f'<option value="{html.escape(value)}">{html.escape(label)}</option>')
            diff_html = '<div class="notice">Select two artifacts to compare generated plans, state, reports, or environment YAML.</div>'
            left_label = right_label = ""
            if query.get("left") and query.get("right"):
                try:
                    left = resolve_artifact(query.get("left", [""])[0])
                    right = resolve_artifact(query.get("right", [""])[0])
                    left_text = left.read_text(encoding="utf-8", errors="replace").splitlines()
                    right_text = right.read_text(encoding="utf-8", errors="replace").splitlines()
                    left_label = str(left.relative_to(ROOT) if ROOT in left.parents else left)
                    right_label = str(right.relative_to(ROOT) if ROOT in right.parents else right)
                    diff = "\n".join(difflib.unified_diff(left_text, right_text, fromfile=left_label, tofile=right_label, lineterm=""))
                    diff_html = f"<pre>{html.escape(diff[:200000] or 'No differences found.')}</pre>"
                except Exception as exc:
                    diff_html = f"<div class='notice'>Diff unavailable: {html.escape(str(exc))}</div>"
            body = f"""
<div class="section-head">
  <div>
    <h2>Artifact Diff</h2>
    <div class="section-copy">Compare generated plans, reports, state files, and environment YAML before operational use.</div>
  </div>
</div>
<section class="panel">
  <form method="get" action="/artifacts/diff">
    <table>
      <thead><tr><th>Side</th><th>Artifact</th></tr></thead>
      <tbody>
        <tr><td>Left</td><td><div class="field"><select name="left">{''.join(options)}</select></div></td></tr>
        <tr><td>Right</td><td><div class="field"><select name="right">{''.join(options)}</select></div></td></tr>
        <tr><td></td><td><button>Compare</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
{diff_html}
<a class="back-link" href="/artifacts">Back to artifacts</a>
"""
            self.send_html(page("Artifact Diff - NKP ZeroTouch Framework", body, "artifacts"))
            return
        if parsed.path == "/artifacts/view":
            query = parse_qs(parsed.query)
            try:
                artifact = resolve_artifact(query.get("path", [""])[0])
                text = artifact.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.send_html(page("Artifact Error", f"<h2>Artifact unavailable</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/artifacts'>Back to artifacts</a>", "artifacts"), status=400)
                return
            body = f"""
<div class="section-head">
  <div>
    <h2>Artifact Viewer</h2>
    <div class="section-copy"><code>{html.escape(str(artifact.relative_to(ROOT) if ROOT in artifact.parents else artifact))}</code></div>
  </div>
</div>
<pre>{html.escape(text[:200000])}</pre>
<a class="back-link" href="/artifacts">Back to artifacts</a>
"""
            self.send_html(page("Artifact Viewer - NKP ZeroTouch Framework", body, "artifacts"))
            return
        if parsed.path == "/health":
            rows = "".join(f"<tr><td>{html.escape(name)}</td><td><span class='chip {status}'>{html.escape(status)}</span></td><td>{html.escape(note)}</td></tr>" for name, status, note in health_checks())
            ok_count = sum(1 for _, status, _ in health_checks() if status == "ok")
            warn_count = len(health_checks()) - ok_count
            body = f"""
<section class="summary-grid">
  {metric_card("Healthy", ok_count, "checks passed", "/health")}
  {metric_card("Warnings", warn_count, "items to review", "/health")}
  {metric_card("Jobs", len(list_jobs(200)), "stored executions", "/jobs")}
  {metric_card("Environments", len(env_configs()), "configured targets", "/")}
</section>
<div class="section-head">
  <div>
    <h2>Health Checks</h2>
    <div class="section-copy">Runner, storage, tools, bundle, Prism, and registry readiness from the console host perspective.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table></section>
"""
            self.send_html(page("Health - NKP ZeroTouch Framework", body, "health"))
            return
        if parsed.path == "/actions":
            action_rows = "".join(
                f"<tr><td><code>{html.escape(action)}</code></td><td>No infrastructure mutation</td><td><span class='chip ok'>Console enabled</span></td></tr>"
                for action in ACTION_ORDER
            )
            blocked_rows = "".join(
                f"<tr><td><code>{action}</code></td><td>Infrastructure-changing or destructive</td><td><span class='chip warn'>Approval gated</span></td></tr>"
                for action in ["registry --apply", "deploy --apply", "upgrade --apply", "destroy --apply --confirm-destroy"]
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>Safe Actions</h2>
    <div class="section-copy">Operational actions are split into safe console execution and approval-gated apply execution.</div>
  </div>
</div>
<section class="action-group">
  <div class="panel"><table><thead><tr><th>Safe Action</th><th>Scope</th><th>Status</th></tr></thead><tbody>{action_rows}</tbody></table></div>
  <div class="panel"><table><thead><tr><th>Apply Action</th><th>Scope</th><th>Status</th></tr></thead><tbody>{blocked_rows}</tbody></table></div>
</section>
<div class="notice">Use safe actions for validation, preparation, generation, verification, backup, and run capture. Use the CLI page for apply requests, then approve the generated job under Jobs.</div>
"""
            self.send_html(page("Safe Actions - NKP ZeroTouch Framework", body, "actions"))
            return
        if parsed.path == "/audit":
            audit_rows = []
            for event in recent_audit_events(50):
                audit_rows.append(
                    f"<tr><td><code>{html.escape(event.get('user', ''))}</code></td><td>{html.escape(event.get('event', ''))}</td><td>{html.escape(event.get('timestamp', ''))}</td><td>{html.escape(event.get('target', ''))}</td></tr>"
                )
            if (ZT / "environments").exists():
                for p in sorted((ZT / "environments").glob("*/state/*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:25]:
                    audit_rows.append(
                        f"<tr><td><code>{html.escape(p.parent.parent.name)}</code></td><td>{html.escape(p.name)}</td><td>{html.escape(mtime_label(p))}</td><td><span class='muted'>{html.escape(str(p.relative_to(ROOT)))}</span></td></tr>"
                    )
            for p in recent_run_summaries(10):
                audit_rows.append(
                    f"<tr><td><code>run</code></td><td>{html.escape(p.parent.name)}</td><td>{html.escape(mtime_label(p))}</td><td><span class='muted'>{html.escape(str(p.relative_to(ROOT)))}</span></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Audit Trail</h2>
    <div class="section-copy">Recent local state and run summary updates from the .zt workspace.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Scope</th><th>Event</th><th>Updated</th><th>Path</th></tr></thead>
    <tbody>{''.join(audit_rows) or '<tr><td colspan="4" class="muted">No audit events found yet.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Audit Trail - NKP ZeroTouch Framework", body, "audit"))
            return
        if parsed.path == "/sources":
            settings = load_setting("sources", default_sources())
            rows = []
            for label, key in [("Standard bundle", "standard_bundle"), ("Air-gapped bundle", "airgapped_bundle"), ("NKP source path", "source_path")]:
                status, note = path_status(settings.get(key, ""))
                rows.append(f"<tr><td>{html.escape(label)}</td><td><code>{html.escape(settings.get(key, ''))}</code></td><td><span class='chip {status}'>{html.escape(note)}</span></td></tr>")
            body = f"""
<div class="section-head">
  <div>
    <h2>Sources</h2>
    <div class="section-copy">Register NKP bundles, source code locations, Git refs, and checksum metadata used by deployment workflows.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/sources/save">
    <table>
      <thead><tr><th>Source</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>NKP version</td><td><div class="field"><input name="version" value="{html.escape(settings.get('version', ''))}"></div></td></tr>
        <tr><td>Standard bundle path</td><td><div class="field"><input name="standard_bundle" value="{html.escape(settings.get('standard_bundle', ''))}"></div></td></tr>
        <tr><td>Air-gapped bundle path</td><td><div class="field"><input name="airgapped_bundle" value="{html.escape(settings.get('airgapped_bundle', ''))}"></div></td></tr>
        <tr><td>NKP source path</td><td><div class="field"><input name="source_path" value="{html.escape(settings.get('source_path', ''))}"></div></td></tr>
        <tr><td>Git URL</td><td><div class="field"><input name="git_url" value="{html.escape(settings.get('git_url', ''))}"></div></td></tr>
        <tr><td>Git ref / tag</td><td><div class="field"><input name="git_ref" value="{html.escape(settings.get('git_ref', ''))}"></div></td></tr>
        <tr><td>SHA256 checksum</td><td><div class="field"><input name="checksum" value="{html.escape(settings.get('checksum', ''))}"></div></td></tr>
        <tr><td></td><td><button>Save sources</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="section-head"><div><h2>Discovery</h2><div class="section-copy">Path availability from the console runner perspective.</div></div></div>
<section class="panel"><table><thead><tr><th>Item</th><th>Path</th><th>Status</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<div class="notice">Sources are saved under <code>.zt/settings/sources.json</code>. Environment YAML can still override bundle paths per target.</div>
"""
            self.send_html(page("Sources - NKP ZeroTouch Framework", body, "sources"))
            return
        if parsed.path == "/inventory":
            settings = load_setting("inventory", default_inventory())
            body = f"""
<div class="section-head">
  <div>
    <h2>Infrastructure Inventory</h2>
    <div class="section-copy">Capture physical node, BMC, image, and boot-mode inputs needed before bare-metal or AHV deployment gates.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/inventory/save">
    <table>
      <thead><tr><th>Inventory Field</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Deployment mode</td><td><div class="field"><select name="mode"><option value="nutanix-ahv" {'selected' if settings.get('mode') == 'nutanix-ahv' else ''}>nutanix-ahv</option><option value="bare-metal" {'selected' if settings.get('mode') == 'bare-metal' else ''}>bare-metal</option></select></div></td></tr>
        <tr><td>Node inventory</td><td><div class="field"><textarea name="nodes" placeholder="node01, role=control-plane, ip=10.10.10.11, bmc=10.10.1.11">{html.escape(settings.get('nodes', ''))}</textarea></div></td></tr>
        <tr><td>BMC network</td><td><div class="field"><input name="bmc_network" value="{html.escape(settings.get('bmc_network', ''))}"></div></td></tr>
        <tr><td>BMC provider</td><td><div class="field"><select name="bmc_provider"><option value="ipmi" {'selected' if settings.get('bmc_provider') == 'ipmi' else ''}>ipmi</option><option value="idrac" {'selected' if settings.get('bmc_provider') == 'idrac' else ''}>idrac</option><option value="ilo" {'selected' if settings.get('bmc_provider') == 'ilo' else ''}>ilo</option><option value="redfish" {'selected' if settings.get('bmc_provider') == 'redfish' else ''}>redfish</option></select></div></td></tr>
        <tr><td>Boot mode</td><td><div class="field"><select name="boot_mode"><option value="uefi" {'selected' if settings.get('boot_mode') == 'uefi' else ''}>uefi</option><option value="bios" {'selected' if settings.get('boot_mode') == 'bios' else ''}>bios</option></select></div></td></tr>
        <tr><td>OS / node image</td><td><div class="field"><input name="os_image" value="{html.escape(settings.get('os_image', ''))}"></div></td></tr>
        <tr><td>Notes</td><td><div class="field"><textarea name="notes">{html.escape(settings.get('notes', ''))}</textarea></div></td></tr>
        <tr><td></td><td><button>Save inventory</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">For AHV deployments this inventory documents dependencies. For future bare-metal support it becomes the node admission and power-control source.</div>
"""
            self.send_html(page("Inventory - NKP ZeroTouch Framework", body, "inventory"))
            return
        if parsed.path == "/network":
            settings = load_setting("network", default_network())
            body = f"""
<div class="section-head">
  <div>
    <h2>Network Plan</h2>
    <div class="section-copy">Define VIPs, CIDRs, DNS, NTP, proxy, and address allocation assumptions before generation and apply phases.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/network/save">
    <table>
      <thead><tr><th>Network Field</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Management CIDR</td><td><div class="field"><input name="management_cidr" value="{html.escape(settings.get('management_cidr', ''))}"></div></td></tr>
        <tr><td>Workload CIDR</td><td><div class="field"><input name="workload_cidr" value="{html.escape(settings.get('workload_cidr', ''))}"></div></td></tr>
        <tr><td>API endpoint VIP</td><td><div class="field"><input name="api_vip" value="{html.escape(settings.get('api_vip', ''))}"></div></td></tr>
        <tr><td>Ingress / load balancer range</td><td><div class="field"><input name="ingress_range" value="{html.escape(settings.get('ingress_range', ''))}"></div></td></tr>
        <tr><td>DNS servers</td><td><div class="field"><input name="dns_servers" value="{html.escape(settings.get('dns_servers', ''))}"></div></td></tr>
        <tr><td>NTP servers</td><td><div class="field"><input name="ntp_servers" value="{html.escape(settings.get('ntp_servers', ''))}"></div></td></tr>
        <tr><td>Proxy</td><td><div class="field"><input name="proxy" value="{html.escape(settings.get('proxy', ''))}"></div></td></tr>
        <tr><td>IP assignment</td><td><div class="field"><select name="ip_mode"><option value="static" {'selected' if settings.get('ip_mode') == 'static' else ''}>static</option><option value="dhcp" {'selected' if settings.get('ip_mode') == 'dhcp' else ''}>dhcp</option><option value="pxe" {'selected' if settings.get('ip_mode') == 'pxe' else ''}>pxe</option></select></div></td></tr>
        <tr><td></td><td><button>Save network plan</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
"""
            self.send_html(page("Network - NKP ZeroTouch Framework", body, "network"))
            return
        if parsed.path == "/preflight":
            checks = preflight_checks()
            ok_count = sum(1 for item in checks if item["status"] == "ok")
            warn_count = len(checks) - ok_count
            rows = "".join(f"<tr><td>{html.escape(item['area'])}</td><td>{html.escape(item['check'])}</td><td><span class='chip {item['status']}'>{html.escape(item['status'])}</span></td><td>{html.escape(item['note'])}</td></tr>" for item in checks)
            body = f"""
<section class="summary-grid">
  {metric_card("Passed", ok_count, "readiness checks", "/preflight")}
  {metric_card("Warnings", warn_count, "items requiring attention", "/preflight")}
  {metric_card("Environments", len(env_configs()), "deployment targets", "/")}
  {metric_card("Sources", 1, "source intake configured", "/sources")}
</section>
<div class="section-head">
  <div>
    <h2>Preflight Matrix</h2>
    <div class="section-copy">Operational readiness checks for source, runner, registry, provider, network, inventory, and secrets.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Area</th><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table></section>
<div class="notice">This matrix is a console-level readiness gate. Environment-specific validation still runs through the <code>validate</code> phase.</div>
"""
            self.send_html(page("Preflight - NKP ZeroTouch Framework", body, "preflight"))
            return
        if parsed.path == "/drift":
            rows = []
            warn_count = 0
            for config in env_configs():
                env_name, status, issues = drift_status(config)
                warn_count += 1 if status == "warn" else 0
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(env_name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='chip {status}'>{html.escape(status)}</span></td>"
                    f"<td>{html.escape('; '.join(issues))}</td></tr>"
                )
            body = f"""
<section class="summary-grid">
  {metric_card("Drift Warnings", warn_count, "environments to review", "/drift")}
  {metric_card("Environments", len(env_configs()), "profiles scanned", "/")}
  {metric_card("Plan Reviews", sum(1 for config in env_configs() if load_plan_review(read_json_from_context(config).get('environmentName') or config.stem).get('status') == 'approved'), "approved plans", "/plan-review")}
  {metric_card("Backups", len(backup_manifests()), "backup manifests", "/backups")}
</section>
<div class="section-head">
  <div>
    <h2>Drift Detection</h2>
    <div class="section-copy">Detect changed plans, changed environment YAML, missing generation, and missing verification evidence.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Environment</th><th>Status</th><th>Signals</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
"""
            self.send_html(page("Drift - NKP ZeroTouch Framework", body, "drift"))
            return
        if parsed.path == "/production-readiness":
            rows = []
            ready_count = 0
            for config in env_configs():
                env_name, channel, ok, checks = production_gate(config)
                ready_count += 1 if ok else 0
                details = "; ".join(f"{name}: {'pass' if passed else detail}" for name, passed, detail in checks)
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(env_name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='badge connected'>{html.escape(channel)}</span></td>"
                    f"<td><span class='chip {'ok' if ok else 'warn'}'>{'ready' if ok else 'blocked'}</span></td>"
                    f"<td>{html.escape(details)}</td></tr>"
                )
            body = f"""
<section class="summary-grid">
  {metric_card("Ready", ready_count, "environments passing gate", "/production-readiness")}
  {metric_card("Blocked", len(env_configs()) - ready_count, "environments needing work", "/production-readiness")}
  {metric_card("Backups", len(backup_manifests()), "backup manifests", "/backups")}
  {metric_card("Channels", len(release_channel_map()), "configured channels", "/release-channels")}
</section>
<div class="section-head">
  <div>
    <h2>Production Readiness Gate</h2>
    <div class="section-copy">Checks plan review, backup evidence, drift, channel policy, and verification evidence.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Environment</th><th>Channel</th><th>Status</th><th>Signals</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
"""
            self.send_html(page("Production Readiness - NKP ZeroTouch Framework", body, "production-readiness"))
            return
        if parsed.path == "/pipeline":
            steps = [("Source", "sources", "ok"), ("Validate", "actions", "warn"), ("Prepare", "actions", "warn"), ("Generate", "actions", "warn"), ("Review", "plan-review", "warn"), ("Registry", "cli", "warn"), ("Deploy", "cli", "warn"), ("Kubeconfig", "kubeconfig", "warn"), ("Verify", "actions", "warn"), ("Operate", "runs", "warn")]
            cards = "".join(f"<a class='pipeline-step' href='{VIEW_PATHS[href]}'><strong>{html.escape(label)}</strong><span class='chip {status}'>{'configured' if status == 'ok' else 'pending'}</span></a>" for label, href, status in steps)
            body = f"""
<div class="section-head">
  <div>
    <h2>Deployment Pipeline</h2>
    <div class="section-copy">ZeroTouch flow from source intake through deployment, verification, and day-2 operations.</div>
  </div>
</div>
<section class="pipeline">{cards}</section>
<div class="notice">Apply stages remain gated through the controlled CLI window. Safe stages can be run from Environments or Safe Actions.</div>
"""
            self.send_html(page("Pipeline - NKP ZeroTouch Framework", body, "pipeline"))
            return
        if parsed.path == "/jobs":
            pending = sum(1 for job in list_jobs(200) if job.get("status") == "pending_approval")
            running = sum(1 for job in list_jobs(200) if job.get("status") == "running")
            failed = sum(1 for job in list_jobs(200) if job.get("status") == "failed")
            job_rows = ""
            for job in list_jobs(30):
                job_rows += (
                    f"<tr><td><code>{html.escape(job['id'])}</code><div class='env-file'>{html.escape(job.get('environment', ''))}</div></td>"
                    f"<td>{html.escape(job.get('action', ''))}</td>"
                    f"<td><span class='chip {job_status_chip(job.get('status', 'queued'))}'>{html.escape(job.get('status', 'queued'))}</span></td>"
                    f"<td>{html.escape(job.get('requestedBy', ''))}</td>"
                    f"<td>{html.escape(job.get('createdAt', ''))}</td>"
                    f"<td><div class='actions'>{job_controls(job, self.current_user(), compact=True)}</div></td></tr>"
                )
            body = f"""
<section class="summary-grid">
  {metric_card("Pending Approval", pending, "apply jobs waiting", "/jobs")}
  {metric_card("Running", running, "active jobs", "/jobs")}
  {metric_card("Failed", failed, "jobs requiring review", "/jobs")}
  {metric_card("Total Jobs", len(list_jobs(200)), "stored executions", "/jobs")}
</section>
<div class="section-head">
  <div>
    <h2>Jobs</h2>
    <div class="section-copy">Execution queue with approval-gated apply requests and captured runner logs.</div>
  </div>
</div>
<section class="panel"><table><thead><tr><th>Job</th><th>Action</th><th>Status</th><th>Requested By</th><th>Created</th><th>Controls</th></tr></thead><tbody>{job_rows or '<tr><td colspan="6" class="muted">No jobs have run yet.</td></tr>'}</tbody></table></section>
<div class="notice">Safe jobs start immediately. Apply jobs are created as approval requests and must be approved by a role with approval permission.</div>
"""
            self.send_html(page("Jobs - NKP ZeroTouch Framework", body, "jobs"))
            return
        if parsed.path == "/locks":
            lock_rows = []
            for config in env_configs():
                env_name = environment_for_config(config)
                lock = active_lock(env_name)
                clear = f"<form method='post' action='/locks/clear'><input type='hidden' name='environment' value='{html.escape(env_name)}'><button class='button-danger'>Clear stale lock</button></form>" if not lock and lock_path(env_name).exists() else ""
                lock_rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(env_name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='chip {'warn' if lock else 'ok'}'>{'locked' if lock else 'available'}</span></td>"
                    f"<td>{html.escape(lock.get('jobId', 'n/a') if lock else 'n/a')}</td>"
                    f"<td>{html.escape(lock.get('action', 'n/a') if lock else 'n/a')}</td>"
                    f"<td>{html.escape(lock.get('lockedBy', 'n/a') if lock else 'n/a')}</td>"
                    f"<td>{clear}</td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Environment Locks</h2>
    <div class="section-copy">Prevent overlapping prepare, generate, and apply operations for the same environment.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Status</th><th>Job</th><th>Action</th><th>Locked By</th><th>Cleanup</th></tr></thead>
    <tbody>{''.join(lock_rows) or '<tr><td colspan="6" class="muted">No environments found.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Locks - NKP ZeroTouch Framework", body, "locks"))
            return
        if parsed.path == "/change-records":
            rows = []
            for record in list_change_records(100):
                rows.append(
                    f"<tr><td><code>{html.escape(record.get('id', ''))}</code><div class='env-file'>job {html.escape(record.get('jobId', ''))}</div></td>"
                    f"<td>{html.escape(record.get('environment', ''))}</td>"
                    f"<td>{html.escape(record.get('action', ''))}</td>"
                    f"<td><span class='chip {'ok' if record.get('status') == 'closed' else 'warn'}'>{html.escape(record.get('status', 'open'))}</span></td>"
                    f"<td>{html.escape(record.get('requestedBy', ''))}</td>"
                    f"<td>{html.escape(record.get('createdAt', ''))}</td>"
                    f"<td><a class='button-link' href='/change-records/view?id={quote(record.get('id', ''))}'>Open</a></td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Change Records</h2>
    <div class="section-copy">Deployment apply requests with plan hashes, requester, job ID, and rollback notes.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Change</th><th>Environment</th><th>Action</th><th>Status</th><th>Requested By</th><th>Created</th><th>Open</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="7" class="muted">No change records yet. Request an apply action from the CLI page.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Change Records - NKP ZeroTouch Framework", body, "change-records"))
            return
        if parsed.path == "/change-records/view":
            query = parse_qs(parsed.query)
            record_id = query.get("id", [""])[0]
            record = read_json(change_record_path(record_id))
            if not record:
                self.send_html(page("Change Record Not Found", "<h2>Change record not found</h2><a class='back-link' href='/change-records'>Back to change records</a>", "change-records"), status=404)
                return
            hashes = record.get("planHashes", {})
            hash_rows = "".join(f"<tr><td>{html.escape(key)}</td><td><code>{html.escape(value or 'n/a')}</code></td></tr>" for key, value in hashes.items())
            job_id = record.get("jobId", "")
            body = f"""
<div class="section-head">
  <div>
    <h2>Change Record</h2>
    <div class="section-copy"><code>{html.escape(record.get('id', ''))}</code></div>
  </div>
  <a class="button-link" href="/jobs/view?id={quote(job_id)}">Open job</a>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Field</th><th>Value</th></tr></thead>
    <tbody>
      <tr><td>Environment</td><td>{html.escape(record.get('environment', ''))}</td></tr>
      <tr><td>Action</td><td>{html.escape(record.get('action', ''))}</td></tr>
      <tr><td>Status</td><td>{html.escape(record.get('status', ''))}</td></tr>
      <tr><td>Requested by</td><td>{html.escape(record.get('requestedBy', ''))} ({html.escape(record.get('requestedRole', ''))})</td></tr>
      <tr><td>Created</td><td>{html.escape(record.get('createdAt', ''))}</td></tr>
      <tr><td>Updated</td><td>{html.escape(record.get('updatedAt', 'n/a'))}</td></tr>
      <tr><td>Rollback notes</td><td>{html.escape(record.get('rollbackNotes', ''))}</td></tr>
    </tbody>
  </table>
</section>
<div class="section-head"><div><h2>Plan Hashes</h2><div class="section-copy">Hashes captured when the apply request was created.</div></div></div>
<section class="panel"><table><thead><tr><th>Artifact</th><th>SHA256</th></tr></thead><tbody>{hash_rows}</tbody></table></section>
<a class="back-link" href="/change-records">Back to change records</a>
"""
            self.send_html(page("Change Record - NKP ZeroTouch Framework", body, "change-records"))
            return
        if parsed.path == "/jobs/view":
            query = parse_qs(parsed.query)
            job = read_job(query.get("id", [""])[0])
            if not job:
                self.send_html(page("Job Not Found", "<h2>Job not found</h2><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=404)
                return
            log_text = job_log_path(job["id"]).read_text(encoding="utf-8") if job_log_path(job["id"]).exists() else ""
            refresh = "<script>setTimeout(() => location.reload(), 5000);</script>" if job.get("status") in {"queued", "running", "pending_approval", "cancel_requested"} else ""
            body = f"""
<div class="section-head">
  <div>
    <h2>Job Detail</h2>
    <div class="section-copy">Live runner output and approval metadata for <code>{html.escape(job['id'])}</code>.</div>
  </div>
  <div class="actions">{job_controls(job, self.current_user(), include_open=False)}</div>
</div>
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Action</div><div class="ops-value">{html.escape(job.get('action', ''))}</div></div>
  <div class="ops-item"><div class="ops-label">Status</div><div class="ops-value"><span class="chip {job_status_chip(job.get('status', 'queued'))}">{html.escape(job.get('status', 'queued'))}</span></div></div>
  <div class="ops-item"><div class="ops-label">Requested By</div><div class="ops-value">{html.escape(job.get('requestedBy', ''))}</div></div>
  <div class="ops-item"><div class="ops-label">Approvals</div><div class="ops-value">{job_approval_count(job)} / {html.escape(str(job.get('requiredApprovals', 0)))}</div></div>
</section>
<section class="panel">
  <table>
    <thead><tr><th>Validated Command</th></tr></thead>
    <tbody><tr><td><pre>{html.escape(job.get('commandLabel', ''))}</pre></td></tr></tbody>
  </table>
</section>
<div class="section-head"><div><h2>Live Log</h2><div class="section-copy">This page auto-refreshes while the job is active or waiting for approval.</div></div></div>
<pre>{html.escape(log_text or '[no output yet]')}</pre>
<a class="back-link" href="/jobs">Back to jobs</a>
{refresh}
"""
            self.send_html(page("Job Detail - NKP ZeroTouch Framework", body, "jobs"))
            return
        if parsed.path == "/approval-policy":
            policy = load_setting("approval-policy", default_approval_policy())
            body = f"""
<div class="section-head">
  <div>
    <h2>Approval Policy</h2>
    <div class="section-copy">Configure how many approvals are required before live apply jobs can run.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/approval-policy/save">
    <table>
      <thead><tr><th>Policy</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Deploy approvals</td><td><div class="field"><input name="deploy_approvals" value="{html.escape(policy.get('deploy_approvals', '1'))}"></div></td></tr>
        <tr><td>Registry approvals</td><td><div class="field"><input name="registry_approvals" value="{html.escape(policy.get('registry_approvals', '1'))}"></div></td></tr>
        <tr><td>Upgrade approvals</td><td><div class="field"><input name="upgrade_approvals" value="{html.escape(policy.get('upgrade_approvals', '1'))}"></div></td></tr>
        <tr><td>Destroy approvals</td><td><div class="field"><input name="destroy_approvals" value="{html.escape(policy.get('destroy_approvals', '2'))}"></div></td></tr>
        <tr><td>Prevent self approval</td><td><div class="field"><select name="prevent_self_approval"><option value="true" {'selected' if policy.get('prevent_self_approval') == 'true' else ''}>true</option><option value="false" {'selected' if policy.get('prevent_self_approval') == 'false' else ''}>false</option></select></div></td></tr>
        <tr><td>Production requires Admin</td><td><div class="field"><select name="production_requires_admin"><option value="true" {'selected' if policy.get('production_requires_admin') == 'true' else ''}>true</option><option value="false" {'selected' if policy.get('production_requires_admin') == 'false' else ''}>false</option></select></div></td></tr>
        <tr><td></td><td><button>Save approval policy</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">Apply jobs remain pending until the configured approval threshold is met. Destroy defaults to two approvals.</div>
"""
            self.send_html(page("Approval Policy - NKP ZeroTouch Framework", body, "approval-policy"))
            return
        if parsed.path == "/release-channels":
            channels = load_setting("release-channels", default_release_channels())
            channel_rows = ""
            for item in channels.get("channels", "").split(","):
                name, _, approvals = item.strip().partition(":")
                if not name:
                    continue
                channel_rows += f"<tr><td><code>{html.escape(name.strip())}</code></td><td>{html.escape(approvals.strip() or '0')}</td><td><span class='chip {'ok' if name.strip() != 'production' else 'warn'}'>{'standard' if name.strip() != 'production' else 'elevated'}</span></td></tr>"
            body = f"""
<div class="section-head">
  <div>
    <h2>Release Channels</h2>
    <div class="section-copy">Promotion lanes for development, lab, pilot, and production deployment governance.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/release-channels/save">
    <table>
      <thead><tr><th>Channel Policy</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Default channel</td><td><div class="field"><input name="default_channel" value="{html.escape(channels.get('default_channel', 'lab'))}"></div></td></tr>
        <tr><td>Channels</td><td><div class="field"><input name="channels" value="{html.escape(channels.get('channels', 'dev:0, lab:1, pilot:1, production:2'))}"></div></td></tr>
        <tr><td>Production requires plan review</td><td><div class="field"><select name="production_requires_plan_review"><option value="true" {'selected' if channels.get('production_requires_plan_review') == 'true' else ''}>true</option><option value="false" {'selected' if channels.get('production_requires_plan_review') == 'false' else ''}>false</option></select></div></td></tr>
        <tr><td>Production requires backup</td><td><div class="field"><select name="production_requires_backup"><option value="true" {'selected' if channels.get('production_requires_backup') == 'true' else ''}>true</option><option value="false" {'selected' if channels.get('production_requires_backup') == 'false' else ''}>false</option></select></div></td></tr>
        <tr><td></td><td><button>Save release channels</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="section-head"><div><h2>Channel Matrix</h2><div class="section-copy">Approval expectations by channel.</div></div></div>
<section class="panel"><table><thead><tr><th>Channel</th><th>Minimum Approvals</th><th>Governance</th></tr></thead><tbody>{channel_rows}</tbody></table></section>
"""
            self.send_html(page("Release Channels - NKP ZeroTouch Framework", body, "release-channels"))
            return
        if parsed.path == "/settings/connections":
            settings = read_json(SETTINGS / "connections.json") or {}
            body = f"""
<div class="section-head">
  <div>
    <h2>Connections</h2>
    <div class="section-copy">Connection profiles required for Prism Central, registries, proxies, and bundle sources.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/connections/save">
    <table>
      <thead><tr><th>Connection</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Prism Central endpoint</td><td><div class="field"><input name="prism" value="{html.escape(settings.get('prism', 'https://prism-central.example.com:9440'))}"></div></td></tr>
        <tr><td>Registry endpoint</td><td><div class="field"><input name="registry" value="{html.escape(settings.get('registry', 'registry.example.com'))}"></div></td></tr>
        <tr><td>HTTP proxy</td><td><div class="field"><input name="http_proxy" value="{html.escape(settings.get('http_proxy', ''))}"></div></td></tr>
        <tr><td>Standard bundle path</td><td><div class="field"><input name="standard_bundle" value="{html.escape(settings.get('standard_bundle', '/mnt/c/Share/nkp-bundle_v2.17.1_linux_amd64/nkp-v2.17.1'))}"></div></td></tr>
        <tr><td>Air-gapped bundle path</td><td><div class="field"><input name="airgapped_bundle" value="{html.escape(settings.get('airgapped_bundle', '/mnt/c/Share/nkp-air-gapped-bundle_v2.17.1_linux_amd64/nkp-v2.17.1'))}"></div></td></tr>
        <tr><td></td><td><button>Save connections</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">Connection profiles are saved locally under <code>.zt/settings/connections.json</code>. Environment YAML remains the deployment source of truth.</div>
"""
            self.send_html(page("Connections - NKP ZeroTouch Framework", body, "connections"))
            return
        if parsed.path == "/settings/new-environment":
            providers = load_setting("providers", default_providers())
            default_provider = providers.get("default_provider", "nutanix-ahv")
            body = f"""
<div class="section-head">
  <div>
    <h2>New Environment</h2>
    <div class="section-copy">Create a deployment profile from the connected, proxied, or air-gapped templates and assign its provider intent.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/new-environment/create">
    <table>
      <thead><tr><th>Field</th><th>Input</th></tr></thead>
      <tbody>
        <tr><td>Environment name</td><td><div class="field"><input name="name" value="lab-new" aria-label="Environment name"></div></td></tr>
        <tr><td>Environment type</td><td><div class="field"><select name="type" aria-label="Environment type"><option>connected</option><option>proxied</option><option>air-gapped</option></select></div></td></tr>
        <tr><td>Provider</td><td><div class="field"><select name="provider" aria-label="Provider"><option value="nutanix-ahv" {'selected' if default_provider == 'nutanix-ahv' else ''}>nutanix-ahv</option><option value="air-gapped-ahv" {'selected' if default_provider == 'air-gapped-ahv' else ''}>air-gapped-ahv</option><option value="proxied-ahv" {'selected' if default_provider == 'proxied-ahv' else ''}>proxied-ahv</option><option value="bare-metal" {'selected' if default_provider == 'bare-metal' else ''}>bare-metal</option></select></div></td></tr>
        <tr><td></td><td><button>Create environment</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">This creates a config under <code>configs/environments/</code> using the same framework helper as <code>scripts/new-env.*</code>.</div>
"""
            self.send_html(page("New Environment - NKP ZeroTouch Framework", body, "new-environment"))
            return
        if parsed.path == "/settings/providers":
            settings = load_setting("providers", default_providers())
            provider_rows = "".join(
                f"<tr><td><code>{html.escape(provider['name'])}</code></td><td><span class='muted'>{html.escape(str(provider['readme'].relative_to(ROOT)))}</span></td><td><a class='button-link' href='/artifacts/view?path={quote(str(provider['readme']))}'>Open</a></td></tr>"
                for provider in provider_catalog()
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>Providers</h2>
    <div class="section-copy">Select deployment provider intent and runner placement for NKP operations.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/providers/save">
    <table>
      <thead><tr><th>Provider Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Default provider</td><td><div class="field"><select name="default_provider"><option value="nutanix-ahv" {'selected' if settings.get('default_provider') == 'nutanix-ahv' else ''}>nutanix-ahv</option><option value="air-gapped-ahv" {'selected' if settings.get('default_provider') == 'air-gapped-ahv' else ''}>air-gapped-ahv</option><option value="proxied-ahv" {'selected' if settings.get('default_provider') == 'proxied-ahv' else ''}>proxied-ahv</option><option value="bare-metal" {'selected' if settings.get('default_provider') == 'bare-metal' else ''}>bare-metal</option></select></div></td></tr>
        <tr><td>Enabled providers</td><td><div class="field"><input name="enabled_providers" value="{html.escape(settings.get('enabled_providers', ''))}"></div></td></tr>
        <tr><td>Runner type</td><td><div class="field"><select name="runner_type"><option value="container" {'selected' if settings.get('runner_type') == 'container' else ''}>container</option><option value="wsl" {'selected' if settings.get('runner_type') == 'wsl' else ''}>wsl</option><option value="linux-vm" {'selected' if settings.get('runner_type') == 'linux-vm' else ''}>linux-vm</option><option value="appliance" {'selected' if settings.get('runner_type') == 'appliance' else ''}>appliance</option></select></div></td></tr>
        <tr><td>Runner notes</td><td><div class="field"><textarea name="runner_notes">{html.escape(settings.get('runner_notes', ''))}</textarea></div></td></tr>
        <tr><td></td><td><button>Save providers</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="section-head"><div><h2>Provider Catalog</h2><div class="section-copy">Extension contracts available in the repository.</div></div></div>
<section class="panel">
  <table>
    <thead><tr><th>Provider</th><th>Contract</th><th>Open</th></tr></thead>
    <tbody>{provider_rows or '<tr><td colspan="3" class="muted">No provider contracts found.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">The current live deployment generator targets Nutanix AHV. Bare-metal is modeled as provider intent until a supported NKP bare-metal command path is wired into generation.</div>
"""
            self.send_html(page("Providers - NKP ZeroTouch Framework", body, "providers"))
            return
        if parsed.path == "/settings/secrets":
            settings = load_setting("secrets", default_secrets())
            secret_rows = "".join(
                f"<tr><td><code>{html.escape(name)}</code></td><td><span class='chip {'ok' if os.environ.get(name) else 'warn'}'>{'present' if os.environ.get(name) else 'missing'}</span></td></tr>"
                for name in ["NUTANIX_PC_USERNAME", "NUTANIX_PC_PASSWORD", "ZT_REGISTRY_USERNAME", "ZT_REGISTRY_PASSWORD", "VAULT_TOKEN"]
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>Secrets</h2>
    <div class="section-copy">Configure where Prism, registry, proxy, BMC, SSH, and Git credentials should be sourced from.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/secrets/save">
    <table>
      <thead><tr><th>Secrets Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Backend</td><td><div class="field"><select name="backend"><option value="local-file" {'selected' if settings.get('backend') == 'local-file' else ''}>local-file</option><option value="hashicorp-vault" {'selected' if settings.get('backend') == 'hashicorp-vault' else ''}>hashicorp-vault</option><option value="cyberark" {'selected' if settings.get('backend') == 'cyberark' else ''}>cyberark</option><option value="azure-key-vault" {'selected' if settings.get('backend') == 'azure-key-vault' else ''}>azure-key-vault</option><option value="onepassword" {'selected' if settings.get('backend') == 'onepassword' else ''}>onepassword</option></select></div></td></tr>
        <tr><td>Vault / service URL</td><td><div class="field"><input name="vault_url" value="{html.escape(settings.get('vault_url', ''))}"></div></td></tr>
        <tr><td>Namespace / tenant</td><td><div class="field"><input name="namespace" value="{html.escape(settings.get('namespace', ''))}"></div></td></tr>
        <tr><td>Secret path</td><td><div class="field"><input name="secret_path" value="{html.escape(settings.get('secret_path', ''))}"></div></td></tr>
        <tr><td>Rotation policy</td><td><div class="field"><select name="rotation_policy"><option value="manual" {'selected' if settings.get('rotation_policy') == 'manual' else ''}>manual</option><option value="90-days" {'selected' if settings.get('rotation_policy') == '90-days' else ''}>90-days</option><option value="external" {'selected' if settings.get('rotation_policy') == 'external' else ''}>external</option></select></div></td></tr>
        <tr><td></td><td><button>Save secrets settings</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="section-head"><div><h2>Runtime Secret Checks</h2><div class="section-copy">Presence checks only. Secret values are never displayed.</div></div></div>
<section class="panel"><table><thead><tr><th>Key</th><th>Status</th></tr></thead><tbody>{secret_rows}</tbody></table></section>
<div class="notice">This records backend metadata only. Secret values are not stored by the console.</div>
"""
            self.send_html(page("Secrets - NKP ZeroTouch Framework", body, "secrets"))
            return
        if parsed.path == "/settings/rbac":
            rbac = load_rbac()
            settings = rbac["settings"]
            roles = rbac["roles"]
            accounts = rbac["accounts"]
            enabled_selected = "selected" if settings.get("enabled") == "true" else ""
            disabled_selected = "selected" if settings.get("enabled") != "true" else ""
            provider = settings.get("provider", "local")
            local_selected = "selected" if provider == "local" else ""
            oidc_selected = "selected" if provider == "oidc" else ""
            role_options = "".join(
                f'<option value="{html.escape(role["name"])}">{html.escape(role["name"])}</option>'
                for role in roles
            )
            role_rows = "".join(
                f"<tr><td><code>{html.escape(role['name'])}</code></td><td>{html.escape(role.get('permissions', ''))}</td><td><span class='chip ok'>Configured</span></td></tr>"
                for role in roles
            )
            account_rows = "".join(
                f"<tr><td><code>{html.escape(account['username'])}</code></td><td>{html.escape(account.get('displayName', ''))}</td><td>{html.escape(account.get('role', ''))}</td><td><span class='chip {'ok' if account.get('status') == 'active' else 'warn'}'>{html.escape(account.get('status', 'pending'))}</span></td></tr>"
                for account in accounts
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>RBAC</h2>
    <div class="section-copy">Create local console accounts and roles for future enforcement.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/rbac/save">
    <table>
      <thead><tr><th>Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>RBAC enforcement</td><td><div class="field"><select name="enabled"><option value="false" {disabled_selected}>disabled</option><option value="true" {enabled_selected}>enabled</option></select></div></td></tr>
        <tr><td>Identity provider</td><td><div class="field"><select name="provider"><option value="local" {local_selected}>local</option><option value="oidc" {oidc_selected}>oidc</option></select></div></td></tr>
        <tr><td>Default admin</td><td><div class="field"><input name="admin" value="{html.escape(settings.get('admin', 'admin'))}"></div></td></tr>
        <tr><td></td><td><button>Save RBAC settings</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="section-head">
  <div>
    <h2>Roles</h2>
    <div class="section-copy">Define permission bundles for console users.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/rbac/role/create">
    <table>
      <thead><tr><th>Role</th><th>Permissions</th><th>Create</th></tr></thead>
      <tbody>
        <tr><td><div class="field"><input name="name" value="Deployment Reviewer"></div></td><td><div class="field"><input name="permissions" value="runs, artifacts, audit"></div></td><td><button>Create role</button></td></tr>
      </tbody>
    </table>
  </form>
  <table>
    <thead><tr><th>Role</th><th>Permissions</th><th>Status</th></tr></thead>
    <tbody>{role_rows}</tbody>
  </table>
</section>
<div class="section-head">
  <div>
    <h2>Accounts</h2>
    <div class="section-copy">Create local bootstrap accounts and map them to roles.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/rbac/account/create">
    <table>
      <thead><tr><th>Username</th><th>Display Name</th><th>Password</th><th>Role</th><th>Status</th><th>Create</th></tr></thead>
      <tbody>
        <tr>
          <td><div class="field"><input name="username" value="operator"></div></td>
          <td><div class="field"><input name="display_name" value="NKP Operator"></div></td>
          <td><div class="field"><input name="password" type="password"></div></td>
          <td><div class="field"><select name="role">{role_options}</select></div></td>
          <td><div class="field"><select name="status"><option value="active">active</option><option value="disabled">disabled</option></select></div></td>
          <td><button>Create account</button></td>
        </tr>
      </tbody>
    </table>
  </form>
  <table>
    <thead><tr><th>Username</th><th>Display Name</th><th>Role</th><th>Status</th></tr></thead>
    <tbody>{account_rows or '<tr><td colspan="4" class="muted">No local accounts configured yet.</td></tr>'}</tbody>
  </table>
</section>
<div class="notice">Accounts and roles are saved to <code>.zt/settings/rbac.json</code>. Exposed first-admin bootstrap requires <code>ZT_BOOTSTRAP_TOKEN</code>.</div>
"""
            self.send_html(page("RBAC - NKP ZeroTouch Framework", body, "rbac"))
            return
        if parsed.path == "/settings/database":
            settings = read_json(SETTINGS / "database.json") or {}
            body = f"""
<div class="section-head">
  <div>
    <h2>Database</h2>
    <div class="section-copy">Persistence backend for future multi-user console state, audit records, and connection profiles.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/database/save">
    <table>
      <thead><tr><th>Postgres Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Host</td><td><div class="field"><input name="host" value="{html.escape(settings.get('host', 'localhost'))}"></div></td></tr>
        <tr><td>Port</td><td><div class="field"><input name="port" value="{html.escape(settings.get('port', '5432'))}"></div></td></tr>
        <tr><td>Database</td><td><div class="field"><input name="database" value="{html.escape(settings.get('database', 'nkp_zerotouch'))}"></div></td></tr>
        <tr><td>Username</td><td><div class="field"><input name="username" value="{html.escape(settings.get('username', 'zt_console'))}"></div></td></tr>
        <tr><td></td><td><button>Save database settings</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">Database settings are saved locally under <code>.zt/settings/database.json</code>. Raw database passwords are intentionally not stored here.</div>
"""
            self.send_html(page("Database - NKP ZeroTouch Framework", body, "database"))
            return
        if parsed.path == "/settings/integrations":
            settings = load_setting("integrations", default_integrations())
            integration_status = {name: (status, note) for name, status, note in integration_checks()}
            postgres_ok, postgres_note = integration_status.get("Postgres", ("warn", "disabled"))
            vault_ok, vault_note = integration_status.get("Vault", ("warn", "disabled"))
            oidc_ok, oidc_note = integration_status.get("OIDC", ("warn", "disabled"))
            session_ok, session_note = integration_status.get("Session store", ("warn", "memory"))
            body = f"""
<div class="section-head">
  <div>
    <h2>Enterprise Integrations</h2>
    <div class="section-copy">Configure and probe durable sessions, Postgres persistence, Vault secrets, and OIDC identity metadata.</div>
  </div>
</div>
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Postgres</div><div class="ops-value"><span class="chip {postgres_ok}">{html.escape(postgres_note)}</span></div></div>
  <div class="ops-item"><div class="ops-label">Vault</div><div class="ops-value"><span class="chip {vault_ok}">{html.escape(vault_note)}</span></div></div>
  <div class="ops-item"><div class="ops-label">OIDC</div><div class="ops-value"><span class="chip {oidc_ok}">{html.escape(oidc_note)}</span></div></div>
  <div class="ops-item"><div class="ops-label">Session Store</div><div class="ops-value"><span class="chip {session_ok}">{html.escape(session_note)}</span></div></div>
</section>
<section class="panel">
  <form method="post" action="/settings/integrations/save">
    <table>
      <thead><tr><th>Integration</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Session store</td><td><div class="field"><select name="session_store"><option value="memory" {'selected' if settings.get('session_store') == 'memory' else ''}>memory</option><option value="file" {'selected' if settings.get('session_store') == 'file' else ''}>file</option><option value="postgres" {'selected' if settings.get('session_store') == 'postgres' else ''}>postgres</option></select></div></td></tr>
        <tr><td>Enable Postgres</td><td><div class="field"><select name="postgres_enabled"><option value="false" {'selected' if settings.get('postgres_enabled') != 'true' else ''}>false</option><option value="true" {'selected' if settings.get('postgres_enabled') == 'true' else ''}>true</option></select></div></td></tr>
        <tr><td>Postgres DSN</td><td><div class="field"><input name="postgres_dsn" value="{html.escape(settings.get('postgres_dsn', ''))}" placeholder="postgresql://zt_console@db/nkp_zerotouch"></div></td></tr>
        <tr><td>Enable OIDC</td><td><div class="field"><select name="oidc_enabled"><option value="false" {'selected' if settings.get('oidc_enabled') != 'true' else ''}>false</option><option value="true" {'selected' if settings.get('oidc_enabled') == 'true' else ''}>true</option></select></div></td></tr>
        <tr><td>OIDC issuer</td><td><div class="field"><input name="oidc_issuer" value="{html.escape(settings.get('oidc_issuer', ''))}"></div></td></tr>
        <tr><td>OIDC client ID</td><td><div class="field"><input name="oidc_client_id" value="{html.escape(settings.get('oidc_client_id', ''))}"></div></td></tr>
        <tr><td>OIDC redirect URI</td><td><div class="field"><input name="oidc_redirect_uri" value="{html.escape(settings.get('oidc_redirect_uri', ''))}"></div></td></tr>
        <tr><td>Enable Vault</td><td><div class="field"><select name="vault_enabled"><option value="false" {'selected' if settings.get('vault_enabled') != 'true' else ''}>false</option><option value="true" {'selected' if settings.get('vault_enabled') == 'true' else ''}>true</option></select></div></td></tr>
        <tr><td>Vault address</td><td><div class="field"><input name="vault_addr" value="{html.escape(settings.get('vault_addr', ''))}" placeholder="https://vault.example.com"></div></td></tr>
        <tr><td>Vault mount</td><td><div class="field"><input name="vault_mount" value="{html.escape(settings.get('vault_mount', 'kv'))}"></div></td></tr>
        <tr><td>Vault secret path</td><td><div class="field"><input name="vault_secret_path" value="{html.escape(settings.get('vault_secret_path', 'nkp/zerotouch'))}"></div></td></tr>
        <tr><td></td><td><button>Save integrations</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">These settings provide concrete integration contracts. External Postgres, Vault, and OIDC services must still be deployed and connected in the target environment.</div>
"""
            self.send_html(page("Integrations - NKP ZeroTouch Framework", body, "integrations"))
            return
        if parsed.path == "/about":
            version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"
            body = f"""
<div class="section-head">
  <div>
    <h2>About</h2>
    <div class="section-copy">NKP ZeroTouch Framework console for Nutanix Kubernetes Platform deployment orchestration.</div>
  </div>
</div>
<section class="settings-grid">
  <div class="settings-card"><h3>Framework</h3><p>Version <code>{html.escape(version)}</code>. Supports connected, proxied, and air-gapped NKP deployment workflows.</p></div>
  <div class="settings-card"><h3>Console</h3><p>Local operator interface for safe actions, generated artifacts, settings, accounts, roles, and audit visibility.</p></div>
  <div class="settings-card"><h3>Safety Model</h3><p>Apply and destructive actions remain CLI-only. The dashboard exposes non-destructive operations and local bootstrap settings.</p></div>
  <div class="settings-card"><h3>Project Status</h3><p>Community automation framework baseline. Not affiliated with or supported by Nutanix.</p></div>
</section>
<div class="notice">RBAC, database, and connection settings are currently local bootstrap configuration. Production authentication, authorization, and database-backed persistence are planned next steps.</div>
"""
            self.send_html(page("About - NKP ZeroTouch Framework", body, "about"))
            return
        self.send_html(page("Not Found", "<h2>Not found</h2>"), status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))

        if parsed.path == "/login":
            username = safe_key(form_value(form, "username"))
            password = form_value(form, "password")
            rbac = load_rbac()
            login_accounts = [account for account in rbac.get("accounts", []) if account.get("passwordHash")]
            if not username or not password:
                self.send_html(page("Login Failed", "<h2>Login failed</h2><div class='notice'>Username and password are required.</div><a class='back-link' href='/login'>Back to login</a>", "about"), status=400)
                return
            if not login_accounts:
                expected_bootstrap_token = os.environ.get("ZT_BOOTSTRAP_TOKEN", "")
                if bootstrap_token_required() and (not expected_bootstrap_token or not secrets.compare_digest(form_value(form, "bootstrap_token"), expected_bootstrap_token)):
                    self.send_html(page("Bootstrap Blocked", "<h2>Bootstrap blocked</h2><div class='notice'>A valid bootstrap token is required before creating the first administrator account.</div><a class='back-link' href='/login'>Back to login</a>", "about"), status=403)
                    return
                account = {
                    "username": username,
                    "displayName": "Console Administrator",
                    "role": "Admin",
                    "status": "active",
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                account.update(password_record(password))
                rbac["accounts"] = [acct for acct in rbac.get("accounts", []) if safe_key(acct.get("username", "")) != username]
                rbac["accounts"].append(account)
                rbac.setdefault("settings", default_rbac()["settings"])
                rbac["settings"]["admin"] = username
                write_json(SETTINGS / "rbac.json", rbac)
            else:
                account = next((acct for acct in login_accounts if safe_key(acct.get("username", "")) == username and acct.get("status") == "active"), None)
                if not account or not verify_password(password, account):
                    self.send_html(page("Login Failed", "<h2>Login failed</h2><div class='notice'>Invalid username, password, or account status.</div><a class='back-link' href='/login'>Back to login</a>", "about"), status=403)
                    return
            token = secrets.token_urlsafe(32)
            session = {
                "username": username,
                "role": account.get("role", "Operator"),
                "loginAt": time.time(),
                "csrf": secrets.token_urlsafe(32),
            }
            save_session(token, session)
            audit_event("login", session, username, "success")
            self.send_redirect("/", {"Set-Cookie": f"zt_session={token}; Path=/; HttpOnly; SameSite=Lax"})
            return

        if not self.require_login(parsed):
            return
        if not self.require_permission(parsed):
            return
        if not self.require_csrf(form):
            return

        if parsed.path == "/approval-policy/save":
            data = {key: form_value(form, key) for key in ["deploy_approvals", "registry_approvals", "upgrade_approvals", "destroy_approvals", "prevent_self_approval", "production_requires_admin"]}
            save_setting("approval-policy", data)
            audit_event("approval_policy_saved", self.current_user(), "approval-policy", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Approval Policy</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/approval-policy'>Back to approval policy</a>"
            self.send_html(page("Approval Policy Saved", body, "approval-policy"))
            return

        if parsed.path == "/release-channels/save":
            data = {key: form_value(form, key) for key in ["default_channel", "channels", "production_requires_plan_review", "production_requires_backup"]}
            save_setting("release-channels", data)
            audit_event("release_channels_saved", self.current_user(), "release-channels", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Release Channels</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/release-channels'>Back to release channels</a>"
            self.send_html(page("Release Channels Saved", body, "release-channels"))
            return

        if parsed.path == "/settings/integrations/save":
            data = {key: form_value(form, key) for key in ["session_store", "postgres_enabled", "postgres_dsn", "oidc_enabled", "oidc_issuer", "oidc_client_id", "oidc_redirect_uri", "vault_enabled", "vault_addr", "vault_mount", "vault_secret_path"]}
            save_setting("integrations", data)
            audit_event("integrations_saved", self.current_user(), "integrations", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Integrations</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/integrations'>Back to integrations</a>"
            self.send_html(page("Integrations Saved", body, "integrations"))
            return

        if parsed.path == "/sources/save":
            data = {key: form_value(form, key) for key in ["version", "standard_bundle", "airgapped_bundle", "source_path", "git_url", "git_ref", "checksum"]}
            save_setting("sources", data)
            audit_event("sources_saved", self.current_user(), "sources", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Sources</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/sources'>Back to sources</a>"
            self.send_html(page("Sources Saved", body, "sources"))
            return

        if parsed.path == "/inventory/save":
            data = {key: form_value(form, key) for key in ["mode", "nodes", "bmc_network", "bmc_provider", "boot_mode", "os_image", "notes"]}
            save_setting("inventory", data)
            audit_event("inventory_saved", self.current_user(), "inventory", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Inventory</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/inventory'>Back to inventory</a>"
            self.send_html(page("Inventory Saved", body, "inventory"))
            return

        if parsed.path == "/network/save":
            data = {key: form_value(form, key) for key in ["management_cidr", "workload_cidr", "api_vip", "ingress_range", "dns_servers", "ntp_servers", "proxy", "ip_mode"]}
            save_setting("network", data)
            audit_event("network_saved", self.current_user(), "network", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Network</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/network'>Back to network</a>"
            self.send_html(page("Network Saved", body, "network"))
            return

        if parsed.path == "/settings/providers/save":
            data = {key: form_value(form, key) for key in ["default_provider", "enabled_providers", "runner_type", "runner_notes"]}
            save_setting("providers", data)
            audit_event("providers_saved", self.current_user(), "providers", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Providers</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/providers'>Back to providers</a>"
            self.send_html(page("Providers Saved", body, "providers"))
            return

        if parsed.path == "/settings/secrets/save":
            data = {key: form_value(form, key) for key in ["backend", "vault_url", "namespace", "secret_path", "rotation_policy"]}
            save_setting("secrets", data)
            audit_event("secrets_saved", self.current_user(), "secrets", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Secrets</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/secrets'>Back to secrets</a>"
            self.send_html(page("Secrets Saved", body, "secrets"))
            return

        if parsed.path == "/settings/connections/save":
            data = {
                "prism": form_value(form, "prism"),
                "registry": form_value(form, "registry"),
                "http_proxy": form_value(form, "http_proxy"),
                "standard_bundle": form_value(form, "standard_bundle"),
                "airgapped_bundle": form_value(form, "airgapped_bundle"),
                "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            write_json(SETTINGS / "connections.json", data)
            audit_event("connections_saved", self.current_user(), "connections", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Connections</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/connections'>Back to connections</a>"
            self.send_html(page("Connections Saved", body, "connections"))
            return

        if parsed.path == "/settings/new-environment/create":
            name = form_value(form, "name")
            env_type = form_value(form, "type", "connected")
            provider = form_value(form, "provider", "nutanix-ahv")
            config_path = ENV_DIR / f"{safe_key(name)}.yaml"
            duplicate_record = {
                "config": config_path,
                "environment": name,
                "cluster": f"{safe_key(name)}-cluster" if name else "",
                "api_vip": "",
                "registry_namespace": "",
            }
            uniqueness = environment_uniqueness_issues(extra=duplicate_record)
            if config_path.exists():
                uniqueness.append(f"Environment config '{config_path.name}' already exists.")
            if uniqueness:
                audit_event("environment_create_blocked", self.current_user(), name, "failed", {"issues": uniqueness})
                issue_rows = "".join(f"<li>{html.escape(issue)}</li>" for issue in uniqueness)
                body = f"<h2>Environment creation blocked</h2><div class='notice'>Resolve these identity conflicts before creating the environment.</div><ul>{issue_rows}</ul><a class='back-link' href='/settings/new-environment'>Back to new environment</a>"
                self.send_html(page("Environment Creation Blocked", body, "new-environment"), status=400)
                return
            code, out, err = create_environment(name, env_type)
            if code == 0:
                try:
                    new_config = resolve_env_config(str(ENV_DIR / f"{safe_key(name)}.yaml"))
                    data = load_env_yaml(new_config)
                    nested_set(data, ["environment", "name"], name)
                    nested_set(data, ["environment", "type"], env_type)
                    nested_set(data, ["environment", "provider"], provider)
                    nested_set(data, ["cluster", "name"], f"{safe_key(name)}-cluster")
                    nested_set(data, ["cluster", "controlPlaneEndpointIp"], "")
                    nested_set(data, ["registry", "namespace"], "")
                    write_env_yaml(new_config, data)
                except Exception as exc:
                    code = 1
                    err += f"\nEnvironment was created, but provider metadata could not be saved: {exc}"
            status_class = "ok" if code == 0 else "warn"
            audit_event("environment_created", self.current_user(), name, "success" if code == 0 else "failed", {"type": env_type, "provider": provider})
            body = (
                "<div class='result-layout'>"
                f"<section class='metric'><div class='metric-label'>Environment Creation</div><div class='metric-value'>{html.escape(name or 'unnamed')}</div>"
                f"<div class='metric-foot'><span class='chip {status_class}'>Exit code {code}</span></div></section>"
                f"<pre>{html.escape(out + err)}</pre>"
                "<a class='back-link' href='/settings/new-environment'>Back to new environment</a>"
                "</div>"
            )
            self.send_html(page("Environment Creation", body, "new-environment"), status=200 if code == 0 else 500)
            return

        if parsed.path == "/settings/rbac/save":
            rbac = load_rbac()
            data = {
                "enabled": form_value(form, "enabled", "false"),
                "provider": form_value(form, "provider", "local"),
                "admin": form_value(form, "admin", "admin"),
                "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            rbac["settings"] = data
            write_json(SETTINGS / "rbac.json", rbac)
            audit_event("rbac_saved", self.current_user(), "rbac", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>RBAC</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/rbac'>Back to RBAC</a>"
            self.send_html(page("RBAC Saved", body, "rbac"))
            return

        if parsed.path == "/settings/rbac/role/create":
            rbac = load_rbac()
            name = form_value(form, "name")
            permissions = form_value(form, "permissions")
            key = safe_key(name)
            if not key:
                self.send_html(page("Role Error", "<h2>Role name is required.</h2><a class='back-link' href='/settings/rbac'>Back to RBAC</a>", "rbac"), status=400)
                return
            existing = {safe_key(role.get("name", "")) for role in rbac["roles"]}
            if key not in existing:
                rbac["roles"].append({"name": name, "permissions": permissions, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                write_json(SETTINGS / "rbac.json", rbac)
            audit_event("role_saved", self.current_user(), name, "success")
            body = f"<section class='metric'><div class='metric-label'>Role Saved</div><div class='metric-value'>{html.escape(name)}</div><div class='metric-foot'><span class='chip ok'>Configured</span></div></section><a class='back-link' href='/settings/rbac'>Back to RBAC</a>"
            self.send_html(page("Role Saved", body, "rbac"))
            return

        if parsed.path == "/settings/rbac/account/create":
            rbac = load_rbac()
            username = safe_key(form_value(form, "username"))
            display_name = form_value(form, "display_name")
            password = form_value(form, "password")
            role = form_value(form, "role")
            status = form_value(form, "status", "active")
            if not username:
                self.send_html(page("Account Error", "<h2>Username is required.</h2><a class='back-link' href='/settings/rbac'>Back to RBAC</a>", "rbac"), status=400)
                return
            existing_account = next((account for account in rbac["accounts"] if safe_key(account.get("username", "")) == username), None)
            if not password and not existing_account:
                self.send_html(page("Account Error", "<h2>Password is required for new accounts.</h2><a class='back-link' href='/settings/rbac'>Back to RBAC</a>", "rbac"), status=400)
                return
            accounts = [account for account in rbac["accounts"] if safe_key(account.get("username", "")) != username]
            account_record = {
                "username": username,
                "displayName": display_name,
                "role": role,
                "status": status,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if existing_account and not password:
                for key in ["salt", "passwordHash", "algorithm", "iterations"]:
                    if key in existing_account:
                        account_record[key] = existing_account[key]
            else:
                account_record.update(password_record(password))
            accounts.append(account_record)
            rbac["accounts"] = accounts
            write_json(SETTINGS / "rbac.json", rbac)
            audit_event("account_saved", self.current_user(), username, "success", {"role": role, "status": status})
            body = f"<section class='metric'><div class='metric-label'>Account Saved</div><div class='metric-value'>{html.escape(username)}</div><div class='metric-foot'><span class='chip ok'>Mapped to {html.escape(role)}</span></div></section><a class='back-link' href='/settings/rbac'>Back to RBAC</a>"
            self.send_html(page("Account Saved", body, "rbac"))
            return

        if parsed.path == "/settings/database/save":
            data = {
                "host": form_value(form, "host"),
                "port": form_value(form, "port"),
                "database": form_value(form, "database"),
                "username": form_value(form, "username"),
                "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            write_json(SETTINGS / "database.json", data)
            audit_event("database_saved", self.current_user(), "database", "success")
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Database</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/database'>Back to database</a>"
            self.send_html(page("Database Saved", body, "database"))
            return

        if parsed.path == "/plan-review/save":
            env_name = form_value(form, "environment")
            decision = form_value(form, "decision")
            if decision not in {"approved", "rejected"}:
                self.send_html(page("Plan Review Error", "<h2>Invalid decision</h2><a class='back-link' href='/plan-review'>Back to plan review</a>", "plan-review"), status=400)
                return
            env_names = {str(read_json_from_context(config).get("environmentName") or config.stem) for config in env_configs()}
            if env_name not in env_names:
                self.send_html(page("Plan Review Error", "<h2>Unknown environment</h2><a class='back-link' href='/plan-review'>Back to plan review</a>", "plan-review"), status=400)
                return
            state = env_state(env_name)
            if not state["generate"] and not (state["base"] / "generated" / "deploy-plan.md").exists():
                self.send_html(page("Plan Review Error", "<h2>Generate required</h2><div class='notice'>Run generate before approving or rejecting a deployment plan.</div><a class='back-link' href='/plan-review'>Back to plan review</a>", "plan-review"), status=400)
                return
            review = {
                "status": decision,
                "reviewedBy": self.current_user().get("username", "operator"),
                "reviewedRole": self.current_user().get("role", ""),
                "reviewedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "note": form_value(form, "note"),
                "planHashes": plan_hashes(env_name),
            }
            write_json(review_path(env_name), review)
            audit_event("plan_review_saved", self.current_user(), env_name, "success", review)
            self.send_redirect("/plan-review")
            return

        if parsed.path == "/locks/clear":
            env_name = form_value(form, "environment")
            if active_lock(env_name):
                self.send_html(page("Lock Active", "<h2>Lock is active</h2><div class='notice'>Active locks cannot be cleared while the linked job is queued, running, or pending approval.</div><a class='back-link' href='/locks'>Back to locks</a>", "locks"), status=409)
                return
            lock_path(env_name).unlink(missing_ok=True)
            audit_event("lock_cleared", self.current_user(), env_name, "success")
            self.send_redirect("/locks")
            return

        if parsed.path == "/restore/plan":
            try:
                manifest = resolve_artifact(form_value(form, "manifest"))
                data = read_json(manifest) or {}
                restore_dir = ZT / "restore-plans"
                restore_dir.mkdir(parents=True, exist_ok=True)
                plan_id = f"restore-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
                plan_path = restore_dir / f"{plan_id}.md"
                plan = f"""# Restore Plan

Created: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
Requested by: {self.current_user().get('username', 'operator')}

Manifest: `{manifest}`
Environment: `{data.get('environment', 'unknown')}`
Backup: `{manifest.parent}`

## Manual Restore Steps

1. Stop active jobs for this environment.
2. Confirm no active lock exists.
3. Copy selected `state`, `generated`, or `reports` folders from the backup path.
4. Re-run preflight and drift detection.
5. Run verify before any apply action.
"""
                plan_path.write_text(plan, encoding="utf-8")
                audit_event("restore_plan_created", self.current_user(), str(manifest), "success", {"plan": str(plan_path)})
            except Exception as exc:
                self.send_html(page("Restore Plan Error", f"<h2>Restore plan failed</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/restore'>Back to restore</a>", "restore"), status=400)
                return
            body = f"<section class='metric'><div class='metric-label'>Restore Plan</div><div class='metric-value'>{html.escape(plan_id)}</div><div class='metric-foot'><span class='chip ok'>Generated</span></div></section><a class='button-link' href='/artifacts/view?path={quote(str(plan_path))}'>Open restore plan</a> <a class='back-link' href='/restore'>Back to restore</a>"
            self.send_html(page("Restore Plan Created", body, "restore"))
            return

        if parsed.path == "/jobs/approve":
            user = self.current_user()
            if not has_permission(user, "approve"):
                self.send_html(page("Approval Blocked", "<h2>Approval blocked</h2><div class='notice'>Your role does not have approval permission.</div><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=403)
                return
            job_id = form_value(form, "job_id")
            job = read_job(job_id)
            if not job or job.get("status") != "pending_approval":
                self.send_html(page("Approval Error", "<h2>Job is not pending approval.</h2><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=400)
                return
            allowed, reason = approval_policy_allows(user, job)
            if not allowed:
                audit_event("approval_denied", user, job_id, "denied", {"reason": reason})
                self.send_html(page("Approval Blocked", f"<h2>Approval blocked</h2><div class='notice'>{html.escape(reason)}</div><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=403)
                return
            approvals = [approval for approval in job.get("approvals", []) if approval.get("user") != user.get("username")]
            approvals.append({"user": user.get("username", "unknown"), "role": user.get("role", ""), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            required = int(job.get("requiredApprovals", approval_requirement(job.get("action", ""))))
            status = "queued" if len({item["user"] for item in approvals}) >= required else "pending_approval"
            update_job(job_id, status=status, approvals=approvals, approvedBy=user.get("username", "unknown"), approvedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            audit_event("job_approved", user, job_id, "success", {"approvals": len(approvals), "required": required})
            append_job_log(job_id, f"[approved by {user.get('username', 'unknown')} ({len(approvals)}/{required})]\n")
            if status == "queued":
                start_job(job_id)
            self.send_redirect(f"/jobs/view?id={quote(job_id)}")
            return

        if parsed.path == "/jobs/reject":
            user = self.current_user()
            if not has_permission(user, "approve"):
                self.send_html(page("Rejection Blocked", "<h2>Rejection blocked</h2><div class='notice'>Your role does not have approval permission.</div><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=403)
                return
            job_id = form_value(form, "job_id")
            job = read_job(job_id)
            if not job or job.get("status") != "pending_approval":
                self.send_html(page("Rejection Error", "<h2>Job is not pending approval.</h2><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=400)
                return
            update_job(job_id, status="rejected", rejectedBy=user.get("username", "unknown"), rejectedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            audit_event("job_rejected", user, job_id, "success")
            append_job_log(job_id, f"[rejected by {user.get('username', 'unknown')}]\n")
            self.send_redirect(f"/jobs/view?id={quote(job_id)}")
            return

        if parsed.path == "/jobs/cancel":
            user = self.current_user()
            if not has_permission(user, "jobs"):
                self.send_html(page("Cancel Blocked", "<h2>Cancel blocked</h2><div class='notice'>Your role does not have job permission.</div><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=403)
                return
            job_id = form_value(form, "job_id")
            job = read_job(job_id)
            if not job or job.get("status") not in {"queued", "running", "pending_approval"}:
                self.send_html(page("Cancel Error", "<h2>Job cannot be cancelled.</h2><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=400)
                return
            update_job(job_id, status="cancel_requested" if job.get("status") == "running" else "cancelled", cancelledBy=user.get("username", "unknown"), cancelledAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            audit_event("job_cancelled", user, job_id, "success")
            append_job_log(job_id, f"[cancel requested by {user.get('username', 'unknown')}]\n")
            if job.get("status") == "running" and job.get("pid"):
                try:
                    os.kill(int(job["pid"]), signal.SIGTERM)
                except OSError as exc:
                    append_job_log(job_id, f"[cancel signal failed] {exc}\n")
            self.send_redirect(f"/jobs/view?id={quote(job_id)}")
            return

        if parsed.path == "/jobs/retry":
            user = self.current_user()
            if not has_permission(user, "jobs"):
                self.send_html(page("Retry Blocked", "<h2>Retry blocked</h2><div class='notice'>Your role does not have job permission.</div><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=403)
                return
            original = read_job(form_value(form, "job_id"))
            if not original or original.get("status") not in {"failed", "cancelled", "rejected", "succeeded"}:
                self.send_html(page("Retry Error", "<h2>Job cannot be retried from its current state.</h2><a class='back-link' href='/jobs'>Back to jobs</a>", "jobs"), status=400)
                return
            retry = create_job(
                original.get("action", ""),
                original.get("config", ""),
                original.get("command", []),
                user,
                kind=original.get("kind", "safe"),
                approval_required=original.get("kind") == "apply",
            )
            append_job_log(retry["id"], f"[retry of {original.get('id')}]\n")
            audit_event("job_retried", user, retry["id"], "success", {"sourceJob": original.get("id")})
            self.send_redirect(f"/jobs/view?id={quote(retry['id'])}")
            return

        if parsed.path == "/cli/run":
            try:
                command_text = form_value(form, "command")
                action, config, apply, confirm_destroy = parse_cli_command(command_text, form_value(form, "config"))
            except Exception as exc:
                self.send_html(page("CLI Error", f"<h2>Command rejected</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/cli'>Back to CLI</a>", "cli"), status=400)
                return
            command = cli_command(action, config, apply=apply, confirm_destroy=confirm_destroy)
            if not command:
                self.send_html(page("CLI Error", "<h2>Runner unavailable</h2><div class='notice'>No supported shell runner found.</div><a class='back-link' href='/cli'>Back to CLI</a>", "cli"), status=500)
                return
            allowed, reasons = apply_gate(config, action)
            if not allowed:
                reason_rows = "".join(f"<li>{html.escape(reason)}</li>" for reason in reasons)
                audit_event("apply_gate_blocked", self.current_user(), action, "denied", {"config": str(config), "reasons": reasons})
                self.send_html(page("Apply Gate Blocked", f"<h2>Apply gate blocked</h2><div class='notice'>Resolve these controls before requesting apply.</div><ul>{reason_rows}</ul><a class='back-link' href='/cli'>Back to CLI</a>", "cli"), status=409)
                return
            job = create_job(action, config, command, self.current_user(), kind="apply", approval_required=True)
            change = create_change_record(job, self.current_user())
            audit_event("apply_requested", self.current_user(), job["id"], "pending", {"action": action, "config": str(config)})
            audit_event("change_record_created", self.current_user(), change["id"], "success", {"jobId": job["id"], "environment": job.get("environment", "")})
            self.send_redirect(f"/jobs/view?id={quote(job['id'])}")
            return

        if parsed.path == "/environment/edit/save":
            try:
                config = resolve_env_config(form_value(form, "config"))
                data = load_env_yaml(config)
                field_map = {
                    "environment_name": (["environment", "name"], str),
                    "environment_type": (["environment", "type"], str),
                    "release_channel": (["environment", "channel"], str),
                    "environment_provider": (["environment", "provider"], str),
                    "nkp_version": (["nkp", "version"], str),
                    "bundle_type": (["nkp", "bundleType"], str),
                    "bundle_path": (["nkp", "bundlePath"], str),
                    "prism_endpoint": (["nutanix", "prismCentralEndpoint"], str),
                    "nutanix_cluster": (["nutanix", "clusterName"], str),
                    "subnet": (["nutanix", "subnetName"], str),
                    "image_name": (["nutanix", "imageName"], str),
                    "cluster_name": (["cluster", "name"], str),
                    "kubernetes_version": (["cluster", "kubernetesVersion"], str),
                    "control_plane_replicas": (["cluster", "controlPlaneReplicas"], int_or_original),
                    "worker_replicas": (["cluster", "workerReplicas"], int_or_original),
                    "registry_endpoint": (["registry", "endpoint"], str),
                    "registry_namespace": (["registry", "namespace"], str),
                }
                for key, (path, converter) in field_map.items():
                    nested_set(data, path, converter(form_value(form, key)))
                candidate = {
                    "config": config,
                    "environment": str(nested_get(data, ["environment", "name"], "")).strip(),
                    "cluster": str(nested_get(data, ["cluster", "name"], "")).strip(),
                    "api_vip": str(nested_get(data, ["cluster", "controlPlaneEndpointIp"], "")).strip(),
                    "registry_namespace": str(nested_get(data, ["registry", "namespace"], "")).strip(),
                }
                uniqueness = environment_uniqueness_issues(extra=candidate, exclude=config)
                if uniqueness:
                    raise ValueError(" ".join(uniqueness))
                write_env_yaml(config, data)
                audit_event("environment_saved", self.current_user(), config.name, "success")
            except Exception as exc:
                self.send_html(page("Environment Save Error", f"<h2>Save failed</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "environments"), status=400)
                return
            body = f"<section class='metric'><div class='metric-label'>Environment Saved</div><div class='metric-value'>{html.escape(config.name)}</div><div class='metric-foot'><span class='chip ok'>YAML updated</span></div></section><a class='back-link' href='/'>Back to environments</a>"
            self.send_html(page("Environment Saved", body, "environments"))
            return

        if parsed.path == "/environment/delete/confirm":
            try:
                config = resolve_env_config(form_value(form, "config"))
                if config.name.endswith(".example.yaml"):
                    raise ValueError("Example environment templates cannot be deleted from the console.")
                data = load_env_yaml(config)
                env_name = str(nested_get(data, ["environment", "name"], config.stem))
                if form_value(form, "confirm") != env_name:
                    raise ValueError(f"Confirmation must exactly match environment name: {env_name}")
                config.unlink()
                removed_state = False
                if form_value(form, "delete_state") == "yes":
                    state_dir = ZT / "environments" / env_name
                    if state_dir.exists() and state_dir.resolve().is_relative_to((ZT / "environments").resolve()):
                        shutil.rmtree(state_dir)
                        removed_state = True
            except Exception as exc:
                self.send_html(page("Environment Delete Error", f"<h2>Delete failed</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "environments"), status=400)
                return
            state_note = "Config and local state removed" if removed_state else "Config removed"
            body = f"<section class='metric'><div class='metric-label'>Environment Deleted</div><div class='metric-value'>{html.escape(env_name)}</div><div class='metric-foot'><span class='chip ok'>{html.escape(state_note)}</span></div></section><a class='back-link' href='/'>Back to environments</a>"
            audit_event("environment_deleted", self.current_user(), env_name, "success", {"stateRemoved": removed_state})
            self.send_html(page("Environment Deleted", body, "environments"))
            return

        if parsed.path != "/action":
            self.send_html(page("Not Found", "<h2>Not found</h2>"), status=404)
            return

        action = form.get("action", [""])[0]
        try:
            config = resolve_env_config(form.get("config", [""])[0])
        except Exception as exc:
            self.send_html(page("Action Error", f"<h2>Invalid environment</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/'>Back to environments</a>", "actions"), status=400)
            return
        if action not in SAFE_ACTIONS:
            self.send_html(page("Blocked", "<h2>Action is not dashboard-safe.</h2>"), status=403)
            return
        if not has_permission(self.current_user(), "safe-actions"):
            self.send_html(page("Blocked", "<h2>Action blocked</h2><div class='notice'>Your role does not have safe-action permission.</div><a class='back-link' href='/'>Back to dashboard</a>", "actions"), status=403)
            return
        if action != "validate":
            data = read_json_from_context(config)
            identity_issues = environment_identity_issues(config, data, env_state(str(data.get("environmentName") or config.stem)))
            if identity_issues:
                issue_rows = "".join(f"<li>{html.escape(issue)}</li>" for issue in identity_issues)
                audit_event("safe_action_blocked", self.current_user(), action, "denied", {"config": str(config), "issues": identity_issues})
                self.send_html(page("Action Blocked", f"<h2>Action blocked</h2><div class='notice'>Resolve environment identity issues before running state-changing actions.</div><ul>{issue_rows}</ul><a class='back-link' href='/'>Back to dashboard</a>", "actions"), status=409)
                return
        command = action_command(action, config)
        if not command:
            self.send_html(page("Action Error", "<h2>Runner unavailable</h2><div class='notice'>No supported shell runner found.</div><a class='back-link' href='/'>Back to dashboard</a>", "actions"), status=500)
            return
        job = create_job(action, config, command, self.current_user(), kind="safe", approval_required=False)
        audit_event("safe_job_created", self.current_user(), job["id"], "queued", {"action": action, "config": str(config)})
        self.send_redirect(f"/jobs/view?id={quote(job['id'])}")


def read_json_from_context(config):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "zt_config.py"), "context", "--config", str(config)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"environmentName": config.stem, "environmentType": "unknown"}
    return json.loads(result.stdout)


def main():
    host = os.environ.get("ZT_DASHBOARD_HOST", "127.0.0.1")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    assert_bootstrap_safe(host)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
