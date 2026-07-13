import http.cookiejar
import os
import threading
import urllib.parse
import urllib.request

from dashboard import app


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(opener, base_url, path, data=None, allow_error=False, timeout=30):
    encoded = None
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(f"{base_url}{path}", data=encoded, headers={"Connection": "close"})
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if not allow_error:
            raise
        try:
            body = exc.read().decode("utf-8")
            return exc.code, exc.headers.get("Content-Type", ""), body
        finally:
            exc.close()


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
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    no_redirect_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar), NoRedirect)

    try:
        status, _, _ = request(opener, base_url, "/login")
        assert status == 200
        status, _, _ = request(no_redirect_opener, base_url, "/login", {"username": "dashboard-smoke", "password": "DashboardSmoke-Local-123!"}, allow_error=True)
        assert status == 303

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


def test_plan_review_approval_requires_hashes(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        env_name = "hashless-review"
        state = app.env_state(env_name)
        generated = state["base"] / "generated"
        generated.mkdir(parents=True)
        (generated / "deploy-plan.md").write_text("plan\n", encoding="utf-8")
        app.write_json(state["base"] / "state" / "generate.json", {"generated": True})
        app.write_json(state["base"] / "state" / "plan-review.json", {"status": "approved", "reviewedBy": "admin"})

        label, status = app.plan_review_status(env_name, app.env_state(env_name))

        assert status == "warn"
        assert "hash" in label
    finally:
        app.ZT = original_zt
        app.LOCKS = original_locks
        app.CHANGE_RECORDS = original_change_records


def test_production_gate_blocks_verification_warnings(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        config = tmp_path / "configs" / "environments" / "verified-warning.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
environment:
  name: verified-warning
  type: connected
nkp:
  version: v2.17.1
  bundleType: standard
  bundlePath: /bundle
nutanix:
  prismCentralEndpoint: https://pc.example.local:9440
  clusterName: pe
  subnetName: vlan
  imageName: image
cluster:
  name: cluster
  controlPlaneEndpointIp: 10.0.0.10
registry:
  endpoint: registry.example.local
""",
            encoding="utf-8",
        )
        env_name = "verified-warning"
        state = app.env_state(env_name)
        app.write_json(state["base"] / "state" / "environment.json", {"paths": {"config": str(config)}, "environment": {"name": env_name}})
        app.write_json(state["base"] / "state" / "generate.json", {"generated": True})
        generated = state["base"] / "generated"
        generated.mkdir(parents=True)
        (generated / "deploy-plan.md").write_text("plan\n", encoding="utf-8")
        app.write_json(state["base"] / "state" / "plan-review.json", {"status": "approved", "planHashes": app.plan_hashes(env_name)})
        reports = state["base"] / "reports"
        reports.mkdir(parents=True)
        (reports / "verification-summary.md").write_text("- warn: kubeconfig - missing\n", encoding="utf-8")
        app.write_json(reports / "component-health.json", [{"name": "kubeconfig", "status": "warn", "detail": "missing"}])

        _, _, ok, checks = app.production_gate(config)

        assert ok is False
        verification = [check for check in checks if check[0] == "Verification"][0]
        assert verification[1] is False
        assert "kubeconfig" in verification[2]
    finally:
        app.ZT = original_zt
        app.LOCKS = original_locks
        app.CHANGE_RECORDS = original_change_records


def test_environment_identity_issues_detect_duplicates_and_state_mismatch(tmp_path):
    original_env_dir = app.ENV_DIR
    app.ENV_DIR = tmp_path / "configs" / "environments"
    app.ENV_DIR.mkdir(parents=True)
    try:
        existing = app.ENV_DIR / "connected.example.yaml"
        existing.write_text(
            """
environment:
  name: lab-connected
  type: connected
cluster:
  name: nkp-mgmt-connected
  controlPlaneEndpointIp: 10.10.10.50
""",
            encoding="utf-8",
        )
        current = app.ENV_DIR / "lab-new.yaml"
        data = {
            "environmentName": "lab-connected",
            "clusterName": "nkp-mgmt-connected",
            "controlPlaneEndpointIp": "10.10.10.50",
            "registryNamespace": "",
        }
        state = {"state": {"paths": {"config": str(existing)}, "environment": {"name": "lab-connected"}}}

        issues = app.environment_identity_issues(current, data, state)

        assert any("Environment name" in issue for issue in issues)
        assert any("Cluster name" in issue for issue in issues)
        assert any("API endpoint VIP" in issue for issue in issues)
        assert any("prepared from connected.example.yaml" in issue for issue in issues)
    finally:
        app.ENV_DIR = original_env_dir
