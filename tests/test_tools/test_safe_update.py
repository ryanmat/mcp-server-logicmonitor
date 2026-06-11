# Description: Tests for update_logicmodule and its helpers (_deep_merge, _diff).
# Description: Validates the export-modify-update workflow against full-replace blanking.

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

from lm_mcp.tools.workflows import (
    _LM_TYPES,
    _deep_merge,
    _diff,
    update_logicmodule,
)


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
    """Patch get_tool_handler to return mock export and update handlers.

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

    export_mock = AsyncMock()
    update_mock = AsyncMock()

    def fake_get_tool_handler(name):
        if name.startswith("export_"):
            return export_mock
        if name.startswith("update_"):
            return update_mock
        raise ValueError(f"unexpected handler: {name}")

    import lm_mcp.registry as registry

    monkeypatch.setattr(registry, "get_tool_handler", fake_get_tool_handler)
    yield export_mock, update_mock
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
        assert "Error" in text
        assert "type must be one of" in text

    async def test_invalid_mode_rejected(self):
        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="commit"
        )
        text = result[0].text
        assert "Error" in text
        assert "mode must be 'preview' or 'apply'" in text

    async def test_invalid_changes_rejected(self):
        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes="not a dict",  # type: ignore[arg-type]
        )
        text = result[0].text
        assert "Error" in text
        assert "changes must be a dict" in text

    async def test_preview_returns_diff_no_update_call(self, patched_handlers):
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS", "displayName": "Old Display"},
            }
        )

        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"displayName": "New Display"},
            mode="preview",
        )

        assert export_mock.await_count == 1
        assert update_mock.await_count == 0  # preview must not write
        payload = json.loads(result[0].text)
        assert payload["dry_run"] is True
        assert payload["mode"] == "preview"
        assert any(d["path"] == "displayName" and d["op"] == "change" for d in payload["diff"])

    async def test_apply_calls_update_handler(self, patched_handlers):
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS", "displayName": "Old"},
            }
        )
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

        assert export_mock.await_count == 1
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
        export_mock, _ = patched_handlers
        # Export returns a definition with no name field — simulate broken export
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": None,
                "format": "json",
                "definition": {"displayName": "X"},  # missing 'name'
            }
        )

        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="preview"
        )
        text = result[0].text
        assert "Error" in text
        assert "missing required field 'name'" in text

    async def test_missing_display_name_field_rejected(self, patched_handlers):
        export_mock, _ = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS"},  # missing displayName
            }
        )

        result = await update_logicmodule(
            client=None, type="datasource", id=1, changes={}, mode="preview"
        )
        text = result[0].text
        assert "Error" in text
        assert "missing required field 'displayName'" in text

    async def test_falsy_definition_unwrap_handled(self, patched_handlers):
        """Empty dict definition is falsy in Python — must not fall through to envelope."""
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {},  # falsy! must still unwrap, not fall back to envelope
            }
        )

        result = await update_logicmodule(
            client=None,
            type="datasource",
            id=1,
            changes={"name": "DS", "displayName": "DS"},
            mode="preview",
        )

        # The merged definition should be {"name": "DS", "displayName": "DS"},
        # NOT the envelope wrapper. If the unwrap was wrong, we'd see
        # "datasource_id", "format" keys leaking into the merged definition.
        payload = json.loads(result[0].text)
        assert payload["merged_field_count"] == 2  # only the two changes
        assert update_mock.await_count == 0

    async def test_audit_log_attempting_then_applied_on_success(self, patched_handlers, caplog):
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS", "displayName": "Old"},
            }
        )
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
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS", "displayName": "Old"},
            }
        )
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
    returns CONFIRMATION_REQUIRED, call_sub_tool raises, and apply mode can
    never apply. The handler-level mocks in the other tests cannot catch
    this, so assert on the forwarded kwargs explicitly.
    """

    async def test_apply_forwards_confirm_true(self, patched_handlers):
        export_mock, update_mock = patched_handlers
        export_mock.return_value = _wrap(
            {
                "datasource_id": 1,
                "name": "DS",
                "format": "json",
                "definition": {"name": "DS", "displayName": "Old"},
            }
        )
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
