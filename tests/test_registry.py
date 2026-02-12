# Description: Tests for MCP tool registry.
# Description: Validates tool definitions and handlers.

import inspect

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

    def test_device_tools_mention_resource(self):
        """Device tools include 'resource' in description for LM UI alignment."""
        device_tools = [
            "get_devices",
            "get_device",
            "create_device",
            "update_device",
            "delete_device",
            "get_device_groups",
            "create_device_group",
            "delete_device_group",
            "get_device_datasources",
            "get_device_instances",
            "get_device_data",
            "get_device_properties",
            "get_device_property",
            "update_device_property",
            "get_device_logsources",
            "get_device_neighbors",
            "get_device_interfaces",
            "get_device_connections",
            "get_device_batchjobs",
            "bulk_create_device_sdt",
        ]
        for tool_name in device_tools:
            tool = next((t for t in TOOLS if t.name == tool_name), None)
            assert tool is not None, f"Tool {tool_name} not found"
            assert "resource" in tool.description.lower(), (
                f"Tool {tool_name} description should mention 'resource': {tool.description}"
            )

    def test_all_tools_have_annotations(self):
        """All tools have ToolAnnotations defined."""
        for tool in TOOLS:
            assert tool.annotations is not None, f"Tool {tool.name} missing annotations"

    def test_read_tools_marked_readonly(self):
        """Read-only tools have readOnlyHint=True."""
        read_prefixes = ("get_", "list_")
        session_reads = {"get_session_context", "get_session_variable", "list_session_history"}
        for tool in TOOLS:
            if tool.name.startswith(read_prefixes) and tool.name not in session_reads:
                assert tool.annotations.readOnlyHint is True, (
                    f"Tool {tool.name} should be readOnlyHint=True"
                )

    def test_delete_tools_marked_destructive(self):
        """Delete tools have destructiveHint=True."""
        # Session deletes are not destructive in the monitoring sense
        session_tools = {"delete_session_variable", "clear_session_context"}
        for tool in TOOLS:
            if tool.name.startswith("delete_") and tool.name not in session_tools:
                assert tool.annotations.destructiveHint is True, (
                    f"Tool {tool.name} should be destructiveHint=True"
                )
            if tool.name.startswith("bulk_delete_"):
                assert tool.annotations.destructiveHint is True, (
                    f"Tool {tool.name} should be destructiveHint=True"
                )

    def test_session_tools_not_open_world(self):
        """Session tools have openWorldHint=False."""
        session_tools = {
            "get_session_context", "set_session_variable",
            "get_session_variable", "delete_session_variable",
            "clear_session_context", "list_session_history",
        }
        for tool in TOOLS:
            if tool.name in session_tools:
                assert tool.annotations.openWorldHint is False, (
                    f"Session tool {tool.name} should be openWorldHint=False"
                )

    def test_schema_params_match_function_params(self):
        """Schema property names must match handler function parameter names.

        The MCP server dispatches tool calls as handler(client, **arguments)
        where arguments come from the schema property names. If a schema
        property name doesn't match the function parameter name, the call
        fails with 'unexpected keyword argument'.
        """
        # Session tools don't receive a client param
        session_tools = {
            "get_session_context", "set_session_variable",
            "get_session_variable", "delete_session_variable",
            "clear_session_context", "list_session_history",
        }

        for tool in TOOLS:
            handler = get_tool_handler(tool.name)
            sig = inspect.signature(handler)
            func_params = set(sig.parameters.keys())

            # Remove 'client' param (injected by server, not from schema)
            if tool.name not in session_tools:
                func_params.discard("client")

            schema_props = set(
                tool.inputSchema.get("properties", {}).keys()
            )

            # Every schema property must be a valid function parameter
            unexpected = schema_props - func_params
            assert not unexpected, (
                f"Tool '{tool.name}' schema has properties {unexpected} "
                f"that don't match function params. "
                f"Schema: {sorted(schema_props)}, "
                f"Function: {sorted(func_params)}"
            )
