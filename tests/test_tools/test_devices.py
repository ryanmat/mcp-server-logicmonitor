# Description: Tests for device MCP tools.
# Description: Validates get_devices, get_device, get_device_groups functions.

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


class TestGetDevices:
    """Tests for get_devices tool."""

    @respx.mock
    async def test_get_devices_returns_formatted_response(self, client):
        """get_devices returns properly formatted device list."""
        from lm_mcp.tools.devices import get_devices

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "displayName": "server01",
                            "hostStatus": 1,
                            "currentCollectorId": 5,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_devices(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["devices"][0]["name"] == "server01"

    @respx.mock
    async def test_get_devices_with_name_filter(self, client):
        """get_devices passes name filter to API."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, name_filter="prod*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_devices_with_group_filter(self, client):
        """get_devices filters by group ID."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, group_id=10)

        assert "filter" in route.calls[0].request.url.params


class TestGetDevice:
    """Tests for get_device tool."""

    @respx.mock
    async def test_get_device_returns_details(self, client):
        """get_device returns single device details."""
        from lm_mcp.tools.devices import get_device

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "displayName": "server01",
                    "hostStatus": 1,
                    "systemProperties": [
                        {"name": "system.hostname", "value": "server01.example.com"}
                    ],
                },
            )
        )

        result = await get_device(client, device_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123

    @respx.mock
    async def test_get_device_not_found(self, client):
        """get_device returns error for missing device."""
        from lm_mcp.tools.devices import get_device

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await get_device(client, device_id=999)

        assert "Error:" in result[0].text


class TestGetDeviceGroups:
    """Tests for get_device_groups tool."""

    @respx.mock
    async def test_get_device_groups_returns_list(self, client):
        """get_device_groups returns group list."""
        from lm_mcp.tools.devices import get_device_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "Production", "numOfHosts": 10},
                        {"id": 2, "name": "Development", "numOfHosts": 5},
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_device_groups(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["groups"]) == 2

    @respx.mock
    async def test_get_device_groups_with_parent_filter(self, client):
        """get_device_groups filters by parent ID."""
        from lm_mcp.tools.devices import get_device_groups

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_device_groups(client, parent_id=1)

        assert "filter" in route.calls[0].request.url.params
