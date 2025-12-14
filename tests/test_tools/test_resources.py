# Description: Tests for resource/property management MCP tools.
# Description: Validates get_device_properties, get_device_property, update_device_property.

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


class TestGetDeviceProperties:
    """Tests for get_device_properties tool."""

    @respx.mock
    async def test_get_device_properties_returns_list(self, client):
        """get_device_properties returns properly formatted property list."""
        from lm_mcp.tools.resources import get_device_properties

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100/properties").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "name": "system.hostname",
                            "value": "server-01.example.com",
                            "type": "system",
                            "inherit": False,
                        },
                        {
                            "name": "system.ips",
                            "value": "192.168.1.100",
                            "type": "system",
                            "inherit": False,
                        },
                        {
                            "name": "location",
                            "value": "US-East",
                            "type": "custom",
                            "inherit": True,
                        },
                    ],
                    "total": 3,
                },
            )
        )

        result = await get_device_properties(client, device_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["total"] == 3
        assert len(data["properties"]) == 3
        assert data["properties"][0]["name"] == "system.hostname"
        assert data["properties"][2]["inherit"] is True

    @respx.mock
    async def test_get_device_properties_with_name_filter(self, client):
        """get_device_properties passes name filter to API."""
        from lm_mcp.tools.resources import get_device_properties

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_device_properties(client, device_id=100, name_filter="system.*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_device_properties_handles_error(self, client):
        """get_device_properties handles 404 error gracefully."""
        from lm_mcp.tools.resources import get_device_properties

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/999/properties").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await get_device_properties(client, device_id=999)

        assert "Error:" in result[0].text


class TestGetDeviceProperty:
    """Tests for get_device_property tool."""

    @respx.mock
    async def test_get_device_property_returns_details(self, client):
        """get_device_property returns property details."""
        from lm_mcp.tools.resources import get_device_property

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/system.hostname"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "system.hostname",
                    "value": "server-01.example.com",
                    "type": "system",
                    "inherit": False,
                },
            )
        )

        result = await get_device_property(client, device_id=100, property_name="system.hostname")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 100
        assert data["name"] == "system.hostname"
        assert data["value"] == "server-01.example.com"
        assert data["type"] == "system"

    @respx.mock
    async def test_get_device_property_not_found(self, client):
        """get_device_property returns error for missing property."""
        from lm_mcp.tools.resources import get_device_property

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/nonexistent"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Property not found"}))

        result = await get_device_property(client, device_id=100, property_name="nonexistent")

        assert "Error:" in result[0].text


class TestUpdateDeviceProperty:
    """Tests for update_device_property tool."""

    @respx.mock
    async def test_update_device_property_blocked_by_default(self, client, monkeypatch):
        """update_device_property blocked when writes disabled."""
        from lm_mcp.tools.resources import update_device_property

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_device_property(
            client, device_id=100, property_name="location", property_value="US-West"
        )

        assert len(result) == 1
        assert "error" in result[0].text.lower()
        assert "write" in result[0].text.lower()

    @respx.mock
    async def test_update_device_property_succeeds_when_enabled(self, client, monkeypatch):
        """update_device_property works when writes enabled."""
        from lm_mcp.tools.resources import update_device_property

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        respx.put(
            "https://test.logicmonitor.com/santaba/rest/device/devices/100/properties/location"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "location",
                    "value": "US-West",
                    "type": "custom",
                },
            )
        )

        result = await update_device_property(
            client, device_id=100, property_name="location", property_value="US-West"
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["device_id"] == 100
        assert data["property"]["name"] == "location"
        assert data["property"]["value"] == "US-West"
