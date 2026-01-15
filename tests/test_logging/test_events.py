# Description: Tests for logging event types.
# Description: Verifies log event creation and formatting.

from __future__ import annotations

from lm_mcp.logging import (
    LogEvent,
    LogLevel,
    create_auth_failure_event,
    create_rate_limit_event,
    create_server_error_event,
    create_slow_request_event,
)


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_level_values_exist(self):
        """LogLevel has expected values."""
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARNING == "warning"
        assert LogLevel.ERROR == "error"


class TestLogEvent:
    """Tests for LogEvent dataclass."""

    def test_log_event_creation(self):
        """LogEvent can be created with required fields."""
        event = LogEvent(
            level=LogLevel.INFO,
            logger="test",
            message="Test message",
            data={"key": "value"},
        )
        assert event.level == LogLevel.INFO
        assert event.logger == "test"
        assert event.message == "Test message"
        assert event.data == {"key": "value"}

    def test_log_event_to_dict(self):
        """LogEvent can be converted to dict."""
        event = LogEvent(
            level=LogLevel.WARNING,
            logger="api",
            message="Warning message",
            data={"count": 5},
        )
        result = event.to_dict()
        assert result["level"] == "warning"
        assert result["logger"] == "api"
        assert result["message"] == "Warning message"
        assert result["data"]["count"] == 5


class TestRateLimitEvent:
    """Tests for rate limit log event creation."""

    def test_create_rate_limit_event(self):
        """create_rate_limit_event creates proper event."""
        event = create_rate_limit_event(
            path="/alert/alerts",
            attempt=2,
            retry_after=30,
        )
        assert event.level == LogLevel.WARNING
        assert event.logger == "lm_mcp.client"
        assert "rate limit" in event.message.lower()
        assert event.data["path"] == "/alert/alerts"
        assert event.data["attempt"] == 2
        assert event.data["retry_after"] == 30


class TestServerErrorEvent:
    """Tests for server error log event creation."""

    def test_create_server_error_event(self):
        """create_server_error_event creates proper event."""
        event = create_server_error_event(
            path="/device/devices",
            status_code=503,
            attempt=1,
        )
        assert event.level == LogLevel.WARNING
        assert event.logger == "lm_mcp.client"
        assert "server error" in event.message.lower() or "503" in event.message
        assert event.data["status_code"] == 503
        assert event.data["attempt"] == 1


class TestSlowRequestEvent:
    """Tests for slow request log event creation."""

    def test_create_slow_request_event(self):
        """create_slow_request_event creates proper event."""
        event = create_slow_request_event(
            path="/alert/alerts",
            method="GET",
            elapsed_seconds=5.5,
        )
        assert event.level == LogLevel.INFO
        assert event.logger == "lm_mcp.client"
        assert event.data["path"] == "/alert/alerts"
        assert event.data["method"] == "GET"
        assert event.data["elapsed_seconds"] == 5.5


class TestAuthFailureEvent:
    """Tests for auth failure log event creation."""

    def test_create_auth_failure_event(self):
        """create_auth_failure_event creates proper event."""
        event = create_auth_failure_event(
            status_code=401,
            message="Invalid token",
        )
        assert event.level == LogLevel.ERROR
        assert event.logger == "lm_mcp.auth"
        assert "auth" in event.message.lower()
        assert event.data["status_code"] == 401
        assert event.data["message"] == "Invalid token"
