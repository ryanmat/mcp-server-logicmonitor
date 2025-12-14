# Description: Tests for device MCP tools.
# Description: Validates device and device group CRUD functions.

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

    @respx.mock
    async def test_get_devices_with_raw_filter(self, client):
        """get_devices passes raw filter expression to API."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, filter="systemProperties.name:system.hostname")

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "systemProperties" in params["filter"]

    @respx.mock
    async def test_get_devices_with_status_filter(self, client):
        """get_devices filters by device status."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, status="dead")

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        assert "hostStatus" in params["filter"]

    @respx.mock
    async def test_get_devices_combined_filters(self, client):
        """get_devices combines multiple filter parameters."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, name_filter="prod*", status="normal", group_id=5)

        params = dict(route.calls[0].request.url.params)
        assert "filter" in params
        # Should contain all three filters combined with AND
        assert "displayName" in params["filter"]
        assert "hostStatus" in params["filter"]
        assert "hostGroupIds" in params["filter"]

    @respx.mock
    async def test_get_devices_raw_filter_overrides_named(self, client):
        """Raw filter takes precedence when provided."""
        from lm_mcp.tools.devices import get_devices

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_devices(client, name_filter="ignored", filter="customProperties.name:env")

        params = dict(route.calls[0].request.url.params)
        assert "customProperties" in params["filter"]
        # Raw filter should be used, not the named filter
        assert "displayName~ignored" not in params["filter"]


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


class TestCreateDevice:
    """Tests for create_device tool."""

    @respx.mock
    async def test_create_device_returns_blocked_when_disabled(self, client, monkeypatch):
        """create_device returns error when write operations disabled."""
        from lm_mcp.tools.devices import create_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await create_device(
            client, name="10.0.0.1", display_name="test-server", preferred_collector_id=1
        )

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_device_success(self, client, monkeypatch):
        """create_device creates device when write enabled."""
        from lm_mcp.tools.devices import create_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        respx.post("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "10.0.0.1",
                    "displayName": "test-server",
                    "currentCollectorId": 1,
                },
            )
        )

        result = await create_device(
            client, name="10.0.0.1", display_name="test-server", preferred_collector_id=1
        )

        data = json.loads(result[0].text)
        assert data["message"] == "Device created successfully"
        assert data["device"]["id"] == 100


class TestUpdateDevice:
    """Tests for update_device tool."""

    @respx.mock
    async def test_update_device_returns_blocked_when_disabled(self, client, monkeypatch):
        """update_device returns error when write operations disabled."""
        from lm_mcp.tools.devices import update_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await update_device(client, device_id=100, display_name="new-name")

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_device_success(self, client, monkeypatch):
        """update_device updates device when write enabled."""
        from lm_mcp.tools.devices import update_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        respx.patch("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "displayName": "new-name",
                    "description": "Updated description",
                },
            )
        )

        result = await update_device(
            client, device_id=100, display_name="new-name", description="Updated description"
        )

        data = json.loads(result[0].text)
        assert data["message"] == "Device updated successfully"
        assert data["device"]["name"] == "new-name"

    @respx.mock
    async def test_update_device_no_changes(self, client, monkeypatch):
        """update_device returns error when no updates provided."""
        from lm_mcp.tools.devices import update_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        result = await update_device(client, device_id=100)

        assert "No updates provided" in result[0].text


class TestDeleteDevice:
    """Tests for delete_device tool."""

    @respx.mock
    async def test_delete_device_returns_blocked_when_disabled(self, client, monkeypatch):
        """delete_device returns error when write operations disabled."""
        from lm_mcp.tools.devices import delete_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await delete_device(client, device_id=100)

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_device_success(self, client, monkeypatch):
        """delete_device deletes device when write enabled."""
        from lm_mcp.tools.devices import delete_device

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        # GET device info first
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(
                200, json={"id": 100, "displayName": "test-server", "name": "192.168.1.1"}
            )
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_device(client, device_id=100)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "test-server" in data["message"]
        assert data["hard_delete"] is False
        assert data["recoverable"] is True


class TestCreateDeviceGroup:
    """Tests for create_device_group tool."""

    @respx.mock
    async def test_create_device_group_returns_blocked_when_disabled(self, client, monkeypatch):
        """create_device_group returns error when write operations disabled."""
        from lm_mcp.tools.devices import create_device_group

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await create_device_group(client, name="Test Group")

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_device_group_success(self, client, monkeypatch):
        """create_device_group creates group when write enabled."""
        from lm_mcp.tools.devices import create_device_group

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        respx.post("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Test Group",
                    "parentId": 1,
                    "fullPath": "/Test Group",
                },
            )
        )

        result = await create_device_group(client, name="Test Group", description="Test")

        data = json.loads(result[0].text)
        assert data["message"] == "Device group created successfully"
        assert data["group"]["id"] == 50


class TestDeleteDeviceGroup:
    """Tests for delete_device_group tool."""

    @respx.mock
    async def test_delete_device_group_returns_blocked_when_disabled(self, client, monkeypatch):
        """delete_device_group returns error when write operations disabled."""
        from lm_mcp.tools.devices import delete_device_group

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await delete_device_group(client, group_id=50)

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_device_group_success(self, client, monkeypatch):
        """delete_device_group deletes group when write enabled."""
        from lm_mcp.tools.devices import delete_device_group

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        # GET group info first for impact assessment
        respx.get("https://test.logicmonitor.com/santaba/rest/device/groups/50").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 50,
                    "name": "Test Group",
                    "fullPath": "/Test Group",
                    "numOfHosts": 0,
                    "numOfDirectSubGroups": 0,
                },
            )
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/device/groups/50").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_device_group(client, group_id=50)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "Test Group" in data["message"]
        assert data["recoverable"] is True
