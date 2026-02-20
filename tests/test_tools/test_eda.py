# Description: Tests for EDA Controller tool handler functions.
# Description: Validates tool output format, parameter handling, and error responses.

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from mcp.types import TextContent


# Helper to parse tool result JSON
def _parse_result(result: list[TextContent]) -> dict:
    assert len(result) == 1
    return json.loads(result[0].text)


class TestTestEdaConnection:
    """Tests for test_eda_connection tool."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Returns connected status on success."""
        from lm_mcp.tools.eda import test_eda_connection

        client = AsyncMock()
        client.get.return_value = {"status": "ready", "version": "2.5"}

        result = await test_eda_connection(client)
        data = _parse_result(result)
        assert data["connected"] is True
        assert data["status"] == "ready"
        client.get.assert_called_once_with("/status/")

    @pytest.mark.asyncio
    async def test_error(self):
        """Returns error on connection failure."""
        from lm_mcp.tools.eda import test_eda_connection

        client = AsyncMock()
        client.get.side_effect = Exception("Connection refused")

        result = await test_eda_connection(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()


class TestGetEdaActivations:
    """Tests for get_eda_activations tool."""

    @pytest.mark.asyncio
    async def test_list_activations(self):
        """Returns activation list with count."""
        from lm_mcp.tools.eda import get_eda_activations

        client = AsyncMock()
        client.get.return_value = {
            "count": 2,
            "results": [{"id": 1, "name": "act1"}, {"id": 2, "name": "act2"}],
        }

        result = await get_eda_activations(client)
        data = _parse_result(result)
        assert data["count"] == 2
        assert len(data["activations"]) == 2

    @pytest.mark.asyncio
    async def test_name_filter(self):
        """Passes name filter as search param."""
        from lm_mcp.tools.eda import get_eda_activations

        client = AsyncMock()
        client.get.return_value = {"count": 0, "results": []}

        await get_eda_activations(client, name_filter="test")
        call_params = client.get.call_args[1]["params"]
        assert call_params["search"] == "test"


class TestGetEdaActivation:
    """Tests for get_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        """Returns single activation details."""
        from lm_mcp.tools.eda import get_eda_activation

        client = AsyncMock()
        client.get.return_value = {"id": 5, "name": "my-activation", "is_enabled": True}

        result = await get_eda_activation(client, activation_id=5)
        data = _parse_result(result)
        assert data["id"] == 5
        client.get.assert_called_once_with("/activations/5/")


class TestCreateEdaActivation:
    """Tests for create_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_create(self, monkeypatch):
        """Creates activation with required fields."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import create_eda_activation

        client = AsyncMock()
        client.post.return_value = {"id": 10, "name": "new-activation"}

        result = await create_eda_activation(
            client,
            name="new-activation",
            rulebook_id=1,
            decision_environment_id=2,
        )
        data = _parse_result(result)
        assert data["id"] == 10

    @pytest.mark.asyncio
    async def test_write_disabled(self, monkeypatch):
        """Returns error when write operations are disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from lm_mcp.tools.eda import create_eda_activation

        client = AsyncMock()
        result = await create_eda_activation(
            client, name="test", rulebook_id=1, decision_environment_id=2
        )
        assert "WRITE_DISABLED" in result[0].text or "Write operations" in result[0].text


class TestEnableEdaActivation:
    """Tests for enable_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_enable(self, monkeypatch):
        """Enables an activation by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import enable_eda_activation

        client = AsyncMock()
        client.post.return_value = {}

        result = await enable_eda_activation(client, activation_id=5)
        data = _parse_result(result)
        assert data["enabled"] is True
        client.post.assert_called_once_with("/activations/5/enable/")


class TestDisableEdaActivation:
    """Tests for disable_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_disable(self, monkeypatch):
        """Disables an activation by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import disable_eda_activation

        client = AsyncMock()
        client.post.return_value = {}

        result = await disable_eda_activation(client, activation_id=5)
        data = _parse_result(result)
        assert data["disabled"] is True
        client.post.assert_called_once_with("/activations/5/disable/")


class TestRestartEdaActivation:
    """Tests for restart_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_restart(self, monkeypatch):
        """Restarts an activation by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import restart_eda_activation

        client = AsyncMock()
        client.post.return_value = {}

        result = await restart_eda_activation(client, activation_id=5)
        data = _parse_result(result)
        assert data["restarted"] is True
        client.post.assert_called_once_with("/activations/5/restart/")


class TestDeleteEdaActivation:
    """Tests for delete_eda_activation tool."""

    @pytest.mark.asyncio
    async def test_delete(self, monkeypatch):
        """Deletes an activation by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import delete_eda_activation

        client = AsyncMock()
        client.delete.return_value = {}

        result = await delete_eda_activation(client, activation_id=5)
        data = _parse_result(result)
        assert data["deleted"] is True
        client.delete.assert_called_once_with("/activations/5/")


class TestGetEdaActivationInstances:
    """Tests for get_eda_activation_instances tool."""

    @pytest.mark.asyncio
    async def test_list_instances(self):
        """Returns instance list for an activation."""
        from lm_mcp.tools.eda import get_eda_activation_instances

        client = AsyncMock()
        client.get.return_value = {
            "count": 1,
            "results": [{"id": 10, "status": "running"}],
        }

        result = await get_eda_activation_instances(client, activation_id=5)
        data = _parse_result(result)
        assert data["count"] == 1
        assert len(data["instances"]) == 1


class TestGetEdaActivationInstanceLogs:
    """Tests for get_eda_activation_instance_logs tool."""

    @pytest.mark.asyncio
    async def test_get_logs(self):
        """Returns logs for an activation instance."""
        from lm_mcp.tools.eda import get_eda_activation_instance_logs

        client = AsyncMock()
        client.get.return_value = {
            "count": 2,
            "results": [
                {"id": 1, "log": "Rule matched"},
                {"id": 2, "log": "Action triggered"},
            ],
        }

        result = await get_eda_activation_instance_logs(client, instance_id=10)
        data = _parse_result(result)
        assert data["count"] == 2
        assert len(data["logs"]) == 2


class TestGetEdaProjects:
    """Tests for get_eda_projects tool."""

    @pytest.mark.asyncio
    async def test_list_projects(self):
        """Returns project list with count."""
        from lm_mcp.tools.eda import get_eda_projects

        client = AsyncMock()
        client.get.return_value = {
            "count": 1,
            "results": [{"id": 1, "name": "my-project"}],
        }

        result = await get_eda_projects(client)
        data = _parse_result(result)
        assert data["count"] == 1
        assert len(data["projects"]) == 1


class TestGetEdaProject:
    """Tests for get_eda_project tool."""

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        """Returns single project details."""
        from lm_mcp.tools.eda import get_eda_project

        client = AsyncMock()
        client.get.return_value = {"id": 3, "name": "my-project", "url": "https://git.example.com/repo"}

        result = await get_eda_project(client, project_id=3)
        data = _parse_result(result)
        assert data["id"] == 3
        client.get.assert_called_once_with("/projects/3/")


class TestCreateEdaProject:
    """Tests for create_eda_project tool."""

    @pytest.mark.asyncio
    async def test_create(self, monkeypatch):
        """Creates project with required fields."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import create_eda_project

        client = AsyncMock()
        client.post.return_value = {"id": 7, "name": "new-project"}

        result = await create_eda_project(
            client, name="new-project", url="https://git.example.com/repo"
        )
        data = _parse_result(result)
        assert data["id"] == 7


class TestSyncEdaProject:
    """Tests for sync_eda_project tool."""

    @pytest.mark.asyncio
    async def test_sync(self, monkeypatch):
        """Syncs project by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import sync_eda_project

        client = AsyncMock()
        client.post.return_value = {}

        result = await sync_eda_project(client, project_id=3)
        data = _parse_result(result)
        assert data["synced"] is True
        client.post.assert_called_once_with("/projects/3/sync/")


class TestGetEdaRulebooks:
    """Tests for get_eda_rulebooks tool."""

    @pytest.mark.asyncio
    async def test_list_rulebooks(self):
        """Returns rulebook list with count."""
        from lm_mcp.tools.eda import get_eda_rulebooks

        client = AsyncMock()
        client.get.return_value = {
            "count": 2,
            "results": [{"id": 1, "name": "rulebook1"}, {"id": 2, "name": "rulebook2"}],
        }

        result = await get_eda_rulebooks(client)
        data = _parse_result(result)
        assert data["count"] == 2
        assert len(data["rulebooks"]) == 2


class TestGetEdaRulebook:
    """Tests for get_eda_rulebook tool."""

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        """Returns single rulebook details."""
        from lm_mcp.tools.eda import get_eda_rulebook

        client = AsyncMock()
        client.get.return_value = {"id": 1, "name": "my-rulebook", "rulesets": "---\n"}

        result = await get_eda_rulebook(client, rulebook_id=1)
        data = _parse_result(result)
        assert data["id"] == 1
        client.get.assert_called_once_with("/rulebooks/1/")


class TestGetEdaEventStreams:
    """Tests for get_eda_event_streams tool."""

    @pytest.mark.asyncio
    async def test_list_event_streams(self):
        """Returns event stream list with count."""
        from lm_mcp.tools.eda import get_eda_event_streams

        client = AsyncMock()
        client.get.return_value = {
            "count": 1,
            "results": [{"id": 1, "name": "lm-webhook"}],
        }

        result = await get_eda_event_streams(client)
        data = _parse_result(result)
        assert data["count"] == 1
        assert len(data["event_streams"]) == 1


class TestGetEdaEventStream:
    """Tests for get_eda_event_stream tool."""

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        """Returns single event stream details."""
        from lm_mcp.tools.eda import get_eda_event_stream

        client = AsyncMock()
        client.get.return_value = {"id": 4, "name": "lm-alerts", "event_stream_type": "basic"}

        result = await get_eda_event_stream(client, event_stream_id=4)
        data = _parse_result(result)
        assert data["id"] == 4
        client.get.assert_called_once_with("/event-streams/4/")


class TestCreateEdaEventStream:
    """Tests for create_eda_event_stream tool."""

    @pytest.mark.asyncio
    async def test_create(self, monkeypatch):
        """Creates event stream with required fields."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import create_eda_event_stream

        client = AsyncMock()
        client.post.return_value = {"id": 8, "name": "new-stream"}

        result = await create_eda_event_stream(
            client, name="new-stream", event_stream_type="basic"
        )
        data = _parse_result(result)
        assert data["id"] == 8


class TestDeleteEdaEventStream:
    """Tests for delete_eda_event_stream tool."""

    @pytest.mark.asyncio
    async def test_delete(self, monkeypatch):
        """Deletes event stream by ID."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from lm_mcp.tools.eda import delete_eda_event_stream

        client = AsyncMock()
        client.delete.return_value = {}

        result = await delete_eda_event_stream(client, event_stream_id=4)
        data = _parse_result(result)
        assert data["deleted"] is True
        client.delete.assert_called_once_with("/event-streams/4/")
