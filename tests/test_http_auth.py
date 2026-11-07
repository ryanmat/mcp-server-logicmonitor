# Description: Tests for opt-in inbound bearer authentication on the HTTP transport.
# Description: Covers gated paths, open probe paths, CORS preflight, and config validation.

import logging

import pytest

from tests.live_uvicorn import free_port, live_uvicorn

# 16 characters: the configured minimum, and below the length a secret scanner flags.
TOKEN = "http-auth-tok-16"
WRONG = "wrong-http-auth-token-999"


@pytest.fixture
def _set_env(monkeypatch):
    """Set required environment variables for HTTP app creation."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.delenv("LM_HTTP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("LM_CORS_ORIGINS", raising=False)


@pytest.fixture
def _set_env_with_auth(_set_env, monkeypatch):
    """Enable inbound auth with a known token."""
    monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", TOKEN)


def _client():
    """Build an httpx client bound to a freshly constructed ASGI app."""
    from httpx import ASGITransport, AsyncClient

    from lm_mcp.transport.http import create_asgi_app

    return AsyncClient(transport=ASGITransport(app=create_asgi_app()), base_url="http://localhost")


class TestHttpAuthRejection:
    """Requests without a valid token are rejected on gated paths."""

    @pytest.mark.asyncio
    async def test_mcp_missing_header_rejected(self, _set_env_with_auth):
        """POST /mcp with no Authorization header returns 401."""
        async with _client() as client:
            resp = await client.post(
                "/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )
        assert resp.status_code == 401
        assert "error" in resp.json()

    @pytest.mark.asyncio
    async def test_mcp_wrong_token_rejected(self, _set_env_with_auth):
        """POST /mcp with the wrong bearer token returns 401."""
        async with _client() as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={"Authorization": f"Bearer {WRONG}"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_401_includes_www_authenticate(self, _set_env_with_auth):
        """A 401 advertises the expected scheme."""
        async with _client() as client:
            resp = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
        assert resp.headers["www-authenticate"] == "Bearer"


class TestHttpAuthAccepted:
    """Requests carrying the configured token pass the middleware to the router."""

    @pytest.mark.asyncio
    async def test_mcp_correct_token_accepted(self, _set_env_with_auth):
        """POST /mcp with the token passes auth; the router has no /mcp route, so 404."""
        async with _client() as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        assert resp.status_code == 404


class TestHttpAuthOpenPaths:
    """Probe and info routes stay reachable without a token."""

    @pytest.mark.asyncio
    async def test_root_open_with_token_set(self, _set_env_with_auth):
        """GET / needs no header."""
        async with _client() as client:
            resp = await client.get("/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_open_with_token_set(self, _set_env_with_auth):
        """GET /health is not gated by auth.

        The 200-vs-503 outcome reflects component checks (create_asgi_app does
        not initialize the LM client, which create_http_server does), so the
        property under test is that auth never rejects the probe.
        """
        async with _client() as client:
            resp = await client.get("/health")
        assert resp.status_code != 401
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_healthz_open_with_token_set(self, _set_env_with_auth):
        """GET /healthz is not gated, so container healthchecks keep working."""
        async with _client() as client:
            resp = await client.get("/healthz")
        assert resp.status_code != 401
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_readyz_open_with_token_set(self, _set_env_with_auth):
        """GET /readyz is not gated, so readiness probes keep working."""
        async with _client() as client:
            resp = await client.get("/readyz")
        assert resp.status_code != 401
        assert resp.status_code in (200, 503)


class TestHttpAuthCors:
    """CORS preflight is answered before auth runs."""

    @pytest.mark.asyncio
    async def test_cors_preflight_bypasses_auth(self, _set_env_with_auth, monkeypatch):
        """OPTIONS preflight succeeds without a token; browsers cannot send one."""
        monkeypatch.setenv("LM_CORS_ORIGINS", "https://example.com")
        async with _client() as client:
            resp = await client.options(
                "/mcp",
                headers={
                    "Origin": "https://example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "https://example.com"


class TestHttpAuthDisabled:
    """With no token configured, behavior matches previous releases."""

    @pytest.mark.asyncio
    async def test_no_token_configured_allows_requests(self, _set_env):
        """POST /mcp with no header passes auth when no token is set; the router answers 404."""
        async with _client() as client:
            resp = await client.post(
                "/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )
        assert resp.status_code == 404

    def test_no_token_logs_warning(self, _set_env, caplog):
        """Building the app without a token warns that the surface is open."""
        from lm_mcp.transport.http import create_asgi_app

        with caplog.at_level(logging.WARNING, logger="lm_mcp.transport.http"):
            create_asgi_app()
        assert any("LM_HTTP_AUTH_TOKEN" in r.getMessage() for r in caplog.records)

    def test_token_set_no_warning(self, _set_env_with_auth, caplog):
        """No warning when inbound auth is configured."""
        from lm_mcp.transport.http import create_asgi_app

        with caplog.at_level(logging.WARNING, logger="lm_mcp.transport.http"):
            create_asgi_app()
        assert not any("LM_HTTP_AUTH_TOKEN" in r.getMessage() for r in caplog.records)


class TestHttpAuthConfig:
    """Token validation at config construction."""

    def test_short_token_rejected(self, _set_env, monkeypatch):
        """A token under the minimum length fails fast."""
        from pydantic import ValidationError

        from lm_mcp.config import LMConfig

        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", "short")
        with pytest.raises(ValidationError, match="16 characters"):
            LMConfig()

    def test_min_length_token_accepted(self, _set_env, monkeypatch):
        """Exactly the minimum length is accepted."""
        from lm_mcp.config import LMConfig

        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", "a" * 16)
        assert LMConfig().http_auth_token == "a" * 16

    def test_none_token_allowed(self, _set_env):
        """Unset means no inbound auth."""
        from lm_mcp.config import LMConfig

        assert LMConfig().http_auth_token is None

    def test_empty_token_treated_as_unset(self, _set_env, monkeypatch):
        """An empty value normalizes to None.

        docker-compose passes ${LM_HTTP_AUTH_TOKEN:-}, which delivers an empty
        string; without normalization the length check would reject every
        tokenless compose deployment.
        """
        from lm_mcp.config import LMConfig

        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", "")
        assert LMConfig().http_auth_token is None


class TestHttpAuthHardening:
    """Regressions from the adversarial review of the auth middleware."""

    @pytest.mark.asyncio
    async def test_scheme_is_case_insensitive(self, _set_env_with_auth):
        """RFC 7235 defines auth-scheme as case-insensitive; each form passes auth to a 404."""
        async with _client() as client:
            for scheme in ("Bearer", "bearer", "BEARER", "BeArEr"):
                resp = await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                    headers={"Authorization": f"{scheme} {TOKEN}"},
                )
                assert resp.status_code == 404, scheme

    @pytest.mark.asyncio
    async def test_wrong_scheme_still_rejected(self, _set_env_with_auth):
        """A non-bearer scheme carrying the token is still refused."""
        async with _client() as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={"Authorization": f"Basic {TOKEN}"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_open_paths_tolerate_trailing_slash(self, _set_env_with_auth):
        """Probes written with a trailing slash must not start 401ing.

        Starlette would redirect /healthz/ to /healthz, but the redirect never
        runs if auth rejects the request first.
        """
        async with _client() as client:
            for path in ("/healthz/", "/readyz/", "/health/"):
                resp = await client.get(path)
                assert resp.status_code != 401, path

    @pytest.mark.asyncio
    async def test_trailing_slash_does_not_open_gated_paths(self, _set_env_with_auth):
        """Slash tolerance must not become a bypass."""
        async with _client() as client:
            for path in ("/mcp/", "/api/v1/analyze/", "/healthz/../mcp"):
                resp = await client.post(path, json={})
                assert resp.status_code == 401, path

    def test_token_whitespace_is_stripped(self, _set_env, monkeypatch):
        """A token from a secret file or .env line often carries a newline.

        Accepting it verbatim would 401 every client forever, since HTTP
        parsers strip optional whitespace from header values.
        """
        from lm_mcp.config import LMConfig

        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", f"{TOKEN}\n")
        assert LMConfig().http_auth_token == TOKEN

    def test_whitespace_only_token_is_unset_and_warns(self, _set_env, monkeypatch, caplog):
        """Spaces must not satisfy the length requirement.

        Blank means no auth, the same rule as an empty value, so the operator
        gets the startup warning rather than a server that looks protected.
        """
        from lm_mcp.config import LMConfig
        from lm_mcp.transport.http import create_asgi_app

        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", " " * 20)
        assert LMConfig().http_auth_token is None

        with caplog.at_level(logging.WARNING, logger="lm_mcp.transport.http"):
            create_asgi_app()
        assert any("LM_HTTP_AUTH_TOKEN" in r.getMessage() for r in caplog.records)

    def test_rejected_token_not_echoed_in_error(self, _set_env, monkeypatch):
        """A rejected token must not reach tracebacks, logs, or /health bodies."""
        from pydantic import ValidationError

        from lm_mcp.config import LMConfig

        secret = "SUPERSECRET-short"[:15]
        monkeypatch.setenv("LM_HTTP_AUTH_TOKEN", secret)
        with pytest.raises(ValidationError) as exc:
            LMConfig()
        assert secret not in str(exc.value)

    def test_rejected_lm_credential_not_echoed_in_error(self, monkeypatch):
        """The same protection covers the LogicMonitor bearer token."""
        from pydantic import ValidationError

        from lm_mcp.config import LMConfig

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "SHORTCRED")
        monkeypatch.delenv("LM_HTTP_AUTH_TOKEN", raising=False)
        with pytest.raises(ValidationError) as exc:
            LMConfig()
        assert "SHORTCRED" not in str(exc.value)


@pytest.fixture
def live_server(monkeypatch):
    """A live uvicorn runner for this module's socket-level tests."""
    return live_uvicorn(monkeypatch)


@pytest.fixture
def _http_server_env(_set_env, monkeypatch):
    """Configure create_http_server for a live start with no optional integrations."""
    monkeypatch.delenv("LM_HTTP_ALLOW_UNAUTHENTICATED", raising=False)
    monkeypatch.setenv("LM_TRANSPORT", "http")


class TestUnauthenticatedBindRefusal:
    """R3.3: create_http_server refuses an unauthenticated non-loopback bind before binding."""

    async def test_non_loopback_without_token_refuses_before_binding(
        self, _http_server_env, monkeypatch, live_server
    ):
        """0.0.0.0 with no token fails with one line naming both variables; no server is built."""
        from pydantic import ValidationError

        from lm_mcp.transport.http import create_http_server

        monkeypatch.setenv("LM_HTTP_HOST", "0.0.0.0")
        monkeypatch.setenv("LM_HTTP_PORT", str(free_port("0.0.0.0")))
        with pytest.raises(ValidationError) as exc:
            async with live_server(create_http_server()):
                pass

        assert live_server.servers == []
        message = exc.value.errors()[0]["msg"]
        assert "\n" not in message
        assert "LM_HTTP_AUTH_TOKEN" in message
        assert "LM_HTTP_ALLOW_UNAUTHENTICATED" in message

    async def test_override_starts_and_logs_the_warning(
        self, _http_server_env, monkeypatch, live_server, caplog
    ):
        """With LM_HTTP_ALLOW_UNAUTHENTICATED=true the 0.0.0.0 bind starts and warns."""
        import httpx

        from lm_mcp.transport.http import create_http_server

        monkeypatch.setenv("LM_HTTP_HOST", "0.0.0.0")
        monkeypatch.setenv("LM_HTTP_PORT", str(free_port("0.0.0.0")))
        monkeypatch.setenv("LM_HTTP_ALLOW_UNAUTHENTICATED", "true")
        with caplog.at_level(logging.WARNING, logger="lm_mcp.transport.http"):
            async with (
                live_server(create_http_server()) as port,
                httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
            ):
                resp = await client.get("/healthz")

        assert resp.status_code == 200
        assert any(
            "Inbound HTTP authentication is disabled" in r.getMessage() for r in caplog.records
        )

    async def test_loopback_without_token_starts(self, _http_server_env, monkeypatch, live_server):
        """A loopback bind needs no token."""
        import httpx

        from lm_mcp.transport.http import create_http_server

        monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")
        monkeypatch.setenv("LM_HTTP_PORT", str(free_port("127.0.0.1")))
        async with (
            live_server(create_http_server()) as port,
            httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
        ):
            resp = await client.get("/healthz")

        assert resp.status_code == 200


async def _statuses_by_host(live_server, requests):
    """Send (method, path, Host) requests to a live server; return their status codes.

    ``{port}`` in a Host value is replaced with the server's bound port.
    """
    import httpx
    import uvicorn

    from lm_mcp.transport.http import create_asgi_app

    rpc = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    server = uvicorn.Server(
        uvicorn.Config(create_asgi_app(), host="127.0.0.1", port=0, log_level="warning")
    )
    async with (
        live_server(server.serve()) as port,
        httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
    ):
        statuses = []
        for method, path, host in requests:
            headers = {"Host": host.format(port=port)}
            if method == "POST":
                resp = await client.post(path, json=rpc, headers=headers)
            else:
                resp = await client.get(path, headers=headers)
            statuses.append(resp.status_code)
        return statuses


class TestHostAllowlist:
    """R3.3: every route except /healthz and /readyz answers only expected Host names."""

    async def test_unknown_host_is_refused_before_the_handler(self, _set_env, live_server):
        """Host: evil.example gets the middleware's 400 on GET /, with or without a port."""
        import httpx
        import uvicorn

        from lm_mcp.transport.http import create_asgi_app

        server = uvicorn.Server(
            uvicorn.Config(create_asgi_app(), host="127.0.0.1", port=0, log_level="warning")
        )
        async with (
            live_server(server.serve()) as port,
            httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
        ):
            bare = await client.get("/", headers={"Host": "evil.example"})
            with_port = await client.get("/", headers={"Host": f"evil.example:{port}"})

        assert bare.status_code == 400
        assert with_port.status_code == 400
        assert bare.json() == {"error": "Invalid Host header"}

    async def test_loopback_hosts_are_accepted(self, _set_env, live_server):
        """127.0.0.1, localhost (any case) and a bracketed [::1] pass, with or without a port."""
        statuses = await _statuses_by_host(
            live_server,
            [
                ("GET", "/", "127.0.0.1:{port}"),
                ("GET", "/", "localhost:{port}"),
                ("GET", "/", "LOCALHOST"),
                ("GET", "/", "[::1]:{port}"),
            ],
        )

        assert statuses == [200, 200, 200, 200]

    async def test_configured_hosts_are_accepted(self, _set_env, live_server, monkeypatch):
        """LM_HTTP_ALLOWED_HOSTS adds names; loopback still passes and others still fail."""
        monkeypatch.setenv("LM_HTTP_ALLOWED_HOSTS", "mcp.internal, Other.Internal")
        statuses = await _statuses_by_host(
            live_server,
            [
                ("GET", "/", "mcp.internal"),
                ("GET", "/", "other.internal:443"),
                ("GET", "/", "localhost:{port}"),
                ("GET", "/", "evil.example"),
                ("POST", "/mcp", "evil.example"),
            ],
        )

        assert statuses == [200, 200, 200, 400, 400]

    async def test_probe_paths_are_exempt(self, _set_env, live_server):
        """/healthz and /readyz answer any Host, so probes by pod IP keep working; others do not."""
        statuses = await _statuses_by_host(
            live_server,
            [
                ("GET", "/healthz", "10.244.1.7:8080"),
                ("GET", "/readyz", "10.244.1.7:8080"),
                ("GET", "/healthz/", "10.244.1.7:8080"),
                ("GET", "/health", "10.244.1.7:8080"),
                ("GET", "/", "10.244.1.7:8080"),
            ],
        )

        # The probes reach their handlers (200, or 503 with no LM client bound; the
        # trailing-slash form gets Starlette's redirect); only the Host check sends 400.
        assert [status != 400 for status in statuses[:3]] == [True, True, True]
        assert statuses[3:] == [400, 400]

    async def test_specific_bind_host_is_accepted(self, _set_env, live_server, monkeypatch):
        """A configured non-wildcard LM_HTTP_HOST is an allowed Host name."""
        monkeypatch.setenv("LM_HTTP_HOST", "10.9.8.7")
        statuses = await _statuses_by_host(live_server, [("GET", "/", "10.9.8.7:{port}")])

        assert statuses == [200]

    async def test_wildcard_bind_host_is_not_a_host_name(self, _set_env, live_server, monkeypatch):
        """No client addresses a server as 0.0.0.0, so the wildcard bind adds nothing."""
        monkeypatch.setenv("LM_HTTP_HOST", "0.0.0.0")
        statuses = await _statuses_by_host(live_server, [("GET", "/", "0.0.0.0:{port}")])

        assert statuses == [400]
