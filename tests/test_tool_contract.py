# Description: Contract snapshot and drift-prevention tests for the MCP tool surface.
# Description: Fails on any accidental tool name, parameter, schema, or description change.

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import respx

from lm_mcp.registry import TOOLS

FIXTURE = Path(__file__).parent / "fixtures" / "tool_list.json"
READONLY_FIXTURE = Path(__file__).parent / "fixtures" / "tool_list_readonly.json"

# The tools that change no portal state but are not read-only: session state and portal
# selection. They stay listed with writes off.
_CLOSED_WORLD_WRITES = {
    "set_session_variable",
    "delete_session_variable",
    "clear_session_context",
    "use_portal",
    "run_portal_reload",
}


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
    """Serialize every tool the registry defines.

    Unconditional on purpose: the snapshot is the contract for every tool the server can
    ever advertise, so drift is caught regardless of which tools a configuration lists.
    """
    surface: dict = {}
    for tool in TOOLS:
        surface[tool.name] = {
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "annotations": _annotations(tool.annotations),
        }
        if tool.outputSchema is not None:
            surface[tool.name]["outputSchema"] = tool.outputSchema
    return surface


def test_no_duplicate_tool_names():
    """No tool name is registered twice."""
    names = [t.name for t in TOOLS]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate tool names: {dupes}"


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


def readonly_tool_names() -> list[str]:
    """Every tool name the server can list with writes off, portal tools included."""
    from lm_mcp.server import _filter_tools

    config = SimpleNamespace(
        enabled_tools=None,
        disabled_tools=None,
        mcp_categories=None,
        multi_portal=True,
        enable_write_operations=False,
    )
    return sorted(tool.name for tool in _filter_tools(TOOLS, config))


def _changes_the_portal(tool) -> bool:
    return tool.annotations.readOnlyHint is False and tool.annotations.openWorldHint is True


@pytest.fixture
def single_portal(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    for name in (
        "LM_ENABLE_WRITE_OPERATIONS",
        "LM_ENABLED_TOOLS",
        "LM_DISABLED_TOOLS",
        "LM_MCP_CATEGORIES",
        "LM_MULTI_PORTAL",
    ):
        monkeypatch.delenv(name, raising=False)


async def test_writes_off_lists_no_tool_that_changes_the_portal(single_portal):
    """R1.9: with writes off, tools/list carries no tool annotated as changing the portal."""
    from lm_mcp.server import EDWIN_TOOLS, PORTAL_TOOLS, list_tools

    listed = await list_tools()
    names = {tool.name for tool in listed}

    assert [tool.name for tool in listed if _changes_the_portal(tool)] == []
    assert {t.name for t in listed if t.annotations.readOnlyHint is False} == (
        _CLOSED_WORLD_WRITES - PORTAL_TOOLS
    )
    assert names == (
        {t.name for t in TOOLS if not _changes_the_portal(t)} - PORTAL_TOOLS - EDWIN_TOOLS
    )


async def test_writes_off_keeps_portal_selection_in_multi_portal(monkeypatch, tmp_path):
    """use_portal and run_portal_reload stay listed with writes off; they change no portal."""
    from lm_mcp.server import list_tools

    portals = tmp_path / "portals.json"
    portals.write_text(json.dumps({"acme": {"portal": "acme.example.com", "bearer_token": "t"}}))
    monkeypatch.setenv("LM_MULTI_PORTAL", "true")
    monkeypatch.setenv("LM_PORTALS_FILE", str(portals))
    for name in ("LM_PORTAL", "LM_BEARER_TOKEN", "LM_ENABLE_WRITE_OPERATIONS", "LM_MCP_CATEGORIES"):
        monkeypatch.delenv(name, raising=False)

    names = {tool.name for tool in await list_tools()}

    assert {"use_portal", "run_portal_reload", "get_portals", "get_current_portal"} <= names
    assert "acknowledge_alert" not in names


async def test_writes_on_lists_every_tool(single_portal, monkeypatch):
    """R1.9: with writes on, tools/list carries every tool of a single portal without Edwin."""
    from lm_mcp.server import EDWIN_TOOLS, PORTAL_TOOLS, list_tools

    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    names = {tool.name for tool in await list_tools()}

    assert names == {t.name for t in TOOLS} - PORTAL_TOOLS - EDWIN_TOOLS


async def test_a_hidden_tool_called_by_name_is_refused(single_portal, caplog):
    """R1.9: tools/call on a tool hidden by the write gate returns the write-disabled error."""
    import logging

    from lm_mcp.server import call_tool
    from tests.envelope import envelope

    with caplog.at_level(logging.WARNING, logger="lm_mcp.audit"):
        result = await call_tool("acknowledge_alert", {"alert_id": "LMA1", "comment": "x"})

    assert result.isError is True
    error = envelope(result.content)
    assert error["code"] == "WRITE_DISABLED"
    assert error["message"].startswith("Write operations are disabled")
    assert [r.getMessage() for r in caplog.records if r.name == "lm_mcp.audit"] == [
        "Write operation failed: acknowledge_alert args={'alert_id': 'LMA1', 'comment': 'x'}"
    ]


@respx.mock
async def test_update_logicmodule_is_refused_with_writes_off(single_portal, reset_portals):
    """update_logicmodule has no write gate of its own; execute_tool refuses it while hidden."""
    from lm_mcp.auth.bearer import BearerAuth
    from lm_mcp.client import LogicMonitorClient
    from lm_mcp.server import _set_client, execute_tool
    from tests.envelope import envelope

    _set_client(
        LogicMonitorClient(
            base_url="https://test.logicmonitor.com/santaba/rest",
            auth=BearerAuth("test-token"),
            timeout=30,
        )
    )

    result = await execute_tool(
        "update_logicmodule", {"type": "datasource", "id": 1, "changes": {"description": "x"}}
    )

    assert envelope(result)["message"].startswith("Write operations are disabled")
    assert respx.calls.call_count == 0


def test_readonly_tool_list_snapshot():
    """The tools listed with writes off match the committed read-only snapshot.

    Regenerate with: uv run python tests/test_tool_contract.py
    """
    assert readonly_tool_names() == json.loads(READONLY_FIXTURE.read_text())


def test_server_instructions_describe_the_write_gate_as_it_is():
    """The instructions say write tools are listed only with writes on."""
    from lm_mcp.server import SERVER_INSTRUCTIONS

    assert "listed only when" in SERVER_INSTRUCTIONS
    assert "LM_ENABLE_WRITE_OPERATIONS" in SERVER_INSTRUCTIONS
    assert f"up to {len(TOOLS)} " in SERVER_INSTRUCTIONS


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    surface = canonical_tool_surface()
    FIXTURE.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
    print(f"wrote {FIXTURE} ({len(surface)} tools)")
    readonly = readonly_tool_names()
    READONLY_FIXTURE.write_text(json.dumps(readonly, indent=2) + "\n")
    print(f"wrote {READONLY_FIXTURE} ({len(readonly)} tools)")


# POST paths whose call changes a monitored host or the collector serving it: a remediation
# run and a collector restart (spec R3.4).
_DESTRUCTIVE_POSTS = ("/setting/remediationsources/executemanually", "/services/restart")


def _handler_sources(tool_name: str) -> str:
    """The handler's source and that of each function its module holds that it calls by name."""
    import inspect
    import re

    from lm_mcp.registry import get_tool_handler

    handler = get_tool_handler(tool_name)
    source = inspect.getsource(handler)
    called = set(re.findall(r"\b([A-Za-z_]\w*)\(", source))
    module = vars(inspect.getmodule(handler))
    helpers = [
        inspect.getsource(module[name])
        for name in sorted(called)
        if name in module and inspect.isfunction(module[name]) and module[name] is not handler
    ]
    return "\n".join([source, *helpers])


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_a_tool_that_deletes_or_runs_a_remediation_is_destructive(tool):
    """R2.9: a handler that issues a DELETE, itself or through a helper of its module, or
    POSTs a remediation run or a collector restart carries destructiveHint=true."""
    source = _handler_sources(tool.name)

    if "client.delete(" in source or any(path in source for path in _DESTRUCTIVE_POSTS):
        assert tool.annotations is not None
        assert tool.annotations.destructiveHint is True, tool.name


def test_execute_remediation_is_destructive_and_execute_diagnostic_is_not():
    """A remediation changes the host, so elicitation can ask first; a
    diagnostic reads it."""
    tools = {tool.name: tool for tool in TOOLS}

    assert tools["execute_remediation"].annotations.destructiveHint is True
    assert tools["execute_diagnostic"].annotations.destructiveHint is False


def test_no_tool_declares_a_confirm_flag():
    """R2.9: destructiveHint and elicitation stand where a model-set confirm flag stood."""
    assert [t.name for t in TOOLS if "confirm" in t.inputSchema.get("properties", {})] == []


def test_ops_note_ids_are_strings_on_every_tool():
    """R2.9: ops note ids carry letters, so get_ops_note takes the string the others take."""
    for name in ("get_ops_note", "update_ops_note", "delete_ops_note"):
        (tool,) = [t for t in TOOLS if t.name == name]
        note_id = tool.inputSchema["properties"]["note_id"]
        assert note_id["type"] == "string", name
        assert "pattern" in note_id, name


def test_no_tool_text_carries_an_em_or_en_dash():
    """Descriptions and parameter descriptions are public text, which the house style
    writes without em or en dashes."""
    hits = [
        (tool.name, where)
        for tool in TOOLS
        for where, text in [("description", tool.description or "")]
        + [
            (name, prop.get("description", ""))
            for name, prop in tool.inputSchema.get("properties", {}).items()
        ]
        if "\N{EM DASH}" in text or "\N{EN DASH}" in text
    ]
    assert hits == []


# The analytics and composite tools that declare their result shape (spec R4.3), with the
# module constant each one's outputSchema is built from.
_OUTPUT_SCHEMA_TOOLS = {
    "analyze_metric": ("analyze_metric", "ANALYZE_METRIC_OUTPUT_SCHEMA"),
    "analyze_alerts": ("analyze_alerts", "ANALYZE_ALERTS_OUTPUT_SCHEMA"),
    "calculate_availability": ("scoring", "CALCULATE_AVAILABILITY_OUTPUT_SCHEMA"),
    "correlate_metrics": ("correlation", "CORRELATE_METRICS_OUTPUT_SCHEMA"),
    "analyze_blast_radius": ("topology_analysis", "ANALYZE_BLAST_RADIUS_OUTPUT_SCHEMA"),
    "triage": ("workflows", "TRIAGE_OUTPUT_SCHEMA"),
    "portal_overview": ("workflows", "PORTAL_OVERVIEW_OUTPUT_SCHEMA"),
    "health_check": ("workflows", "HEALTH_CHECK_OUTPUT_SCHEMA"),
    "capacity_plan": ("workflows", "CAPACITY_PLAN_OUTPUT_SCHEMA"),
    "diagnose": ("workflows", "DIAGNOSE_OUTPUT_SCHEMA"),
    "detect_site_outage": ("workflows", "DETECT_SITE_OUTAGE_OUTPUT_SCHEMA"),
}

_BLAST_RADIUS = {
    "device_id": 1,
    "depth": 2,
    "total_affected_devices": 0,
    "neighbor_count": 0,
    "dependent_count": 0,
    "affected_devices": [],
    "critical_path_devices": [],
    "critical_alert_count": 0,
    "unreadable": [],
}


async def test_the_analytics_and_composites_declare_their_output_schema(single_portal):
    """R4.3: exactly these eleven tools list an outputSchema, their module's schema plus the
    portal a multi-portal result is stamped with."""
    import importlib

    import jsonschema

    from lm_mcp.server import list_tools

    declared = {tool.name: tool.outputSchema for tool in await list_tools() if tool.outputSchema}

    assert set(declared) == set(_OUTPUT_SCHEMA_TOOLS)
    for name, (module, constant) in _OUTPUT_SCHEMA_TOOLS.items():
        schema = getattr(importlib.import_module(f"lm_mcp.tools.{module}"), constant)
        properties = dict(declared[name]["properties"])
        assert properties.pop("portal")["type"] == ["string", "null"], name
        assert {**declared[name], "properties": properties} == schema, name
        assert schema["additionalProperties"] is False, name
        jsonschema.Draft202012Validator.check_schema(schema)


async def test_a_result_that_breaks_its_schema_is_an_error(single_portal, monkeypatch):
    """R4.3: the SDK validates an analytics result on call_tool and refuses one that breaks it."""
    from lm_mcp.tools import format_response
    from tests.sdk_call import replay_through_sdk

    broken = format_response({**_BLAST_RADIUS, "health_score": 80})

    result = await replay_through_sdk(monkeypatch, "analyze_blast_radius", {"device_id": 1}, broken)

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text.startswith("Output validation error:")
    assert "health_score" in result.content[0].text


async def test_a_result_carries_structured_content_beside_its_text(single_portal, monkeypatch):
    """R4.3: a valid result reaches the client as structuredContent and as the same JSON text."""
    from lm_mcp.tools import format_response
    from tests.sdk_call import replay_through_sdk, structured

    result = await replay_through_sdk(
        monkeypatch, "analyze_blast_radius", {"device_id": 1}, format_response(_BLAST_RADIUS)
    )

    assert structured(result) == _BLAST_RADIUS


async def test_a_tool_without_an_output_schema_sends_text_alone(single_portal, monkeypatch):
    """Only the eleven send structuredContent; any other result stays one JSON text."""
    from lm_mcp.tools import format_response
    from tests.sdk_call import replay_through_sdk

    device = {"id": 1, "displayName": "web-01"}

    result = await replay_through_sdk(
        monkeypatch, "get_device", {"device_id": 1}, format_response(device)
    )

    assert result.isError is False
    assert result.structuredContent is None
    assert json.loads(result.content[0].text) == device


async def test_an_error_result_passes_through_unvalidated(single_portal, monkeypatch):
    """An error envelope from a tool with an outputSchema stays the tool's error."""
    from lm_mcp.tools import error_content
    from tests.envelope import envelope
    from tests.sdk_call import replay_through_sdk

    refusal = error_content("NOT_FOUND", "Device 1 not found")

    result = await replay_through_sdk(
        monkeypatch, "analyze_blast_radius", {"device_id": 1}, refusal
    )

    assert result.isError is True
    assert result.structuredContent is None
    assert envelope(result.content)["code"] == "NOT_FOUND"


async def test_a_multi_portal_result_validates_with_its_portal(
    monkeypatch, tmp_path, reset_portals
):
    """In multi-portal mode a result names its portal and still meets its outputSchema."""
    from mcp import types

    from lm_mcp.server import server
    from lm_mcp.tools import format_response
    from tests.portal_env import two_portal_vault

    two_portal_vault(tmp_path, monkeypatch)

    async def handler(client, **kwargs):
        return format_response(_BLAST_RADIUS)

    request = types.CallToolRequest(
        params=types.CallToolRequestParams(
            name="analyze_blast_radius", arguments={"device_id": 1, "portal": "globex"}
        )
    )
    with respx.mock, patch("lm_mcp.server.get_tool_handler", return_value=handler):
        await server.request_handlers[types.ListToolsRequest](None)
        result = (await server.request_handlers[types.CallToolRequest](request)).root

    assert result.isError is False, result.content[0].text
    assert result.structuredContent == {**_BLAST_RADIUS, "portal": "globex"}
