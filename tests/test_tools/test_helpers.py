# Description: Tests for tool helper functions.
# Description: Validates format_response and handle_error utilities.

import json

from lm_mcp.exceptions import AuthenticationError, LMError, NotFoundError
from tests.envelope import envelope


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

    def test_dicts_and_lists_are_compact_json(self):
        """R4.3: no indentation and no spaces after separators."""
        from lm_mcp.tools import format_response

        assert format_response({"count": 5, "items": [1, 2]})[0].text == '{"count":5,"items":[1,2]}'
        assert format_response([{"id": 1}, {"id": 2}])[0].text == '[{"id":1},{"id":2}]'

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
        """Error dict's suggestion is joined onto the envelope's message."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "INVALID_REQUEST",
            "message": "Something went wrong",
            "suggestion": "Try again",
        }
        result = format_response(data)

        assert len(result) == 1
        assert envelope(result)["message"] == "Something went wrong. Try again"

    def test_format_error_response_without_suggestion(self):
        """Error dict without suggestion keeps its message as written."""
        from lm_mcp.tools import format_response

        data = {
            "error": True,
            "code": "INVALID_REQUEST",
            "message": "Something went wrong",
        }
        result = format_response(data)

        assert envelope(result)["message"] == "Something went wrong"


class TestHandleError:
    """Tests for handle_error function."""

    def test_handle_lm_error(self):
        """LMError is converted to formatted error response."""
        from lm_mcp.tools import handle_error

        error = LMError("Test error", code="TEST_CODE", suggestion="Fix it")
        result = handle_error(error)

        assert len(result) == 1
        error = envelope(result)
        assert error["message"] == "Test error. Fix it"
        assert error["code"] == "UPSTREAM_ERROR"
        assert error["details"] == {"lm_code": "TEST_CODE"}

    def test_handle_authentication_error(self):
        """AuthenticationError preserves its code and suggestion."""
        from lm_mcp.tools import handle_error

        error = AuthenticationError("Invalid token")
        result = handle_error(error)

        assert envelope(result)["message"].startswith("Invalid token")
        # Should include the default suggestion from AuthenticationError

    def test_handle_not_found_error(self):
        """NotFoundError is handled correctly."""
        from lm_mcp.tools import handle_error

        error = NotFoundError("Device 123 not found")
        result = handle_error(error)

        assert envelope(result)["message"].startswith("Device 123 not found")

    def test_handle_generic_exception(self):
        """Generic exceptions map to UPSTREAM_ERROR."""
        from lm_mcp.tools import handle_error

        error = ValueError("Something unexpected")
        result = handle_error(error)

        assert envelope(result)["message"].startswith("Something unexpected")

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


class TestCallSubTool:
    """Tests for the shared call_sub_tool helper exported from lm_mcp.tools."""

    def test_is_importable_from_tools_package(self):
        """call_sub_tool is part of the public tools namespace."""
        from lm_mcp import tools

        assert hasattr(tools, "call_sub_tool")
        assert "call_sub_tool" in tools.__all__

    async def test_happy_path_returns_parsed_dict(self):
        from mcp.types import TextContent

        from lm_mcp.tools import call_sub_tool

        async def handler(_client):
            return [TextContent(type="text", text=json.dumps({"ok": True, "count": 3}))]

        data = await call_sub_tool(handler, client=None)
        assert data == {"ok": True, "count": 3}

    async def test_error_text_raises_runtime_error(self):
        """A sub-tool's error envelope surfaces as a RuntimeError carrying its message."""
        import pytest

        from lm_mcp.tools import call_sub_tool, validation_error

        async def handler(_client):
            return validation_error("NOT_FOUND", "device 42 not found", "Check the ID.")

        with pytest.raises(RuntimeError, match=r"^device 42 not found\. Check the ID\.$"):
            await call_sub_tool(handler, client=None)

    async def test_non_json_text_raises_with_snippet(self):
        import pytest
        from mcp.types import TextContent

        from lm_mcp.tools import call_sub_tool

        async def handler(_client):
            return [TextContent(type="text", text="<html>gateway timeout</html>")]

        with pytest.raises(RuntimeError, match="non-JSON response"):
            await call_sub_tool(handler, client=None)

    async def test_parsed_error_dict_raises(self):
        import pytest
        from mcp.types import TextContent

        from lm_mcp.tools import call_sub_tool

        async def handler(_client):
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": {"code": "NOT_FOUND", "message": "boom"}}),
                )
            ]

        with pytest.raises(RuntimeError, match="boom"):
            await call_sub_tool(handler, client=None)


class TestValidationError:
    """Tests for the validation_error helper."""

    def test_is_importable_from_tools_package(self):
        from lm_mcp import tools

        assert hasattr(tools, "validation_error")
        assert "validation_error" in tools.__all__

    def test_returns_canonical_envelope(self):
        from lm_mcp.tools import validation_error

        result = validation_error("INVALID_REQUEST", "name is required")
        assert len(result) == 1
        assert envelope(result)["message"] == "name is required"

    def test_envelope_includes_suggestion(self):
        from lm_mcp.tools import validation_error

        result = validation_error(
            "INVALID_REQUEST",
            "logs list cannot be empty",
            suggestion="Pass at least one log entry.",
        )
        assert envelope(result)["message"] == (
            "logs list cannot be empty. Pass at least one log entry."
        )
