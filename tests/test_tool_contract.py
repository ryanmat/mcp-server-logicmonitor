# Description: Contract snapshot and drift-prevention tests for the MCP tool surface.
# Description: Fails on any accidental tool name, parameter, schema, or description change.

import json
from pathlib import Path

from lm_mcp.registry import AWX_TOOLS, TF_TOOLS, TOOLS, WATSONX_TOOLS

FIXTURE = Path(__file__).parent / "fixtures" / "tool_list.json"


def _annotations(annotations) -> dict | None:
    if annotations is None:
        return None
    return {
        "readOnlyHint": annotations.readOnlyHint,
        "destructiveHint": annotations.destructiveHint,
        "idempotentHint": annotations.idempotentHint,
        "openWorldHint": annotations.openWorldHint,
        "title": annotations.title,
    }


def canonical_tool_surface() -> dict:
    """Serialize the full possible tool surface (core plus every conditional integration).

    Unconditional on purpose: the snapshot is the contract for every tool the server can
    ever advertise, so drift is caught regardless of which integrations are configured.
    """
    surface: dict = {}
    for tool in [*TOOLS, *AWX_TOOLS, *WATSONX_TOOLS, *TF_TOOLS]:
        surface[tool.name] = {
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "annotations": _annotations(tool.annotations),
        }
    return surface


def test_no_duplicate_tool_names():
    """No tool name is registered twice across the core and conditional registries."""
    names = [t.name for t in [*TOOLS, *AWX_TOOLS, *WATSONX_TOOLS, *TF_TOOLS]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate tool names across registries: {dupes}"


def test_tool_contract_snapshot():
    """The advertised tool surface matches the committed snapshot.

    Any added or removed tool, renamed parameter, changed type or required field, or
    edited description fails this test. If the change is intentional, regenerate with:
        uv run python tests/test_tool_contract.py
    """
    current = canonical_tool_surface()
    expected = json.loads(FIXTURE.read_text())

    cur, exp = set(current), set(expected)
    added = sorted(cur - exp)
    removed = sorted(exp - cur)
    changed = sorted(n for n in cur & exp if current[n] != expected[n])

    problems = []
    if added:
        problems.append(f"ADDED tools: {added}")
    if removed:
        problems.append(f"REMOVED tools: {removed}")
    if changed:
        problems.append(f"CHANGED (param/type/required/description/schema): {changed}")

    assert not problems, (
        "MCP tool contract drift detected:\n  "
        + "\n  ".join(problems)
        + "\nIf intentional, regenerate: uv run python tests/test_tool_contract.py"
    )


def test_workflow_handlers_in_workflow_tools():
    """Every tool implemented in tools/workflows.py is in the curated WORKFLOW_TOOLS set.

    Guards the LM_MCP_CATEGORIES=workflow filter from silently dropping a newly added
    composite (the detect_site_outage / audit_network_monitoring_coverage drift class).
    """
    from lm_mcp.categories import WORKFLOW_TOOLS
    from lm_mcp.registry import get_tool_handler

    workflow_impl = []
    for tool in TOOLS:
        handler = get_tool_handler(tool.name)
        if getattr(handler, "__module__", "").endswith("tools.workflows"):
            workflow_impl.append(tool.name)

    missing = sorted(n for n in workflow_impl if n not in WORKFLOW_TOOLS)
    assert not missing, f"workflows.py tools missing from WORKFLOW_TOOLS: {missing}"


def test_server_instructions_point_to_search_tools():
    """The server instructions steer the model to search_tools first."""
    from lm_mcp.server import SERVER_INSTRUCTIONS

    assert "search_tools" in SERVER_INSTRUCTIONS


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    surface = canonical_tool_surface()
    FIXTURE.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
    print(f"wrote {FIXTURE} ({len(surface)} tools)")
