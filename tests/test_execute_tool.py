# Description: Tests for the shared execute_tool middleware function.
# Description: Validates tool filtering, write audit, and session recording.

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent


class TestExecuteToolMiddleware:
    """Tests for execute_tool applying the full middleware chain."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock tool handler returning TextContent."""
        return AsyncMock(
            return_value=[TextContent(type="text", text=json.dumps({"id": 1}))]
        )

    @pytest.fixture
    def mock_client(self):
        """Create a mock LogicMonitor client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_calls_handler_with_client(
        self, monkeypatch, mock_handler, mock_client
    ):
        """execute_tool passes client and arguments to the handler."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_client", return_value=mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": 10})

        mock_handler.assert_called_once_with(mock_client, limit=10)
        assert len(result) == 1
        assert json.loads(result[0].text) == {"id": 1}

    @pytest.mark.asyncio
    async def test_session_tool_called_without_client(
        self, monkeypatch, mock_handler
    ):
        """execute_tool calls session tools without the LM client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        with patch("lm_mcp.server.get_tool_handler", return_value=mock_handler):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_session_context", {})

        mock_handler.assert_called_once_with()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_rejects_disabled_tool(self, monkeypatch):
        """execute_tool rejects tools matching disabled_tools pattern."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")

        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})

        assert "disabled" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_rejects_non_enabled_tool(self, monkeypatch):
        """execute_tool rejects tools not in enabled_tools list."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        from lm_mcp.server import execute_tool

        result = await execute_tool("delete_device", {"device_id": 1})

        assert "not enabled" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_allows_enabled_tool(
        self, monkeypatch, mock_handler, mock_client
    ):
        """execute_tool allows tools in the enabled_tools list."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_client", return_value=mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": 5})

        mock_handler.assert_called_once()
        assert json.loads(result[0].text) == {"id": 1}

    @pytest.mark.asyncio
    async def test_logs_write_operation_on_success(
        self, monkeypatch, mock_handler, mock_client
    ):
        """execute_tool logs successful write operations."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_client", return_value=mock_client),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("create_device", {"name": "test"})

        mock_log.assert_called_once_with("create_device", {"name": "test"}, success=True)

    @pytest.mark.asyncio
    async def test_logs_write_operation_on_failure(self, monkeypatch):
        """execute_tool logs failed write operations."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        failing_handler = AsyncMock(side_effect=Exception("API error"))

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=failing_handler),
            patch("lm_mcp.server.get_client", return_value=MagicMock()),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("create_device", {"name": "test"})

        mock_log.assert_called_once_with("create_device", {"name": "test"}, success=False)
        assert "error" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_records_session_when_enabled(
        self, monkeypatch, mock_handler, mock_client
    ):
        """execute_tool records results in session when session is enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_SESSION_ENABLED", "true")

        mock_session = MagicMock()

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_client", return_value=mock_client),
            patch("lm_mcp.server.get_session", return_value=mock_session),
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("get_devices", {"limit": 10})

        mock_session.record_result.assert_called_once_with(
            "get_devices", {"limit": 10}, {"id": 1}, success=True
        )

    @pytest.mark.asyncio
    async def test_skips_session_for_session_tools(
        self, monkeypatch, mock_handler
    ):
        """execute_tool does not record session tools in session history."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_SESSION_ENABLED", "true")

        mock_session = MagicMock()

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=mock_handler),
            patch("lm_mcp.server.get_session", return_value=mock_session),
        ):
            from lm_mcp.server import execute_tool

            await execute_tool("get_session_context", {})

        mock_session.record_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_value_error_returns_error_text(
        self, monkeypatch, mock_client
    ):
        """execute_tool catches ValueError and returns error message."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        failing_handler = AsyncMock(side_effect=ValueError("bad input"))

        with (
            patch("lm_mcp.server.get_tool_handler", return_value=failing_handler),
            patch("lm_mcp.server.get_client", return_value=mock_client),
        ):
            from lm_mcp.server import execute_tool

            result = await execute_tool("get_devices", {"limit": -1})

        assert "bad input" in result[0].text


class TestCallToolDelegatesToExecuteTool:
    """Tests that the MCP call_tool handler delegates to execute_tool."""

    @pytest.mark.asyncio
    async def test_call_tool_uses_execute_tool(self, monkeypatch):
        """The MCP call_tool handler delegates to execute_tool."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        expected = [TextContent(type="text", text="delegated")]

        with patch("lm_mcp.server.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = expected
            from lm_mcp.server import call_tool

            result = await call_tool("get_devices", {"limit": 10})

        mock_exec.assert_called_once_with("get_devices", {"limit": 10})
        assert result == expected
