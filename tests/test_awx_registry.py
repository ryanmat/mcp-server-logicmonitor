# Description: Tests for AWX/AAP tool definitions in the registry.
# Description: Validates tool schemas, annotations, handlers, and naming conventions.

from __future__ import annotations

import inspect


class TestAwxToolDefinitions:
    """Tests for AWX_TOOLS list correctness and completeness."""

    def test_awx_tools_list_not_empty(self):
        """AWX_TOOLS list has at least one tool."""
        from lm_mcp.registry import AWX_TOOLS

        assert len(AWX_TOOLS) > 0

    def test_awx_tool_count_is_18(self):
        """AWX_TOOLS list has exactly 18 tools."""
        from lm_mcp.registry import AWX_TOOLS

        assert len(AWX_TOOLS) == 18

    def test_awx_tools_have_names(self):
        """Every AWX tool has a non-empty name."""
        from lm_mcp.registry import AWX_TOOLS

        for tool in AWX_TOOLS:
            assert tool.name, f"Tool missing name: {tool}"

    def test_awx_tools_have_descriptions(self):
        """Every AWX tool has a non-empty description."""
        from lm_mcp.registry import AWX_TOOLS

        for tool in AWX_TOOLS:
            assert tool.description, f"Tool {tool.name} missing description"

    def test_awx_tools_have_schemas(self):
        """Every AWX tool has an inputSchema with type 'object'."""
        from lm_mcp.registry import AWX_TOOLS

        for tool in AWX_TOOLS:
            assert tool.inputSchema is not None, f"Tool {tool.name} missing inputSchema"
            assert tool.inputSchema.get("type") == "object", (
                f"Tool {tool.name} inputSchema type is not 'object'"
            )

    def test_awx_tools_have_annotations(self):
        """Every AWX tool has annotations set."""
        from lm_mcp.registry import AWX_TOOLS

        for tool in AWX_TOOLS:
            assert tool.annotations is not None, f"Tool {tool.name} missing annotations"

    def test_awx_tool_names_are_unique(self):
        """All AWX tool names are unique within the AWX_TOOLS list."""
        from lm_mcp.registry import AWX_TOOLS

        names = [t.name for t in AWX_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_no_overlap_with_lm_tools(self):
        """No AWX tool name collides with an existing LM tool name."""
        from lm_mcp.registry import AWX_TOOLS, TOOLS

        lm_names = {t.name for t in TOOLS}
        awx_names = {t.name for t in AWX_TOOLS}
        overlap = lm_names & awx_names
        assert not overlap, f"Name collision between LM and AWX tools: {overlap}"

    def test_awx_read_tools_marked_readonly(self):
        """All 14 read-only AWX tools have readOnlyHint=True."""
        from lm_mcp.registry import AWX_TOOLS

        read_tools = {
            "test_awx_connection",
            "get_job_templates",
            "get_job_template",
            "get_job_status",
            "get_job_output",
            "get_inventories",
            "get_inventory_hosts",
            "get_workflow_status",
            "get_workflow_templates",
            "get_projects",
            "get_credentials",
            "get_organizations",
            "get_job_events",
            "get_hosts",
        }
        awx_map = {t.name: t for t in AWX_TOOLS}
        for name in read_tools:
            tool = awx_map[name]
            assert tool.annotations.readOnlyHint is True, (
                f"{name} should be readOnlyHint=True"
            )

    def test_awx_write_tools_not_readonly(self):
        """Launch and relaunch tools are not marked read-only."""
        from lm_mcp.registry import AWX_TOOLS

        write_tools = {"launch_job", "launch_workflow", "relaunch_job"}
        awx_map = {t.name: t for t in AWX_TOOLS}
        for name in write_tools:
            tool = awx_map[name]
            assert tool.annotations.readOnlyHint is False, (
                f"{name} should be readOnlyHint=False"
            )

    def test_cancel_job_marked_destructive(self):
        """cancel_job has destructiveHint=True."""
        from lm_mcp.registry import AWX_TOOLS

        awx_map = {t.name: t for t in AWX_TOOLS}
        tool = awx_map["cancel_job"]
        assert tool.annotations.destructiveHint is True

    def test_launch_tools_not_destructive(self):
        """Launch tools have destructiveHint=False."""
        from lm_mcp.registry import AWX_TOOLS

        launch_tools = {"launch_job", "launch_workflow", "relaunch_job"}
        awx_map = {t.name: t for t in AWX_TOOLS}
        for name in launch_tools:
            tool = awx_map[name]
            assert tool.annotations.destructiveHint is False, (
                f"{name} should not be destructive"
            )

    def test_awx_tools_all_open_world(self):
        """All AWX tools have openWorldHint=True."""
        from lm_mcp.registry import AWX_TOOLS

        for tool in AWX_TOOLS:
            assert tool.annotations.openWorldHint is True, (
                f"{tool.name} should be openWorldHint=True"
            )


class TestAwxToolHandlers:
    """Tests for AWX tool handler wiring in the registry."""

    def test_all_awx_tools_have_handlers(self):
        """Every AWX tool name maps to a handler in get_tool_handler."""
        from lm_mcp.registry import AWX_TOOLS, get_tool_handler

        for tool in AWX_TOOLS:
            handler = get_tool_handler(tool.name)
            assert callable(handler), f"No handler for {tool.name}"

    def test_awx_schema_params_match_function_params(self):
        """Schema properties (minus 'client') match handler function parameters."""
        from lm_mcp.registry import AWX_TOOLS, get_tool_handler

        for tool in AWX_TOOLS:
            handler = get_tool_handler(tool.name)
            schema_props = set(tool.inputSchema.get("properties", {}).keys())
            sig = inspect.signature(handler)
            func_params = {
                p for p in sig.parameters if p != "client"
            }
            assert schema_props == func_params, (
                f"{tool.name}: schema={schema_props} != func={func_params}"
            )

    def test_awx_write_tools_mention_write_permission(self):
        """Write tool descriptions mention write permission requirement."""
        from lm_mcp.registry import AWX_TOOLS

        write_tools = {"launch_job", "cancel_job", "relaunch_job", "launch_workflow"}
        awx_map = {t.name: t for t in AWX_TOOLS}
        for name in write_tools:
            tool = awx_map[name]
            assert "write permission" in tool.description.lower(), (
                f"{name} description should mention write permission"
            )
