# Description: Tests for tool helper functions.
# Description: Validates format_response and handle_error utilities.

import json

from lm_mcp.exceptions import AuthenticationError, LMError, NotFoundError


class TestFormatResponse:
    """Tests for format_response function."""

    def test_format_dict_response(self):
        """Dict data is formatted as JSON text content."""
        from lm_mcp.tools import format_response

        data = {"count": 5, "items": [1, 2, 3]}
        result = format_response(data)

        assert len(result) == 1
        assert result[0].type == "text"
        parsed = json.loads(result[0].text)
        assert parsed["count"] == 5
        assert parsed["items"] == [1, 2, 3]

    def test_format_list_response(self):
        """List data is formatted as JSON text content."""
        from lm_mcp.tools import format_response

        data = [{"id": 1}, {"id": 2}]
        result = format_response(data)

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1

    def test_format_string_response(self):
        """String data is returned as-is."""
        from lm_mcp.tools import format_response

        data = "Simple message"
        result = format_response(data)

        assert len(result) == 1
        assert result[0].text == "Simple message"

    def test_format_error_response(self):
        """Error dict includes error message and suggestion."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "TEST_ERROR",
            "message": "Something went wrong",
            "suggestion": "Try again",
        }
        result = format_response(data)

        assert len(result) == 1
        assert "Error: Something went wrong" in result[0].text
        assert "Suggestion: Try again" in result[0].text

    def test_format_error_response_without_suggestion(self):
        """Error dict without suggestion omits suggestion line."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "TEST_ERROR",
            "message": "Something went wrong",
        }
        result = format_response(data)

        assert "Error: Something went wrong" in result[0].text
        assert "Suggestion:" not in result[0].text


class TestHandleError:
    """Tests for handle_error function."""

    def test_handle_lm_error(self):
        """LMError is converted to formatted error response."""
        from lm_mcp.tools import handle_error

        error = LMError("Test error", code="TEST_CODE", suggestion="Fix it")
        result = handle_error(error)

        assert len(result) == 1
        assert "Error: Test error" in result[0].text
        assert "Suggestion: Fix it" in result[0].text

    def test_handle_authentication_error(self):
        """AuthenticationError preserves its code and suggestion."""
        from lm_mcp.tools import handle_error

        error = AuthenticationError("Invalid token")
        result = handle_error(error)

        assert "Error: Invalid token" in result[0].text
        # Should include the default suggestion from AuthenticationError

    def test_handle_not_found_error(self):
        """NotFoundError is handled correctly."""
        from lm_mcp.tools import handle_error

        error = NotFoundError("Device 123 not found")
        result = handle_error(error)

        assert "Error: Device 123 not found" in result[0].text

    def test_handle_generic_exception(self):
        """Generic exceptions are wrapped in UNEXPECTED_ERROR."""
        from lm_mcp.tools import handle_error

        error = ValueError("Something unexpected")
        result = handle_error(error)

        assert "Error: Something unexpected" in result[0].text

    def test_handle_error_returns_text_content(self):
        """handle_error returns list of TextContent."""
        from mcp.types import TextContent

        from lm_mcp.tools import handle_error

        error = LMError("Test")
        result = handle_error(error)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)


class TestPortalUrl:
    """Tests for portal_url helper function."""

    def test_device_url(self, monkeypatch):
        """portal_url builds correct device URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("device", 123) == "https://test.logicmonitor.com/santaba/uiv4/devices/123"

    def test_alert_url(self, monkeypatch):
        """portal_url builds correct alert URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("alert", "456") == "https://test.logicmonitor.com/santaba/uiv4/alerts/456"

    def test_dashboard_url(self, monkeypatch):
        """portal_url builds correct dashboard URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("dashboard", 789) == (
            "https://test.logicmonitor.com/santaba/uiv4/dashboard/789"
        )

    def test_device_group_url(self, monkeypatch):
        """portal_url builds correct device group URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("device_group", 42) == (
            "https://test.logicmonitor.com/santaba/uiv4/device/groups/42"
        )

    def test_website_url(self, monkeypatch):
        """portal_url builds correct website URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("website", 55) == (
            "https://test.logicmonitor.com/santaba/uiv4/setting/websites/55"
        )

    def test_alert_rule_url(self, monkeypatch):
        """portal_url builds correct alert rule URL."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("alert_rule", 10) == (
            "https://test.logicmonitor.com/santaba/uiv4/setting/alert/rules/10"
        )

    def test_unknown_type_returns_empty(self, monkeypatch):
        """portal_url returns empty string for unknown resource types."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        assert portal_url("nonexistent", 1) == ""

    def test_string_id(self, monkeypatch):
        """portal_url works with string IDs."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)
        from lm_mcp.tools import portal_url

        url = portal_url("device", "999")
        assert url == "https://test.logicmonitor.com/santaba/uiv4/devices/999"
