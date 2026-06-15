import http.cookiejar
import threading
import urllib.parse
import urllib.request

from dashboard import app


def request(opener, base_url, path, data=None, allow_error=False):
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(f"{base_url}{path}", data=encoded)
    try:
        with opener.open(req, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if not allow_error:
            raise
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def test_dashboard_pages_and_api_routes():
    rbac_path = app.SETTINGS / "rbac.json"
    original = rbac_path.read_text(encoding="utf-8") if rbac_path.exists() else None
    rbac = app.default_rbac()
    account = {
        "username": "dashboard-smoke",
        "displayName": "Dashboard Smoke",
        "role": "Admin",
        "status": "active",
    }
    account.update(app.password_record("DashboardSmoke-Local-123!"))
    rbac["accounts"] = [account]
    app.write_json(rbac_path, rbac)

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    try:
        status, _, _ = request(opener, base_url, "/login")
        assert status == 200
        status, _, _ = request(opener, base_url, "/login", {"username": "dashboard-smoke", "password": "DashboardSmoke-Local-123!"}, allow_error=True)
        assert status in {200, 303}

        for path in ["/", "/setup", "/plan-review", "/kubeconfig", "/drift", "/locks", "/change-records", "/backups", "/restore", "/production-readiness", "/release-channels"]:
            status, content_type, body = request(opener, base_url, path)
            assert status == 200
            assert "text/html" in content_type
            assert "NKP ZeroTouch" in body

        for path in ["/api/status", "/api/environments", "/api/jobs", "/api/locks", "/api/change-records"]:
            status, content_type, body = request(opener, base_url, path)
            assert status == 200
            assert "application/json" in content_type
            assert body.strip().startswith("{")
    finally:
        server.shutdown()
        server.server_close()
        if original is None:
            rbac_path.unlink(missing_ok=True)
        else:
            rbac_path.write_text(original, encoding="utf-8")
