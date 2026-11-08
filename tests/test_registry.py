# Description: Tests for MCP tool registry.
# Description: Validates tool definitions and handlers.

import ast
import inspect

import pytest

from lm_mcp.registry import TOOLS, get_tool_handler

# List tool handlers that still format their own size or offset query, each mapped to
# the plan step that moves it onto list_tool or removes it. The guard below fails on an
# entry whose handler no longer exists or no longer formats its own query, so an entry
# leaves when its handler moves.
_LIST_TOOL_PENDING: dict[str, int] = {
    "get_action_chains": 24,
    "get_action_rules": 24,
    "get_configsource_update_reasons": 24,
    "get_device_config": 24,
    "get_device_datasources": 24,
    "get_device_eventsources": 24,
    "get_device_instances": 24,
    "get_device_logsources": 24,
    "get_access_groups": 25,
    "get_alert_rules": 25,
    "get_api_tokens": 25,
    "get_batchjobs": 25,
    "get_cost_recommendations": 25,
    "get_dashboard_groups": 25,
    "get_device_batchjobs": 25,
    "get_device_interfaces": 25,
    "get_device_properties": 25,
    "get_idle_resources": 25,
    "get_netscans": 25,
    "get_network_flows": 25,
    "get_oids": 25,
    "get_ops_notes": 25,
    "get_scheduled_downtime_jobs": 25,
    "get_service_groups": 25,
    "get_services": 25,
    "get_topology_map": 25,
    "get_trace_operations": 37,
    "get_trace_service_alerts": 37,
    "get_trace_service_datasources": 37,
    "get_trace_service_properties": 37,
    "get_trace_services": 37,
    "get_audit_logs": 38,
    "get_api_token_audit": 39,
    "get_change_audit": 39,
    "get_login_audit": 39,
    "get_configsources": 42,
    "get_datasources": 42,
    "get_diagnosticsources": 42,
    "get_eventsources": 42,
    "get_logsources": 42,
    "get_propertysources": 42,
    "get_remediationsources": 42,
    "get_topologysources": 42,
}


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
            "get_session_context",
            "set_session_variable",
            "get_session_variable",
            "delete_session_variable",
            "clear_session_context",
            "list_session_history",
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
            "get_session_context",
            "set_session_variable",
            "get_session_variable",
            "delete_session_variable",
            "clear_session_context",
            "list_session_history",
        }

        for tool in TOOLS:
            handler = get_tool_handler(tool.name)
            sig = inspect.signature(handler)
            func_params = set(sig.parameters.keys())

            # Remove 'client' param (injected by server, not from schema)
            if tool.name not in session_tools:
                func_params.discard("client")

            schema_props = set(tool.inputSchema.get("properties", {}).keys())

            # Every schema property must be a valid function parameter
            unexpected = schema_props - func_params
            assert not unexpected, (
                f"Tool '{tool.name}' schema has properties {unexpected} "
                f"that don't match function params. "
                f"Schema: {sorted(schema_props)}, "
                f"Function: {sorted(func_params)}"
            )


def _handler_sources() -> dict[str, tuple[inspect.Signature, ast.Module]]:
    """Map each registered tool's handler name to its signature and parsed source."""
    sources = {}
    for tool in TOOLS:
        handler = inspect.unwrap(get_tool_handler(tool.name))
        sources[handler.__name__] = (
            inspect.signature(handler),
            ast.parse(inspect.getsource(handler)),
        )
    return sources


def _calls_list_tool(tree: ast.Module) -> bool:
    """Return True when the handler's source calls list_tool."""
    return any(
        isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) == "list_tool"
        for node in ast.walk(tree)
    )


def _formats_own_page_query(tree: ast.Module) -> bool:
    """Return True when the handler's source writes a size or offset query key itself.

    Covers a dict literal with a "size" or "offset" key and an assignment to a "size"
    or "offset" subscript, such as params["size"].
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and any(
            isinstance(key, ast.Constant) and key.value in ("size", "offset") for key in node.keys
        ):
            return True
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value in ("size", "offset")
        ):
            return True
    return False


class TestListToolGuard:
    """R2.5: a list tool pages through list_tool and takes and declares limit and offset.

    The guard covers the registered handlers that take ``limit``, and a handler that
    formats its own page query passes only while _LIST_TOOL_PENDING names it. A handler
    that takes no ``limit``, such as a size=1 lookup by name or id, stays outside it.
    """

    def test_list_tool_handlers_take_and_declare_limit_and_offset(self):
        sources = _handler_sources()
        schemas = {tool.name: tool.inputSchema.get("properties", {}) for tool in TOOLS}
        missing = []
        for name, (sig, tree) in sources.items():
            if not _calls_list_tool(tree):
                continue
            for param in ("limit", "offset"):
                if param not in sig.parameters:
                    missing.append(f"{name} takes no {param}")
                if param not in schemas[name]:
                    missing.append(f"{name} schema declares no {param}")
        assert not missing, missing

    def test_handlers_that_format_their_own_page_query_are_pending(self):
        unlisted = sorted(
            name
            for name, (sig, tree) in _handler_sources().items()
            if "limit" in sig.parameters
            and _formats_own_page_query(tree)
            and name not in _LIST_TOOL_PENDING
        )
        assert not unlisted, f"move these onto list_tool or into _LIST_TOOL_PENDING: {unlisted}"

    def test_pending_entries_still_format_their_own_page_query(self):
        sources = _handler_sources()
        stale = sorted(
            name
            for name in _LIST_TOOL_PENDING
            if name not in sources
            or "limit" not in sources[name][0].parameters
            or not _formats_own_page_query(sources[name][1])
        )
        assert not stale, f"remove these from _LIST_TOOL_PENDING: {stale}"
