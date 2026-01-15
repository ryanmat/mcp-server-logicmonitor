# Description: Tests for DataSource MCP tools.
# Description: Validates get_datasources, get_datasource functions.

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
