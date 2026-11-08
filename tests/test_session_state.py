# Description: Tests for the in-memory session state behind the session tools.
# Description: Covers variables, history, the module's session, and the names R1.6 removed.

import dataclasses
import json

import pytest
import respx

from lm_mcp import session as session_module
from lm_mcp.config import LMConfig
from lm_mcp.session import HistoryEntry, SessionContext, get_session
from tests.envelope import envelope
from tests.portal_env import two_portal_vault


class TestHistoryEntry:
    """Tests for HistoryEntry dataclass."""

    def test_create_history_entry(self):
        """HistoryEntry can be created with required fields."""
        entry = HistoryEntry(
            tool_name="get_devices",
            timestamp="2024-01-01T00:00:00Z",
            arguments={"limit": 10},
            success=True,
        )

        assert entry.tool_name == "get_devices"
        assert entry.timestamp == "2024-01-01T00:00:00Z"
        assert entry.arguments == {"limit": 10}
        assert entry.success is True
        assert entry.result_summary is None

    def test_history_entry_with_summary(self):
        """HistoryEntry can include result summary."""
        entry = HistoryEntry(
            tool_name="get_device",
            timestamp="2024-01-01T00:00:00Z",
            arguments={"device_id": 123},
            success=True,
            result_summary="id=123, name=server01",
        )

        assert entry.result_summary == "id=123, name=server01"


class TestSessionContext:
    """Tests for SessionContext class."""

    def test_create_empty_session(self):
        """SessionContext initializes with empty state."""
        session = SessionContext()

        assert session.variables == {}
        assert session.history == []

    def test_set_and_get_variable(self):
        """Variables can be set and retrieved."""
        session = SessionContext()

        session.set_variable("target_device", 123)
        session.set_variable("filter_string", "name~prod*")

        assert session.get_variable("target_device") == 123
        assert session.get_variable("filter_string") == "name~prod*"
        assert session.get_variable("nonexistent") is None
        assert session.get_variable("nonexistent", "default") == "default"

    def test_delete_variable(self):
        """Variables can be deleted."""
        session = SessionContext()
        session.set_variable("temp", "value")

        assert session.delete_variable("temp") is True
        assert session.get_variable("temp") is None
        assert session.delete_variable("temp") is False

    def test_record_result_adds_history(self):
        """Recording a result adds to history."""
        session = SessionContext()

        session.record_result(
            tool_name="get_devices",
            arguments={"limit": 10},
            result={"items": []},
            success=True,
        )

        assert len(session.history) == 1
        assert session.history[0].tool_name == "get_devices"
        assert session.history[0].success is True

    def test_history_size_limit(self):
        """History is trimmed when exceeding max size."""
        session = SessionContext()
        session.max_history_size = 5

        for i in range(10):
            session.record_result(
                tool_name=f"tool_{i}",
                arguments={},
                result={},
                success=True,
            )

        assert len(session.history) == 5
        assert session.history[0].tool_name == "tool_5"
        assert session.history[-1].tool_name == "tool_9"

    def test_clear_resets_all_state(self):
        """Clear resets all session state."""
        session = SessionContext()

        session.set_variable("key", "value")
        session.record_result("get_devices", {}, {}, True)

        session.clear()

        assert session.variables == {}
        assert session.history == []

    def test_to_dict_serializes_session(self):
        """Session can be serialized to dictionary."""
        session = SessionContext()
        session.set_variable("filter", "name~prod*")
        session.record_result(
            "get_device", {"device_id": 123}, {"id": 123, "name": "server01"}, True
        )

        result = session.to_dict()

        assert result["variables"] == {"filter": "name~prod*"}
        assert "history" in result
        assert result["history_count"] == 1


class TestGlobalSession:
    """Tests for the module's session."""

    def test_get_session_creates_if_missing(self, monkeypatch):
        """get_session creates a new session if none exists."""
        monkeypatch.setattr(session_module, "_sessions", {})

        session = get_session()

        assert session is not None
        assert isinstance(session, SessionContext)

    def test_get_session_returns_same_instance(self, monkeypatch):
        """get_session returns the same instance on subsequent calls."""
        monkeypatch.setattr(session_module, "_sessions", {})

        session1 = get_session()
        session2 = get_session()

        assert session1 is session2


class TestResultSummarization:
    """Tests for result summarization in history."""

    def test_summarize_list_result(self):
        """List results are summarized as item counts."""
        session = SessionContext()

        session.record_result(
            tool_name="get_devices",
            arguments={},
            result={"items": [{"id": 1}, {"id": 2}, {"id": 3}]},
            success=True,
        )

        assert session.history[0].result_summary == "3 items"

    def test_summarize_singular_with_id_and_name(self):
        """Singular results with id and name are summarized."""
        session = SessionContext()

        session.record_result(
            tool_name="get_device",
            arguments={},
            result={"id": 123, "name": "server01"},
            success=True,
        )

        assert session.history[0].result_summary == "id=123, name=server01"

    def test_summarize_singular_with_display_name(self):
        """Singular results with displayName are summarized."""
        session = SessionContext()

        session.record_result(
            tool_name="get_device",
            arguments={},
            result={"id": 123, "displayName": "Server 01"},
            success=True,
        )

        assert session.history[0].result_summary == "id=123, name=Server 01"

    def test_failed_result_no_summary(self):
        """Failed results don't get summarized."""
        session = SessionContext()

        session.record_result(
            tool_name="get_device",
            arguments={},
            result={"error": "Not found"},
            success=False,
        )

        assert session.history[0].result_summary is None


class TestRemovedSessionNames:
    """R1.6: the session keeps variables and history only, in memory."""

    def test_session_holds_no_last_result_field(self):
        """The session has no last_* result field and no tool-to-type map."""
        names = {field.name for field in dataclasses.fields(SessionContext)}

        assert "variables" in names
        assert {name for name in names if name.startswith("last_")} == set()
        assert "_tool_resource_map" not in names

    @pytest.mark.parametrize("name", ["get_implicit_id", "get_implicit_ids"])
    def test_session_has_no_implicit_id_lookup(self, name):
        assert not hasattr(SessionContext, name)

    @pytest.mark.parametrize(
        "name",
        ["get_persistence_path", "set_persistence_path", "reset_session", "set_session"],
    )
    def test_module_has_no_removed_function(self, name):
        assert not hasattr(session_module, name)

    def test_recorded_device_leaves_no_last_results(self):
        """A recorded get_device lands in history and nowhere else."""
        session = SessionContext()
        session.record_result("get_device", {}, {"id": 123, "name": "server01"}, True)

        assert set(session.to_dict()) == {"variables", "history", "history_count"}

    @pytest.mark.parametrize("field", ["session_enabled", "session_persist_path"])
    def test_config_has_no_removed_session_setting(self, field):
        """LM_SESSION_ENABLED and LM_SESSION_PERSIST_PATH are not settings."""
        assert "session_history_size" in LMConfig.model_fields
        assert field not in LMConfig.model_fields


@pytest.fixture
def two_portals(tmp_path, monkeypatch, reset_portals):
    """Multi-portal mode over a vault with a writable acme and a read-only globex."""
    two_portal_vault(tmp_path, monkeypatch)


class TestSessionKeyedByPortal:
    """Session variables, baselines and history are kept per portal (spec R2.12)."""

    @pytest.fixture(autouse=True)
    def _fresh_sessions(self, monkeypatch):
        monkeypatch.setattr(session_module, "_sessions", {})

    @staticmethod
    async def _call(tool: str, **arguments) -> list:
        from lm_mcp.server import execute_tool

        return await execute_tool(tool, arguments)

    async def test_variable_set_under_one_portal_is_absent_under_another(self, two_portals):
        from lm_mcp import portals

        portals.activate("acme")
        await self._call("set_session_variable", name="target", value="acme-web")
        await self._call("use_portal", customer="globex")
        under_globex = await self._call("get_session_variable", name="target")
        await self._call("use_portal", customer="acme")
        under_acme = await self._call("get_session_variable", name="target")

        assert envelope(under_globex)["code"] == "NOT_FOUND"
        assert json.loads(under_acme[0].text)["value"] == "acme-web"

    @respx.mock
    async def test_baseline_saved_under_one_portal_is_absent_under_another(self, two_portals):
        from lm_mcp import portals

        portals.activate("acme")
        await self._call("set_session_variable", name="baseline_cpu", value={"datapoints": {}})
        await self._call("use_portal", customer="globex")

        error = envelope(await self._call("compare_to_baseline", baseline_name="cpu"))

        assert error["code"] == "NOT_FOUND"
        assert "Baseline 'cpu' not found" in error["message"]

    async def test_history_is_per_portal(self, two_portals):
        from lm_mcp import portals

        portals.activate("acme")
        await self._call("search_tools", query="device")
        await self._call("use_portal", customer="globex")
        globex = json.loads((await self._call("list_session_history"))[0].text)
        await self._call("use_portal", customer="acme")
        acme = json.loads((await self._call("list_session_history"))[0].text)

        assert "search_tools" not in [entry["tool"] for entry in globex["history"]]
        assert "search_tools" in [entry["tool"] for entry in acme["history"]]

    async def test_clear_session_context_clears_one_portal(self, two_portals):
        from lm_mcp import portals

        portals.activate("acme")
        await self._call("set_session_variable", name="kept", value=1)
        await self._call("use_portal", customer="globex")
        await self._call("set_session_variable", name="cleared", value=2)
        await self._call("clear_session_context")
        cleared = await self._call("get_session_variable", name="cleared")
        await self._call("use_portal", customer="acme")
        kept = await self._call("get_session_variable", name="kept")

        assert envelope(cleared)["code"] == "NOT_FOUND"
        assert json.loads(kept[0].text)["value"] == 1

    async def test_single_portal_uses_one_implicit_key(self, monkeypatch):
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.delenv("LM_MULTI_PORTAL", raising=False)

        await self._call("set_session_variable", name="target", value=7)

        assert list(session_module._sessions) == [None]
        assert get_session().get_variable("target") == 7

    def test_get_session_outside_a_call_raises_in_multi_portal(self, two_portals):
        from lm_mcp import portals

        portals.activate("acme")
        with pytest.raises(RuntimeError, match="binding"):
            get_session()

    def test_history_size_applies_to_every_portal_session(self, monkeypatch):
        monkeypatch.setattr(session_module, "_history_size", session_module._history_size)

        session_module.set_history_size(3)

        assert get_session().max_history_size == 3
