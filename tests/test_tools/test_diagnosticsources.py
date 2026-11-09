# Description: Tests for diagnostic source MCP tools.
# Description: Validates diagnostic source tool registration and execute_diagnostic.

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
        max_retries=0,
    )


class TestDiagnosticSourceToolRegistration:
    """Tests for diagnostic source tool registration."""

    def test_get_diagnosticsources_registered(self):
        """get_diagnosticsources is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_diagnosticsources" in tool_names

    def test_get_diagnosticsource_registered(self):
        """get_diagnosticsource is registered in tool registry."""
        from lm_mcp.registry import TOOLS

        tool_names = [t.name for t in TOOLS]
        assert "get_diagnosticsource" in tool_names

    def test_get_diagnosticsources_handler_registered(self):
        """get_diagnosticsources handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_diagnosticsources")
        assert handler is not None

    def test_get_diagnosticsource_handler_registered(self):
        """get_diagnosticsource handler is registered."""
        from lm_mcp.registry import get_tool_handler

        handler = get_tool_handler("get_diagnosticsource")
        assert handler is not None

    def test_get_diagnosticsources_schema_includes_pagination(self):
        """Schema advertises limit/offset/filter for the public REST surface."""
        from lm_mcp.registry import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_diagnosticsources")
        props = tool.inputSchema["properties"]
        for required in ("name_filter", "group_filter", "filter", "limit", "offset"):
            assert required in props

    def test_descriptions_drop_preview_marker(self):
        """[PREVIEW] prefix is gone now that the tools call the public REST endpoint."""
        from lm_mcp.registry import TOOLS

        for name in ("get_diagnosticsources", "get_diagnosticsource"):
            tool = next(t for t in TOOLS if t.name == name)
            assert "[PREVIEW]" not in tool.description


@pytest.fixture
def enable_writes(monkeypatch):
    """Enable write operations for testing."""
    monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
    monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

    from importlib import reload

    import lm_mcp.config

    reload(lm_mcp.config)


BASE_URL = "https://test.logicmonitor.com/santaba/rest"


def _mock_execute_prechecks(host_status="normal", build="39.300"):
    """Stub the shared pre-execution check endpoints for execute_diagnostic."""
    respx.get(f"{BASE_URL}/device/devices/1786").mock(
        return_value=httpx.Response(
            200, json={"id": 1786, "hostStatus": host_status, "preferredCollectorId": 5}
        )
    )
    respx.get(f"{BASE_URL}/setting/collector/collectors/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "build": build})
    )
    respx.get(f"{BASE_URL}/setting/diagnosticsources/12").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 12,
                "name": "Top CPU",
                "appliesTo": "isLinux()",
                "groovyScript": "println 'top cpu'",
            },
        )
    )


class TestExecuteDiagnostic:
    """Tests for execute_diagnostic tool."""

    async def test_execute_diagnostic_requires_write_permission(self, client, monkeypatch):
        """execute_diagnostic is blocked when writes are disabled."""
        from lm_mcp.tools.diagnosticsources import execute_diagnostic

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        result = await execute_diagnostic(client, host_id=1786, diagnostic_source_id=12)

        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_execute_diagnostic_posts_manual_trigger(self, client, enable_writes):
        """execute_diagnostic posts hostId/diagnosticId/triggerType to executemanually."""
        from lm_mcp.tools.diagnosticsources import execute_diagnostic

        _mock_execute_prechecks()
        route = respx.post(f"{BASE_URL}/setting/diagnosticsources/executemanually").mock(
            return_value=httpx.Response(
                200, json={"executionId": "abc-123", "executionStatus": "SCHEDULED"}
            )
        )

        result = await execute_diagnostic(
            client, host_id=1786, diagnostic_source_id=12, alert_id="DS99"
        )

        body = json.loads(route.calls[0].request.content)
        assert body == {
            "hostId": 1786,
            "diagnosticId": 12,
            "triggerType": "manual",
            "alertId": "DS99",
        }
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["execution_response"]["executionId"] == "abc-123"
        assert "get_diagnostic_remediation_results" in data["next_step"]

    @respx.mock
    async def test_execute_diagnostic_blocks_dead_device(self, client, enable_writes):
        """execute_diagnostic refuses to run against a dead device."""
        from lm_mcp.tools.diagnosticsources import execute_diagnostic

        _mock_execute_prechecks(host_status="dead")

        result = await execute_diagnostic(client, host_id=1786, diagnostic_source_id=12)

        assert "is dead (hostStatus=dead)" in result[0].text

    @respx.mock
    async def test_execute_diagnostic_blocks_old_collector(self, client, enable_writes):
        """execute_diagnostic refuses when collector build < 39.200."""
        from lm_mcp.tools.diagnosticsources import execute_diagnostic

        _mock_execute_prechecks(build="36.100")

        result = await execute_diagnostic(client, host_id=1786, diagnostic_source_id=12)

        assert "39.2" in result[0].text
        assert "below" in result[0].text.lower()
