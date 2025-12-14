# Description: Tests for metrics MCP tools.
# Description: Validates datasource, instance, and data retrieval functions.

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


class TestGetDeviceDatasources:
    """Tests for get_device_datasources tool."""

    @respx.mock
    async def test_get_device_datasources_returns_list(self, client):
        """get_device_datasources returns properly formatted datasource list."""
        from lm_mcp.tools.metrics import get_device_datasources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "dataSourceId": 50,
                            "dataSourceName": "CPU",
                            "instanceNumber": 1,
                            "monitoringInstanceNumber": 1,
                        },
                        {
                            "id": 1002,
                            "dataSourceId": 51,
                            "dataSourceName": "Memory",
                            "instanceNumber": 1,
                            "monitoringInstanceNumber": 1,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_device_datasources(client, device_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["total"] == 2
        assert len(data["datasources"]) == 2
        assert data["datasources"][0]["name"] == "CPU"
        assert data["datasources"][1]["name"] == "Memory"

    @respx.mock
    async def test_get_device_datasources_with_name_filter(self, client):
        """get_device_datasources passes name filter to API."""
        from lm_mcp.tools.metrics import get_device_datasources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_device_datasources(client, device_id=100, name_filter="CPU*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_device_datasources_handles_error(self, client):
        """get_device_datasources handles 404 error gracefully."""
        from lm_mcp.tools.metrics import get_device_datasources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/999/devicedatasources"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Device not found"}))

        result = await get_device_datasources(client, device_id=999)

        assert "Error:" in result[0].text


class TestGetDeviceInstances:
    """Tests for get_device_instances tool."""

    @respx.mock
    async def test_get_device_instances_returns_list(self, client):
        """get_device_instances returns properly formatted instance list."""
        from lm_mcp.tools.metrics import get_device_instances

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 5001,
                            "displayName": "CPU_Total",
                            "description": "Total CPU usage",
                            "groupName": "",
                            "lockDescription": False,
                            "stopMonitoring": False,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_device_instances(client, device_id=100, device_datasource_id=1001)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["device_datasource_id"] == 1001
        assert data["total"] == 1
        assert data["instances"][0]["name"] == "CPU_Total"

    @respx.mock
    async def test_get_device_instances_with_name_filter(self, client):
        """get_device_instances passes name filter to API."""
        from lm_mcp.tools.metrics import get_device_instances

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_device_instances(
            client, device_id=100, device_datasource_id=1001, name_filter="CPU*"
        )

        assert "filter" in route.calls[0].request.url.params


class TestGetDeviceData:
    """Tests for get_device_data tool."""

    @respx.mock
    async def test_get_device_data_returns_metrics(self, client):
        """get_device_data returns metric data."""
        from lm_mcp.tools.metrics import get_device_data

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["CPUBusyPercent", "CPUIdlePercent"],
                    "values": {
                        "CPUBusyPercent": [25.5, 30.2, 28.1],
                        "CPUIdlePercent": [74.5, 69.8, 71.9],
                    },
                    "time": [1702500000, 1702500060, 1702500120],
                },
            )
        )

        result = await get_device_data(
            client, device_id=100, device_datasource_id=1001, instance_id=5001
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["instance_id"] == 5001
        assert "CPUBusyPercent" in data["datapoints"]
        assert len(data["time"]) == 3

    @respx.mock
    async def test_get_device_data_with_time_range(self, client):
        """get_device_data passes time range parameters."""
        from lm_mcp.tools.metrics import get_device_data

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/data"
        ).mock(return_value=httpx.Response(200, json={"dataPoints": [], "values": {}, "time": []}))

        await get_device_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            start_time=1702500000,
            end_time=1702503600,
        )

        params = route.calls[0].request.url.params
        assert "start" in params
        assert "end" in params

    @respx.mock
    async def test_get_device_data_with_datapoints(self, client):
        """get_device_data passes datapoints filter."""
        from lm_mcp.tools.metrics import get_device_data

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/data"
        ).mock(return_value=httpx.Response(200, json={"dataPoints": [], "values": {}, "time": []}))

        await get_device_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            datapoints="CPUBusyPercent,CPUIdlePercent",
        )

        params = route.calls[0].request.url.params
        assert "datapoints" in params


class TestGetGraphData:
    """Tests for get_graph_data tool."""

    @respx.mock
    async def test_get_graph_data_returns_data(self, client):
        """get_graph_data returns graph data."""
        from lm_mcp.tools.metrics import get_graph_data

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/graphs/200/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "lines": [
                        {"legend": "CPU Usage", "data": [25.5, 30.2, 28.1]},
                    ],
                    "timestamps": [1702500000, 1702500060, 1702500120],
                },
            )
        )

        result = await get_graph_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            graph_id=200,
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["graph_id"] == 200
        assert len(data["lines"]) == 1

    @respx.mock
    async def test_get_graph_data_with_time_range(self, client):
        """get_graph_data passes time range parameters."""
        from lm_mcp.tools.metrics import get_graph_data

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/graphs/200/data"
        ).mock(return_value=httpx.Response(200, json={"lines": [], "timestamps": []}))

        await get_graph_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            graph_id=200,
            start_time=1702500000,
            end_time=1702503600,
        )

        params = route.calls[0].request.url.params
        assert "start" in params
        assert "end" in params

    @respx.mock
    async def test_get_graph_data_handles_error(self, client):
        """get_graph_data handles 404 error gracefully."""
        from lm_mcp.tools.metrics import get_graph_data

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/graphs/999/data"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Graph not found"}))

        result = await get_graph_data(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            graph_id=999,
        )

        assert "Error:" in result[0].text
