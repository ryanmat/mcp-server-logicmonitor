# Description: Tests for the transport abstraction module.
# Description: Validates transport runner selection and configuration.

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from lm_mcp.transport import get_transport_runner, run_http, run_stdio
from tests.live_uvicorn import free_port, live_uvicorn


class TestTransportModule:
    """Tests for transport module imports and exports."""

    def test_run_stdio_is_callable(self):
        """run_stdio function is importable and callable."""
        assert callable(run_stdio)

    def test_run_http_is_callable(self):
        """run_http function is importable and callable."""
        assert callable(run_http)

    def test_get_transport_runner_is_callable(self):
        """get_transport_runner function is importable and callable."""
        assert callable(get_transport_runner)


class TestGetTransportRunner:
    """Tests for transport runner selection."""

    def test_stdio_transport_returns_run_stdio(self, monkeypatch):
        """stdio transport returns run_stdio function."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_TRANSPORT", "stdio")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        runner = get_transport_runner(config)

        assert runner is run_stdio

    def test_http_transport_returns_run_http(self, monkeypatch):
        """http transport returns run_http function."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_TRANSPORT", "http")
        monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        runner = get_transport_runner(config)

        assert runner is run_http

    def test_invalid_transport_raises_error(self, monkeypatch):
        """Invalid transport type raises ValueError."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_TRANSPORT", "invalid")

        from lm_mcp.config import LMConfig

        # LMConfig validation should catch invalid transport
        with pytest.raises(ValidationError):
            LMConfig()

    def test_default_transport_is_stdio(self, monkeypatch):
        """Default transport is stdio when not specified."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_TRANSPORT", raising=False)

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.transport == "stdio"


class TestTransportConfig:
    """Tests for transport-related configuration."""

    def test_http_host_default(self, monkeypatch):
        """Default HTTP host is 0.0.0.0."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.http_host == "0.0.0.0"

    def test_http_host_from_env(self, monkeypatch):
        """HTTP host can be set from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.http_host == "127.0.0.1"

    def test_http_port_default(self, monkeypatch):
        """Default HTTP port is 8080."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.http_port == 8080

    def test_http_port_from_env(self, monkeypatch):
        """HTTP port can be set from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_HTTP_PORT", "9000")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.http_port == 9000

    def test_http_port_validation_min(self, monkeypatch):
        """HTTP port below minimum raises error."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_HTTP_PORT", "0")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError):
            LMConfig()

    def test_http_port_validation_max(self, monkeypatch):
        """HTTP port above maximum raises error."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_HTTP_PORT", "70000")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError):
            LMConfig()

    def test_cors_origins_default(self, monkeypatch):
        """Default CORS origins is wildcard."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.cors_origins == ""

    def test_cors_origins_from_env(self, monkeypatch):
        """CORS origins can be set from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_CORS_ORIGINS", "https://example.com,https://other.com")

        from lm_mcp.config import LMConfig

        config = LMConfig()

        assert config.cors_origins == "https://example.com,https://other.com"

    def test_cors_origins_list_property(self, monkeypatch):
        """cors_origins_list property parses comma-separated origins."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_CORS_ORIGINS", "https://a.com,https://b.com")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        origins = config.cors_origins_list

        assert origins == ["https://a.com", "https://b.com"]

    def test_cors_origins_list_wildcard(self, monkeypatch):
        """cors_origins_list returns wildcard as single-item list."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_CORS_ORIGINS", "*")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        origins = config.cors_origins_list

        assert origins == ["*"]


def _fake_stdio_server():
    """Stand-in for mcp.stdio_server that yields placeholder streams."""

    @asynccontextmanager
    async def _cm():
        yield (None, None)

    return _cm


class TestRunStdioStartup:
    """R1.2: run_stdio setup reaches the serve loop in single- and multi-portal mode.

    The serve loop and the stdio streams are faked; everything before them runs
    for real, including client construction and the backend bootstrap.
    """

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch, reset_portals):
        from lm_mcp import server as server_module

        for var in (
            "LM_MULTI_PORTAL",
            "LM_PORTALS_FILE",
            "LM_VAULT_FILE",
            "LM_AGE_KEY",
            "LM_MAX_RETRIES",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        self.serve = AsyncMock()
        monkeypatch.setattr(server_module.server, "run", self.serve)
        monkeypatch.setattr("mcp.stdio_server", _fake_stdio_server())

    async def test_multi_portal_reaches_serve_loop(self, monkeypatch, tmp_path):
        """Multi-portal mode with a plaintext portals file reaches the serve loop."""
        portals_file = tmp_path / "portals.json"
        portals_file.write_text('{"acme": {"portal": "acme.example.com", "bearer_token": "t"}}')
        monkeypatch.setenv("LM_MULTI_PORTAL", "true")
        monkeypatch.setenv("LM_PORTALS_FILE", str(portals_file))
        monkeypatch.delenv("LM_PORTAL")
        monkeypatch.delenv("LM_BEARER_TOKEN")

        await run_stdio()

        self.serve.assert_awaited_once()

    async def test_single_portal_client_uses_configured_max_retries(self, monkeypatch):
        """R1.6, R3.5: the client gets LM_MAX_RETRIES and LM_RETRY_AFTER_CAP_SECONDS."""
        from lm_mcp import server as server_module

        monkeypatch.setenv("LM_MAX_RETRIES", "7")
        monkeypatch.setenv("LM_RETRY_AFTER_CAP_SECONDS", "45")
        # Shutdown nulls the global client, so read it while the loop is serving.
        serving_clients = []
        self.serve.side_effect = lambda *args: serving_clients.append(server_module._client)

        await run_stdio()

        self.serve.assert_awaited_once()
        assert serving_clients[0] is not None
        assert serving_clients[0].max_retries == 7
        assert serving_clients[0].retry_after_cap == 45


async def _stdio_tool_names(serve: AsyncMock) -> list[str]:
    """Run stdio setup and return the tool names list_tools gives while it serves."""
    from lm_mcp.server import list_tools

    names: list[str] = []

    async def capture(*_args):
        names.extend(t.name for t in await list_tools())

    serve.side_effect = capture
    await run_stdio()
    return names


async def _http_healthz(monkeypatch) -> int:
    """Start the HTTP server on loopback and return the status GET /healthz gives."""
    import httpx

    from lm_mcp.transport.http import create_http_server

    live = live_uvicorn(monkeypatch)
    async with (
        live(create_http_server()) as port,
        httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client,
    ):
        resp = await client.get("/healthz")
    return resp.status_code


class TestOneBootstrapForBothTransports:
    """R4.7: both transports build backends through one function.

    The stdio serve loop and streams are faked; the HTTP server runs on a real
    loopback socket. Backend construction runs for real.
    """

    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch, reset_portals):
        from lm_mcp import server as server_module

        for var in (
            "LM_MULTI_PORTAL",
            "LM_PORTALS_FILE",
            "LM_ENABLED_TOOLS",
            "LM_DISABLED_TOOLS",
            "LM_MCP_CATEGORIES",
            "LM_HTTP_AUTH_TOKEN",
            "LM_HTTP_ALLOW_UNAUTHENTICATED",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_HTTP_HOST", "127.0.0.1")
        monkeypatch.setenv("LM_HTTP_PORT", str(free_port("127.0.0.1")))

        self.serve = AsyncMock()
        monkeypatch.setattr(server_module.server, "run", self.serve)
        monkeypatch.setattr("mcp.stdio_server", _fake_stdio_server())

    async def test_no_backends_list_the_filtered_core_tools(self):
        """With no backend configured stdio lists exactly the filtered TOOLS."""
        from lm_mcp.config import get_config
        from lm_mcp.registry import TOOLS
        from lm_mcp.server import _filter_tools

        expected = [t.name for t in _filter_tools(list(TOOLS), get_config())]

        assert await _stdio_tool_names(self.serve) == expected

    async def test_each_transport_calls_bootstrap_backends_once(self, monkeypatch):
        """bootstrap_backends is the one function both transports build backends with."""
        from unittest.mock import patch

        from lm_mcp.transport import bootstrap

        with patch.object(
            bootstrap, "bootstrap_backends", wraps=bootstrap.bootstrap_backends
        ) as spy:
            await _stdio_tool_names(self.serve)
            assert spy.call_count == 1
            assert await _http_healthz(monkeypatch) == 200
            assert spy.call_count == 2

    async def test_each_transport_sizes_session_history_from_config(self, monkeypatch):
        """Both transports set the session's history length from LM_SESSION_HISTORY_SIZE."""
        from lm_mcp import session as session_module

        monkeypatch.setenv("LM_SESSION_HISTORY_SIZE", "7")

        monkeypatch.setattr(session_module, "_session", None)
        await _stdio_tool_names(self.serve)
        assert session_module.get_session().max_history_size == 7

        monkeypatch.setattr(session_module, "_session", None)
        assert await _http_healthz(monkeypatch) == 200
        assert session_module.get_session().max_history_size == 7
