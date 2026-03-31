# Description: Tests for watsonx tool dispatch and list_tools integration.
# Description: Validates dispatch routing for watsonx tools and conditional tool listing.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent


class TestWatsonxToolDispatch:
    """Tests for execute_tool dispatching watsonx tools to watsonx_client."""

    @pytest.mark.asyncio
    async def test_watsonx_tool_dispatched_to_watsonx_client(self, monkeypatch):
        """Watsonx tool is dispatched with watsonx_client, not lm_client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_watsonx_client, execute_tool

        mock_lm = MagicMock()
        mock_wx = MagicMock()
        _set_client(mock_lm)
        _set_watsonx_client(mock_wx)

        mock_result = [TextContent(type="text", text='{"summary": "test"}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            result = await execute_tool("watsonx_summarize", {"data": "{}"})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_wx, data="{}")
        assert result == mock_result

        _set_watsonx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_watsonx_tool_returns_error_when_not_configured(self, monkeypatch):
        """Watsonx tool returns error message when watsonx client is not set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_watsonx_client, execute_tool

        mock_lm = MagicMock()
        _set_client(mock_lm)
        _set_watsonx_client(None)

        result = await execute_tool("watsonx_summarize", {"data": "{}"})
        assert len(result) == 1
        assert "not configured" in result[0].text.lower()

        _set_client(None)

    @pytest.mark.asyncio
    async def test_lm_tool_unaffected_by_watsonx(self, monkeypatch):
        """LM tools still dispatch to lm_client when watsonx is configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_watsonx_client, execute_tool

        mock_lm = MagicMock()
        mock_wx = MagicMock()
        _set_client(mock_lm)
        _set_watsonx_client(mock_wx)

        mock_result = [TextContent(type="text", text='{"items": []}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            await execute_tool("get_devices", {"limit": 5})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_lm, limit=5)

        _set_watsonx_client(None)
        _set_client(None)


class TestListToolsWithWatsonx:
    """Tests for list_tools conditionally including watsonx tools."""

    @pytest.mark.asyncio
    async def test_list_tools_excludes_watsonx_when_not_configured(self, monkeypatch):
        """list_tools returns only LM tools when watsonx is not configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import TOOLS
        from lm_mcp.server import _set_watsonx_client, list_tools

        _set_watsonx_client(None)

        result = await list_tools()
        assert len(result) == len(TOOLS)

    @pytest.mark.asyncio
    async def test_list_tools_includes_watsonx_when_configured(self, monkeypatch):
        """list_tools includes watsonx tools when watsonx client is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import TOOLS, WATSONX_TOOLS
        from lm_mcp.server import _set_watsonx_client, list_tools

        _set_watsonx_client(MagicMock())

        result = await list_tools()
        assert len(result) == len(TOOLS) + len(WATSONX_TOOLS)

        _set_watsonx_client(None)

    @pytest.mark.asyncio
    async def test_watsonx_tool_names_set_matches_registry(self):
        """WATSONX_TOOL_NAMES set matches the actual WATSONX_TOOLS list."""
        from lm_mcp.registry import WATSONX_TOOLS
        from lm_mcp.server import WATSONX_TOOL_NAMES

        expected = {t.name for t in WATSONX_TOOLS}
        assert expected == WATSONX_TOOL_NAMES
