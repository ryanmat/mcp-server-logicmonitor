# Description: Tests for update_logicmodule and its helpers (_deep_merge, _diff).
# Description: Validates the read-modify-update workflow against full-replace blanking.

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result
from lm_mcp.tools.workflows import (
    _LM_TYPES,
    _deep_merge,
    _diff,
    update_logicmodule,
)
from tests.envelope import envelope


class TestDeepMerge:
    """Unit tests for the _deep_merge helper."""

    def test_merge_dicts_recurses(self):
        base = {"a": {"b": 1, "c": 2}}
        overlay = {"a": {"b": 10}}
        out, warnings = _deep_merge(base, overlay)
        assert out == {"a": {"b": 10, "c": 2}}
        assert warnings == []

    def test_merge_lists_replace_not_append(self):
        base = {"dataPoints": [{"name": "a"}, {"name": "b"}]}
        overlay = {"dataPoints": [{"name": "c"}]}
        out, _ = _deep_merge(base, overlay)
        assert out == {"dataPoints": [{"name": "c"}]}

    def test_overlay_primitive_wins(self):
        base = {"name": "old", "id": 5}
        overlay = {"name": "new"}
        out, _ = _deep_merge(base, overlay)
        assert out == {"name": "new", "id": 5}

    def test_none_in_overlay_deletes_key(self):
        base = {"description": "doomed", "name": "keep"}
        overlay = {"description": None}
        out, warnings = _deep_merge(base, overlay)
        assert "description" not in out
        assert "name" in out
        assert warnings == []

    def test_none_on_missing_key_warns(self):
        base = {"name": "x"}
        overlay = {"misspelled_field": None}
        out, warnings = _deep_merge(base, overlay)
        assert out == {"name": "x"}
        assert any("misspelled_field" in w for w in warnings)

    def test_type_conflict_raises(self):
        base = {"items": [1, 2, 3]}
        overlay = {"items": {"key": "value"}}
        with pytest.raises(ValueError, match="type conflict"):
            _deep_merge(base, overlay)

    def test_none_in_base_accepts_any_overlay(self):
        base = {"placeholder": None}
        overlay = {"placeholder": {"new": "structure"}}
        out, _ = _deep_merge(base, overlay)
        assert out == {"placeholder": {"new": "structure"}}

    def test_new_key_added(self):
        base = {"existing": 1}
        overlay = {"new": 2}
        out, _ = _deep_merge(base, overlay)
        assert out == {"existing": 1, "new": 2}

    def test_path_threading_in_warnings(self):
        base = {"outer": {"inner": "x"}}
        overlay = {"outer": {"missing": None}}
        _, warnings = _deep_merge(base, overlay)
        assert any("outer.missing" in w for w in warnings)


class TestDiff:
    """Unit tests for the _diff helper."""

    def test_no_changes_empty_diff(self):
        assert _diff({"a": 1}, {"a": 1}) == []

    def test_add_op(self):
        diff = _diff({}, {"a": 1})
        assert diff == [{"path": "a", "op": "add", "before": None, "after": 1}]

    def test_remove_op(self):
        diff = _diff({"a": 1}, {})
        assert diff == [{"path": "a", "op": "remove", "before": 1, "after": None}]

    def test_change_op(self):
        diff = _diff({"a": 1}, {"a": 2})
        assert diff == [{"path": "a", "op": "change", "before": 1, "after": 2}]

    def test_nested_changes(self):
        diff = _diff({"x": {"y": 1, "z": 2}}, {"x": {"y": 1, "z": 99}})
        assert {"path": "x.z", "op": "change", "before": 2, "after": 99} in diff


@pytest.fixture
def patched_handlers(monkeypatch):
    """Patch the internal raw read to a mock, and every type's PUT to a mock.

    Also configures the env so check_required_tools can build LMConfig
    without raising on missing portal/auth.
    """
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
    monkeypatch.delenv("LM_ENABLED_TOOLS", raising=False)
    monkeypatch.delenv("LM_DISABLED_TOOLS", raising=False)
    monkeypatch.delenv("LM_MCP_CATEGORIES", raising=False)

    from lm_mcp.config import reset_config

    reset_config()

    read_mock = AsyncMock()
    update_mock = AsyncMock()

    import lm_mcp.tools.workflows as workflows

    monkeypatch.setattr(workflows, "_get_module_raw", read_mock)
    for module_type, (path, _, id_arg, required) in list(_LM_TYPES.items()):
        monkeypatch.setitem(_LM_TYPES, module_type, (path, update_mock, id_arg, required))
    yield read_mock, update_mock
    reset_config()


def _wrap(payload: dict) -> list:
    """Mimic the format_response output (list of TextContent with .text JSON)."""
    from mcp.types import TextContent

    return [TextContent(type="text", text=json.dumps(payload))]


class TestUpdateLogicmodule:
    """End-to-end tests for update_logicmodule."""

    async def test_unknown_type_rejected(self):
        result = await update_logicmodule(client=None, type="bogussource", id=1, changes={})
        text = result[0].text
        assert is_error_result(result)
        assert "type must be one of" in text

    async def test_invalid_mode_rejected(self):
        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="commit"
        )
        text = result[0].text
        assert is_error_result(result)
        assert "mode must be 'preview' or 'apply'" in text

    async def test_invalid_changes_rejected(self):
        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes="not a dict",  # type: ignore[arg-type]
        )
        text = result[0].text
        assert is_error_result(result)
        assert "changes must be a dict" in text

    async def test_preview_returns_diff_no_update_call(self, patched_handlers):
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {"name": "DS", "displayName": "Old Display"}

        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"displayName": "New Display"},
            mode="preview",
        )

        assert read_mock.await_count == 1
        assert update_mock.await_count == 0  # preview must not write
        payload = json.loads(result[0].text)
        assert payload["dry_run"] is True
        assert payload["mode"] == "preview"
        assert any(d["path"] == "displayName" and d["op"] == "change" for d in payload["diff"])

    async def test_apply_calls_update_handler(self, patched_handlers):
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {"name": "DS", "displayName": "Old"}
        update_mock.return_value = _wrap(
            {"success": True, "datasource": {"id": 1, "name": "DS", "display_name": "New"}}
        )

        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"displayName": "New"},
            mode="apply",
        )

        assert read_mock.await_count == 1
        assert update_mock.await_count == 1
        # Verify the merged definition was passed to the update handler
        call_kwargs = update_mock.await_args.kwargs
        assert call_kwargs["datasource_id"] == 1
        assert call_kwargs["definition"]["displayName"] == "New"
        assert call_kwargs["definition"]["name"] == "DS"  # preserved from base

        payload = json.loads(result[0].text)
        assert payload["applied"] is True
        assert payload["result"]["success"] is True

    async def test_missing_name_field_rejected(self, patched_handlers):
        read_mock, _ = patched_handlers
        # The read returns a definition with no name field, as a broken module would
        read_mock.return_value = {"displayName": "X"}  # missing 'name'

        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="preview"
        )
        text = result[0].text
        assert is_error_result(result)
        assert "missing required field 'name'" in text

    async def test_missing_display_name_field_rejected(self, patched_handlers):
        read_mock, _ = patched_handlers
        read_mock.return_value = {"name": "DS"}  # missing displayName

        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="preview"
        )
        text = result[0].text
        assert is_error_result(result)
        assert "missing required field 'displayName'" in text

    async def test_an_empty_definition_merges_only_the_changes(self, patched_handlers):
        """An empty REST object merges to the changes alone, with nothing else added."""
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {}

        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"name": "DS", "displayName": "DS"},
            mode="preview",
        )

        # The merged definition should be {"name": "DS", "displayName": "DS"}.
        payload = json.loads(result[0].text)
        assert payload["merged_field_count"] == 2  # only the two changes
        assert update_mock.await_count == 0

    async def test_audit_log_attempting_then_applied_on_success(self, patched_handlers, caplog):
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {"name": "DS", "displayName": "Old"}
        update_mock.return_value = _wrap({"success": True})

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            await update_logicmodule(
                client=None,
                type="datasource",
                id=1,
                changes={"displayName": "New"},
                mode="apply",
            )

        messages = [r.message for r in caplog.records]
        assert any("attempting" in m for m in messages)
        assert any("applied" in m for m in messages)

    async def test_audit_log_attempting_no_applied_on_error(self, patched_handlers, caplog):
        """When update fails, the audit log MUST NOT claim success."""
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {"name": "DS", "displayName": "Old"}
        # Simulate update failure
        update_mock.return_value = _wrap(
            {"error": True, "code": "API_ERROR", "message": "PUT failed"}
        )

        with caplog.at_level(logging.INFO, logger="lm_mcp.audit"):
            result = await update_logicmodule(
                client=None,
                type="datasource",
                id=1,
                changes={"displayName": "New"},
                mode="apply",
            )

        messages = [r.message for r in caplog.records]
        assert any("attempting" in m for m in messages)
        # No "applied" record on failure
        assert not any("applied" in m for m in messages)
        # Error surfaced
        assert "Error" in result[0].text or "PUT failed" in result[0].text

    async def test_lm_types_covers_all_six_sources(self):
        """Sanity check: all 6 supported types are wired."""
        assert set(_LM_TYPES) == {
            "configsource",
            "datasource",
            "diagnosticsource",
            "eventsource",
            "logsource",
            "propertysource",
            "remediationsource",
            "topologysource",
        }


class TestApplyPassesConfirm:
    """Regression: apply mode must satisfy the update tools' confirm guard.

    Every update_<type> tool requires confirm=True; without it the sub-tool
    returns INVALID_REQUEST, call_sub_tool raises, and apply mode can
    never apply. The handler-level mocks in the other tests cannot catch
    this, so assert on the forwarded kwargs explicitly.
    """

    async def test_apply_forwards_confirm_true(self, patched_handlers):
        read_mock, update_mock = patched_handlers
        read_mock.return_value = {"name": "DS", "displayName": "Old"}
        update_mock.return_value = _wrap({"success": True})

        from lm_mcp.tools.workflows import update_logicmodule

        await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"displayName": "New"},
            mode="apply",
        )

        assert update_mock.await_args.kwargs["confirm"] is True


_RAW_UPDATE_TOOLS = (
    "update_datasource",
    "update_configsource",
    "update_eventsource",
    "update_propertysource",
    "update_logsource",
    "update_topologysource",
    "update_diagnosticsource",
    "update_remediationsource",
)

# GET /setting/topologysources/1 on a live portal, 2026-11-07, with the groovy script cut to
# its header comment. A TopologySource has no displayName.
_TOPOLOGYSOURCE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "topologysource_1.json").read_text()
)
_TOPOLOGYSOURCE_URL = "https://test.logicmonitor.com/santaba/rest/setting/topologysources/1"


@pytest.fixture
def lm_client():
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=BearerAuth("test-token"),
        timeout=30,
    )


@pytest.fixture
def writes_on(monkeypatch):
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    for name in ("LM_ENABLED_TOOLS", "LM_DISABLED_TOOLS", "LM_MCP_CATEGORIES"):
        monkeypatch.delenv(name, raising=False)


class TestTopologysourceArm:
    """R1.8: update_logicmodule reads a TopologySource from its settings path and PUTs it back."""

    @respx.mock
    async def test_apply_puts_the_merged_definition(self, lm_client, writes_on):
        respx.get(_TOPOLOGYSOURCE_URL).mock(return_value=httpx.Response(200, json=_TOPOLOGYSOURCE))
        put = respx.put(_TOPOLOGYSOURCE_URL).mock(
            return_value=httpx.Response(200, json={**_TOPOLOGYSOURCE, "description": "probe"})
        )

        result = await update_logicmodule(
            lm_client, type="topologysource", id=1, changes={"description": "probe"}, mode="apply"
        )

        payload = json.loads(result[0].text)
        assert payload["applied"] is True
        assert put.call_count == 1
        expected = {k: v for k, v in _TOPOLOGYSOURCE.items() if k != "id"}
        expected["description"] = "probe"
        assert json.loads(put.calls[0].request.content) == expected

    @respx.mock
    async def test_preview_reads_and_does_not_write(self, lm_client, writes_on):
        get = respx.get(_TOPOLOGYSOURCE_URL).mock(
            return_value=httpx.Response(200, json=_TOPOLOGYSOURCE)
        )
        put = respx.put(_TOPOLOGYSOURCE_URL).mock(return_value=httpx.Response(200, json={}))

        result = await update_logicmodule(
            lm_client, type="topologysource", id=1, changes={"description": "probe"}
        )

        payload = json.loads(result[0].text)
        assert get.call_count == 1
        assert put.call_count == 0
        assert payload["dry_run"] is True
        assert payload["diff"] == [
            {
                "path": "description",
                "op": "change",
                "before": _TOPOLOGYSOURCE["description"],
                "after": "probe",
            }
        ]


@pytest.mark.parametrize(
    ("module_type", "needs_display_name"),
    [
        ("configsource", True),
        ("datasource", True),
        ("eventsource", False),
        ("logsource", False),
        ("propertysource", False),
        ("diagnosticsource", False),
        ("remediationsource", False),
    ],
)
async def test_display_name_is_required_only_where_the_api_model_has_it(
    patched_handlers, module_type, needs_display_name
):
    """Only DataSource and ConfigSource bodies carry displayName (swagger and a live read)."""
    read_mock, _ = patched_handlers
    read_mock.return_value = {"name": "M"}

    result = await update_logicmodule(client=None, type=module_type, id=1, changes={})

    refused = "missing required field 'displayName'" in result[0].text
    assert refused is needs_display_name


async def test_an_allowlist_needs_only_the_getter(patched_handlers, monkeypatch):
    """The read and the PUT are no tools; LM_ENABLED_TOOLS gates the read by the getter's name."""
    monkeypatch.setenv("LM_ENABLED_TOOLS", "update_logicmodule,get_datasource")
    read_mock, _ = patched_handlers
    read_mock.return_value = {"name": "DS", "displayName": "DS"}

    result = await update_logicmodule(client=None, type="datasource", id=1, changes={})

    assert json.loads(result[0].text)["dry_run"] is True


class TestRawUpdatesLeaveTheSurface:
    """R1.8: the eight raw update_<module> names are neither registered nor dispatchable."""

    def test_raw_update_tools_are_not_registered(self):
        from lm_mcp.registry import TOOLS

        names = {tool.name for tool in TOOLS}

        assert names.isdisjoint(_RAW_UPDATE_TOOLS)
        assert "update_device_eventsource" in names

    async def test_execute_tool_refuses_a_raw_update(self, writes_on):
        from lm_mcp.server import execute_tool

        result = await execute_tool(
            "update_datasource", {"datasource_id": 1, "definition": {}, "confirm": True}
        )

        error = envelope(result)
        assert error["code"] == "INVALID_REQUEST"
        assert error["message"] == "Unknown tool: update_datasource"


_SETTINGS_PATHS = {
    "configsource": "configsources",
    "datasource": "datasources",
    "diagnosticsource": "diagnosticsources",
    "eventsource": "eventsources",
    "logsource": "logsources",
    "propertysource": "propertyrules",
    "remediationsource": "remediationsources",
    "topologysource": "topologysources",
}


@respx.mock
@pytest.mark.parametrize(("module_type", "path"), sorted(_SETTINGS_PATHS.items()))
async def test_the_read_is_one_get_on_the_settings_path_not_a_sub_tool(
    lm_client, writes_on, monkeypatch, module_type, path
):
    """R2.3: update_logicmodule reads the REST object itself; no registered tool is called."""
    import lm_mcp.registry as registry

    def no_sub_tool(name):
        raise AssertionError(f"update_logicmodule called the tool {name}")

    monkeypatch.setattr(registry, "get_tool_handler", no_sub_tool)
    body = {"id": 1, "name": "M", "displayName": "M", "description": "before"}
    get = respx.get(f"https://test.logicmonitor.com/santaba/rest/setting/{path}/1").mock(
        return_value=httpx.Response(200, json=body)
    )

    result = await update_logicmodule(
        lm_client, type=module_type, id=1, changes={"description": "after"}
    )

    payload = json.loads(result[0].text)
    assert get.call_count == 1
    assert payload["dry_run"] is True
    assert payload["diff"] == [
        {"path": "description", "op": "change", "before": "before", "after": "after"}
    ]
