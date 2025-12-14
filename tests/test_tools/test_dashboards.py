# Description: Tests for dashboard MCP tools.
# Description: Validates get_dashboards, get_dashboard, get_dashboard_widgets, create_dashboard.

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


class TestGetDashboards:
    """Tests for get_dashboards tool."""

    @respx.mock
    async def test_get_dashboards_returns_list(self, client):
        """get_dashboards returns properly formatted dashboard list."""
        from lm_mcp.tools.dashboards import get_dashboards

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production Overview",
                            "description": "Main production dashboard",
                            "groupId": 1,
                            "groupFullPath": "Dashboards",
                            "owner": "admin",
                            "widgetsConfig": [1, 2, 3],
                        },
                        {
                            "id": 2,
                            "name": "Network Status",
                            "description": "Network monitoring",
                            "groupId": 2,
                            "groupFullPath": "Dashboards/Network",
                            "owner": "admin",
                            "widgetsConfig": [4, 5],
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_dashboards(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["dashboards"]) == 2
        assert data["dashboards"][0]["name"] == "Production Overview"
        assert data["dashboards"][1]["name"] == "Network Status"

    @respx.mock
    async def test_get_dashboards_with_name_filter(self, client):
        """get_dashboards passes name filter to API."""
        from lm_mcp.tools.dashboards import get_dashboards

        route = respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_dashboards(client, name_filter="Prod*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_dashboards_with_group_filter(self, client):
        """get_dashboards filters by group ID."""
        from lm_mcp.tools.dashboards import get_dashboards

        route = respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_dashboards(client, group_id=5)

        assert "filter" in route.calls[0].request.url.params


class TestGetDashboard:
    """Tests for get_dashboard tool."""

    @respx.mock
    async def test_get_dashboard_returns_details(self, client):
        """get_dashboard returns single dashboard details."""
        from lm_mcp.tools.dashboards import get_dashboard

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Production Overview",
                    "description": "Main production dashboard",
                    "groupId": 1,
                    "groupFullPath": "Dashboards",
                    "owner": "admin",
                    "widgetsConfig": {"count": 5},
                },
            )
        )

        result = await get_dashboard(client, dashboard_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123
        assert data["name"] == "Production Overview"

    @respx.mock
    async def test_get_dashboard_not_found(self, client):
        """get_dashboard returns error for missing dashboard."""
        from lm_mcp.tools.dashboards import get_dashboard

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Dashboard not found"})
        )

        result = await get_dashboard(client, dashboard_id=999)

        assert "Error:" in result[0].text


class TestGetDashboardWidgets:
    """Tests for get_dashboard_widgets tool."""

    @respx.mock
    async def test_get_dashboard_widgets_returns_list(self, client):
        """get_dashboard_widgets returns widget list."""
        from lm_mcp.tools.dashboards import get_dashboard_widgets

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "name": "CPU Usage",
                            "type": "cgraph",
                            "description": "CPU graph",
                            "columnIdx": 0,
                            "rowSpan": 1,
                            "colSpan": 6,
                        },
                        {
                            "id": 1002,
                            "name": "Memory Usage",
                            "type": "cgraph",
                            "description": "Memory graph",
                            "columnIdx": 6,
                            "rowSpan": 1,
                            "colSpan": 6,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_dashboard_widgets(client, dashboard_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["dashboard_id"] == 123
        assert data["total"] == 2
        assert len(data["widgets"]) == 2
        assert data["widgets"][0]["name"] == "CPU Usage"
        assert data["widgets"][0]["type"] == "cgraph"

    @respx.mock
    async def test_get_dashboard_widgets_handles_error(self, client):
        """get_dashboard_widgets handles 404 error gracefully."""
        from lm_mcp.tools.dashboards import get_dashboard_widgets

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/999/widgets"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Dashboard not found"}))

        result = await get_dashboard_widgets(client, dashboard_id=999)

        assert "Error:" in result[0].text


class TestCreateDashboard:
    """Tests for create_dashboard tool."""

    @respx.mock
    async def test_create_dashboard_blocked_by_default(self, client, monkeypatch):
        """create_dashboard requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import create_dashboard

        result = await create_dashboard(client, name="Test Dashboard")

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_create_dashboard_succeeds_when_enabled(self, client, enable_writes):
        """create_dashboard creates dashboard when writes enabled."""
        from lm_mcp.tools.dashboards import create_dashboard

        respx.post("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 500,
                    "name": "New Dashboard",
                    "groupId": 1,
                    "description": "Test description",
                },
            )
        )

        result = await create_dashboard(
            client,
            name="New Dashboard",
            description="Test description",
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["dashboard"]["id"] == 500
        assert data["dashboard"]["name"] == "New Dashboard"
