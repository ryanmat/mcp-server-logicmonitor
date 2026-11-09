# Description: Tests for remediation source MCP tools.
# Description: Validates remediation source tool registration and execute_remediation.

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
        max_retries=0,
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

    def test_execute_remediation_handler_registered(self):
        """execute_remediation handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("execute_remediation")
        assert handler is not None

    def test_get_remediationsources_schema_includes_pagination(self):
        """Schema advertises limit/offset/filter for the public REST surface."""
        from lm_mcp.registry import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_remediationsources")
        props = tool.inputSchema["properties"]
        for required in ("name_filter", "group_filter", "filter", "limit", "offset"):
            assert required in props

    def test_descriptions_drop_preview_marker(self):
        """[PREVIEW] prefix is gone now that the tools call the public REST endpoint."""
        from lm_mcp.registry import TOOLS

        for name in ("get_remediationsources", "get_remediationsource"):
            tool = next(t for t in TOOLS if t.name == name)
            assert "[PREVIEW]" not in tool.description


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

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": "dead", "preferredCollectorId": 10},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        data = result[0].text
        assert "is dead (hostStatus=dead)" in data

    @respx.mock
    async def test_execute_remediation_old_collector_blocked(self, client, enable_writes):
        """execute_remediation blocks when collector version is too old."""
        from lm_mcp.tools.remediationsources import execute_remediation

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": "normal", "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/10"
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

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": "normal", "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/100").mock(
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
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources/executemanually"
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

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": "normal", "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/100").mock(
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
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources/executemanually"
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

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "hostStatus": "normal", "preferredCollectorId": 10},
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"id": 10, "build": "40.100"},
            )
        )
        respx.get("https://test.logicmonitor.com/santaba/rest/setting/remediationsources/100").mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "name": "Test", "groovyScript": "test"},
            )
        )
        respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/remediationsources/executemanually"
        ).mock(
            return_value=httpx.Response(
                500,
                json={"errorMessage": "Internal server error"},
            )
        )

        result = await execute_remediation(client, host_id=1, remediation_source_id=100)
        assert is_error_result(result)
