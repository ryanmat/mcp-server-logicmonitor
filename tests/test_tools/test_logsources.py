# Description: Tests for LogSource MCP tools.
# Description: Validates get_device_logsources.

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


class TestGetDeviceLogsources:
    """Tests for get_device_logsources tool."""

    @respx.mock
    async def test_get_device_logsources_returns_list(self, client):
        """get_device_logsources returns logsources applied to device."""
        from lm_mcp.tools.logsources import get_device_logsources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/456/devicelogsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1001,
                            "logSourceId": 123,
                            "logSourceName": "LinuxSyslog",
                            "deviceId": 456,
                            "deviceDisplayName": "server01",
                            "status": "active",
                            "lastCollectTime": 1702400000,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_device_logsources(client, device_id=456)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["device_id"] == 456
        assert data["total"] == 1
        assert len(data["logsources"]) == 1
        assert data["logsources"][0]["logsource_name"] == "LinuxSyslog"

    @respx.mock
    async def test_get_device_logsources_handles_error(self, client):
        """get_device_logsources handles error gracefully."""
        from lm_mcp.tools.logsources import get_device_logsources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/999/devicelogsources"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Device not found"}))

        result = await get_device_logsources(client, device_id=999)

        assert is_error_result(result)
