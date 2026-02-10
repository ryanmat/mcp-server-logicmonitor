# Description: Tests for request logging and debug mode.
# Description: Verifies log level config, event structure, and debug/warning mode behavior.

import logging

import pytest


class TestLogLevelConfig:
    """Tests for LM_LOG_LEVEL configuration."""

    def test_default_log_level_is_warning(self, monkeypatch):
        """Default log_level is 'warning'."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_value")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.log_level == "warning"

    def test_log_level_accepts_debug(self, monkeypatch):
        """log_level accepts 'debug' value."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_value")
        monkeypatch.setenv("LM_LOG_LEVEL", "debug")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.log_level == "debug"

    def test_log_level_accepts_info(self, monkeypatch):
        """log_level accepts 'info' value."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_value")
        monkeypatch.setenv("LM_LOG_LEVEL", "info")

        from lm_mcp.config import LMConfig

        config = LMConfig()
        assert config.log_level == "info"

    def test_log_level_rejects_invalid(self, monkeypatch):
        """log_level rejects invalid values."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test_token_value")
        monkeypatch.setenv("LM_LOG_LEVEL", "verbose")

        from lm_mcp.config import LMConfig

        with pytest.raises(ValueError):
            LMConfig()


class TestApiRequestEvent:
    """Tests for create_api_request_event."""

    def test_request_event_structure(self):
        """create_api_request_event returns properly structured dict."""
        from lm_mcp.logging import create_api_request_event

        event = create_api_request_event("GET", "/alert/alerts", {"size": 50})
        assert event["event"] == "api_request"
        assert event["method"] == "GET"
        assert event["path"] == "/alert/alerts"
        assert event["params"] == {"size": 50}

    def test_request_event_none_params(self):
        """create_api_request_event handles None params."""
        from lm_mcp.logging import create_api_request_event

        event = create_api_request_event("POST", "/device/devices", None)
        assert event["params"] is None


class TestApiResponseEvent:
    """Tests for create_api_response_event."""

    def test_response_event_structure(self):
        """create_api_response_event returns properly structured dict."""
        from lm_mcp.logging import create_api_response_event

        event = create_api_response_event(200, 0.125, "/alert/alerts")
        assert event["event"] == "api_response"
        assert event["status_code"] == 200
        assert event["elapsed_ms"] == 125.0
        assert event["path"] == "/alert/alerts"

    def test_response_event_error_status(self):
        """create_api_response_event handles error status codes."""
        from lm_mcp.logging import create_api_response_event

        event = create_api_response_event(429, 1.5, "/device/devices")
        assert event["status_code"] == 429


class TestDebugModeLogging:
    """Tests for debug mode log output integration."""

    def test_debug_mode_produces_request_log(self, caplog):
        """Debug mode produces log for API request details."""
        from lm_mcp.logging import log_api_request

        with caplog.at_level(logging.DEBUG, logger="lm_mcp.client"):
            log_api_request("GET", "/alert/alerts", {"size": 50})

        assert "GET /alert/alerts" in caplog.text

    def test_warning_mode_suppresses_request_log(self, caplog):
        """Warning mode suppresses debug-level request logs."""
        from lm_mcp.logging import log_api_request

        with caplog.at_level(logging.WARNING, logger="lm_mcp.client"):
            log_api_request("GET", "/alert/alerts", {"size": 50})

        assert caplog.text == ""
