# Description: Tests for session management tools.
# Description: Validates session context, variable, and history tool handlers.

import json

import pytest

from lm_mcp.session import SessionContext, get_session, set_session
from lm_mcp.tools.session import (
    clear_session_context,
    delete_session_variable,
    get_session_context,
    get_session_variable,
    list_session_history,
    set_session_variable,
)


@pytest.fixture(autouse=True)
def reset_session_for_tests():
    """Reset session before each test."""
    set_session(SessionContext())
    yield
    set_session(SessionContext())


class TestGetSessionContext:
    """Tests for get_session_context tool."""

    async def test_returns_empty_session(self):
        """Returns empty session context structure."""
        result = await get_session_context()

        assert len(result) == 1
        data = json.loads(result[0].text)

        assert "last_results" in data
        assert "variables" in data
        assert "history" in data

    async def test_returns_session_with_device(self):
        """Returns session with last device."""
        session = get_session()
        session.last_device = {"id": 123, "name": "server01"}

        result = await get_session_context()
        data = json.loads(result[0].text)

        assert data["last_results"]["device"] == {"id": 123, "name": "server01"}

    async def test_returns_session_with_variables(self):
        """Returns session with user variables."""
        session = get_session()
        session.set_variable("target", 42)

        result = await get_session_context()
        data = json.loads(result[0].text)

        assert data["variables"] == {"target": 42}


class TestSetSessionVariable:
    """Tests for set_session_variable tool."""

    async def test_sets_string_variable(self):
        """Sets a string variable successfully."""
        result = await set_session_variable(name="filter", value="name~prod*")

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["name"] == "filter"
        assert data["value"] == "name~prod*"

        session = get_session()
        assert session.get_variable("filter") == "name~prod*"

    async def test_sets_numeric_variable(self):
        """Sets a numeric variable successfully."""
        result = await set_session_variable(name="count", value=42)

        data = json.loads(result[0].text)
        assert data["success"] is True

        session = get_session()
        assert session.get_variable("count") == 42

    async def test_sets_boolean_variable(self):
        """Sets a boolean variable successfully."""
        result = await set_session_variable(name="enabled", value=True)

        data = json.loads(result[0].text)
        assert data["success"] is True

        session = get_session()
        assert session.get_variable("enabled") is True

    async def test_sets_list_variable(self):
        """Sets a list variable successfully."""
        result = await set_session_variable(name="ids", value=[1, 2, 3])

        data = json.loads(result[0].text)
        assert data["success"] is True

        session = get_session()
        assert session.get_variable("ids") == [1, 2, 3]

    async def test_sets_dict_variable(self):
        """Sets a dict variable successfully."""
        result = await set_session_variable(name="config", value={"key": "value"})

        data = json.loads(result[0].text)
        assert data["success"] is True

        session = get_session()
        assert session.get_variable("config") == {"key": "value"}

    async def test_rejects_empty_name(self):
        """Rejects empty variable name."""
        result = await set_session_variable(name="", value="test")

        # Error responses are formatted as plain text
        assert "Error:" in result[0].text
        assert "non-empty string" in result[0].text


class TestGetSessionVariable:
    """Tests for get_session_variable tool."""

    async def test_gets_existing_variable(self):
        """Gets an existing variable."""
        session = get_session()
        session.set_variable("target", 123)

        result = await get_session_variable(name="target")

        data = json.loads(result[0].text)
        assert data["name"] == "target"
        assert data["value"] == 123

    async def test_returns_error_for_missing_variable(self):
        """Returns error for missing variable."""
        result = await get_session_variable(name="nonexistent")

        # Error responses are formatted as plain text
        assert "Error:" in result[0].text
        assert "not found" in result[0].text

    async def test_gets_none_value_if_explicitly_set(self):
        """Gets None value if variable was explicitly set to None."""
        session = get_session()
        session.set_variable("nullable", None)

        result = await get_session_variable(name="nullable")

        data = json.loads(result[0].text)
        assert data["name"] == "nullable"
        assert data["value"] is None


class TestDeleteSessionVariable:
    """Tests for delete_session_variable tool."""

    async def test_deletes_existing_variable(self):
        """Deletes an existing variable."""
        session = get_session()
        session.set_variable("temp", "value")

        result = await delete_session_variable(name="temp")

        data = json.loads(result[0].text)
        assert data["success"] is True

        assert session.get_variable("temp") is None

    async def test_returns_error_for_missing_variable(self):
        """Returns error for missing variable."""
        result = await delete_session_variable(name="nonexistent")

        # Error responses are formatted as plain text
        assert "Error:" in result[0].text
        assert "not found" in result[0].text


class TestClearSessionContext:
    """Tests for clear_session_context tool."""

    async def test_clears_all_session_state(self):
        """Clears all session state."""
        session = get_session()
        session.last_device = {"id": 123}
        session.set_variable("key", "value")
        session.record_result("get_devices", {}, {}, True)

        result = await clear_session_context()

        data = json.loads(result[0].text)
        assert data["success"] is True

        assert session.last_device is None
        assert session.variables == {}
        assert session.history == []


class TestListSessionHistory:
    """Tests for list_session_history tool."""

    async def test_returns_empty_history(self):
        """Returns empty history when no operations."""
        result = await list_session_history()

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["history"] == []

    async def test_returns_history_entries(self):
        """Returns history entries."""
        session = get_session()
        session.record_result("get_devices", {"limit": 10}, {"items": []}, True)
        session.record_result("get_device", {"device_id": 1}, {"id": 1}, True)

        result = await list_session_history()

        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["history"]) == 2
        # Most recent first
        assert data["history"][0]["tool"] == "get_device"
        assert data["history"][1]["tool"] == "get_devices"

    async def test_respects_limit(self):
        """Respects limit parameter."""
        session = get_session()
        for i in range(10):
            session.record_result(f"tool_{i}", {}, {}, True)

        result = await list_session_history(limit=3)

        data = json.loads(result[0].text)
        assert data["count"] == 3
        assert data["total_history"] == 10

    async def test_clamps_limit_minimum(self):
        """Clamps limit to minimum of 1."""
        session = get_session()
        session.record_result("tool_1", {}, {}, True)
        session.record_result("tool_2", {}, {}, True)

        result = await list_session_history(limit=0)

        data = json.loads(result[0].text)
        assert data["count"] == 1

    async def test_clamps_limit_maximum(self):
        """Clamps limit to maximum of 50."""
        session = get_session()
        for i in range(60):
            session.record_result(f"tool_{i}", {}, {}, True)

        result = await list_session_history(limit=100)

        data = json.loads(result[0].text)
        assert data["count"] == 50
