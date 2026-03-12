# Description: Tests for remediation source MCP tools.
# Description: Validates read, execution, status, and history functions.

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


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


class TestGetRemediationSources:
    """Tests for get_remediationsources tool."""

    @respx.mock
    async def test_get_remediationsources_returns_list(self, client):
        """get_remediationsources unwraps envelope and returns source list."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Restart Service",
                                "description": "Restart a failed service",
                                "group": "Services",
                                "tags": ["restart", "service"],
                                "technicalNotes": "Uses systemctl",
                            },
                            "2": {
                                "id": 2,
                                "name": "Clear Disk",
                                "description": "Clear temp files",
                                "group": "Storage",
                                "tags": ["disk", "cleanup"],
                                "technicalNotes": "",
                            },
                        },
                    }
                },
            )
        )

        result = await get_remediationsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["remediationsources"]) == 2
        assert data["remediationsources"][0]["name"] in [
            "Restart Service",
            "Clear Disk",
        ]

    @respx.mock
    async def test_get_remediationsources_with_name_filter(self, client):
        """get_remediationsources filters by name client-side."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Restart Service",
                                "description": "Restart",
                                "group": "Services",
                            },
                            "2": {
                                "id": 2,
                                "name": "Clear Disk",
                                "description": "Clear",
                                "group": "Storage",
                            },
                        },
                    }
                },
            )
        )

        result = await get_remediationsources(client, name_filter="Restart")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["remediationsources"][0]["name"] == "Restart Service"

    @respx.mock
    async def test_get_remediationsources_with_group_filter(self, client):
        """get_remediationsources filters by group client-side."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Restart Service",
                                "description": "Restart",
                                "group": "Services",
                            },
                            "2": {
                                "id": 2,
                                "name": "Clear Disk",
                                "description": "Clear",
                                "group": "Storage",
                            },
                        },
                    }
                },
            )
        )

        result = await get_remediationsources(client, group_filter="Storage")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["remediationsources"][0]["group"] == "Storage"

    @respx.mock
    async def test_get_remediationsources_empty_response(self, client):
        """get_remediationsources handles empty data envelope."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"allIds": [], "byId": {}}},
            )
        )

        result = await get_remediationsources(client)

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["remediationsources"] == []

    @respx.mock
    async def test_get_remediationsources_handles_error(self, client):
        """get_remediationsources returns error on API failure."""
        from lm_mcp.tools.remediationsources import get_remediationsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources"
        ).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_remediationsources(client)

        assert "Error:" in result[0].text


class TestGetRemediationSource:
    """Tests for get_remediationsource tool."""

    @respx.mock
    async def test_get_remediationsource_returns_details(self, client):
        """get_remediationsource returns detailed source info."""
        from lm_mcp.tools.remediationsources import get_remediationsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [10],
                        "byId": {
                            "10": {
                                "id": 10,
                                "name": "Restart Service",
                                "description": "Restart a systemd service",
                                "group": "Services",
                                "tags": ["restart"],
                                "technicalNotes": "Uses systemctl restart",
                                "appliesToScript": "isLinux()",
                                "script": {
                                    "type": "groovy",
                                    "groovyScript": "println 'restart'",
                                },
                            }
                        },
                    }
                },
            )
        )

        result = await get_remediationsource(client, source_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Restart Service"
        assert data["group"] == "Services"
        assert data["script"]["type"] == "groovy"

    @respx.mock
    async def test_get_remediationsource_direct_response(self, client):
        """get_remediationsource handles direct (non-envelope) response."""
        from lm_mcp.tools.remediationsources import get_remediationsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Restart Service",
                    "description": "Direct response",
                    "group": "Services",
                },
            )
        )

        result = await get_remediationsource(client, source_id=10)

        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Restart Service"

    @respx.mock
    async def test_get_remediationsource_not_found(self, client):
        """get_remediationsource returns error for missing source."""
        from lm_mcp.tools.remediationsources import get_remediationsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeRemediationSources/999"
        ).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_remediationsource(client, source_id=999)

        assert "Error:" in result[0].text


class TestRemediationSourceToolRegistration:
    """Tests for remediation source tool registration."""

    def test_get_remediationsources_registered(self):
        """get_remediationsources is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_remediationsources" in tool_names

    def test_get_remediationsource_registered(self):
        """get_remediationsource is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_remediationsource" in tool_names

    def test_get_remediationsources_handler_registered(self):
        """get_remediationsources handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_remediationsources")
        assert handler is not None

    def test_get_remediationsource_handler_registered(self):
        """get_remediationsource handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_remediationsource")
        assert handler is not None

    def test_execute_remediation_registered(self):
        """execute_remediation is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "execute_remediation" in tool_names

    def test_get_remediation_status_registered(self):
        """get_remediation_status is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_remediation_status" in tool_names

    def test_get_remediation_history_registered(self):
        """get_remediation_history is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_remediation_history" in tool_names

    def test_execute_remediation_handler_registered(self):
        """execute_remediation handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("execute_remediation")
        assert handler is not None

    def test_get_remediation_status_handler_registered(self):
        """get_remediation_status handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_remediation_status")
        assert handler is not None

    def test_get_remediation_history_handler_registered(self):
        """get_remediation_history handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_remediation_history")
        assert handler is not None


class TestExecuteRemediation:
    """Tests for execute_remediation tool."""

    async def test_execute_remediation_requires_write_permission(self, client, monkeypatch):
        """execute_remediation requires write permission."""
        from lm_mcp.tools.remediationsources import execute_remediation

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_execute_remediation_dead_device_blocked(self, client, enable_writes):
        """execute_remediation blocks execution on dead devices."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": 1, "preferredCollectorId": 10},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        data = result[0].text
        assert "dead" in data.lower() or "DEVICE_UNREACHABLE" in data

    @respx.mock
    async def test_execute_remediation_old_collector_blocked(self, client, enable_writes):
        """execute_remediation blocks when collector version is too old."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": 0, "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "35.100"},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        data = result[0].text
        assert "COLLECTOR_VERSION_LOW" in data or "39.200" in data

    @respx.mock
    async def test_execute_remediation_happy_path(self, client, enable_writes):
        """execute_remediation succeeds with valid device and collector."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": 0, "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "RestartApache",
                    "appliesTo": "isLinux()",
                    "groovyScript": "def cmd = 'systemctl restart httpd'.execute()",
                },
            )
        )
        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/executemanually"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"status": "initiated"},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["host_id"] == 1
        assert "restart" in data.get("mutation_warning", "").lower()

    @respx.mock
    async def test_execute_remediation_with_alert_id(self, client, enable_writes):
        """execute_remediation passes alert_id in the request payload."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": 0, "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "CheckDisk",
                    "appliesTo": "true()",
                    "groovyScript": "println 'checking disk'",
                },
            )
        )
        post_route = respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/executemanually"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"status": "initiated"},
            )
        )

        result = await execute_remediation(
            client, host_id=1, remediation_source_id=100, alert_id="LMA12345"
        )
        data = json.loads(result[0].text)
        assert data["alert_id"] == "LMA12345"
        # Verify alert_id was sent in the POST body
        request_body = json.loads(post_route.calls[0].request.content)
        assert request_body["alertId"] == "LMA12345"

    @respx.mock
    async def test_execute_remediation_api_error(self, client, enable_writes):
        """execute_remediation handles API errors gracefully."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": 0, "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "Test", "groovyScript": "test"},
            )
        )
        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/executemanually"
        ).mock(
            return_value=httpx.Response(
                500,
                json={"errorMessage": "Internal server error"},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        assert "Error:" in result[0].text


class TestGetRemediationStatus:
    """Tests for get_remediation_status tool."""

    @respx.mock
    async def test_get_remediation_status_returns_info(self, client):
        """get_remediation_status returns device and source info."""
        from lm_mcp.tools.remediationsources import get_remediation_status

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/100"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "RestartApache", "group": "Linux"},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "displayName": "prod-web-01", "hostStatus": 0},
            )
        )

        result = await get_remediation_status(
            client, host_id=1, remediation_source_id=100
        )
        data = json.loads(result[0].text)
        assert data["host_id"] == 1
        assert data["source_name"] == "RestartApache"
        assert data["device_name"] == "prod-web-01"

    @respx.mock
    async def test_get_remediation_status_not_found(self, client):
        """get_remediation_status handles missing source gracefully."""
        from lm_mcp.tools.remediationsources import get_remediation_status

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/setting/remediationsources/999"
        ).mock(
            return_value=httpx.Response(
                404,
                json={"errorMessage": "Not found"},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/1"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "displayName": "prod-web-01", "hostStatus": 0},
            )
        )

        result = await get_remediation_status(
            client, host_id=1, remediation_source_id=999
        )
        data = json.loads(result[0].text)
        assert data["source_name"] == "unknown"


class TestGetRemediationHistory:
    """Tests for get_remediation_history tool."""

    @respx.mock
    async def test_get_remediation_history_returns_entries(self, client):
        """get_remediation_history returns filtered audit entries."""
        from lm_mcp.tools.remediationsources import get_remediation_history

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/accesslogs"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "happenedOn": 1710288000,
                            "username": "admin",
                            "description": (
                                "Remediation source 100 executed on host 1"
                            ),
                            "ip": "10.0.1.1",
                        },
                        {
                            "happenedOn": 1710287000,
                            "username": "admin",
                            "description": "Device updated",
                            "ip": "10.0.1.1",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_remediation_history(client, host_id=1)
        data = json.loads(result[0].text)
        assert data["total_entries"] == 1  # Only the remediation entry
        assert data["truncated"] is False

    @respx.mock
    async def test_get_remediation_history_empty(self, client):
        """get_remediation_history handles no entries gracefully."""
        from lm_mcp.tools.remediationsources import get_remediation_history

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/accesslogs"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        result = await get_remediation_history(client, host_id=1)
        data = json.loads(result[0].text)
        assert data["total_entries"] == 0
        assert "note" in data

    @respx.mock
    async def test_get_remediation_history_with_source_filter(self, client):
        """get_remediation_history filters by remediation_source_id."""
        from lm_mcp.tools.remediationsources import get_remediation_history

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/accesslogs"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "happenedOn": 1710288000,
                            "username": "admin",
                            "description": "Remediation source 100 executed",
                            "ip": "10.0.1.1",
                        },
                        {
                            "happenedOn": 1710287000,
                            "username": "admin",
                            "description": "Remediation source 200 executed",
                            "ip": "10.0.1.1",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_remediation_history(
            client, host_id=1, remediation_source_id=100
        )
        data = json.loads(result[0].text)
        assert data["total_entries"] == 1
        assert "100" in data["entries"][0]["description"]
