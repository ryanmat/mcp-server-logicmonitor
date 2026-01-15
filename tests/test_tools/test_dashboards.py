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


class TestUpdateDashboard:
    """Tests for update_dashboard tool."""

    @respx.mock
    async def test_update_dashboard_blocked_by_default(self, client, monkeypatch):
        """update_dashboard requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import update_dashboard

        result = await update_dashboard(client, dashboard_id=123, name="Updated Name")

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_update_dashboard_succeeds_when_enabled(self, client, enable_writes):
        """update_dashboard updates dashboard when writes enabled."""
        from lm_mcp.tools.dashboards import update_dashboard

        # First GET to fetch current
        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Old Name",
                    "description": "Old description",
                    "groupId": 1,
                    "sharable": True,
                },
            )
        )

        # Then PUT to update
        respx.put("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "New Name",
                    "groupId": 1,
                },
            )
        )

        result = await update_dashboard(client, dashboard_id=123, name="New Name")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["dashboard"]["name"] == "New Name"


class TestDeleteDashboard:
    """Tests for delete_dashboard tool."""

    @respx.mock
    async def test_delete_dashboard_blocked_by_default(self, client, monkeypatch):
        """delete_dashboard requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import delete_dashboard

        result = await delete_dashboard(client, dashboard_id=123)

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_delete_dashboard_succeeds_when_enabled(self, client, enable_writes):
        """delete_dashboard deletes dashboard when writes enabled."""
        from lm_mcp.tools.dashboards import delete_dashboard

        # First GET to fetch info
        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "Dashboard To Delete",
                    "widgetsConfig": [1, 2, 3],
                },
            )
        )

        # Then DELETE
        respx.delete("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_dashboard(client, dashboard_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "deleted" in data["message"].lower()
        assert data["details"]["widgets_removed"] == 3


class TestGetWidget:
    """Tests for get_widget tool."""

    @respx.mock
    async def test_get_widget_returns_details(self, client):
        """get_widget returns single widget details."""
        from lm_mcp.tools.dashboards import get_widget

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets/456"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 456,
                    "name": "CPU Graph",
                    "type": "cgraph",
                    "dashboardId": 123,
                    "columnIdx": 0,
                    "rowSpan": 2,
                    "colSpan": 6,
                },
            )
        )

        result = await get_widget(client, dashboard_id=123, widget_id=456)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 456
        assert data["name"] == "CPU Graph"
        assert data["type"] == "cgraph"

    @respx.mock
    async def test_get_widget_not_found(self, client):
        """get_widget returns error for missing widget."""
        from lm_mcp.tools.dashboards import get_widget

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets/999"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Widget not found"}))

        result = await get_widget(client, dashboard_id=123, widget_id=999)

        assert "Error:" in result[0].text


class TestAddWidget:
    """Tests for add_widget tool."""

    @respx.mock
    async def test_add_widget_blocked_by_default(self, client, monkeypatch):
        """add_widget requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import add_widget

        result = await add_widget(client, dashboard_id=123, name="Test Widget", widget_type="text")

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_add_widget_succeeds_when_enabled(self, client, enable_writes):
        """add_widget creates widget when writes enabled."""
        from lm_mcp.tools.dashboards import add_widget

        respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 789,
                    "name": "New Widget",
                    "type": "cgraph",
                    "dashboardId": 123,
                },
            )
        )

        result = await add_widget(
            client,
            dashboard_id=123,
            name="New Widget",
            widget_type="cgraph",
            column_index=0,
            row_span=2,
            col_span=6,
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["widget"]["id"] == 789
        assert data["widget"]["name"] == "New Widget"


class TestUpdateWidget:
    """Tests for update_widget tool."""

    @respx.mock
    async def test_update_widget_blocked_by_default(self, client, monkeypatch):
        """update_widget requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import update_widget

        result = await update_widget(client, dashboard_id=123, widget_id=456, name="Updated Widget")

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_update_widget_succeeds_when_enabled(self, client, enable_writes):
        """update_widget updates widget when writes enabled."""
        from lm_mcp.tools.dashboards import update_widget

        # First the GET to fetch current widget
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets/456"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 456,
                    "name": "Old Widget",
                    "type": "cgraph",
                    "dashboardId": 123,
                    "columnIdx": 0,
                    "rowSpan": 1,
                    "colSpan": 6,
                },
            )
        )

        # Then the PUT to update
        respx.put(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets/456"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 456,
                    "name": "Updated Widget",
                    "type": "cgraph",
                    "dashboardId": 123,
                },
            )
        )

        result = await update_widget(client, dashboard_id=123, widget_id=456, name="Updated Widget")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["widget"]["name"] == "Updated Widget"


class TestDeleteWidget:
    """Tests for delete_widget tool."""

    @respx.mock
    async def test_delete_widget_blocked_by_default(self, client, monkeypatch):
        """delete_widget requires write permission."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.dashboards import delete_widget

        result = await delete_widget(client, dashboard_id=123, widget_id=456)

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_delete_widget_succeeds_when_enabled(self, client, enable_writes):
        """delete_widget deletes widget when writes enabled."""
        from lm_mcp.tools.dashboards import delete_widget

        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards/123/widgets/456"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_widget(client, dashboard_id=123, widget_id=456)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "deleted" in data["message"].lower()


class TestGetDashboardsFilters:
    """Tests for get_dashboards filter parameters."""

    @respx.mock
    async def test_get_dashboards_with_raw_filter(self, client):
        """get_dashboards passes raw filter expression to API."""
        from lm_mcp.tools.dashboards import get_dashboards

        route = respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_dashboards(client, filter="name~prod,owner:admin")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "name~prod,owner:admin"

    @respx.mock
    async def test_get_dashboards_with_offset(self, client):
        """get_dashboards passes offset for pagination."""
        from lm_mcp.tools.dashboards import get_dashboards

        route = respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_dashboards(client, offset=25)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "25"

    @respx.mock
    async def test_get_dashboards_pagination_info(self, client):
        """get_dashboards returns pagination info."""
        from lm_mcp.tools.dashboards import get_dashboards

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "name": "Dashboard 1"}],
                    "total": 100,
                },
            )
        )

        result = await get_dashboards(client, limit=10, offset=0)

        data = json.loads(result[0].text)
        assert data["total"] == 100
        assert data["has_more"] is True
        assert data["offset"] == 0
