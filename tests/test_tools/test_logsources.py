# Description: Tests for LogSource MCP tools.
# Description: Validates get_logsources, get_logsource, get_device_logsources.

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


class TestGetLogsources:
    """Tests for get_logsources tool."""

    @respx.mock
    async def test_get_logsources_returns_list(self, client):
        """get_logsources returns properly formatted list."""
        from lm_mcp.tools.logsources import get_logsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "LinuxSyslog",
                            "description": "Linux syslog collection",
                            "appliesTo": "isLinux()",
                            "group": "Linux",
                            "logType": "syslog",
                            "collectMethod": "file",
                            "version": 1,
                        },
                        {
                            "id": 2,
                            "name": "WindowsEventLog",
                            "description": "Windows event log collection",
                            "appliesTo": "isWindows()",
                            "group": "Windows",
                            "logType": "eventlog",
                            "collectMethod": "wmi",
                            "version": 2,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_logsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["logsources"]) == 2
        assert data["logsources"][0]["name"] == "LinuxSyslog"
        assert data["logsources"][1]["name"] == "WindowsEventLog"

    @respx.mock
    async def test_get_logsources_with_name_filter(self, client):
        """get_logsources passes name filter to API."""
        from lm_mcp.tools.logsources import get_logsources

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_logsources(client, name_filter="Linux*")

        assert "filter" in route.calls[0].request.url.params
        # Wildcards are stripped by sanitize_filter_value
        assert 'name~"Linux"' in route.calls[0].request.url.params.get("filter", "")

    @respx.mock
    async def test_get_logsources_handles_error(self, client):
        """get_logsources returns error response on API failure."""
        from lm_mcp.tools.logsources import get_logsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(401, json={"errorMessage": "Unauthorized"})
        )

        result = await get_logsources(client)

        assert len(result) == 1
        assert "Error:" in result[0].text


class TestGetLogsource:
    """Tests for get_logsource tool."""

    @respx.mock
    async def test_get_logsource_returns_details(self, client):
        """get_logsource returns single logsource details."""
        from lm_mcp.tools.logsources import get_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "name": "LinuxSyslog",
                    "description": "Linux syslog collection",
                    "appliesTo": "isLinux()",
                    "group": "Linux",
                    "logType": "syslog",
                    "collectMethod": "file",
                    "version": 1,
                    "logFilePath": "/var/log/syslog",
                    "logFileFormat": "auto",
                    "filters": [],
                },
            )
        )

        result = await get_logsource(client, logsource_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123
        assert data["name"] == "LinuxSyslog"
        assert data["log_file_path"] == "/var/log/syslog"

    @respx.mock
    async def test_get_logsource_not_found(self, client):
        """get_logsource returns error for missing logsource."""
        from lm_mcp.tools.logsources import get_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "LogSource not found"})
        )

        result = await get_logsource(client, logsource_id=999)

        assert "Error:" in result[0].text


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

        assert "Error:" in result[0].text


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestCreateLogsource:
    """Tests for create_logsource tool."""

    async def test_create_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import create_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await create_logsource(client, definition={"name": "TestLS"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_logsource_posts_definition(self, client, enable_writes):
        from lm_mcp.tools.logsources import create_logsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"id": 10001, "name": "CustomLS"})
        )

        result = await create_logsource(
            client, definition={"name": "CustomLS", "collectionMethod": "script"}
        )

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["logsource"]["id"] == 10001

    @respx.mock
    async def test_create_logsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.logsources import create_logsource

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/logsources").mock(
            return_value=httpx.Response(200, json={"id": 10002, "name": "LS"}),
        )

        await create_logsource(client, definition={"id": 999, "name": "LS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestUpdateLogsource:
    """Tests for update_logsource tool."""

    async def test_update_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import update_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await update_logsource(client, logsource_id=100, definition={"name": "Updated"})
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_update_logsource_puts_definition(self, client, enable_writes):
        from lm_mcp.tools.logsources import update_logsource

        route = respx.put("https://test.logicmonitor.com/santaba/rest/setting/logsources/100").mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "UpdatedLS"})
        )

        result = await update_logsource(client, logsource_id=100, definition={"name": "UpdatedLS"})

        assert route.called
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["logsource"]["id"] == 100

    @respx.mock
    async def test_update_logsource_strips_id(self, client, enable_writes):
        from lm_mcp.tools.logsources import update_logsource

        route = respx.put("https://test.logicmonitor.com/santaba/rest/setting/logsources/100").mock(
            return_value=httpx.Response(200, json={"id": 100, "name": "LS"}),
        )

        await update_logsource(client, logsource_id=100, definition={"id": 999, "name": "LS"})
        request_body = json.loads(route.calls[0].request.content)
        assert "id" not in request_body


class TestDeleteLogsource:
    """Tests for delete_logsource tool."""

    async def test_delete_logsource_requires_write_permission(self, client, monkeypatch):
        from lm_mcp.tools.logsources import delete_logsource

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await delete_logsource(client, logsource_id=1)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_logsource_success(self, client, enable_writes):
        from lm_mcp.tools.logsources import delete_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/1").mock(
            return_value=httpx.Response(200, json={"id": 1, "name": "OldLS"})
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/logsources/1").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_logsource(client, logsource_id=1)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "OldLS" in data["message"]

    @respx.mock
    async def test_delete_logsource_not_found(self, client, enable_writes):
        from lm_mcp.tools.logsources import delete_logsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/logsources/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await delete_logsource(client, logsource_id=999)
        assert "Error" in result[0].text
