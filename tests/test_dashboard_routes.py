import http.cookiejar
import os
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

        page_paths = ["/", "/setup", "/plan-review", "/kubeconfig", "/drift", "/locks", "/change-records", "/backups", "/restore", "/production-readiness", "/release-channels"]
        configs = app.env_configs()
        if configs:
            page_paths.append(f"/environment/view?config={urllib.parse.quote(str(configs[0]))}")

        for path in page_paths:
            status, content_type, body = request(opener, base_url, path)
            assert status == 200
            assert "text/html" in content_type
            assert "NKP ZeroTouch" in body
            assert "data-theme-toggle" in body

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


def test_dashboard_exposed_bootstrap_requires_token():
    rbac_path = app.SETTINGS / "rbac.json"
    original = rbac_path.read_text(encoding="utf-8") if rbac_path.exists() else None
    old_token = os.environ.pop("ZT_BOOTSTRAP_TOKEN", None)
    try:
        app.write_json(rbac_path, app.default_rbac())
        try:
            app.assert_bootstrap_safe("0.0.0.0")
        except RuntimeError as exc:
            assert "ZT_BOOTSTRAP_TOKEN" in str(exc)
        else:
            raise AssertionError("Expected exposed bootstrap without token to be blocked")

        os.environ["ZT_BOOTSTRAP_TOKEN"] = "local-test-token"
        app.assert_bootstrap_safe("0.0.0.0")
        app.assert_bootstrap_safe("127.0.0.1")
    finally:
        if old_token is None:
            os.environ.pop("ZT_BOOTSTRAP_TOKEN", None)
        else:
            os.environ["ZT_BOOTSTRAP_TOKEN"] = old_token
        if original is None:
            rbac_path.unlink(missing_ok=True)
        else:
            rbac_path.write_text(original, encoding="utf-8")


def test_dashboard_cli_apply_actions_require_apply_flag():
    fallback = "configs/environments/connected.example.yaml"

    try:
        app.parse_cli_command(f"deploy --config {fallback}", fallback)
    except ValueError as exc:
        assert "requires --apply" in str(exc)
    else:
        raise AssertionError("Expected deploy without --apply to be rejected")

    action, config, apply, confirm_destroy = app.parse_cli_command(f"deploy --apply --config {fallback}", fallback)
    assert action == "deploy"
    assert config.name == "connected.example.yaml"
    assert apply is True
    assert confirm_destroy is False


def test_dashboard_cli_destroy_requires_confirmation_flag():
    fallback = "configs/environments/connected.example.yaml"

    try:
        app.parse_cli_command(f"destroy --apply --config {fallback}", fallback)
    except ValueError as exc:
        assert "requires --confirm-destroy" in str(exc)
    else:
        raise AssertionError("Expected destroy without --confirm-destroy to be rejected")

    action, config, apply, confirm_destroy = app.parse_cli_command(
        f"destroy --apply --confirm-destroy --config {fallback}",
        fallback,
    )
    assert action == "destroy"
    assert config.name == "connected.example.yaml"
    assert apply is True
    assert confirm_destroy is True
