import http.cookiejar
import os
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

from dashboard import app


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProbeHandler(BaseHTTPRequestHandler):
    expected_path = "/"
    expected_auth = ""
    seen_paths = []
    seen_auth = []

    def log_message(self, format, *args):
        return

    def do_GET(self):
        type(self).seen_paths.append(self.path)
        type(self).seen_auth.append(self.headers.get("Authorization", ""))
        if self.path == type(self).expected_path and self.headers.get("Authorization", "") == type(self).expected_auth:
            self.send_response(200)
        else:
            self.send_response(401)
        self.end_headers()


class JsonHandler(BaseHTTPRequestHandler):
    expected_path = "/"
    payload = {}

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path != type(self).expected_path:
            self.send_response(404)
            self.end_headers()
            return
        body = app.json.dumps(type(self).payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_probe_server(expected_path, expected_auth):
    class Handler(ProbeHandler):
        pass

    Handler.expected_path = expected_path
    Handler.expected_auth = expected_auth
    Handler.seen_paths = []
    Handler.seen_auth = []
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, Handler


def start_json_server(expected_path, payload):
    class Handler(JsonHandler):
        pass

    Handler.expected_path = expected_path
    Handler.payload = payload
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


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

        page_paths = ["/", "/setup", "/plan-review", "/kubeconfig", "/drift", "/locks", "/change-records", "/backups", "/restore", "/evidence", "/production-readiness", "/release-channels"]
        configs = app.env_configs()
        if configs:
            page_paths.append(f"/environment/view?config={urllib.parse.quote(str(configs[0]))}")

        for path in page_paths:
            status, content_type, body = request(opener, base_url, path)
            assert status == 200
            assert "text/html" in content_type
            assert "NKP ZeroTouch" in body
            assert "data-theme-toggle" in body

        for path in ["/api/status", "/api/preflight", "/api/evidence", "/api/environments", "/api/jobs", "/api/locks", "/api/change-records", "/api/production-readiness"]:
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


def test_preflight_evidence_records_summarize_endpoint_status(tmp_path):
    original_zt = app.ZT
    app.ZT = tmp_path / ".zt"
    try:
        app.write_json(
            app.ZT / "preflight" / "lab-connected.json",
            {
                "capturedAt": "2026-07-13T19:00:00Z",
                "config": "configs/environments/connected.example.yaml",
                "environment": "lab-connected",
                "type": "connected",
                "summary": {"failures": 0, "warnings": 1},
                "endpoints": [
                    {"name": "Prism Central", "endpoint": "https://pc.example.local:9440", "required": True, "status": "warn", "detail": "timed out"}
                ],
            },
        )

        records = app.preflight_evidence_records()

        assert records[0]["environment"] == "lab-connected"
        assert records[0]["summary"]["warnings"] == 1
        assert records[0]["endpoints"][0]["name"] == "Prism Central"
        assert records[0]["endpoints"][0]["status"] == "warn"
    finally:
        app.ZT = original_zt


def test_evidence_packs_read_manifest_and_archive(tmp_path):
    original_zt = app.ZT
    app.ZT = tmp_path / ".zt"
    try:
        pack_dir = app.ZT / "evidence" / "lab-connected-20260713-120000"
        pack_dir.mkdir(parents=True)
        archive = app.ZT / "evidence" / "lab-connected-20260713-120000.zip"
        archive.write_text("archive placeholder", encoding="utf-8")
        app.write_json(
            pack_dir / "evidence-manifest.json",
            {
                "createdAt": "2026-07-13T12:00:00Z",
                "environment": "lab-connected",
                "type": "connected",
                "cluster": "nkp-mgmt-connected",
                "redaction": {
                    "rawKubeconfigExcluded": True,
                    "secretValuesExcluded": True,
                    "operatorReviewRequired": True,
                },
                "files": ["environment/reports/verification-evidence.json"],
            },
        )

        packs = app.evidence_packs()

        assert len(packs) == 1
        assert packs[0]["environment"] == "lab-connected"
        assert packs[0]["archive"] == str(archive)
        assert packs[0]["fileCount"] == 1
        assert packs[0]["redaction"]["rawKubeconfigExcluded"] is True
    finally:
        app.ZT = original_zt


def test_preflight_evidence_status_requires_clean_latest_record(tmp_path):
    original_zt = app.ZT
    app.ZT = tmp_path / ".zt"
    try:
        ok, detail = app.preflight_evidence_status("lab-connected")
        assert ok is False
        assert "missing" in detail

        app.write_json(
            app.ZT / "preflight" / "lab-connected.json",
            {
                "capturedAt": "2026-07-13T19:00:00Z",
                "environment": "lab-connected",
                "summary": {"failures": 0, "warnings": 1},
                "endpoints": [{"name": "Prism Central", "status": "pass", "detail": "pc:9440"}],
            },
        )
        ok, detail = app.preflight_evidence_status("lab-connected")
        assert ok is False
        assert "1 warning" in detail

        app.write_json(
            app.ZT / "preflight" / "lab-connected.json",
            {
                "capturedAt": "2026-07-13T19:05:00Z",
                "environment": "lab-connected",
                "summary": {"failures": 0, "warnings": 0},
                "endpoints": [{"name": "Prism Central", "status": "pass", "detail": "pc:9440"}],
            },
        )
        ok, detail = app.preflight_evidence_status("lab-connected")
        assert ok is True
        assert "clean" in detail
    finally:
        app.ZT = original_zt


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


def test_dashboard_file_session_store_persists_and_logs_out():
    rbac_path = app.SETTINGS / "rbac.json"
    integrations_path = app.SETTINGS / "integrations.json"
    sessions_path = app.SETTINGS / "sessions.json"
    original_rbac = rbac_path.read_text(encoding="utf-8") if rbac_path.exists() else None
    original_integrations = integrations_path.read_text(encoding="utf-8") if integrations_path.exists() else None
    original_sessions = sessions_path.read_text(encoding="utf-8") if sessions_path.exists() else None
    original_memory_sessions = dict(app.SESSIONS)

    rbac = app.default_rbac()
    account = {
        "username": "file-session-smoke",
        "displayName": "File Session Smoke",
        "role": "Admin",
        "status": "active",
    }
    account.update(app.password_record("FileSessionSmoke-Local-123!"))
    rbac["accounts"] = [account]
    app.write_json(rbac_path, rbac)
    app.save_setting("integrations", {**app.default_integrations(), "session_store": "file"})
    app.SESSIONS.clear()

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    no_redirect_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar), NoRedirect)

    try:
        status, _, _ = request(
            no_redirect_opener,
            base_url,
            "/login",
            {"username": "file-session-smoke", "password": "FileSessionSmoke-Local-123!"},
            allow_error=True,
        )
        assert status == 303
        persisted = app.read_json(sessions_path)
        assert persisted and persisted.get("sessions")

        app.SESSIONS.clear()
        status, content_type, body = request(opener, base_url, "/")
        assert status == 200
        assert "text/html" in content_type
        assert "file-session-smoke (Admin)" in body

        status, _, _ = request(no_redirect_opener, base_url, "/logout", allow_error=True)
        assert status == 303
        assert not (app.read_json(sessions_path) or {}).get("sessions")
    finally:
        server.shutdown()
        server.server_close()
        app.SESSIONS.clear()
        app.SESSIONS.update(original_memory_sessions)
        if original_rbac is None:
            rbac_path.unlink(missing_ok=True)
        else:
            rbac_path.write_text(original_rbac, encoding="utf-8")
        if original_integrations is None:
            integrations_path.unlink(missing_ok=True)
        else:
            integrations_path.write_text(original_integrations, encoding="utf-8")
        if original_sessions is None:
            sessions_path.unlink(missing_ok=True)
        else:
            sessions_path.write_text(original_sessions, encoding="utf-8")


def test_authenticated_prism_probe_uses_credentials():
    old_user = os.environ.get("NUTANIX_PC_USERNAME")
    old_password = os.environ.get("NUTANIX_PC_PASSWORD")
    server, handler = start_probe_server("/api/nutanix/v3/versions", "Basic cGMtdXNlcjpwYy1wYXNz")
    try:
        os.environ["NUTANIX_PC_USERNAME"] = "pc-user"
        os.environ["NUTANIX_PC_PASSWORD"] = "pc-pass"
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"

        status, note = app.prism_authenticated_status(endpoint)

        assert status == "ok"
        assert "HTTP 200" in note
        assert handler.seen_paths == ["/api/nutanix/v3/versions"]
        assert handler.seen_auth == ["Basic cGMtdXNlcjpwYy1wYXNz"]
    finally:
        server.shutdown()
        server.server_close()
        if old_user is None:
            os.environ.pop("NUTANIX_PC_USERNAME", None)
        else:
            os.environ["NUTANIX_PC_USERNAME"] = old_user
        if old_password is None:
            os.environ.pop("NUTANIX_PC_PASSWORD", None)
        else:
            os.environ["NUTANIX_PC_PASSWORD"] = old_password


def test_authenticated_registry_probe_uses_credentials():
    old_user = os.environ.get("ZT_REGISTRY_USERNAME")
    old_password = os.environ.get("ZT_REGISTRY_PASSWORD")
    server, handler = start_probe_server("/v2/", "Basic cmVnLXVzZXI6cmVnLXBhc3M=")
    try:
        os.environ["ZT_REGISTRY_USERNAME"] = "reg-user"
        os.environ["ZT_REGISTRY_PASSWORD"] = "reg-pass"
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"

        status, note = app.registry_authenticated_status(endpoint)

        assert status == "ok"
        assert "HTTP 200" in note
        assert handler.seen_paths == ["/v2/"]
        assert handler.seen_auth == ["Basic cmVnLXVzZXI6cmVnLXBhc3M="]
    finally:
        server.shutdown()
        server.server_close()
        if old_user is None:
            os.environ.pop("ZT_REGISTRY_USERNAME", None)
        else:
            os.environ["ZT_REGISTRY_USERNAME"] = old_user
        if old_password is None:
            os.environ.pop("ZT_REGISTRY_PASSWORD", None)
        else:
            os.environ["ZT_REGISTRY_PASSWORD"] = old_password


def test_authenticated_probes_warn_without_credentials():
    old_pc_user = os.environ.pop("NUTANIX_PC_USERNAME", None)
    old_pc_password = os.environ.pop("NUTANIX_PC_PASSWORD", None)
    old_reg_user = os.environ.pop("ZT_REGISTRY_USERNAME", None)
    old_reg_password = os.environ.pop("ZT_REGISTRY_PASSWORD", None)
    try:
        prism_status, prism_note = app.prism_authenticated_status("https://pc.lab.local:9440")
        registry_status, registry_note = app.registry_authenticated_status("registry.lab.local")

        assert prism_status == "warn"
        assert "NUTANIX_PC_USERNAME/NUTANIX_PC_PASSWORD" in prism_note
        assert registry_status == "warn"
        assert "ZT_REGISTRY_USERNAME/ZT_REGISTRY_PASSWORD" in registry_note
    finally:
        if old_pc_user is not None:
            os.environ["NUTANIX_PC_USERNAME"] = old_pc_user
        if old_pc_password is not None:
            os.environ["NUTANIX_PC_PASSWORD"] = old_pc_password
        if old_reg_user is not None:
            os.environ["ZT_REGISTRY_USERNAME"] = old_reg_user
        if old_reg_password is not None:
            os.environ["ZT_REGISTRY_PASSWORD"] = old_reg_password


def test_oidc_readiness_validates_discovery_metadata():
    server = start_json_server(
        "/.well-known/openid-configuration",
        {
            "issuer": "",
            "authorization_endpoint": "",
            "token_endpoint": "",
            "jwks_uri": "",
        },
    )
    try:
        issuer = f"http://127.0.0.1:{server.server_address[1]}"
        JsonHandler.payload = {}
        server.RequestHandlerClass.payload = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks.json",
        }
        status, note, metadata, checks = app.oidc_readiness({
            "oidc_enabled": "true",
            "oidc_issuer": issuer,
            "oidc_client_id": "zt-console",
            "oidc_redirect_uri": "http://localhost:18080/login/oidc/callback",
        })

        assert status == "ok"
        assert "discovery ready" in note
        assert metadata["issuer"] == issuer
        assert all(passed for _, passed, _ in checks)
    finally:
        server.shutdown()
        server.server_close()


def test_oidc_readiness_warns_on_issuer_mismatch_and_missing_endpoints():
    server = start_json_server(
        "/.well-known/openid-configuration",
        {
            "issuer": "https://different-issuer.example.test",
            "authorization_endpoint": "",
            "token_endpoint": "",
        },
    )
    try:
        issuer = f"http://127.0.0.1:{server.server_address[1]}"
        status, note, _, checks = app.oidc_readiness({
            "oidc_enabled": "true",
            "oidc_issuer": issuer,
            "oidc_client_id": "zt-console",
            "oidc_redirect_uri": "http://localhost:18080/login/oidc/callback",
        })

        assert status == "warn"
        assert "metadata incomplete" in note
        failed = {name: detail for name, passed, detail in checks if not passed}
        assert failed["Issuer match"] == "https://different-issuer.example.test"
        assert failed["authorization_endpoint"] == "missing"
        assert failed["jwks_uri"] == "missing"
    finally:
        server.shutdown()
        server.server_close()


def test_oidc_login_page_shows_readiness_contract():
    rbac_path = app.SETTINGS / "rbac.json"
    integrations_path = app.SETTINGS / "integrations.json"
    original_rbac = rbac_path.read_text(encoding="utf-8") if rbac_path.exists() else None
    original_integrations = integrations_path.read_text(encoding="utf-8") if integrations_path.exists() else None
    server = start_json_server(
        "/.well-known/openid-configuration",
        {
            "issuer": "",
            "authorization_endpoint": "",
            "token_endpoint": "",
            "jwks_uri": "",
        },
    )
    try:
        issuer = f"http://127.0.0.1:{server.server_address[1]}"
        server.RequestHandlerClass.payload = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks.json",
        }
        app.save_setting("integrations", {
            **app.default_integrations(),
            "oidc_enabled": "true",
            "oidc_issuer": issuer,
            "oidc_client_id": "zt-console",
        })

        dashboard_server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=dashboard_server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{dashboard_server.server_address[1]}"
        opener = urllib.request.build_opener()

        status, content_type, body = request(opener, base_url, "/login/oidc")

        assert status == 200
        assert "text/html" in content_type
        assert "Readiness Contract" in body
        assert "authorization_endpoint" in body
        assert "token validation" in body
    finally:
        server.shutdown()
        server.server_close()
        try:
            dashboard_server.shutdown()
            dashboard_server.server_close()
        except UnboundLocalError:
            pass
        if original_rbac is None:
            rbac_path.unlink(missing_ok=True)
        else:
            rbac_path.write_text(original_rbac, encoding="utf-8")
        if original_integrations is None:
            integrations_path.unlink(missing_ok=True)
        else:
            integrations_path.write_text(original_integrations, encoding="utf-8")


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


def test_production_gate_blocks_missing_preflight_evidence(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        config = tmp_path / "configs" / "environments" / "preflight-missing.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
environment:
  name: preflight-missing
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

        _, _, ok, checks = app.production_gate(config)

        assert ok is False
        preflight = [check for check in checks if check[0] == "Preflight evidence"][0]
        assert preflight[1] is False
        assert "missing" in preflight[2]
    finally:
        app.ZT = original_zt
        app.LOCKS = original_locks
        app.CHANGE_RECORDS = original_change_records


def test_verification_status_prefers_structured_evidence(tmp_path):
    original_zt = app.ZT
    app.ZT = tmp_path / ".zt"
    try:
        state = app.env_state("verified-evidence")
        reports = state["base"] / "reports"
        reports.mkdir(parents=True)
        (reports / "verification-summary.md").write_text("- pass: kubeconfig - captured\n", encoding="utf-8")
        app.write_json(reports / "component-health.json", [{"name": "legacy", "status": "warn", "detail": "old report"}])
        app.write_json(
            reports / "verification-evidence.json",
            {
                "checks": [{"name": "kubeconfig", "status": "pass", "detail": "captured"}],
                "liveVerification": {"attempted": True, "status": "pass", "log": "verify-kubectl.log"},
            },
        )

        ok, detail = app.verification_status(state)

        assert ok is True
        assert detail == "structured verification evidence passed"
    finally:
        app.ZT = original_zt


def test_verification_status_blocks_on_live_evidence_warning(tmp_path):
    original_zt = app.ZT
    app.ZT = tmp_path / ".zt"
    try:
        state = app.env_state("verified-live-warning")
        reports = state["base"] / "reports"
        reports.mkdir(parents=True)
        (reports / "verification-summary.md").write_text("- pass: kubeconfig - captured\n", encoding="utf-8")
        app.write_json(
            reports / "verification-evidence.json",
            {
                "checks": [{"name": "kubeconfig", "status": "pass", "detail": "captured"}],
                "liveVerification": {"attempted": True, "status": "warn", "log": "verify-kubectl.log"},
            },
        )

        ok, detail = app.verification_status(state)

        assert ok is False
        assert "live verification warn" in detail
        assert "verify-kubectl.log" in detail
    finally:
        app.ZT = original_zt


def test_production_gate_payload_serializes_checks(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        config = tmp_path / "configs" / "environments" / "payload-lab.yaml"
        config.parent.mkdir(parents=True)
        config.write_text(
            """
environment:
  name: payload-lab
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
  name: payload-cluster
  controlPlaneEndpointIp: 10.0.0.20
""",
            encoding="utf-8",
        )

        payload = app.production_gate_payload(config)

        assert payload["name"] == "payload-lab"
        assert payload["channel"] == "lab"
        assert payload["ready"] is False
        assert any(check["name"] == "Plan review" for check in payload["checks"])
        assert all(set(check) == {"name", "passed", "detail"} for check in payload["checks"])
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


def test_restore_plan_records_controls_and_metadata(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        backup_dir = app.ZT / "environments" / "restore-lab" / "backup" / "20260713-120000"
        for folder in ["state", "generated", "reports"]:
            target = backup_dir / folder
            target.mkdir(parents=True)
            (target / f"{folder}.txt").write_text(folder, encoding="utf-8")
        target_state = app.ZT / "environments" / "restore-lab"
        (target_state / "state").mkdir(parents=True, exist_ok=True)
        (target_state / "state" / "state.txt").write_text("current", encoding="utf-8")
        (target_state / "state" / "target-only.txt").write_text("current only", encoding="utf-8")
        app.write_json(
            target_state / "state" / "environment.json",
            {
                "environment": {"name": "restore-lab", "type": "connected"},
                "paths": {
                    "config": str(tmp_path / "restore-lab.yaml"),
                    "environmentRoot": str(target_state),
                },
            },
        )
        manifest = backup_dir / "backup-manifest.json"
        app.write_json(
            manifest,
            {
                "environment": "restore-lab",
                "createdAt": "2026-07-13T12:00:00Z",
                "source": str(target_state),
            },
        )

        plan_id, plan_path, metadata_path, metadata = app.build_restore_plan(manifest, {"username": "tester"})

        assert plan_id.startswith("restore-")
        plan_text = plan_path.read_text(encoding="utf-8")
        assert "Create a fresh backup before restoring: required" in plan_text
        assert "Target Identity Evidence" in plan_text
        assert "Dry-Run File Impact" in plan_text
        assert "would overwrite=1" in plan_text
        assert "Keep restore execution manual" in plan_text
        assert "state: present; files=1" in plan_text
        assert metadata["environment"] == "restore-lab"
        assert metadata["identityChecks"][0]["status"] == "pass"
        assert metadata["dryRunImpacts"][0]["overwriteCount"] == 1
        assert metadata["dryRunImpacts"][0]["newCount"] == 0
        assert metadata["dryRunImpacts"][0]["targetOnlyCount"] == 2
        assert "state.txt" in metadata["dryRunImpacts"][0]["overwritten"]
        assert metadata["changeRecord"]["action"] == "restore-plan"
        assert metadata["changeRecord"]["status"] == "planning"
        assert metadata["requiresCurrentBackup"] is True
        assert metadata["manualOnly"] is True
        assert metadata["blocked"] == []
        assert app.read_json(metadata_path)["components"][0]["name"] == "state"
        assert app.read_json(app.change_record_path(metadata["changeRecord"]["id"]))["restorePlan"] == str(plan_path)
    finally:
        app.ZT = original_zt
        app.LOCKS = original_locks
        app.CHANGE_RECORDS = original_change_records


def test_restore_plan_flags_active_locks_and_missing_components(tmp_path):
    original_zt = app.ZT
    original_locks = app.LOCKS
    original_change_records = app.CHANGE_RECORDS
    app.ZT = tmp_path / ".zt"
    app.LOCKS = app.ZT / "locks"
    app.CHANGE_RECORDS = app.ZT / "change-records"
    try:
        backup_dir = app.ZT / "environments" / "locked-lab" / "backup" / "20260713-120000"
        (backup_dir / "state").mkdir(parents=True)
        manifest = backup_dir / "backup-manifest.json"
        app.write_json(manifest, {"environment": "locked-lab", "createdAt": "2026-07-13T12:00:00Z"})
        app.write_job({"id": "job-lock-restore", "status": "running", "action": "restore", "environment": "locked-lab"})
        app.write_json(app.lock_path("locked-lab"), {"environment": "locked-lab", "jobId": "job-lock-restore", "action": "restore"})

        _, plan_path, _, metadata = app.build_restore_plan(manifest, {"username": "tester"})

        plan_text = plan_path.read_text(encoding="utf-8")
        assert "Confirm no active lock exists: blocked" in plan_text
        assert any("Active lock exists" in item for item in metadata["blocked"])
        assert any("backup components are missing" in item for item in metadata["blocked"])
        assert any("Identity check failed" in item for item in metadata["blocked"])
        assert metadata["changeRecord"]["status"] == "blocked"
    finally:
        app.ZT = original_zt
        app.LOCKS = original_locks
        app.CHANGE_RECORDS = original_change_records
