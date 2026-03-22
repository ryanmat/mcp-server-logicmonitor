# Description: Tests for EventSource MCP tools.
# Description: Validates get/update eventsource functions and registry integration.

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


class TestGetEventsources:
    """Tests for get_eventsources tool."""

    @respx.mock
    async def test_get_eventsources_returns_list(self, client):
        """get_eventsources returns properly formatted list."""
        from lm_mcp.tools.eventsources import get_eventsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "WindowsEventLog",
                            "displayName": "Windows Event Log",
                            "description": "Collects Windows events",
                            "appliesTo": "isWindows()",
                            "technology": "Windows",
                            "group": "Events",
                            "version": 1,
                        },
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_eventsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert len(data["eventsources"]) == 1
        assert data["eventsources"][0]["name"] == "WindowsEventLog"

    @respx.mock
    async def test_get_eventsources_with_name_filter(self, client):
        """get_eventsources applies name filter."""
        from lm_mcp.tools.eventsources import get_eventsources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        await get_eventsources(client, name_filter="Windows")

        params = dict(route.calls[0].request.url.params)
        assert "name~" in params.get("filter", "")


class TestGetEventsource:
    """Tests for get_eventsource tool."""

    @respx.mock
    async def test_get_eventsource_returns_detail(self, client):
        """get_eventsource returns detailed EventSource info."""
        from lm_mcp.tools.eventsources import get_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "WindowsEventLog",
                    "displayName": "Windows Event Log",
                    "description": "Collects Windows events",
                    "appliesTo": "isWindows()",
                    "technology": "Windows",
                    "group": "Events",
                    "version": 1,
                    "tags": "windows,events",
                    "auditVersion": 123,
                    "installDate": "2024-01-15",
                    "filters": [],
                },
            )
        )

        result = await get_eventsource(client, eventsource_id=1)

        data = json.loads(result[0].text)
        assert data["id"] == 1
        assert data["name"] == "WindowsEventLog"
        assert data["display_name"] == "Windows Event Log"


class TestGetDeviceEventsources:
    """Tests for get_device_eventsources tool."""

    @respx.mock
    async def test_get_device_eventsources_returns_list(self, client):
        """get_device_eventsources returns formatted EventSource list."""
        from lm_mcp.tools.eventsources import get_device_eventsources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/9196/deviceeventsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 12345,
                            "eventSourceId": 100,
                            "eventSourceDisplayName": "Azure Advisor Recommendations",
                            "alertDisableStatus": "none",
                            "alertStatus": "warn",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_device_eventsources(client, device_id=9196)
        data = json.loads(result[0].text)
        assert data["device_id"] == 9196
        assert data["total"] == 1
        assert data["eventsources"][0]["name"] == "Azure Advisor Recommendations"


class TestUpdateDeviceEventsource:
    """Tests for update_device_eventsource tool."""

    @respx.mock
    async def test_disable_eventsource_alerting(self, client, monkeypatch):
        """update_device_eventsource sends correct PATCH body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.eventsources import update_device_eventsource

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/9196/deviceeventsources/12345"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 12345,
                    "eventSourceDisplayName": "Azure Advisor Recommendations",
                    "alertDisableStatus": "ad",
                },
            )
        )

        result = await update_device_eventsource(
            client, device_id=9196, device_eventsource_id=12345, disable_alerting=True
        )
        data = json.loads(result[0].text)
        assert data["message"] == "Device EventSource updated successfully"

        # Verify PATCH body
        import json as json_mod

        body = json_mod.loads(route.calls[0].request.content)
        assert body["disableAlerting"] is True

    @respx.mock
    async def test_update_eventsource_no_changes(self, client, monkeypatch):
        """update_device_eventsource returns error when no updates provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token-value")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.eventsources import update_device_eventsource

        result = await update_device_eventsource(
            client, device_id=9196, device_eventsource_id=12345
        )
        assert "Error:" in result[0].text
        assert "No updates provided" in result[0].text
