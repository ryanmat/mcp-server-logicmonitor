# Description: Tests for DataSource MCP tools.
# Description: Validates DataSource CRUD functions including create, update, and delete.

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


class TestGetDatasources:
    """Tests for get_datasources tool."""

    @respx.mock
    async def test_get_datasources_returns_list(self, client):
        """get_datasources returns properly formatted datasource list."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "CPU",
                            "displayName": "CPU Usage",
                            "description": "Monitors CPU usage",
                            "appliesTo": "isWindows()",
                            "group": "Core",
                            "collectMethod": "wmi",
                            "hasMultiInstances": False,
                        },
                        {
                            "id": 2,
                            "name": "Memory",
                            "displayName": "Memory Usage",
                            "description": "Monitors memory usage",
                            "appliesTo": "isWindows()",
                            "group": "Core",
                            "collectMethod": "wmi",
                            "hasMultiInstances": False,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_datasources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["datasources"]) == 2
        assert data["datasources"][0]["name"] == "CPU"
        assert data["datasources"][1]["name"] == "Memory"

    @respx.mock
    async def test_get_datasources_with_name_filter(self, client):
        """get_datasources passes name filter to API."""
        from lm_mcp.tools.datasources import get_datasources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_datasources(client, name_filter="CPU*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_datasources_with_applies_to_filter(self, client):
        """get_datasources passes appliesTo filter to API."""
        from lm_mcp.tools.datasources import get_datasources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_datasources(client, applies_to_filter="isLinux()")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_datasources_handles_error(self, client):
        """get_datasources handles errors gracefully."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Permission denied"})
        )

        result = await get_datasources(client)

        assert "Error:" in result[0].text


class TestGetDatasource:
    """Tests for get_datasource tool."""

    @respx.mock
    async def test_get_datasource_returns_details(self, client):
        """get_datasource returns detailed datasource info."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "CPU",
                    "displayName": "CPU Usage",
                    "description": "Monitors CPU usage metrics",
                    "appliesTo": "isWindows()",
                    "group": "Core",
                    "collectMethod": "wmi",
                    "collectInterval": 60,
                    "hasMultiInstances": True,
                    "dataPoints": [
                        {
                            "id": 1,
                            "name": "CPUBusyPercent",
                            "description": "CPU busy percentage",
                            "type": 0,
                            "alertExpr": "> 90",
                        },
                        {
                            "id": 2,
                            "name": "CPUIdlePercent",
                            "description": "CPU idle percentage",
                            "type": 0,
                            "alertExpr": "",
                        },
                    ],
                    "graphs": [
                        {
                            "id": 10,
                            "name": "CPUGraph",
                            "title": "CPU Usage Over Time",
                        }
                    ],
                },
            )
        )

        result = await get_datasource(client, datasource_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "CPU"
        assert len(data["datapoints"]) == 2
        assert data["datapoints"][0]["name"] == "CPUBusyPercent"
        assert len(data["graphs"]) == 1
        assert data["graphs"][0]["title"] == "CPU Usage Over Time"

    @respx.mock
    async def test_get_datasource_not_found(self, client):
        """get_datasource returns error for missing datasource."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "DataSource not found"})
        )

        result = await get_datasource(client, datasource_id=999)

        assert "Error:" in result[0].text

    @respx.mock
    async def test_get_datasource_empty_datapoints(self, client):
        """get_datasource handles datasource with no datapoints."""
        from lm_mcp.tools.datasources import get_datasource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 101,
                    "name": "SimpleDS",
                    "displayName": "Simple DataSource",
                    "description": "A simple datasource",
                    "appliesTo": "true()",
                    "group": "Test",
                    "collectMethod": "script",
                    "collectInterval": 300,
                    "hasMultiInstances": False,
                    "dataPoints": [],
                    "graphs": [],
                },
            )
        )

        result = await get_datasource(client, datasource_id=101)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 101
        assert len(data["datapoints"]) == 0
        assert len(data["graphs"]) == 0


class TestGetDatasourcesFilters:
    """Tests for get_datasources filter parameters."""

    @respx.mock
    async def test_get_datasources_with_raw_filter(self, client):
        """get_datasources passes raw filter expression to API."""
        from lm_mcp.tools.datasources import get_datasources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_datasources(client, filter="name~CPU,group:Core")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "name~CPU,group:Core"

    @respx.mock
    async def test_get_datasources_with_offset(self, client):
        """get_datasources passes offset for pagination."""
        from lm_mcp.tools.datasources import get_datasources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_datasources(client, offset=100)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "100"

    @respx.mock
    async def test_get_datasources_pagination_info(self, client):
        """get_datasources returns pagination info."""
        from lm_mcp.tools.datasources import get_datasources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "name": "CPU"}],
                    "total": 500,
                },
            )
        )

        result = await get_datasources(client, limit=50, offset=0)

        data = json.loads(result[0].text)
        assert data["total"] == 500
        assert data["has_more"] is True
        assert data["offset"] == 0


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestCreateDatasource:
    """Tests for create_datasource tool."""

    async def test_create_datasource_requires_write_permission(self, client, monkeypatch):
        """create_datasource requires write permission."""
        from lm_mcp.tools.datasources import create_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_datasource(client, definition={"name": "TestDS"})

        assert len(result) == 1
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_datasource_posts_definition(self, client, enable_writes):
        """create_datasource posts definition to /setting/datasources."""
        from lm_mcp.tools.datasources import create_datasource

        definition = {
            "name": "CustomDS",
            "displayName": "Custom DataSource",
            "appliesTo": "isLinux()",
            "collectMethod": "script",
            "dataPoints": [{"name": "dp1", "type": 0}],
        }

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5001,
                    "name": "CustomDS",
                    "displayName": "Custom DataSource",
                },
            )
        )

        await create_datasource(client, definition=definition)

        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body["name"] == "CustomDS"
        assert request_body["appliesTo"] == "isLinux()"

    @respx.mock
    async def test_create_datasource_returns_created_fields(self, client, enable_writes):
        """create_datasource returns id, name, displayName from response."""
        from lm_mcp.tools.datasources import create_datasource

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5002,
                    "name": "NewDS",
                    "displayName": "New DataSource",
                },
            )
        )

        result = await create_datasource(
            client,
            definition={"name": "NewDS", "displayName": "New DataSource"},
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 5002
        assert data["datasource"]["name"] == "NewDS"
        assert data["datasource"]["display_name"] == "New DataSource"

    @respx.mock
    async def test_create_datasource_strips_id_from_definition(self, client, enable_writes):
        """create_datasource strips id from definition before POST."""
        from lm_mcp.tools.datasources import create_datasource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 5003, "name": "ClonedDS", "displayName": "Cloned DS"},
            )
        )

        definition = {"id": 999, "name": "ClonedDS", "displayName": "Cloned DS"}
        await create_datasource(client, definition=definition)

        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    @respx.mock
    async def test_create_datasource_handles_api_error(self, client, enable_writes):
        """create_datasource handles API errors gracefully."""
        from lm_mcp.tools.datasources import create_datasource

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                400, json={"errorMessage": "Invalid DataSource definition"}
            )
        )

        result = await create_datasource(
            client, definition={"name": "Bad"}
        )

        assert "Error:" in result[0].text


class TestCreateDatasourceOverwrite:
    """Tests for create_datasource overwrite parameter."""

    @respx.mock
    async def test_create_datasource_overwrite_deletes_existing(self, client, enable_writes):
        """create_datasource with overwrite=True deletes existing DS before creating."""
        from lm_mcp.tools.datasources import create_datasource

        # GET to look up existing DS by name
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 500, "name": "MyDS"}],
                    "total": 1,
                },
            )
        )

        # DELETE existing DS
        delete_route = respx.delete(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/500"
        ).mock(return_value=httpx.Response(200, json={}))

        # POST new DS
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 501, "name": "MyDS", "displayName": "My DataSource"},
            )
        )

        result = await create_datasource(
            client,
            definition={"name": "MyDS", "displayName": "My DataSource"},
            overwrite=True,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 501
        assert delete_route.called

    @respx.mock
    async def test_create_datasource_overwrite_no_existing(self, client, enable_writes):
        """create_datasource with overwrite=True works when no existing DS found."""
        from lm_mcp.tools.datasources import create_datasource

        # GET returns no existing DS
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        # POST new DS (no DELETE needed)
        respx.post("https://test.logicmonitor.com/santaba/rest/setting/datasources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 502, "name": "NewDS", "displayName": "New DS"},
            )
        )

        result = await create_datasource(
            client,
            definition={"name": "NewDS", "displayName": "New DS"},
            overwrite=True,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 502

    @respx.mock
    async def test_create_datasource_without_overwrite_unchanged(self, client, enable_writes):
        """create_datasource without overwrite flag does not look up existing."""
        from lm_mcp.tools.datasources import create_datasource

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 503, "name": "PlainDS", "displayName": "Plain DS"},
            )
        )

        result = await create_datasource(
            client, definition={"name": "PlainDS"}, overwrite=False
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        # Should only have the POST call, no GET for lookup
        assert route.called


class TestUpdateDatasource:
    """Tests for update_datasource tool."""

    async def test_update_datasource_requires_write_permission(self, client, monkeypatch):
        """update_datasource requires write permission."""
        from lm_mcp.tools.datasources import update_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_datasource(
            client, datasource_id=100, definition={"name": "Updated"}
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_datasource_puts_definition(self, client, enable_writes):
        """update_datasource PUTs definition to /setting/datasources/{id}."""
        from lm_mcp.tools.datasources import update_datasource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "UpdatedDS",
                    "displayName": "Updated DataSource",
                },
            )
        )

        result = await update_datasource(
            client,
            datasource_id=100,
            definition={"name": "UpdatedDS", "displayName": "Updated DataSource"},
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["datasource"]["id"] == 100
        assert data["datasource"]["name"] == "UpdatedDS"

    @respx.mock
    async def test_update_datasource_strips_id_from_definition(self, client, enable_writes):
        """update_datasource strips id from definition before PUT."""
        from lm_mcp.tools.datasources import update_datasource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "DS", "displayName": "DS"},
            )
        )

        await update_datasource(
            client, datasource_id=100, definition={"id": 999, "name": "DS"}
        )

        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    @respx.mock
    async def test_update_datasource_handles_error(self, client, enable_writes):
        """update_datasource handles API errors."""
        from lm_mcp.tools.datasources import update_datasource

        respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/999"
        ).mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "DataSource not found"}
            )
        )

        result = await update_datasource(
            client, datasource_id=999, definition={"name": "Missing"}
        )

        assert "Error:" in result[0].text


class TestDeleteDatasource:
    """Tests for delete_datasource tool."""

    async def test_delete_datasource_requires_write_permission(self, client, monkeypatch):
        """delete_datasource requires write permission."""
        from lm_mcp.tools.datasources import delete_datasource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_datasource(client, datasource_id=100)

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_datasource_success(self, client, enable_writes):
        """delete_datasource deletes and returns confirmation."""
        from lm_mcp.tools.datasources import delete_datasource

        # GET for confirmation info
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "OldDS", "displayName": "Old DataSource"},
            )
        )
        respx.delete(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/100"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await delete_datasource(client, datasource_id=100)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "OldDS" in data["message"]
        assert data["datasource_id"] == 100

    @respx.mock
    async def test_delete_datasource_not_found(self, client, enable_writes):
        """delete_datasource handles 404 errors."""
        from lm_mcp.tools.datasources import delete_datasource

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/datasources/999"
        ).mock(
            return_value=httpx.Response(
                404, json={"errorMessage": "DataSource not found"}
            )
        )

        result = await delete_datasource(client, datasource_id=999)

        assert "Error:" in result[0].text
