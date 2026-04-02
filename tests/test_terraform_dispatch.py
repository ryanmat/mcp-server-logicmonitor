# Description: Dispatch tests for Terraform tools in the MCP server.
# Description: Verifies 5th dispatch lane routing, conditional registration, and audit logging.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import TextContent

from lm_mcp.registry import TF_TOOLS


class TestTerraformToolDispatch:
    """Test that Terraform tools dispatch to the TerraformRunner."""

    @pytest.mark.asyncio
    async def test_tf_tool_dispatched_to_runner(self, monkeypatch):
        """Terraform tool receives the TF runner, not the LM client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, execute_tool

        mock_lm = MagicMock()
        mock_runner = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(mock_runner)

        mock_result = [TextContent(type="text", text='{"ok": true}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            result = await execute_tool("terraform_plan", {"workspace": "test"})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_runner, workspace="test")
        assert result == mock_result

        _set_tf_runner(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_tf_tool_returns_error_when_not_configured(self, monkeypatch):
        """Terraform tool returns error when runner is None."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, execute_tool

        mock_lm = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(None)

        result = await execute_tool("terraform_plan", {"workspace": "test"})
        assert len(result) == 1
        assert "not configured" in result[0].text.lower()

        _set_client(None)

    @pytest.mark.asyncio
    async def test_lm_tool_unaffected_by_tf(self, monkeypatch):
        """LM tools still dispatch to LM client when TF is configured."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, execute_tool

        mock_lm = MagicMock()
        mock_runner = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(mock_runner)

        mock_result = [TextContent(type="text", text='{"items": []}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ) as mock_get:
            await execute_tool("get_devices", {})

        handler = mock_get.return_value
        handler.assert_called_once_with(mock_lm)

        _set_tf_runner(None)
        _set_client(None)

    @pytest.mark.asyncio
    async def test_session_tool_unaffected(self, monkeypatch):
        """Session tools still work without any client."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, execute_tool

        _set_client(None)
        _set_tf_runner(None)

        mock_result = [TextContent(type="text", text='{"context": {}}')]
        with patch(
            "lm_mcp.server.get_tool_handler",
            return_value=AsyncMock(return_value=mock_result),
        ):
            result = await execute_tool("get_session_context", {})
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_tf_write_tool_logged(self, monkeypatch):
        """Terraform write tools trigger audit logging."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, execute_tool

        mock_lm = MagicMock()
        mock_runner = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(mock_runner)

        mock_result = [TextContent(type="text", text='{"success": true}')]
        with (
            patch(
                "lm_mcp.server.get_tool_handler",
                return_value=AsyncMock(return_value=mock_result),
            ),
            patch("lm_mcp.server.log_write_operation") as mock_log,
        ):
            await execute_tool("terraform_apply", {"workspace": "test", "confirm": True})
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "terraform_apply"

        _set_tf_runner(None)
        _set_client(None)


class TestListToolsWithTerraform:
    """Test conditional tool registration for Terraform."""

    @pytest.mark.asyncio
    async def test_excludes_tf_when_not_configured(self, monkeypatch):
        """list_tools excludes TF tools when runner is None."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, list_tools

        mock_lm = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(None)

        result = await list_tools()
        result_names = {t.name for t in result}
        assert "terraform_plan" not in result_names

        _set_client(None)

    @pytest.mark.asyncio
    async def test_includes_tf_when_configured(self, monkeypatch):
        """list_tools includes TF tools when runner is set."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")

        from lm_mcp.server import _set_client, _set_tf_runner, list_tools

        mock_lm = MagicMock()
        mock_runner = MagicMock()
        _set_client(mock_lm)
        _set_tf_runner(mock_runner)

        result = await list_tools()
        result_names = {t.name for t in result}
        assert "terraform_plan" in result_names
        assert "terraform_apply" in result_names

        _set_tf_runner(None)
        _set_client(None)

    def test_tf_tool_names_set_matches_registry(self):
        """TF_TOOL_NAMES set matches TF_TOOLS registry."""
        from lm_mcp.server import TF_TOOL_NAMES

        expected = {t.name for t in TF_TOOLS}
        assert expected == TF_TOOL_NAMES
