# Description: Tests for AWX tool dispatch and list_tools integration.
# Description: Validates 3-way dispatch in execute_tool and conditional tool listing.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent


class TestAwxToolDispatch:
    """Tests for execute_tool dispatching AWX tools to awx_client."""

    @pytest.mark.asyncio
    async def test_awx_tool_dispatched_to_awx_client(self, monkeypatch):
        """AWX tool is dispatched with awx_client, not lm_client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)

        mock_result = [TextContent(type="text", text='{"connected": true}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            result = await execute_tool("test_awx_connection", {})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_awx)
        assert result == mock_result

        # Clean up
        _set_awx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_awx_tool_returns_error_when_not_configured(self, monkeypatch):
        """AWX tool returns error message when AWX client is not set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, execute_tool

        mock_lm = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(None)

        result = await execute_tool("test_awx_connection", {})
        assert len(result) == 1
        assert "not configured" in result[0].text.lower()

        _set_client(None)

    @pytest.mark.asyncio
    async def test_lm_tool_still_uses_lm_client(self, monkeypatch):
        """LM tools still dispatch to lm_client when AWX is configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)

        mock_result = [TextContent(type="text", text='{"items": []}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            await execute_tool("get_devices", {"limit": 5})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_lm, limit=5)

        _set_awx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_session_tool_still_works(self, monkeypatch):
        """Session tools still work without any client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, execute_tool

        _set_client(None)
        _set_awx_client(None)

        mock_result = [TextContent(type="text", text='{"variables": {}}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ):
            result = await execute_tool("get_session_context", {})

        assert result == mock_result

    @pytest.mark.asyncio
    async def test_awx_write_tool_logged(self, monkeypatch):
        """AWX write tools trigger audit logging."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)

        mock_result = [TextContent(type="text", text='{"job_id": 42}')]
        with (
            patch(
                "lm_mcp.server.get_tool_handler",
                return_value=AsyncMock(return_value=mock_result),
            ),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            await execute_tool("launch_job", {"template_id": 1})

        mock_log.assert_called_once_with("launch_job", {"template_id": 1}, success=True)

        _set_awx_client(None)
        _set_client(None)


class TestListToolsWithAwx:
    """Tests for list_tools conditionally including AWX tools."""

    @pytest.mark.asyncio
    async def test_list_tools_excludes_awx_when_not_configured(self, monkeypatch):
        """list_tools returns only LM tools when AWX is not configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("AWX_URL", raising=False)
        monkeypatch.delenv("AWX_TOKEN", raising=False)

        from lm_mcp.registry import TOOLS
        from lm_mcp.server import _set_awx_client, list_tools

        _set_awx_client(None)

        result = await list_tools()
        assert len(result) == len(TOOLS)

    @pytest.mark.asyncio
    async def test_list_tools_includes_awx_when_configured(self, monkeypatch):
        """list_tools includes AWX tools when AWX client is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import AWX_TOOLS, TOOLS
        from lm_mcp.server import _set_awx_client, list_tools

        _set_awx_client(MagicMock())

        result = await list_tools()
        assert len(result) == len(TOOLS) + len(AWX_TOOLS)

        _set_awx_client(None)

    @pytest.mark.asyncio
    async def test_list_tools_filter_applies_to_combined(self, monkeypatch):
        """Tool filtering applies to combined LM + AWX tools."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,test_awx_connection")

        from lm_mcp.server import _set_awx_client, list_tools

        _set_awx_client(MagicMock())

        result = await list_tools()
        names = {t.name for t in result}
        assert names == {"get_devices", "test_awx_connection"}

        _set_awx_client(None)

    @pytest.mark.asyncio
    async def test_awx_tool_names_set_matches_registry(self, monkeypatch):
        """AWX_TOOL_NAMES set matches the actual AWX_TOOLS list."""
        from lm_mcp.registry import AWX_TOOLS
        from lm_mcp.server import AWX_TOOL_NAMES

        expected = {t.name for t in AWX_TOOLS}
        assert AWX_TOOL_NAMES == expected
