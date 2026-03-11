# Description: Tests for dashboard and widget MCP tools.
# Description: Validates dashboard CRUD, widget CRUD, SLA defaults, and field remapping.

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


class TestCreateDashboardWithWidgetTokens:
    """Tests for create_dashboard with widget_tokens and template params."""

    @respx.mock
    async def test_create_dashboard_with_widget_tokens(self, client, enable_writes):
        """create_dashboard passes widget_tokens as widgetTokens in payload."""
        from lm_mcp.tools.dashboards import create_dashboard

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 600, "name": "Token Dashboard", "groupId": 1},
            )
        )

        tokens = [
            {"name": "##hostname##", "value": "prod-web-01"},
            {"name": "##group##", "value": "Production"},
        ]

        result = await create_dashboard(
            client,
            name="Token Dashboard",
            widget_tokens=tokens,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["dashboard"]["id"] == 600

        # Verify widgetTokens was sent in the request body
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["widgetTokens"] == tokens

    @respx.mock
    async def test_create_dashboard_with_template(self, client, enable_writes):
        """create_dashboard uses template as base payload, overriding name and stripping id."""
        from lm_mcp.tools.dashboards import create_dashboard

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 700, "name": "Cloned Dashboard", "groupId": 2},
            )
        )

        template = {
            "id": 999,
            "name": "Original Dashboard",
            "groupId": 2,
            "sharable": True,
            "widgetsConfig": [1, 2, 3],
            "description": "From template",
        }

        result = await create_dashboard(
            client,
            name="Cloned Dashboard",
            template=template,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["dashboard"]["id"] == 700

        # Verify template fields are used, name is overridden, id is stripped
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Cloned Dashboard"
        assert "id" not in request_body
        assert request_body["description"] == "From template"
        assert request_body["widgetsConfig"] == [1, 2, 3]

    @respx.mock
    async def test_create_dashboard_template_with_tokens_override(
        self, client, enable_writes
    ):
        """create_dashboard with both template and widget_tokens merges correctly."""
        from lm_mcp.tools.dashboards import create_dashboard

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/dashboards"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 800, "name": "Merged Dashboard", "groupId": 1},
            )
        )

        template = {
            "id": 100,
            "name": "Template Name",
            "groupId": 5,
            "widgetTokens": [{"name": "##old##", "value": "old_val"}],
        }
        tokens = [{"name": "##new##", "value": "new_val"}]

        result = await create_dashboard(
            client,
            name="Merged Dashboard",
            group_id=1,
            widget_tokens=tokens,
            template=template,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True

        # Explicit params override template values
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "Merged Dashboard"
        assert request_body["groupId"] == 1
        assert request_body["widgetTokens"] == tokens


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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets/456"
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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets/999"
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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
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

    @respx.mock
    async def test_add_widget_dashboard_id_in_body(self, client, enable_writes):
        """add_widget includes dashboardId in the request body."""
        from lm_mcp.tools.dashboards import add_widget

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 790,
                    "name": "Body Check Widget",
                    "type": "text",
                    "dashboardId": 456,
                },
            )
        )

        await add_widget(
            client,
            dashboard_id=456,
            name="Body Check Widget",
            widget_type="text",
        )

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["dashboardId"] == 456


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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets/456"
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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets/456"
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
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets/456"
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


class TestWidgetCountAccuracy:
    """Tests for widget_count calculation in get_dashboards (Bug 3 fix)."""

    @respx.mock
    async def test_widget_count_from_num_of_widgets(self, client):
        """get_dashboards uses numOfWidgets when available."""
        from lm_mcp.tools.dashboards import get_dashboards

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Dashboard",
                            "numOfWidgets": 11,
                            "widgetsConfig": {},
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_dashboards(client)
        data = json.loads(result[0].text)
        assert data["dashboards"][0]["widget_count"] == 11

    @respx.mock
    async def test_widget_count_from_empty_dict_without_num(self, client):
        """get_dashboards returns 0 when widgetsConfig is empty dict and no numOfWidgets."""
        from lm_mcp.tools.dashboards import get_dashboards

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "name": "Dashboard", "widgetsConfig": {}}],
                    "total": 1,
                },
            )
        )

        result = await get_dashboards(client)
        data = json.loads(result[0].text)
        assert data["dashboards"][0]["widget_count"] == 0

    @respx.mock
    async def test_widget_count_from_list(self, client):
        """get_dashboards counts widget IDs in list format."""
        from lm_mcp.tools.dashboards import get_dashboards

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/dashboards").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "Dashboard", "widgetsConfig": [1, 2, 3, 4, 5]}
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_dashboards(client)
        data = json.loads(result[0].text)
        assert data["dashboards"][0]["widget_count"] == 5


class TestAddWidgetSLADefaults:
    """Tests for deviceSLA default fields (Bug 4 fix)."""

    @respx.mock
    async def test_sla_defaults_applied(self, client, enable_writes):
        """add_widget applies deviceSLA defaults when not provided in config."""
        from lm_mcp.tools.dashboards import add_widget

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 900, "name": "SLA Widget", "type": "deviceSLA", "dashboardId": 123},
            )
        )

        await add_widget(
            client,
            dashboard_id=123,
            name="SLA Widget",
            widget_type="deviceSLA",
            config={
                "groupName": "Production",
                "deviceName": "server1",
                "dataSourceFullName": "Ping",
                "metric": "PingLossPercent",
                "threshold": 100,
            },
        )

        body = json.loads(route.calls[0].request.content)
        assert body["daysInWeek"] == "1,2,3,4,5,6,7"
        assert body["periodInOneDay"] == "0:00-23:59"
        assert body["displayType"] == 0
        assert body["calculationMethod"] == 0
        assert body["unmonitoredTimeAlertStatus"] == 0

    @respx.mock
    async def test_sla_defaults_not_overridden(self, client, enable_writes):
        """add_widget does not override explicitly provided SLA fields."""
        from lm_mcp.tools.dashboards import add_widget

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 901, "name": "SLA Widget", "type": "deviceSLA", "dashboardId": 123},
            )
        )

        await add_widget(
            client,
            dashboard_id=123,
            name="SLA Widget",
            widget_type="deviceSLA",
            config={
                "groupName": "Production",
                "deviceName": "server1",
                "dataSourceFullName": "Ping",
                "metric": "PingLossPercent",
                "threshold": 100,
                "daysInWeek": "1,2,3,4,5",
                "displayType": 1,
            },
        )

        body = json.loads(route.calls[0].request.content)
        assert body["daysInWeek"] == "1,2,3,4,5"
        assert body["displayType"] == 1


class TestAddWidgetFieldRemapping:
    """Tests for config field name remapping (Bug 5 fix)."""

    @respx.mock
    async def test_sla_field_alias_remapped(self, client, enable_writes):
        """add_widget remaps deviceGroupFullPath to groupName for deviceSLA widgets."""
        from lm_mcp.tools.dashboards import add_widget

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 902, "name": "SLA", "type": "deviceSLA", "dashboardId": 123},
            )
        )

        await add_widget(
            client,
            dashboard_id=123,
            name="SLA",
            widget_type="deviceSLA",
            config={
                "deviceGroupFullPath": "Production/Web",
                "deviceName": "server1",
                "dataSourceFullName": "Ping",
                "metric": "PingLossPercent",
                "threshold": 100,
            },
        )

        body = json.loads(route.calls[0].request.content)
        assert body["groupName"] == "Production/Web"
        assert "deviceGroupFullPath" not in body

    @respx.mock
    async def test_text_html_to_content_remapped(self, client, enable_writes):
        """add_widget remaps 'html' to 'content' for text widgets."""
        from lm_mcp.tools.dashboards import add_widget

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/dashboard/widgets"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 903, "name": "Info", "type": "text", "dashboardId": 123},
            )
        )

        await add_widget(
            client,
            dashboard_id=123,
            name="Info",
            widget_type="text",
            config={"html": "<h1>Hello</h1>"},
        )

        body = json.loads(route.calls[0].request.content)
        assert body["content"] == "<h1>Hello</h1>"
        assert "html" not in body
