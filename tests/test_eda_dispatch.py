# Description: Tests for EDA tool dispatch and list_tools integration.
# Description: Validates 4-way dispatch in execute_tool and conditional EDA tool listing.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent


class TestEdaToolDispatch:
    """Tests for execute_tool dispatching EDA tools to eda_client."""

    @pytest.mark.asyncio
    async def test_eda_tool_dispatched_to_eda_client(self, monkeypatch):
        """EDA tool is dispatched with eda_client, not lm_client or awx_client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, _set_eda_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        mock_eda = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)
        _set_eda_client(mock_eda)

        mock_result = [TextContent(type="text", text='{"connected": true}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            result = await execute_tool("test_eda_connection", {})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_eda)
        assert result == mock_result

        _set_eda_client(None)
        _set_awx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_eda_tool_returns_error_when_not_configured(self, monkeypatch):
        """EDA tool returns error message when EDA client is not set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_eda_client, execute_tool

        mock_lm = MagicMock()
        _set_client(mock_lm)
        _set_eda_client(None)

        result = await execute_tool("test_eda_connection", {})
        assert len(result) == 1
        assert "not configured" in result[0].text.lower()

        _set_client(None)

    @pytest.mark.asyncio
    async def test_awx_tool_still_dispatches_correctly(self, monkeypatch):
        """AWX tools still dispatch to awx_client when EDA is also configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, _set_eda_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        mock_eda = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)
        _set_eda_client(mock_eda)

        mock_result = [TextContent(type="text", text='{"connected": true}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            await execute_tool("test_awx_connection", {})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_awx)

        _set_eda_client(None)
        _set_awx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_lm_tool_still_uses_lm_client(self, monkeypatch):
        """LM tools still dispatch to lm_client when EDA+AWX are configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_awx_client, _set_client, _set_eda_client, execute_tool

        mock_lm = MagicMock()
        mock_awx = MagicMock()
        mock_eda = MagicMock()
        _set_client(mock_lm)
        _set_awx_client(mock_awx)
        _set_eda_client(mock_eda)

        mock_result = [TextContent(type="text", text='{"items": []}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            await execute_tool("get_devices", {"limit": 5})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_lm, limit=5)

        _set_eda_client(None)
        _set_awx_client(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_eda_write_tool_logged(self, monkeypatch):
        """EDA write tools trigger audit logging."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_eda_client, execute_tool

        mock_lm = MagicMock()
        mock_eda = MagicMock()
        _set_client(mock_lm)
        _set_eda_client(mock_eda)

        mock_result = [TextContent(type="text", text='{"id": 10}')]
        with (
            patch(
                "lm_mcp.server.get_tool_handler",
                return_value=AsyncMock(return_value=mock_result),
            ),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            await execute_tool(
                "create_eda_activation",
                {"name": "test", "rulebook_id": 1, "decision_environment_id": 2},
            )

        mock_log.assert_called_once_with(
            "create_eda_activation",
            {"name": "test", "rulebook_id": 1, "decision_environment_id": 2},
            success=True,
        )

        _set_eda_client(None)
        _set_client(None)


class TestListToolsWithEda:
    """Tests for list_tools conditionally including EDA tools."""

    @pytest.mark.asyncio
    async def test_list_tools_excludes_eda_when_not_configured(self, monkeypatch):
        """list_tools returns only LM tools when EDA is not configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import TOOLS
        from lm_mcp.server import _set_eda_client, list_tools

        _set_eda_client(None)

        result = await list_tools()
        assert len(result) == len(TOOLS)

    @pytest.mark.asyncio
    async def test_list_tools_includes_eda_when_configured(self, monkeypatch):
        """list_tools includes EDA tools when EDA client is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import EDA_TOOLS, TOOLS
        from lm_mcp.server import _set_eda_client, list_tools

        _set_eda_client(MagicMock())

        result = await list_tools()
        assert len(result) == len(TOOLS) + len(EDA_TOOLS)

        _set_eda_client(None)

    @pytest.mark.asyncio
    async def test_list_tools_includes_all_when_both_configured(self, monkeypatch):
        """list_tools includes LM+AWX+EDA tools when all are configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.registry import AWX_TOOLS, EDA_TOOLS, TOOLS
        from lm_mcp.server import _set_awx_client, _set_eda_client, list_tools

        _set_awx_client(MagicMock())
        _set_eda_client(MagicMock())

        result = await list_tools()
        assert len(result) == len(TOOLS) + len(AWX_TOOLS) + len(EDA_TOOLS)

        _set_awx_client(None)
        _set_eda_client(None)

    @pytest.mark.asyncio
    async def test_eda_tool_names_set_matches_registry(self):
        """EDA_TOOL_NAMES set matches the actual EDA_TOOLS list."""
        from lm_mcp.registry import EDA_TOOLS
        from lm_mcp.server import EDA_TOOL_NAMES

        expected = {t.name for t in EDA_TOOLS}
        assert EDA_TOOL_NAMES == expected
