#!/usr/bin/env python3
import html
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
ZT = ROOT / ".zt"
SAFE_ACTIONS = {"validate", "prepare", "generate", "verify", "backup", "runs"}


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
    body {{ margin: 0; font: 14px/1.45 system-ui, Segoe UI, sans-serif; color: #1f2937; background: #f6f7f9; }}
    header {{ background: #111827; color: white; padding: 16px 24px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin-top: 28px; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8dee6; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; font-weight: 650; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 14px; overflow: auto; border-radius: 6px; }}
    .actions form {{ display: inline; }}
    button {{ border: 1px solid #9ca3af; background: white; padding: 6px 10px; border-radius: 6px; cursor: pointer; }}
    button:hover {{ background: #eef2ff; }}
    .muted {{ color: #6b7280; }}
    .ok {{ color: #047857; font-weight: 650; }}
    .warn {{ color: #b45309; font-weight: 650; }}
  </style>
</head>
<body>
<header><h1>NKP ZeroTouch Console</h1></header>
<main>{body}</main>
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
            for config in env_configs():
                data = read_json_from_context(config)
                name = data.get("environmentName") or config.stem
                state = env_state(name)
                prepared = "yes" if state["state"] else "no"
                generated = "yes" if state["generate"] else "no"
                report = "yes" if state["verification"].exists() else "no"
                buttons = "".join(
                    f'<form method="post" action="/action"><input type="hidden" name="action" value="{a}"><input type="hidden" name="config" value="{html.escape(str(config))}"><button>{a}</button></form> '
                    for a in sorted(SAFE_ACTIONS)
                )
                rows.append(
                    f"<tr><td><code>{html.escape(name)}</code><br><span class='muted'>{html.escape(config.name)}</span></td>"
                    f"<td>{html.escape(data.get('environmentType', ''))}</td><td>{prepared}</td><td>{generated}</td><td>{report}</td><td class='actions'>{buttons}</td></tr>"
                )
            runs = sorted((ZT / "runs").glob("*/summary.md")) if (ZT / "runs").exists() else []
            run_rows = "".join(f"<li><code>{html.escape(p.parent.name)}</code></li>" for p in runs[-10:])
            body = f"""
<h2>Environments</h2>
<table><thead><tr><th>Name</th><th>Type</th><th>Prepared</th><th>Generated</th><th>Report</th><th>Safe Actions</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Recent Runs</h2>
<ul>{run_rows or '<li class="muted">No run summaries yet.</li>'}</ul>
<p class="muted">Destructive/apply actions are intentionally CLI-only.</p>
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
        body = f"<h2>{html.escape(action)}: exit {code}</h2><pre>{html.escape(out + err)}</pre><p><a href='/'>Back</a></p>"
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
    host = "127.0.0.1"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
