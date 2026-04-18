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


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestCreateEventsource:
    """Tests for create_eventsource tool."""

    async def test_create_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import create_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_eventsource(client, definition={"name": "TestES"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_eventsource_posts_definition(self, client, enable_writes):
        from lm_mcp.tools.eventsources import create_eventsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={"id": 9001, "name": "CustomES", "displayName": "Custom EventSource"},
            )
        )

        result = await create_eventsource(
            client,
            definition={
                "name": "CustomES",
                "alertEffectiveIval": 60,
            },
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["eventsource"]["id"] == 9001

    @respx.mock
    async def test_create_eventsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.eventsources import create_eventsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(200, json={"id": 9002, "name": "ES"}),
        )

        await create_eventsource(client, definition={"id": 999, "name": "ES"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestUpdateEventsource:
    """Tests for update_eventsource tool."""

    async def test_update_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import update_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_eventsource(
            client, eventsource_id=100, definition={"name": "Updated"}
        )
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_eventsource_puts_definition(self, client, enable_writes):
        from lm_mcp.tools.eventsources import update_eventsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/eventsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "UpdatedES", "displayName": "Updated EventSource"},
            )
        )

        result = await update_eventsource(
            client,
            eventsource_id=100,
            definition={"name": "UpdatedES", "displayName": "Updated EventSource"},
            confirm=True,
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["eventsource"]["id"] == 100

    @respx.mock
    async def test_update_eventsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.eventsources import update_eventsource

        route = respx.put(
            "https://test.logicmonitor.com/santaba/rest/setting/eventsources/100"
        ).mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "ES"}),
        )

        await update_eventsource(
            client, eventsource_id=100, definition={"id": 999, "name": "ES"}, confirm=True
        )
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body

    async def test_update_eventsource_without_confirm_errors_with_pointer(
        self, client, enable_writes
    ):
        from lm_mcp.tools.eventsources import update_eventsource

        result = await update_eventsource(
            client, eventsource_id=100, definition={"name": "X"}
        )
        text = result[0].text
        assert "confirm" in text.lower()
        assert "update_logicmodule" in text


class TestDeleteEventsource:
    """Tests for delete_eventsource tool."""

    async def test_delete_eventsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.eventsources import delete_eventsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_eventsource(client, eventsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_eventsource_success(self, client, enable_writes):
        from lm_mcp.tools.eventsources import delete_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "OldES"})
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_eventsource(client, eventsource_id=1)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "OldES" in data["message"]

    @respx.mock
    async def test_delete_eventsource_not_found(self, client, enable_writes):
        from lm_mcp.tools.eventsources import delete_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_eventsource(client, eventsource_id=999)
        assert "Error" in result[0].text
