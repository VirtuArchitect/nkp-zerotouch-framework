#!/usr/bin/env python3
import html
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
ZT = ROOT / ".zt"
SAFE_ACTIONS = {"validate", "prepare", "generate", "verify", "backup", "runs"}
ACTION_ORDER = ["validate", "prepare", "generate", "verify", "backup", "runs"]


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def env_configs():
    return sorted((ROOT / "configs" / "environments").glob("*.yaml"))


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


def run_action(action, config):
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "zt.ps1"),
        action,
        "-Config",
        str(config),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    return completed.returncode, completed.stdout, completed.stderr


def page(title, body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #eef1f5;
      --panel: #ffffff;
      --panel-2: #f8fafc;
      --ink: #172033;
      --muted: #647089;
      --line: #d9e0ea;
      --line-strong: #c8d2df;
      --nav: #121826;
      --nav-2: #1b2435;
      --accent: #2563eb;
      --accent-soft: #e7efff;
      --good: #057a55;
      --good-soft: #dcfce7;
      --warn: #9a5b05;
      --warn-soft: #fef3c7;
      --bad: #b42318;
      --bad-soft: #fee4e2;
      --shadow: 0 16px 38px rgba(15, 23, 42, .08);
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
      padding: 22px 18px;
      border-right: 1px solid rgba(255,255,255,.08);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }}
    .brand-mark {{
      width: 34px; height: 34px; border-radius: 7px;
      display: grid; place-items: center;
      background: #2f6fed; color: #fff; font-weight: 800;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.16);
    }}
    .brand-title {{ font-size: 15px; font-weight: 700; letter-spacing: 0; }}
    .brand-subtitle {{ color: #aab4c6; font-size: 12px; margin-top: 2px; }}
    .nav-label {{ color: #7f8ba3; font-size: 11px; font-weight: 700; text-transform: uppercase; margin: 22px 10px 8px; }}
    .nav-item {{
      display: flex; align-items: center; gap: 10px;
      min-height: 38px; padding: 0 10px; border-radius: 7px;
      color: #d9e3f3; font-weight: 600;
    }}
    .nav-item.active {{ background: rgba(255,255,255,.1); color: #fff; }}
    .nav-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #3dd6a3; }}
    .content {{ min-width: 0; }}
    .topbar {{
      min-height: 68px; background: var(--panel);
      border-bottom: 1px solid var(--line);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 28px;
    }}
    .topbar h1 {{ margin: 0; font-size: 20px; font-weight: 750; letter-spacing: 0; }}
    .topbar-meta {{ display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 12px; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px 28px 42px; }}
    h2 {{ margin: 0; font-size: 16px; }}
    .section-head {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin: 24px 0 12px; }}
    .section-copy {{ color: var(--muted); font-size: 12px; margin-top: 3px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 14px; }}
    .metric {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
      padding: 16px; box-shadow: var(--shadow);
    }}
    .metric-label {{ color: var(--muted); font-size: 12px; font-weight: 650; }}
    .metric-value {{ margin-top: 8px; font-size: 28px; font-weight: 780; }}
    .metric-foot {{ margin-top: 4px; color: var(--muted); font-size: 12px; }}
    .panel {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
      box-shadow: var(--shadow); overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: 0; }}
    th {{
      background: var(--panel-2); color: #3b465a;
      font-size: 12px; font-weight: 750; text-transform: uppercase;
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
    .actions {{ display: flex; flex-wrap: wrap; gap: 7px; min-width: 330px; }}
    .actions form {{ display: inline; }}
    button {{
      min-height: 32px; border: 1px solid var(--line-strong); background: #fff;
      padding: 0 10px; border-radius: 6px; cursor: pointer;
      color: #263449; font-weight: 700; font-size: 12px;
    }}
    button:hover {{ background: var(--accent-soft); border-color: #9bb8f5; color: #1746a2; }}
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
    .result-layout {{ display: grid; gap: 16px; }}
    .back-link {{ display: inline-flex; align-items: center; margin-top: 16px; font-weight: 700; }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: none; }}
      .topbar {{ align-items: flex-start; flex-direction: column; gap: 10px; padding: 16px 20px; }}
      main {{ padding: 18px 16px 32px; }}
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .actions {{ min-width: 360px; }}
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
      <div class="brand-mark">NKP</div>
      <div>
        <div class="brand-title">ZeroTouch</div>
        <div class="brand-subtitle">Deployment Console</div>
      </div>
    </div>
    <div class="nav-label">Operations</div>
    <div class="nav-item active"><span class="nav-dot"></span>Environments</div>
    <div class="nav-item">Runs</div>
    <div class="nav-item">Artifacts</div>
    <div class="nav-label">Governance</div>
    <div class="nav-item">Safe Actions</div>
    <div class="nav-item">Audit Trail</div>
  </aside>
  <div class="content">
    <div class="topbar">
      <div>
        <h1>NKP ZeroTouch Console</h1>
        <div class="section-copy">Nutanix Kubernetes Platform deployment orchestration</div>
      </div>
      <div class="topbar-meta">
        <span class="badge connected">Console Online</span>
        <span>CLI apply actions disabled</span>
      </div>
    </div>
    <main>{body}</main>
  </div>
</div>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, content, status=200):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
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
                    f'<form method="post" action="/action"><input type="hidden" name="action" value="{a}"><input type="hidden" name="config" value="{html.escape(str(config))}"><button>{a}</button></form> '
                    for a in ACTION_ORDER
                )
                rows.append(
                    f"<tr><td><div class='env-name'>{html.escape(name)}</div><div class='env-file'>{html.escape(config.name)}</div></td>"
                    f"<td><span class='badge {html.escape(env_type)}'>{html.escape(env_type)}</span></td>"
                    f"<td><span class='chip {'ok' if prepared else 'warn'}'>{'Ready' if prepared else 'Pending'}</span></td>"
                    f"<td><span class='chip {'ok' if generated else 'warn'}'>{'Generated' if generated else 'Pending'}</span></td>"
                    f"<td><span class='chip {'ok' if report else 'warn'}'>{'Available' if report else 'Missing'}</span></td>"
                    f"<td class='actions'>{buttons}</td></tr>"
                )
            runs = sorted((ZT / "runs").glob("*/summary.md")) if (ZT / "runs").exists() else []
            recent_runs = list(reversed(runs[-10:]))
            run_rows = "".join(
                f"<li><code>{html.escape(p.parent.name)}</code><span class='muted'>summary.md</span></li>"
                for p in recent_runs
            )
            body = f"""
<section class="summary-grid">
  <div class="metric"><div class="metric-label">Environments</div><div class="metric-value">{env_total}</div><div class="metric-foot">configured deployment targets</div></div>
  <div class="metric"><div class="metric-label">Prepared</div><div class="metric-value">{prepared_total}</div><div class="metric-foot">workspace states available</div></div>
  <div class="metric"><div class="metric-label">Generated</div><div class="metric-value">{generated_total}</div><div class="metric-foot">artifact sets created</div></div>
  <div class="metric"><div class="metric-label">Reports</div><div class="metric-value">{report_total}</div><div class="metric-foot">verification summaries present</div></div>
</section>

<div class="section-head">
  <div>
    <h2>Environments</h2>
    <div class="section-copy">Validated deployment profiles for connected, proxied, and air-gapped NKP installs.</div>
  </div>
</div>
<section class="panel">
  <table>
    <thead><tr><th>Name</th><th>Type</th><th>Prepared</th><th>Generated</th><th>Report</th><th>Safe Actions</th></tr></thead>
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
            self.send_html(page("NKP ZeroTouch Console", body))
            return
        self.send_html(page("Not Found", "<h2>Not found</h2>"), status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/action":
            self.send_html(page("Not Found", "<h2>Not found</h2>"), status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
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
        self.send_html(page("Action Result", body), status=200 if code == 0 else 500)


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
