# Description: Tests for dashboard group MCP tools.
# Description: Validates create_dashboard_group and delete_dashboard_group tools.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestCreateDashboardGroup:
    """Tests for create_dashboard_group tool."""

    @respx.mock
    async def test_create_dashboard_group_blocked_by_default(self, client, monkeypatch):
        """create_dashboard_group requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboard_groups import create_dashboard_group

        result = await create_dashboard_group(client, name="Test Group")

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_create_dashboard_group_success(self, client, enable_writes):
        """create_dashboard_group creates a group with minimal params."""
        from lm_mcp.tools.dashboard_groups import create_dashboard_group

        respx.post("https://test.logicmonitor.com/santaba/rest/dashboard/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 42,
                    "name": "Production Dashboards",
                    "parentId": 1,
                },
            )
        )

        result = await create_dashboard_group(
            client, name="Production Dashboards"
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["group_id"] == 42
        assert "Production Dashboards" in data["message"]

    @respx.mock
    async def test_create_dashboard_group_with_parent_and_description(
        self, client, enable_writes
    ):
        """create_dashboard_group passes parent_id and description."""
        from lm_mcp.tools.dashboard_groups import create_dashboard_group

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/groups"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 43,
                    "name": "Sub Group",
                    "parentId": 10,
                    "description": "A sub group",
                },
            )
        )

        result = await create_dashboard_group(
            client,
            name="Sub Group",
            parent_id=10,
            description="A sub group",
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["group_id"] == 43

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Sub Group"
        assert request_body["parentId"] == 10
        assert request_body["description"] == "A sub group"


class TestDeleteDashboardGroup:
    """Tests for delete_dashboard_group tool."""

    @respx.mock
    async def test_delete_dashboard_group_blocked_by_default(self, client, monkeypatch):
        """delete_dashboard_group requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboard_groups import delete_dashboard_group

        result = await delete_dashboard_group(client, group_id=42)

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_delete_dashboard_group_success(self, client, enable_writes):
        """delete_dashboard_group deletes the group successfully."""
        from lm_mcp.tools.dashboard_groups import delete_dashboard_group

        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/dashboard/groups/42"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_dashboard_group(client, group_id=42)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "42" in data["message"]

    @respx.mock
    async def test_delete_dashboard_group_not_found(self, client, enable_writes):
        """delete_dashboard_group handles 404 gracefully."""
        from lm_mcp.tools.dashboard_groups import delete_dashboard_group

        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/dashboard/groups/999"
        ).mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "Dashboard group not found"}
            )
        )

        result = await delete_dashboard_group(client, group_id=999)

        assert "Error:" in result[0].text
