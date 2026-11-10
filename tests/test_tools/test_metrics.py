# Description: Tests for metrics MCP tools.
# Description: Validates datasource, instance, and data retrieval functions.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result


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

        assert is_error_result(result)


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

    _DATA = (
        "https://test.logicmonitor.com/santaba/rest/device/devices/100"
        "/devicedatasources/1001/instances/5001/data"
    )

    @respx.mock
    async def test_a_day_of_minutes_is_read_in_both_pages(self, client):
        """R2.10: 1,440 samples over two pages all arrive, newest first, as the API orders them.

        A start with no end is sent with end=now: the endpoint answers a start alone with
        its last hour (probe of lmryanmatuszewski, 2026-11-09).
        """
        import time

        from lm_mcp.tools.metrics import get_device_data
        from tests.metric_pages import day_of_minutes

        pages = day_of_minutes()
        route = respx.get(self._DATA).mock(side_effect=pages)

        before = int(time.time())
        result = await get_device_data(
            client, device_id=100, device_datasource_id=1001, instance_id=5001, start_time=1
        )

        data = json.loads(result[0].text)
        first = route.calls[0].request.url.params
        assert first["start"] == "1"
        assert before <= int(first["end"]) <= int(time.time())
        assert route.call_count == 2
        next_page = json.loads(pages[0].content)["nextPageParams"]
        assert dict(route.calls[1].request.url.params) == dict(
            p.split("=") for p in next_page.split("&")
        )
        assert len(data["time"]) == len(data["values"]) == 1440
        assert data["time"] == sorted(data["time"], reverse=True)
        assert data["truncated"] is False
        assert "warning" not in data

    @respx.mock
    async def test_a_read_the_page_cap_stops_says_so(self, client):
        """R2.10: a window past the page cap is flagged, not silently cut."""
        from lm_mcp.tools.metrics import get_device_data
        from lm_mcp.tools.stats_helpers import MAX_SERIES_PAGES
        from tests.metric_pages import capped_read

        route = respx.get(self._DATA).mock(side_effect=capped_read())

        result = await get_device_data(
            client, device_id=100, device_datasource_id=1001, instance_id=5001, start_time=1
        )

        data = json.loads(result[0].text)
        assert route.call_count == MAX_SERIES_PAGES
        assert data["truncated"] is True
        assert f"{MAX_SERIES_PAGES}-page cap" in data["warning"]

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
                    "values": [[28.1, 71.9], [30.2, 69.8], [25.5, 74.5]],
                    "time": [1702500120000, 1702500060000, 1702500000000],
                    "nextPageParams": "",
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
        assert data["values"][0] == [28.1, 71.9]

    @respx.mock
    async def test_get_device_data_with_time_range(self, client):
        """get_device_data passes time range parameters."""
        from lm_mcp.tools.metrics import get_device_data

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/devicedatasources/1001/instances/5001/data"
        ).mock(return_value=httpx.Response(200, json={"dataPoints": [], "values": [], "time": []}))

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
        ).mock(return_value=httpx.Response(200, json={"dataPoints": [], "values": [], "time": []}))

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

        assert is_error_result(result)


# -- Instance management tools (write) ----------------------------------------


BASE_URL = "https://test.logicmonitor.com/santaba/rest"
INSTANCES_URL = f"{BASE_URL}/device/devices/100/devicedatasources/1001/instances"


def _enable_writes(monkeypatch):
    """Configure environment for write operations."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")


def _disable_writes(monkeypatch):
    """Configure environment with write operations disabled."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")


class TestAddDeviceInstance:
    """Tests for add_device_instance tool."""

    async def test_blocked_without_write_permission(self, client, monkeypatch):
        """add_device_instance returns error when write operations disabled."""
        _disable_writes(monkeypatch)
        from lm_mcp.tools.metrics import add_device_instance

        result = await add_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            display_name="nginx",
            wild_value="nginx.service",
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_creates_instance_successfully(self, client, monkeypatch):
        """add_device_instance creates an instance and returns its details."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import add_device_instance

        respx.post(INSTANCES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5002,
                    "displayName": "nginx",
                    "wildValue": "nginx.service",
                    "description": "nginx web server",
                    "deviceId": 100,
                    "deviceDataSourceId": 1001,
                },
            )
        )

        result = await add_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            display_name="nginx",
            wild_value="nginx.service",
            description="nginx web server",
        )

        data = json.loads(result[0].text)
        assert data["instance"]["id"] == 5002
        assert data["instance"]["display_name"] == "nginx"
        assert data["instance"]["wild_value"] == "nginx.service"

    @respx.mock
    async def test_sends_correct_body(self, client, monkeypatch):
        """add_device_instance sends displayName and wildValue in request body."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import add_device_instance

        route = respx.post(INSTANCES_URL).mock(
            return_value=httpx.Response(
                200,
                json={"id": 5003, "displayName": "sshd", "wildValue": "sshd.service"},
            )
        )

        await add_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            display_name="sshd",
            wild_value="sshd.service",
        )

        body = json.loads(route.calls[0].request.content)
        assert body["displayName"] == "sshd"
        assert body["wildValue"] == "sshd.service"

    @respx.mock
    async def test_handles_api_error(self, client, monkeypatch):
        """add_device_instance handles 404 error gracefully."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import add_device_instance

        respx.post(INSTANCES_URL).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await add_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            display_name="nginx",
            wild_value="nginx.service",
        )
        assert is_error_result(result)


class TestUpdateDeviceInstance:
    """Tests for update_device_instance tool."""

    async def test_blocked_without_write_permission(self, client, monkeypatch):
        """update_device_instance returns error when write operations disabled."""
        _disable_writes(monkeypatch)
        from lm_mcp.tools.metrics import update_device_instance

        result = await update_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            description="updated",
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_updates_instance_successfully(self, client, monkeypatch):
        """update_device_instance updates and returns instance details."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import update_device_instance

        respx.patch(f"{INSTANCES_URL}/5001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5001,
                    "displayName": "nginx-updated",
                    "description": "updated desc",
                    "stopMonitoring": False,
                },
            )
        )

        result = await update_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
            description="updated desc",
        )

        data = json.loads(result[0].text)
        assert data["instance"]["id"] == 5001
        assert data["instance"]["display_name"] == "nginx-updated"

    async def test_returns_error_when_no_changes(self, client, monkeypatch):
        """update_device_instance returns error when no fields provided."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import update_device_instance

        result = await update_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
        )

        assert "No updates provided" in result[0].text


class TestDeleteDeviceInstance:
    """Tests for delete_device_instance tool."""

    async def test_blocked_without_write_permission(self, client, monkeypatch):
        """delete_device_instance returns error when write operations disabled."""
        _disable_writes(monkeypatch)
        from lm_mcp.tools.metrics import delete_device_instance

        result = await delete_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_deletes_instance_successfully(self, client, monkeypatch):
        """delete_device_instance deletes and returns confirmation."""
        _enable_writes(monkeypatch)
        from lm_mcp.tools.metrics import delete_device_instance

        respx.get(f"{INSTANCES_URL}/5001").mock(
            return_value=httpx.Response(
                200,
                json={"id": 5001, "displayName": "nginx"},
            )
        )
        respx.delete(f"{INSTANCES_URL}/5001").mock(return_value=httpx.Response(200, json={}))

        result = await delete_device_instance(
            client,
            device_id=100,
            device_datasource_id=1001,
            instance_id=5001,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["instance_id"] == 5001
        assert data["display_name"] == "nginx"
