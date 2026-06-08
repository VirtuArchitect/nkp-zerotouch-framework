#!/usr/bin/env python3
import html
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

try:
    import yaml
except ImportError:
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
ZT = ROOT / ".zt"
SETTINGS = ZT / "settings"
ENV_DIR = ROOT / "configs" / "environments"
SESSIONS = {}
SAFE_ACTIONS = {"validate", "prepare", "generate", "verify", "backup", "runs"}
ACTION_ORDER = ["validate", "prepare", "generate", "verify", "backup", "runs"]
VIEW_PATHS = {
    "environments": "/",
    "cli": "/cli",
    "runs": "/runs",
    "artifacts": "/artifacts",
    "actions": "/actions",
    "audit": "/audit",
    "connections": "/settings/connections",
    "new-environment": "/settings/new-environment",
    "rbac": "/settings/rbac",
    "database": "/settings/database",
    "about": "/about",
}


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
            {"name": "Admin", "permissions": "settings, environments, safe-actions, audit"},
            {"name": "Operator", "permissions": "environments, safe-actions, artifacts"},
            {"name": "Auditor", "permissions": "runs, artifacts, audit"},
        ],
        "accounts": [],
    }


def load_rbac():
    data = read_json(SETTINGS / "rbac.json") or default_rbac()
    if "settings" not in data:
        data = {"settings": data, "roles": default_rbac()["roles"], "accounts": []}
    data.setdefault("settings", default_rbac()["settings"])
    data.setdefault("roles", default_rbac()["roles"])
    data.setdefault("accounts", [])
    return data


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


def run_action(action, config):
    bash_path = shutil.which("bash")
    pwsh_path = shutil.which("pwsh") or shutil.which("powershell")

    if bash_path and (ROOT / "scripts" / "zt.sh").exists():
        command = [bash_path, str(ROOT / "scripts" / "zt.sh"), action, "--config", str(config)]
    elif pwsh_path and (ROOT / "scripts" / "zt.ps1").exists():
        command = [
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
    else:
        return 127, "", "No supported shell runner found. Install bash, PowerShell, or run the dashboard container image."

    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", (exc.stderr or "") + "\nAction timed out after 300 seconds."
    except OSError as exc:
        return 127, "", f"Failed to start action runner: {exc}"


def page(title, body, active="environments", user=None):
    def nav_class(key):
        return "nav-item active" if key == active else "nav-item"

    nav = f"""
    <div class="nav-label">Operations</div>
    <a class="{nav_class('environments')}" href="{VIEW_PATHS['environments']}"><span class="nav-dot"></span>Environments</a>
    <a class="{nav_class('cli')}" href="{VIEW_PATHS['cli']}">CLI</a>
    <a class="{nav_class('runs')}" href="{VIEW_PATHS['runs']}">Runs</a>
    <a class="{nav_class('artifacts')}" href="{VIEW_PATHS['artifacts']}">Artifacts</a>
    <div class="nav-label">Governance</div>
    <a class="{nav_class('actions')}" href="{VIEW_PATHS['actions']}">Safe Actions</a>
    <a class="{nav_class('audit')}" href="{VIEW_PATHS['audit']}">Audit Trail</a>
    <div class="nav-label">Settings</div>
    <a class="{nav_class('connections')}" href="{VIEW_PATHS['connections']}">Connections</a>
    <a class="{nav_class('new-environment')}" href="{VIEW_PATHS['new-environment']}">New Environment</a>
    <a class="{nav_class('rbac')}" href="{VIEW_PATHS['rbac']}">RBAC</a>
    <a class="{nav_class('database')}" href="{VIEW_PATHS['database']}">Database</a>
    <div class="nav-label">System</div>
    <a class="{nav_class('about')}" href="{VIEW_PATHS['about']}">About</a>
"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f2f5f8;
      --panel: #ffffff;
      --panel-2: #f7f9fc;
      --ink: #111827;
      --muted: #667085;
      --line: #d7dee8;
      --line-strong: #c3ccd8;
      --nav: #0f1724;
      --nav-2: #182235;
      --accent: #1a6b6b;
      --accent-2: #2563eb;
      --accent-soft: #e6f4f4;
      --good: #057a55;
      --good-soft: #dcfce7;
      --warn: #9a5b05;
      --warn-soft: #fef3c7;
      --bad: #b42318;
      --bad-soft: #fee4e2;
      --shadow: 0 12px 30px rgba(16, 24, 40, .07);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 "Segoe UI", Roboto, Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    .shell {{ display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: 100vh; }}
    .sidebar {{
      background: linear-gradient(180deg, var(--nav) 0%, var(--nav-2) 100%);
      color: #f8fafc;
      padding: 20px 16px;
      border-right: 1px solid rgba(255,255,255,.08);
      position: sticky; top: 0; height: 100vh; overflow-y: auto;
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 24px; padding: 2px 2px 14px; border-bottom: 1px solid rgba(255,255,255,.08); }}
    .brand-mark {{
      width: 34px; height: 34px; border-radius: 7px;
      display: grid; place-items: center;
      background: #1a6b6b;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.16), 0 8px 18px rgba(0,0,0,.22);
    }}
    .brand-mark img {{ width: 34px; height: 34px; display: block; border-radius: 7px; }}
    .brand-title {{ font-size: 15px; font-weight: 760; letter-spacing: 0; }}
    .brand-subtitle {{ color: #aab4c6; font-size: 12px; margin-top: 2px; }}
    .nav-label {{ color: #8894aa; font-size: 11px; font-weight: 760; text-transform: uppercase; margin: 20px 10px 8px; letter-spacing: .04em; }}
    .nav-item {{
      display: flex; align-items: center; gap: 10px;
      min-height: 36px; padding: 0 10px; border-radius: 6px;
      color: #d9e3f3; font-weight: 600; text-decoration: none;
      border: 1px solid transparent;
    }}
    .nav-item:hover {{ background: rgba(255,255,255,.07); color: #fff; border-color: rgba(255,255,255,.06); }}
    .nav-item.active {{ background: rgba(255,255,255,.11); color: #fff; border-color: rgba(255,255,255,.1); }}
    .nav-dot {{ width: 8px; height: 8px; border-radius: 50%; background: transparent; }}
    .nav-item.active .nav-dot {{ background: #3dd6a3; }}
    .content {{ min-width: 0; }}
    .topbar {{
      min-height: 72px; background: rgba(255,255,255,.96);
      border-bottom: 1px solid var(--line);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 28px;
      position: sticky; top: 0; z-index: 5; backdrop-filter: blur(10px);
    }}
    .topbar h1 {{ margin: 0; font-size: 20px; font-weight: 780; letter-spacing: 0; }}
    .topbar-meta {{ display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 12px; flex-wrap: wrap; justify-content: flex-end; }}
    .operator-pill {{ display: inline-flex; align-items: center; gap: 8px; min-height: 28px; padding: 0 10px; border: 1px solid var(--line); border-radius: 999px; background: #fff; color: #344054; font-weight: 700; }}
    .operator-pill::before {{ content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--good); }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 24px 28px 42px; }}
    h2 {{ margin: 0; font-size: 16px; }}
    .section-head {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 24px 0 12px; }}
    .section-copy {{ color: var(--muted); font-size: 12px; margin-top: 3px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 14px; }}
    .ops-strip {{ display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 1px; border: 1px solid var(--line); border-radius: 8px; background: var(--line); overflow: hidden; box-shadow: var(--shadow); margin-bottom: 18px; }}
    .ops-item {{ background: #fff; padding: 13px 15px; }}
    .ops-label {{ color: var(--muted); font-size: 11px; font-weight: 760; text-transform: uppercase; letter-spacing: .04em; }}
    .ops-value {{ margin-top: 5px; font-weight: 780; color: #172033; }}
    .metric {{
      background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%); border: 1px solid var(--line); border-radius: 8px;
      padding: 17px; box-shadow: var(--shadow); position: relative; overflow: hidden;
    }}
    .metric::after {{ content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: #d6e3ef; }}
    .metric-link::after {{ background: var(--accent); }}
    }}
    .metric-link {{
      display: block; color: var(--ink);
      transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease;
    }}
    .metric-link:hover {{
      transform: translateY(-1px);
      border-color: #9bb8f5;
      box-shadow: 0 18px 42px rgba(26, 107, 107, .13);
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
      background: var(--panel-2); color: #475467;
      font-size: 11px; font-weight: 780; text-transform: uppercase; letter-spacing: .035em;
      border-bottom: 1px solid var(--line-strong);
    }}
    tbody tr:hover {{ background: #fbfdff; }}
    code, pre {{ font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace; }}
    pre {{
      margin: 0; background: #111827; color: #dbeafe;
      padding: 16px; overflow: auto; border-radius: 8px;
      border: 1px solid #263349;
    }}
    .env-name {{ font-weight: 750; }}
    .env-file {{ color: var(--muted); font-size: 12px; margin-top: 3px; white-space: nowrap; }}
    .badge {{
      display: inline-flex; align-items: center; gap: 6px;
      min-height: 24px; padding: 0 9px; border-radius: 999px;
      font-size: 12px; font-weight: 700; border: 1px solid transparent;
      white-space: nowrap;
    }}
    .badge.connected {{ color: #075985; background: #e0f2fe; border-color: #bae6fd; }}
    .badge.proxied {{ color: #5b21b6; background: #ede9fe; border-color: #ddd6fe; }}
    .badge.air-gapped {{ color: #854d0e; background: #fef9c3; border-color: #fde68a; }}
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
      min-height: 32px; border: 1px solid var(--line-strong); background: #fff;
      padding: 0 9px; border-radius: 6px; cursor: pointer;
      color: #263449; font-weight: 700; font-size: 12px;
    }}
    button:hover {{ background: var(--accent-soft); border-color: #8ababa; color: #155e5e; }}
    .button-link {{
      display: inline-flex; align-items: center; min-height: 32px;
      border: 1px solid var(--line-strong); background: #fff;
      padding: 0 9px; border-radius: 6px; color: #263449;
      font-weight: 700; font-size: 12px;
    }}
    .button-link:hover {{ background: var(--accent-soft); border-color: #8ababa; color: #155e5e; }}
    .button-danger {{ border-color: #f0b4af; color: var(--bad); }}
    .button-danger:hover {{ background: var(--bad-soft); border-color: #f0b4af; color: var(--bad); }}
    .run-list {{ list-style: none; margin: 0; padding: 0; }}
    .run-list li {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 11px 16px; border-bottom: 1px solid var(--line);
    }}
    .run-list li:last-child {{ border-bottom: 0; }}
    .muted {{ color: var(--muted); }}
    .notice {{
      margin-top: 16px; padding: 12px 14px; border-radius: 8px;
      border: 1px solid #d7e3f8; background: #f5f8ff; color: #40516d;
      font-size: 13px;
    }}
    .login-panel {{ max-width: 520px; margin: 38px auto 0; }}
    .login-panel .panel {{ box-shadow: 0 24px 70px rgba(16, 24, 40, .14); }}
    .settings-grid {{ display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; }}
    .settings-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); }}
    .settings-card h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .settings-card p {{ margin: 0; color: var(--muted); }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 14px; }}
    .field label {{ display: block; color: #3b465a; font-size: 12px; font-weight: 750; margin-bottom: 6px; text-transform: uppercase; }}
    .field input, .field select {{
      width: 100%; min-height: 36px; border: 1px solid var(--line-strong); border-radius: 6px;
      padding: 0 10px; color: var(--ink); background: #fff;
    }}
    .result-layout {{ display: grid; gap: 16px; }}
    .back-link {{ display: inline-flex; align-items: center; margin-top: 16px; font-weight: 700; }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: none; }}
      .topbar {{ align-items: flex-start; flex-direction: column; gap: 10px; padding: 16px 20px; }}
      main {{ padding: 18px 16px 32px; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .ops-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .settings-grid, .form-grid {{ grid-template-columns: 1fr; }}
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
        <div class="brand-title">Veridian ZeroTouch</div>
        <div class="brand-subtitle">Deployment Console</div>
      </div>
    </div>
{nav}
  </aside>
  <div class="content">
    <div class="topbar">
      <div>
        <h1>NKP ZeroTouch Console</h1>
        <div class="section-copy">Nutanix Kubernetes Platform deployment orchestration</div>
      </div>
      <div class="topbar-meta">
        <span class="badge connected">Console Online</span>
        <span class="operator-pill">{html.escape(user.get('username', 'operator session') if user else 'operator session')}</span>
        <a class="button-link" href="/logout">Log out</a>
        <span>CLI apply actions disabled</span>
      </div>
    </div>
    <main>{body}</main>
  </div>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content, status=200, headers=None):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
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
        return SESSIONS.get(token)

    def require_login(self, parsed):
        if parsed.path in {"/login", "/assets/veridian-mark-teal.svg"}:
            return True
        if self.current_user():
            return True
        self.send_redirect("/login")
        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self.require_login(parsed):
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
            hint = "Use a local console account." if has_login_accounts else "No password-enabled accounts exist yet. Create the first local administrator account."
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
        <tr><td></td><td><button>{'Sign in' if has_login_accounts else 'Create admin and sign in'}</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">This is local console authentication for operator workstations. Production use should move to OIDC/SSO and server-side session storage.</div>
</div>
"""
            self.send_html(page("Login - NKP ZeroTouch Console", body, "about"))
            return
        if parsed.path == "/logout":
            token = cookie_value(self.headers, "zt_session")
            SESSIONS.pop(token, None)
            self.send_redirect("/login", {"Set-Cookie": "zt_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            return
        if parsed.path in ("/", "/environments"):
            rows = []
            env_total = 0
            prepared_total = 0
            generated_total = 0
            report_total = 0
            for config in env_configs():
                data = read_json_from_context(config)
                name = data.get("environmentName") or config.stem
                env_type = data.get("environmentType", "unknown")
                state = env_state(name)
                prepared = bool(state["state"])
                generated = bool(state["generate"])
                report = state["verification"].exists()
                env_total += 1
                prepared_total += 1 if prepared else 0
                generated_total += 1 if generated else 0
                report_total += 1 if report else 0
                buttons = "".join(
                    f'<form method="post" action="/action"><input type="hidden" name="action" value="{a}"><input type="hidden" name="config" value="{html.escape(str(config))}"><button title="Run {a}">{a}</button></form> '
                    for a in ACTION_ORDER
                )
                config_arg = quote(str(config))
                manage_buttons = (
                    f'<a class="button-link" href="/environment/edit?config={config_arg}">Edit</a> '
                    f'<a class="button-link button-danger" href="/environment/delete?config={config_arg}">Delete</a>'
                )
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='badge {html.escape(env_type)}'>{html.escape(env_type)}</span></td>"
                    f"<td><span class='chip {'ok' if prepared else 'warn'}'>{'Ready' if prepared else 'Pending'}</span></td>"
                    f"<td><span class='chip {'ok' if generated else 'warn'}'>{'Generated' if generated else 'Pending'}</span></td>"
                    f"<td><span class='chip {'ok' if report else 'warn'}'>{'Available' if report else 'Missing'}</span></td>"
                    f"<td class='actions'>{buttons}</td>"
                    f"<td class='manage-actions'>{manage_buttons}</td></tr>"
                )
            runs = sorted((ZT / "runs").glob("*/summary.md")) if (ZT / "runs").exists() else []
            recent_runs = list(reversed(runs[-10:]))
            rbac = load_rbac()
            auth_mode = "Local RBAC" if any(account.get("passwordHash") for account in rbac.get("accounts", [])) else "Bootstrap"
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
  {metric_card("Environments", env_total, "configured deployment targets", "/")}
  {metric_card("Prepared", prepared_total, "workspace states available", "/artifacts")}
  {metric_card("Generated", generated_total, "artifact sets created", "/artifacts")}
  {metric_card("Reports", report_total, "verification summaries present", "/artifacts")}
</section>

<div class="section-head">
  <div>
    <h2>Environments</h2>
    <div class="section-copy">Validated deployment profiles for connected, proxied, and air-gapped NKP installs.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Name</th><th>Type</th><th>Prepared</th><th>Generated</th><th>Report</th><th>Safe Actions</th><th>Manage</th></tr></thead>
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
            self.send_html(page("NKP ZeroTouch Console", body, "environments"))
            return
        if parsed.path == "/cli":
            config_options = []
            for config in env_configs():
                data = read_json_from_context(config)
                label = data.get("environmentName") or config.stem
                config_options.append(f'<option value="{html.escape(str(config))}">{html.escape(label)} - {html.escape(config.name)}</option>')
            action_options = "".join(f'<option value="{html.escape(action)}">{html.escape(action)}</option>' for action in ACTION_ORDER)
            default_config = str(env_configs()[0]) if env_configs() else ""
            default_action = ACTION_ORDER[0]
            runner_hint = "bash scripts/zt.sh" if shutil.which("bash") else "powershell scripts/zt.ps1"
            body = f"""
<div class="section-head">
  <div>
    <h2>CLI</h2>
    <div class="section-copy">Run approved ZeroTouch commands from inside the console.</div>
  </div>
</div>
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Command Mode</div><div class="ops-value">Controlled Runner</div></div>
  <div class="ops-item"><div class="ops-label">Allowed Commands</div><div class="ops-value">{len(ACTION_ORDER)} safe actions</div></div>
  <div class="ops-item"><div class="ops-label">Apply Commands</div><div class="ops-value">Blocked</div></div>
  <div class="ops-item"><div class="ops-label">Runner</div><div class="ops-value">{html.escape(runner_hint)}</div></div>
</section>
<section class="panel">
  <form method="post" action="/cli/run">
    <table>
      <thead><tr><th>Control</th><th>Selection</th></tr></thead>
      <tbody>
        <tr><td>Environment</td><td><div class="field"><select name="config">{''.join(config_options)}</select></div></td></tr>
        <tr><td>Command</td><td><div class="field"><select name="action">{action_options}</select></div></td></tr>
        <tr><td>Preview</td><td><pre>{html.escape(runner_hint)} {html.escape(default_action)} --config {html.escape(default_config)}</pre></td></tr>
        <tr><td></td><td><button>Run command</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">This is not an unrestricted shell. It only runs dashboard-safe framework commands and captures output inline.</div>
"""
            self.send_html(page("CLI - NKP ZeroTouch Console", body, "cli"))
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
            self.send_html(page("Edit Environment - NKP ZeroTouch Console", body, "environments"))
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
            self.send_html(page("Delete Environment - NKP ZeroTouch Console", body, "environments"))
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
            self.send_html(page("Runs - NKP ZeroTouch Console", body, "runs"))
            return
        if parsed.path == "/artifacts":
            artifact_rows = []
            for env_dir in sorted((ZT / "environments").glob("*")) if (ZT / "environments").exists() else []:
                if not env_dir.is_dir():
                    continue
                artifact_rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(env_dir.name)}</div><div class='env-file'>{html.escape(str(env_dir.relative_to(ROOT)))}</div></td>"
                    f"<td>{file_count(env_dir / 'generated')}</td>"
                    f"<td>{file_count(env_dir / 'reports')}</td>"
                    f"<td>{file_count(env_dir / 'state')}</td>"
                    f"<td>{html.escape(mtime_label(env_dir))}</td></tr>"
                )
            body = f"""
<div class="section-head">
  <div>
    <h2>Artifacts</h2>
    <div class="section-copy">Generated plans, reports, state files, and staged environment outputs.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Environment</th><th>Generated</th><th>Reports</th><th>State</th><th>Updated</th></tr></thead>
    <tbody>{''.join(artifact_rows) or '<tr><td colspan="5" class="muted">No environment artifacts found. Run prepare or generate first.</td></tr>'}</tbody>
  </table>
</section>
"""
            self.send_html(page("Artifacts - NKP ZeroTouch Console", body, "artifacts"))
            return
        if parsed.path == "/actions":
            action_rows = "".join(
                f"<tr><td><code>{html.escape(action)}</code></td><td>Dashboard-safe</td><td><span class='chip ok'>Enabled</span></td></tr>"
                for action in ACTION_ORDER
            )
            blocked_rows = "".join(
                f"<tr><td><code>{action}</code></td><td>CLI-only guarded operation</td><td><span class='chip warn'>Blocked in console</span></td></tr>"
                for action in ["registry --apply", "deploy --apply", "destroy --apply --confirm-destroy"]
            )
            body = f"""
<div class="section-head">
  <div>
    <h2>Safe Actions</h2>
    <div class="section-copy">Console-enabled actions are intentionally limited to non-destructive workflows.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Action</th><th>Scope</th><th>Status</th></tr></thead>
    <tbody>{action_rows}{blocked_rows}</tbody>
  </table>
</section>
<div class="notice">Live apply and destructive workflows remain CLI-only so operators must explicitly run guarded commands from a prepared shell.</div>
"""
            self.send_html(page("Safe Actions - NKP ZeroTouch Console", body, "actions"))
            return
        if parsed.path == "/audit":
            audit_rows = []
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
            self.send_html(page("Audit Trail - NKP ZeroTouch Console", body, "audit"))
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
            self.send_html(page("Connections - NKP ZeroTouch Console", body, "connections"))
            return
        if parsed.path == "/settings/new-environment":
            body = """
<div class="section-head">
  <div>
    <h2>New Environment</h2>
    <div class="section-copy">Create a deployment profile from the connected, proxied, or air-gapped templates.</div>
  </div>
</div>
<section class="panel">
  <form method="post" action="/settings/new-environment/create">
    <table>
      <thead><tr><th>Field</th><th>Input</th></tr></thead>
      <tbody>
        <tr><td>Environment name</td><td><div class="field"><input name="name" value="lab-new" aria-label="Environment name"></div></td></tr>
        <tr><td>Environment type</td><td><div class="field"><select name="type" aria-label="Environment type"><option>connected</option><option>proxied</option><option>air-gapped</option></select></div></td></tr>
        <tr><td></td><td><button>Create environment</button></td></tr>
      </tbody>
    </table>
  </form>
</section>
<div class="notice">This creates a config under <code>configs/environments/</code> using the same framework helper as <code>scripts/new-env.*</code>.</div>
"""
            self.send_html(page("New Environment - NKP ZeroTouch Console", body, "new-environment"))
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
<div class="notice">Accounts and roles are saved to <code>.zt/settings/rbac.json</code>. Passwords and login enforcement are intentionally not implemented yet.</div>
"""
            self.send_html(page("RBAC - NKP ZeroTouch Console", body, "rbac"))
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
            self.send_html(page("Database - NKP ZeroTouch Console", body, "database"))
            return
        if parsed.path == "/about":
            version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "dev"
            body = f"""
<div class="section-head">
  <div>
    <h2>About</h2>
    <div class="section-copy">Veridian ZeroTouch console for Nutanix Kubernetes Platform deployment orchestration.</div>
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
            self.send_html(page("About - NKP ZeroTouch Console", body, "about"))
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
            SESSIONS[token] = {"username": username, "role": account.get("role", "Operator"), "loginAt": time.time()}
            self.send_redirect("/", {"Set-Cookie": f"zt_session={token}; Path=/; HttpOnly; SameSite=Lax"})
            return

        if not self.require_login(parsed):
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
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Connections</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/connections'>Back to connections</a>"
            self.send_html(page("Connections Saved", body, "connections"))
            return

        if parsed.path == "/settings/new-environment/create":
            name = form_value(form, "name")
            env_type = form_value(form, "type", "connected")
            code, out, err = create_environment(name, env_type)
            status_class = "ok" if code == 0 else "warn"
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
            body = "<section class='metric'><div class='metric-label'>Settings Saved</div><div class='metric-value'>Database</div><div class='metric-foot'><span class='chip ok'>Saved locally</span></div></section><a class='back-link' href='/settings/database'>Back to database</a>"
            self.send_html(page("Database Saved", body, "database"))
            return

        if parsed.path == "/cli/run":
            action = form_value(form, "action")
            config_raw = form_value(form, "config")
            if action not in SAFE_ACTIONS:
                self.send_html(page("CLI Blocked", "<h2>Command blocked</h2><div class='notice'>Only dashboard-safe CLI actions can run from the console.</div><a class='back-link' href='/cli'>Back to CLI</a>", "cli"), status=403)
                return
            try:
                config = resolve_env_config(config_raw)
            except Exception as exc:
                self.send_html(page("CLI Error", f"<h2>Invalid environment</h2><div class='notice'>{html.escape(str(exc))}</div><a class='back-link' href='/cli'>Back to CLI</a>", "cli"), status=400)
                return
            code, out, err = run_action(action, config)
            status_class = "ok" if code == 0 else "warn"
            runner_hint = "bash scripts/zt.sh" if shutil.which("bash") else "powershell scripts/zt.ps1"
            body = f"""
<div class="section-head">
  <div>
    <h2>CLI Result</h2>
    <div class="section-copy">Controlled command output for <code>{html.escape(config.name)}</code>.</div>
  </div>
</div>
<section class="ops-strip">
  <div class="ops-item"><div class="ops-label">Command</div><div class="ops-value">{html.escape(action)}</div></div>
  <div class="ops-item"><div class="ops-label">Environment</div><div class="ops-value">{html.escape(config.stem)}</div></div>
  <div class="ops-item"><div class="ops-label">Exit Code</div><div class="ops-value"><span class="chip {status_class}">{code}</span></div></div>
  <div class="ops-item"><div class="ops-label">Runner</div><div class="ops-value">{html.escape(runner_hint)}</div></div>
</section>
<section class="panel">
  <table>
    <thead><tr><th>Command Preview</th></tr></thead>
    <tbody><tr><td><pre>{html.escape(runner_hint)} {html.escape(action)} --config {html.escape(str(config))}</pre></td></tr></tbody>
  </table>
</section>
<div class="section-head"><div><h2>Output</h2><div class="section-copy">Captured stdout and stderr.</div></div></div>
<pre>{html.escape(out + err)}</pre>
<a class="back-link" href="/cli">Back to CLI</a>
"""
            self.send_html(page("CLI Result - NKP ZeroTouch Console", body, "cli"), status=200 if code == 0 else 500)
            return

        if parsed.path == "/environment/edit/save":
            try:
                config = resolve_env_config(form_value(form, "config"))
                data = load_env_yaml(config)
                field_map = {
                    "environment_name": (["environment", "name"], str),
                    "environment_type": (["environment", "type"], str),
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
                write_env_yaml(config, data)
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
            self.send_html(page("Environment Deleted", body, "environments"))
            return

        if parsed.path != "/action":
            self.send_html(page("Not Found", "<h2>Not found</h2>"), status=404)
            return

        action = form.get("action", [""])[0]
        config = Path(form.get("config", [""])[0])
        if action not in SAFE_ACTIONS:
            self.send_html(page("Blocked", "<h2>Action is not dashboard-safe.</h2>"), status=403)
            return
        code, out, err = run_action(action, config)
        status_class = "ok" if code == 0 else "warn"
        body = (
            "<div class='result-layout'>"
            f"<section class='metric'><div class='metric-label'>Action Result</div><div class='metric-value'>{html.escape(action)}</div>"
            f"<div class='metric-foot'><span class='chip {status_class}'>Exit code {code}</span></div></section>"
            f"<pre>{html.escape(out + err)}</pre>"
            "<a class='back-link' href='/'>Back to dashboard</a>"
            "</div>"
        )
        self.send_html(page("Action Result", body, "actions"), status=200 if code == 0 else 500)


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
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
