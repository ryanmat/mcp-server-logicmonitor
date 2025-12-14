# Description: Tests for MCP tool registry.
# Description: Validates tool definitions and handlers.

import pytest

from lm_mcp.registry import TOOLS, get_tool_handler


class TestRegistry:
    """Tests for tool registry."""

    def test_tools_list_not_empty(self):
        """Registry has tools defined."""
        assert len(TOOLS) > 0

    def test_tools_have_names(self):
        """All tools have names."""
        for tool in TOOLS:
            assert tool.name
            assert isinstance(tool.name, str)

    def test_tools_have_descriptions(self):
        """All tools have descriptions."""
        for tool in TOOLS:
            assert tool.description
            assert isinstance(tool.description, str)

    def test_tools_have_schemas(self):
        """All tools have input schemas."""
        for tool in TOOLS:
            assert tool.inputSchema
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"

    def test_tool_names_are_unique(self):
        """All tool names are unique."""
        names = [tool.name for tool in TOOLS]
        assert len(names) == len(set(names))

    def test_get_tool_handler_valid(self):
        """get_tool_handler returns handler for valid tool."""
        handler = get_tool_handler("get_devices")
        assert callable(handler)

    def test_get_tool_handler_invalid(self):
        """get_tool_handler raises for invalid tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler("nonexistent_tool")

    def test_all_tools_have_handlers(self):
        """All registered tools have handlers."""
        for tool in TOOLS:
            handler = get_tool_handler(tool.name)
            assert callable(handler)

    def test_write_tools_have_permission_warning(self):
        """Write operation tools mention 'write permission' in description."""
        write_tools = [
            "create_device",
            "update_device",
            "delete_device",
            "acknowledge_alert",
            "create_sdt",
            "delete_sdt",
        ]
        for tool_name in write_tools:
            tool = next((t for t in TOOLS if t.name == tool_name), None)
            assert tool is not None, f"Tool {tool_name} not found"
            assert "write permission" in tool.description.lower()

    def test_bulk_tools_mention_limit(self):
        """Bulk operation tools mention max limit in description."""
        bulk_tools = [
            "bulk_acknowledge_alerts",
            "bulk_create_device_sdt",
            "bulk_delete_sdt",
        ]
        for tool_name in bulk_tools:
            tool = next((t for t in TOOLS if t.name == tool_name), None)
            assert tool is not None, f"Tool {tool_name} not found"
            assert "100" in tool.description or "max" in tool.description.lower()
