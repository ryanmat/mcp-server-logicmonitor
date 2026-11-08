# Description: Tests for the typed error result (R1.4): ErrorContent and is_error_result.
# Description: Covers the response helpers and every inline error return in execute_tool.

import logging

import pytest
from mcp.types import TextContent

from lm_mcp.exceptions import LMError
from lm_mcp.tools import ErrorContent, format_response, handle_error, is_error_result
from tests.envelope import envelope


class TestErrorContentHelpers:
    def test_handle_error_lm_error_returns_error_content(self):
        result = handle_error(LMError("Device 7 not found", code="NOT_FOUND"))

        assert isinstance(result, list)
        assert isinstance(result[0], ErrorContent)
        assert isinstance(result[0], TextContent)
        assert result[0].type == "text"
        assert result[0].is_error is True
        assert envelope(result)["message"].startswith("Device 7 not found")

    def test_handle_error_unexpected_returns_error_content_and_logs_traceback(self, caplog):
        """Handlers call handle_error inside their except block, as here."""
        with caplog.at_level(logging.ERROR, logger="lm_mcp.tools"):
            try:
                raise RuntimeError("boom")
            except RuntimeError as e:
                result = handle_error(e)

        assert isinstance(result[0], ErrorContent)
        assert envelope(result)["message"].startswith("boom")
        records = [r for r in caplog.records if r.name == "lm_mcp.tools"]
        assert records and records[-1].exc_info is not None
        assert records[-1].exc_info[0] is RuntimeError

    def test_format_response_success_is_plain_text_content(self):
        result = format_response({"a": 1})

        assert type(result[0]) is TextContent
        assert not isinstance(result[0], ErrorContent)

    def test_is_error_result(self):
        assert is_error_result(handle_error(LMError("x", code="X"))) is True
        assert is_error_result(handle_error(RuntimeError("y"))) is True
        assert is_error_result(format_response({"a": 1})) is False
        assert is_error_result([]) is False


@pytest.fixture
def single_portal(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)
    for var in ("LM_ENABLED_TOOLS", "LM_DISABLED_TOOLS", "LM_MCP_CATEGORIES"):
        monkeypatch.delenv(var, raising=False)


class TestExecuteToolInlineErrors:
    """Every refusal execute_tool builds itself is an ErrorContent carrying the envelope."""

    async def test_portal_tool_in_single_portal_mode(self, single_portal):
        from lm_mcp.server import execute_tool

        result = await execute_tool("list_portals", {})
        assert is_error_result(result)
        error = envelope(result)
        assert error["code"] == "FEATURE_DISABLED"
        assert error["message"].startswith("Tool 'list_portals' is only available")

    async def test_tool_not_enabled(self, single_portal, monkeypatch):
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_alerts")
        from lm_mcp.server import execute_tool

        result = await execute_tool("get_devices", {})
        assert is_error_result(result)
        error = envelope(result)
        assert error["code"] == "FEATURE_DISABLED"
        assert "is not enabled" in error["message"]

    async def test_tool_disabled(self, single_portal, monkeypatch):
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")
        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})
        assert is_error_result(result)
        error = envelope(result)
        assert error["code"] == "FEATURE_DISABLED"
        assert "is disabled" in error["message"]

    async def test_tool_excluded_by_categories(self, single_portal, monkeypatch):
        monkeypatch.setenv("LM_MCP_CATEGORIES", "read")
        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})
        assert is_error_result(result)
        error = envelope(result)
        assert error["code"] == "FEATURE_DISABLED"
        assert "excluded by LM_MCP_CATEGORIES" in error["message"]

    async def test_unknown_tool_value_error_path(self, single_portal):
        from lm_mcp.server import execute_tool

        result = await execute_tool("no_such_tool", {})
        assert is_error_result(result)
        assert envelope(result)["code"] == "INVALID_REQUEST"

    async def test_missing_client(self, single_portal, reset_portals, caplog):
        """No client bound: the dispatcher refuses the call, not retryable, with no traceback."""
        from lm_mcp.server import execute_tool

        with caplog.at_level(logging.ERROR, logger="lm_mcp.server"):
            result = await execute_tool("get_devices", {})
        assert is_error_result(result)
        error = envelope(result)
        assert (error["code"], error["isRetryable"]) == ("INVALID_REQUEST", False)
        assert error["message"] == "Client not initialized"
        assert caplog.records == []

    async def test_exception_path(self, single_portal):
        """A handler that raises: the dispatcher's except path answers."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from lm_mcp.server import execute_tool

        handler = AsyncMock(side_effect=RuntimeError("boom"))
        with (
            patch("lm_mcp.server._client", MagicMock()),
            patch("lm_mcp.server.get_tool_handler", return_value=handler),
        ):
            result = await execute_tool("get_devices", {})
        assert is_error_result(result)
        error = envelope(result)
        assert error["code"] == "UPSTREAM_ERROR"
        assert error["message"] == "boom"
        assert error["details"] == {"exception": "RuntimeError"}

    async def test_success_is_not_an_error(self, single_portal):
        from lm_mcp.server import execute_tool

        result = await execute_tool("search_tools", {"query": "device"})
        assert not is_error_result(result)
