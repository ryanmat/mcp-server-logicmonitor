# Description: Tests for MCP tool filtering by enabled/disabled config.
# Description: Validates tool cherry-picking with glob patterns and rejection.

import pytest

from lm_mcp.registry import TOOLS
from lm_mcp.server import _filter_tools


class _MockConfig:
    """Lightweight config mock for tool filtering tests."""

    def __init__(self, enabled_tools=None, disabled_tools=None):
        self.enabled_tools = enabled_tools
        self.disabled_tools = disabled_tools


class TestFilterTools:
    """Tests for the _filter_tools function."""

    def test_no_filters_returns_all(self):
        """No filters returns all tools."""
        config = _MockConfig()
        result = _filter_tools(TOOLS, config)
        assert len(result) == len(TOOLS)

    def test_enabled_exact_names(self):
        """Enabled list with exact names returns only those tools."""
        config = _MockConfig(enabled_tools="get_devices,get_alerts")
        result = _filter_tools(TOOLS, config)
        names = {t.name for t in result}
        assert names == {"get_devices", "get_alerts"}

    def test_enabled_glob_pattern(self):
        """Enabled list with glob pattern matches correctly."""
        config = _MockConfig(enabled_tools="get_device*")
        result = _filter_tools(TOOLS, config)
        for tool in result:
            assert tool.name.startswith("get_device")
        assert len(result) > 1

    def test_disabled_exact_names(self):
        """Disabled list hides specific tools."""
        config = _MockConfig(disabled_tools="delete_device,delete_device_group")
        result = _filter_tools(TOOLS, config)
        names = {t.name for t in result}
        assert "delete_device" not in names
        assert "delete_device_group" not in names
        assert "get_devices" in names

    def test_disabled_glob_pattern(self):
        """Disabled list with glob hides matching tools."""
        config = _MockConfig(disabled_tools="delete_*")
        result = _filter_tools(TOOLS, config)
        for tool in result:
            assert not tool.name.startswith("delete_"), (
                f"Tool {tool.name} should be hidden by delete_* pattern"
            )

    def test_enabled_multiple_patterns(self):
        """Multiple glob patterns in enabled list work together."""
        config = _MockConfig(enabled_tools="get_devices,get_alerts,export_*")
        result = _filter_tools(TOOLS, config)
        names = {t.name for t in result}
        assert "get_devices" in names
        assert "get_alerts" in names
        # Should include export tools
        export_tools = [n for n in names if n.startswith("export_")]
        assert len(export_tools) > 0
        # Should NOT include other tools
        assert "create_device" not in names


class TestCallToolRejection:
    """Tests for call_tool rejection of disabled tools."""

    @pytest.mark.asyncio
    async def test_disabled_tool_rejected(self, monkeypatch):
        """Calling a disabled tool returns error message."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
        monkeypatch.setenv("LM_DISABLED_TOOLS", "delete_*")

        from lm_mcp.server import call_tool

        result = await call_tool("delete_device", {"device_id": 1})
        assert "disabled" in result[0].text.lower() or "not enabled" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_enabled_tool_not_in_list_rejected(self, monkeypatch):
        """Calling a tool not in enabled list returns error message."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
        monkeypatch.setenv("LM_ENABLED_TOOLS", "get_devices,get_alerts")

        from lm_mcp.server import call_tool

        result = await call_tool("delete_device", {"device_id": 1})
        assert "not enabled" in result[0].text.lower() or "error" in result[0].text.lower()
