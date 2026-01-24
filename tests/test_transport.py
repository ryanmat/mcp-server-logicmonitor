# Description: Tests for the transport abstraction module.
# Description: Validates transport runner selection and configuration.

import pytest

from lm_mcp.transport import get_transport_runner, run_http, run_stdio


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
        with pytest.raises(Exception):
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

        assert config.cors_origins == "*"

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
