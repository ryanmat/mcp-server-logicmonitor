# Description: Tests for MCP tool registry.
# Description: Validates tool definitions and handlers.

import ast
import inspect

import pytest

from lm_mcp.registry import TOOLS, get_tool_handler

# The eight per-series tools analyze_metric replaces (spec R2.1).
_SERIES_TOOLS_REPLACED = (
    "forecast_metric",
    "classify_trend",
    "detect_seasonality",
    "detect_change_points",
    "get_metric_anomalies",
    "score_device_health",
    "save_baseline",
    "compare_to_baseline",
)


class TestSeriesToolsReplaced:
    """analyze_metric is registered and the eight per-series tools it replaces are not (R2.1)."""

    def test_analyze_metric_is_registered(self):
        assert "analyze_metric" in {tool.name for tool in TOOLS}
        assert get_tool_handler("analyze_metric").__name__ == "analyze_metric"

    @pytest.mark.parametrize("name", _SERIES_TOOLS_REPLACED)
    def test_replaced_tool_is_not_registered(self, name):
        assert name not in {tool.name for tool in TOOLS}
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler(name)


# The five alert-window tools analyze_alerts replaces (spec R2.2).
_ALERT_WINDOW_TOOLS_REPLACED = (
    "correlate_alerts",
    "get_alert_statistics",
    "score_alert_noise",
    "detect_alert_burst",
    "correlate_changes",
)


class TestAlertWindowToolsReplaced:
    """analyze_alerts is registered; the five tools it replaces are not (R2.2, R2.13)."""

    def test_analyze_alerts_is_registered(self):
        assert "analyze_alerts" in {tool.name for tool in TOOLS}
        assert get_tool_handler("analyze_alerts").__name__ == "analyze_alerts"

    @pytest.mark.parametrize("name", _ALERT_WINDOW_TOOLS_REPLACED)
    def test_replaced_tool_is_not_registered(self, name):
        assert name not in {tool.name for tool in TOOLS}
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler(name)


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
        session_reads = {"get_session_context", "get_session_variable", "get_session_history"}
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
            "get_session_history",
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
            "get_session_history",
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


_EDWIN_TOOLS = {
    "get_edwin_insights",
    "get_edwin_insight",
    "get_edwin_records",
    "get_edwin_alert_volume",
    "get_edwin_metadata",
    "get_edwin_tools",
    "edwin_run_tool",
    "ask_edwin",
}


_LOG_TOOLS = {
    "get_log_pipelines",
    "get_tracked_log_queries",
    "get_log_query_groups",
    "get_log_partitions",
    "get_log_usage",
}


class TestLogTools:
    """R3.3: the five LM Logs reads are registered, read-only, handled and grouped."""

    def test_each_is_registered_read_only_with_its_handler(self):
        registered = {tool.name: tool for tool in TOOLS if tool.name in _LOG_TOOLS}

        assert set(registered) == _LOG_TOOLS
        assert all(tool.annotations.readOnlyHint is True for tool in registered.values())
        assert {name: get_tool_handler(name).__name__ for name in _LOG_TOOLS} == {
            name: name for name in _LOG_TOOLS
        }

    def test_the_paged_reads_declare_limit_and_offset_and_the_others_do_not(self):
        schemas = {tool.name: tool.inputSchema["properties"] for tool in TOOLS}

        for name in ("get_tracked_log_queries", "get_log_query_groups", "get_log_partitions"):
            assert {"limit", "offset"} <= set(schemas[name]), name
        assert schemas["get_log_pipelines"] == {}
        assert schemas["get_log_usage"] == {}

    def test_the_logs_category_holds_the_five_tools(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert set(TOOL_CATEGORIES["categories"]["logs"]["tools"]) == _LOG_TOOLS


_COLLECTOR_READS = {
    "get_collector_events",
    "get_collector_log_files",
    "get_collector_log_file",
    "get_collector_upgrade_history",
}


class TestCollectorReadTools:
    """R3.4: the collector event, log file and upgrade history reads are registered,
    read-only, handled and grouped."""

    def test_each_is_registered_read_only_with_its_handler(self):
        registered = {tool.name: tool for tool in TOOLS if tool.name in _COLLECTOR_READS}

        assert set(registered) == _COLLECTOR_READS
        assert all(tool.annotations.readOnlyHint is True for tool in registered.values())
        assert {name: get_tool_handler(name).__name__ for name in _COLLECTOR_READS} == {
            name: name for name in _COLLECTOR_READS
        }

    def test_the_schemas_declare_paging_ids_and_the_bounded_byte_cap(self):
        tools = {tool.name: tool.inputSchema for tool in TOOLS}

        for name in ("get_collector_events", "get_collector_log_files"):
            assert {"collector_id", "limit", "offset"} <= set(tools[name]["properties"]), name
            assert tools[name]["required"] == ["collector_id"], name
        assert set(tools["get_collector_upgrade_history"]["properties"]) == {"limit", "offset"}
        log_file = tools["get_collector_log_file"]
        assert log_file["required"] == ["collector_id", "file_name"]
        assert log_file["properties"]["max_bytes"] == {
            "type": "integer",
            "default": 20000,
            "minimum": 1,
            "maximum": 200000,
            "description": log_file["properties"]["max_bytes"]["description"],
        }

    @pytest.mark.parametrize(
        ("file_name", "valid"),
        [
            ("82.postcheck.log.zip", True),
            ("stamp_1783411000000.48721.wrapper.1.log.zip", True),
            ("a/b", False),
            ("../x", False),
            (".hidden", False),
        ],
    )
    def test_file_name_admits_one_plain_path_segment(self, file_name, valid):
        import jsonschema

        (schema,) = [t.inputSchema for t in TOOLS if t.name == "get_collector_log_file"]
        arguments = {"collector_id": 82, "file_name": file_name}

        if valid:
            jsonschema.validate(arguments, schema)
        else:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(arguments, schema)

    def test_the_collectors_category_holds_them(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert set(TOOL_CATEGORIES["categories"]["collectors"]["tools"]) >= _COLLECTOR_READS


_COLLECTOR_OPERATIONS = {
    "run_collector_status_check",
    "restart_collector",
    "acknowledge_collector_down",
}


class TestCollectorOperationTools:
    """R3.4: the status check, restart and down acknowledgement are write tools; the
    restart alone is destructive."""

    def test_each_is_a_write_tool_with_its_handler_and_says_so(self):
        registered = {tool.name: tool for tool in TOOLS if tool.name in _COLLECTOR_OPERATIONS}

        assert set(registered) == _COLLECTOR_OPERATIONS
        assert {name: tool.annotations.readOnlyHint for name, tool in registered.items()} == {
            name: False for name in _COLLECTOR_OPERATIONS
        }
        assert {name: tool.annotations.destructiveHint for name, tool in registered.items()} == {
            "run_collector_status_check": False,
            "restart_collector": True,
            "acknowledge_collector_down": False,
        }
        assert all("requires write permission" in tool.description for tool in registered.values())
        assert {name: get_tool_handler(name).__name__ for name in _COLLECTOR_OPERATIONS} == {
            name: name for name in _COLLECTOR_OPERATIONS
        }

    def test_the_acknowledgement_requires_a_comment(self):
        (schema,) = [t.inputSchema for t in TOOLS if t.name == "acknowledge_collector_down"]

        assert schema["required"] == ["collector_id", "comment"]
        assert schema["properties"]["comment"]["minLength"] == 1

    def test_the_collectors_category_holds_them(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert set(TOOL_CATEGORIES["categories"]["collectors"]["tools"]) >= _COLLECTOR_OPERATIONS


class TestAlertSettingTools:
    """R3.5: the threshold read and write are registered, gated and grouped."""

    def test_the_read_is_read_only_and_the_write_is_a_write(self):
        tools = {tool.name: tool for tool in TOOLS}

        assert tools["get_alert_settings"].annotations.readOnlyHint is True
        assert tools["update_alert_settings"].annotations.readOnlyHint is False
        assert tools["update_alert_settings"].annotations.destructiveHint is False
        assert "requires write permission" in tools["update_alert_settings"].description
        assert {
            name: get_tool_handler(name).__name__ for name in tools if "alert_settings" in name
        } == {
            "get_alert_settings": "get_alert_settings",
            "update_alert_settings": "update_alert_settings",
        }

    def test_both_name_the_three_levels_and_the_write_needs_a_threshold(self):
        schemas = {tool.name: tool.inputSchema for tool in TOOLS}

        for name in ("get_alert_settings", "update_alert_settings"):
            assert schemas[name]["properties"]["level"]["enum"] == ["instance", "device", "group"]
        assert schemas["get_alert_settings"]["required"] == ["level"]
        assert schemas["update_alert_settings"]["required"] == ["level", "threshold"]

    def test_the_alerts_category_holds_them(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert set(TOOL_CATEGORIES["categories"]["alerts"]["tools"]) >= {
            "get_alert_settings",
            "update_alert_settings",
        }


class TestEdwinTools:
    """R3.1: the eight Edwin tools are registered, annotated and grouped."""

    def test_the_server_gates_exactly_the_registered_edwin_tools(self):
        from lm_mcp.server import EDWIN_TOOLS

        assert set(EDWIN_TOOLS) == _EDWIN_TOOLS
        assert {tool.name for tool in TOOLS} >= _EDWIN_TOOLS

    def test_edwin_run_tool_is_a_destructive_run_and_the_other_seven_read_only(self):
        annotations = {tool.name: tool.annotations for tool in TOOLS if tool.name in _EDWIN_TOOLS}

        run = annotations.pop("edwin_run_tool")
        assert (run.readOnlyHint, run.destructiveHint, run.idempotentHint) == (False, True, False)
        assert all(a.readOnlyHint is True for a in annotations.values())

    def test_edwin_run_tool_says_it_needs_write_permission(self):
        tool = next(t for t in TOOLS if t.name == "edwin_run_tool")
        assert "write permission" in tool.description.lower()

    def test_the_edwin_category_holds_the_eight_tools(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        assert set(TOOL_CATEGORIES["categories"]["edwin"]["tools"]) == _EDWIN_TOOLS


class TestListToolGuard:
    """R2.5: a list tool pages through list_tool and takes and declares limit and offset.

    The guard covers the registered handlers that take ``limit``; none may format its
    own page query. A handler that takes no ``limit``, such as a size=1 lookup by name or
    id, stays outside it.
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

    def test_list_tool_calls_forward_limit_and_offset(self):
        """Each list_tool call passes the handler's own offset, and a limit read from its limit."""
        unforwarded = []
        for name, (_sig, tree) in _handler_sources().items():
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
                    == "list_tool"
                ):
                    continue
                keywords = {kw.arg: kw.value for kw in node.keywords}
                offset = keywords.get("offset")
                if not (isinstance(offset, ast.Name) and offset.id == "offset"):
                    unforwarded.append(f"{name} offset")
                limit = keywords.get("limit")
                if limit is None or not any(
                    isinstance(n, ast.Name) and n.id == "limit" for n in ast.walk(limit)
                ):
                    unforwarded.append(f"{name} limit")
        assert not unforwarded, unforwarded

    def test_no_list_handler_formats_its_own_page_query(self):
        """The Edwin reads stay outside: Edwin's record query is not a LogicMonitor list, its
        body carries ``size`` and it takes no offset (spec R3.1)."""
        own = sorted(
            name
            for name, (sig, tree) in _handler_sources().items()
            if "limit" in sig.parameters
            and name not in _EDWIN_TOOLS
            and _formats_own_page_query(tree)
        )
        assert not own, f"move these onto list_tool: {own}"


# R3.6, Step 67: the device and group property tools, Active Discovery and escalation.
_STEP_67_ANNOTATIONS = {
    "get_device_group_properties": (True, False),
    "update_device_group_property": (False, False),
    "delete_device_group_property": (False, True),
    "delete_device_property": (False, True),
    "run_auto_discovery": (False, False),
    "escalate_alert": (False, False),
}
# Tools whose property_name goes into a URL path segment.
_PROPERTY_PATH_TOOLS = (
    "get_device_group_properties",
    "update_device_group_property",
    "delete_device_group_property",
    "delete_device_property",
)


class TestStep67Tools:
    """R3.6: the six tools are registered with their handlers, gated, grouped, and refuse a
    property name that is not one path segment."""

    def test_each_has_its_handler_and_its_read_and_destructive_hints(self):
        tools = {tool.name: tool for tool in TOOLS if tool.name in _STEP_67_ANNOTATIONS}

        assert {
            name: (tool.annotations.readOnlyHint, tool.annotations.destructiveHint)
            for name, tool in tools.items()
        } == _STEP_67_ANNOTATIONS
        assert {name: get_tool_handler(name).__name__ for name in _STEP_67_ANNOTATIONS} == {
            name: name for name in _STEP_67_ANNOTATIONS
        }

    def test_each_write_says_it_requires_write_permission(self):
        tools = {tool.name: tool for tool in TOOLS}

        assert [
            name
            for name, (read_only, _) in _STEP_67_ANNOTATIONS.items()
            if not read_only and "requires write permission" not in tools[name].description
        ] == []

    def test_the_schemas_name_their_ids_and_required_arguments(self):
        schemas = {tool.name: tool.inputSchema for tool in TOOLS}

        assert {name: schemas[name]["required"] for name in _STEP_67_ANNOTATIONS} == {
            "get_device_group_properties": ["group_id"],
            "update_device_group_property": ["group_id", "property_name", "property_value"],
            "delete_device_group_property": ["group_id", "property_name"],
            "delete_device_property": ["device_id", "property_name"],
            "run_auto_discovery": ["device_id"],
            "escalate_alert": ["alert_id"],
        }
        assert {"limit", "offset", "name_filter", "property_name"} <= set(
            schemas["get_device_group_properties"]["properties"]
        )

    def test_the_group_write_uses_the_argument_pair_the_audit_masks(self):
        from lm_mcp.logging import redact_arguments

        (schema,) = [t.inputSchema for t in TOOLS if t.name == "update_device_group_property"]
        arguments = {"group_id": 3339, "property_name": "snmp.community", "property_value": "s"}

        assert set(arguments) == set(schema["properties"])
        assert redact_arguments(arguments)["property_value"] == "***"

    @pytest.mark.parametrize("tool_name", _PROPERTY_PATH_TOOLS)
    @pytest.mark.parametrize(
        ("property_name", "valid"),
        [
            ("lmmcp.seed", True),
            ("snmp.community", True),
            ("system.categories", True),
            ("kubernetes-label_x.1", True),
            ("..", False),
            (".", False),
            ("../5", False),
            ("kubernetes.io/metadata.name", False),
            ("a?b", False),
            ("a#b", False),
            ("", False),
        ],
    )
    def test_property_name_admits_one_plain_path_segment(self, tool_name, property_name, valid):
        import jsonschema

        (schema,) = [t.inputSchema for t in TOOLS if t.name == tool_name]
        arguments = {
            "group_id": 3339,
            "device_id": 1786,
            "property_name": property_name,
            "property_value": "x",
        }
        arguments = {key: value for key, value in arguments.items() if key in schema["properties"]}

        if valid:
            jsonschema.validate(arguments, schema)
        else:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(arguments, schema)

    def test_the_alert_id_admits_an_lm_id_and_refuses_a_path(self):
        import jsonschema

        (schema,) = [t.inputSchema for t in TOOLS if t.name == "escalate_alert"]

        for bad in ("../x", "a/b", "1?x=y", ""):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate({"alert_id": bad}, schema)
        for good in ("DS362817020", "LMA123", "LMD33315752"):
            jsonschema.validate({"alert_id": good}, schema)

    def test_the_device_tools_mention_resource(self):
        tools = {tool.name: tool for tool in TOOLS}

        assert [
            name
            for name in _STEP_67_ANNOTATIONS
            if name != "escalate_alert" and "resource" not in tools[name].description.lower()
        ] == []

    def test_the_devices_and_alerts_categories_hold_them(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        categories = TOOL_CATEGORIES["categories"]
        assert set(categories["devices"]["tools"]) >= set(_STEP_67_ANNOTATIONS) - {"escalate_alert"}
        assert "escalate_alert" in categories["alerts"]["tools"]


# R3.6, Step 68: the four reads and the category each joins.
_STEP_68_CATEGORIES = {
    "get_datasource_devices": "datasources",
    "get_unmonitored_devices": "devices",
    "get_website_checkpoints": "websites",
    "get_device_delta": "devices",
}


class TestStep68Tools:
    """R3.6: the four reads are registered read-only with their handlers and grouped."""

    def test_each_is_read_only_with_its_handler(self):
        tools = {tool.name: tool for tool in TOOLS if tool.name in _STEP_68_CATEGORIES}

        assert {name: tool.annotations.readOnlyHint for name, tool in tools.items()} == {
            name: True for name in _STEP_68_CATEGORIES
        }
        assert {name: get_tool_handler(name).__name__ for name in _STEP_68_CATEGORIES} == {
            name: name for name in _STEP_68_CATEGORIES
        }

    def test_the_schemas(self):
        schemas = {tool.name: tool.inputSchema for tool in TOOLS}

        assert schemas["get_datasource_devices"]["required"] == ["datasource_id"]
        assert {"name_filter", "limit", "offset"} <= set(
            schemas["get_datasource_devices"]["properties"]
        )
        assert set(schemas["get_unmonitored_devices"]["properties"]) == {"limit", "offset"}
        assert set(schemas["get_website_checkpoints"]["properties"]) == {"limit", "offset"}
        assert set(schemas["get_device_delta"]["properties"]) == {
            "delta_id",
            "name_filter",
            "limit",
            "offset",
        }

    def test_the_delta_id_admits_a_delta_id_and_refuses_a_path(self):
        import jsonschema

        (schema,) = [t.inputSchema for t in TOOLS if t.name == "get_device_delta"]

        jsonschema.validate({"delta_id": "a11654364568495ba22ffa4c4c61a259"}, schema)
        for bad in ("../x", "a/b", ""):
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate({"delta_id": bad}, schema)

    def test_each_category_holds_its_tool(self):
        from lm_mcp.resources.guides import TOOL_CATEGORIES

        categories = TOOL_CATEGORIES["categories"]
        assert [
            name
            for name, category in _STEP_68_CATEGORIES.items()
            if name not in categories[category]["tools"]
        ] == []
