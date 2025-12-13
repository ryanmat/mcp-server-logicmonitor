# Description: Tests for MCP server initialization and configuration.
# Description: Validates server can be created with correct name and settings.

import pytest


class TestServerCreation:
    """Tests for basic server creation."""

    def test_server_can_be_imported(self):
        """Server module can be imported without errors."""
        from lm_mcp.server import server

        assert server is not None

    def test_server_has_correct_name(self):
        """Server has the expected name."""
        from lm_mcp.server import server

        assert server.name == "logicmonitor-platform"

    def test_main_function_exists(self):
        """Entry point main function exists."""
        from lm_mcp.server import main

        assert callable(main)

    def test_get_client_raises_before_init(self):
        """get_client raises RuntimeError if called before initialization."""
        from lm_mcp.server import get_client

        with pytest.raises(RuntimeError, match="Client not initialized"):
            get_client()


class TestServerConfig:
    """Tests for server configuration integration."""

    def test_server_uses_lm_config(self, monkeypatch):
        """Server can load configuration from environment."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.portal == "test.logicmonitor.com"
        assert config.bearer_token == "test-token"
