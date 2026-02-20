# Description: Tests for EDA tool registry definitions.
# Description: Validates tool count, naming, annotations, and handler parity.

from __future__ import annotations

from lm_mcp.registry import AWX_TOOLS, EDA_TOOLS, TOOLS, get_tool_handler


class TestEdaToolsList:
    """Tests for the EDA_TOOLS registry list."""

    def test_eda_tool_count(self):
        """EDA_TOOLS contains exactly 20 tools."""
        assert len(EDA_TOOLS) == 20

    def test_no_overlap_with_lm_tools(self):
        """EDA tool names do not collide with LM tool names."""
        lm_names = {t.name for t in TOOLS}
        eda_names = {t.name for t in EDA_TOOLS}
        overlap = lm_names & eda_names
        assert not overlap, f"Name collision with LM tools: {overlap}"

    def test_no_overlap_with_awx_tools(self):
        """EDA tool names do not collide with AWX tool names."""
        awx_names = {t.name for t in AWX_TOOLS}
        eda_names = {t.name for t in EDA_TOOLS}
        overlap = awx_names & eda_names
        assert not overlap, f"Name collision with AWX tools: {overlap}"

    def test_all_eda_tools_have_names(self):
        """Every EDA tool has a non-empty name."""
        for tool in EDA_TOOLS:
            assert tool.name, "EDA tool has empty name"

    def test_all_eda_tools_have_descriptions(self):
        """Every EDA tool has a non-empty description."""
        for tool in EDA_TOOLS:
            assert tool.description, f"EDA tool '{tool.name}' has empty description"

    def test_all_eda_tools_have_annotations(self):
        """Every EDA tool has tool annotations set."""
        for tool in EDA_TOOLS:
            assert tool.annotations is not None, (
                f"EDA tool '{tool.name}' missing annotations"
            )

    def test_all_eda_tools_have_input_schema(self):
        """Every EDA tool has an input schema."""
        for tool in EDA_TOOLS:
            assert tool.inputSchema is not None, (
                f"EDA tool '{tool.name}' missing inputSchema"
            )
            assert tool.inputSchema.get("type") == "object", (
                f"EDA tool '{tool.name}' inputSchema type is not 'object'"
            )

    def test_all_eda_names_prefixed(self):
        """All EDA tools (except test_eda_connection) use eda naming convention."""
        for tool in EDA_TOOLS:
            assert "eda" in tool.name, (
                f"EDA tool '{tool.name}' does not contain 'eda' in name"
            )


class TestEdaToolAnnotations:
    """Tests for EDA tool annotation correctness."""

    def test_read_only_tools_marked_correctly(self):
        """Read-only EDA tools have readOnlyHint=True."""
        read_only_names = {
            "test_eda_connection",
            "get_eda_activations",
            "get_eda_activation",
            "get_eda_activation_instances",
            "get_eda_activation_instance_logs",
            "get_eda_projects",
            "get_eda_project",
            "get_eda_rulebooks",
            "get_eda_rulebook",
            "get_eda_event_streams",
            "get_eda_event_stream",
        }
        for tool in EDA_TOOLS:
            if tool.name in read_only_names:
                assert tool.annotations.readOnlyHint is True, (
                    f"Tool '{tool.name}' should be READ_ONLY"
                )

    def test_write_tools_marked_correctly(self):
        """Write EDA tools have readOnlyHint=False."""
        write_names = {
            "create_eda_activation",
            "enable_eda_activation",
            "disable_eda_activation",
            "restart_eda_activation",
            "create_eda_project",
            "sync_eda_project",
            "create_eda_event_stream",
        }
        for tool in EDA_TOOLS:
            if tool.name in write_names:
                assert tool.annotations.readOnlyHint is False, (
                    f"Tool '{tool.name}' should be WRITE"
                )

    def test_delete_tools_marked_correctly(self):
        """Delete EDA tools have destructiveHint=True."""
        delete_names = {"delete_eda_activation", "delete_eda_event_stream"}
        for tool in EDA_TOOLS:
            if tool.name in delete_names:
                assert tool.annotations.destructiveHint is True, (
                    f"Tool '{tool.name}' should be DELETE"
                )


class TestEdaHandlerParity:
    """Tests that every EDA tool has a registered handler."""

    def test_every_eda_tool_has_handler(self):
        """Every EDA_TOOLS entry maps to a handler in get_tool_handler."""
        for tool in EDA_TOOLS:
            handler = get_tool_handler(tool.name)
            assert callable(handler), (
                f"EDA tool '{tool.name}' has no handler"
            )
