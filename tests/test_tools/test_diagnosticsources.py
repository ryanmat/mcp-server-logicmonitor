# Description: Tests for diagnostic source MCP tools.
# Description: Validates diagnostic source read functions and registry integration.

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


class TestGetDiagnosticSources:
    """Tests for get_diagnosticsources tool."""

    @respx.mock
    async def test_get_diagnosticsources_returns_list(self, client):
        """get_diagnosticsources unwraps envelope and returns source list."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Disk Check",
                                "description": "Check disk utilization",
                                "group": "Storage",
                                "tags": ["disk", "storage"],
                                "technicalNotes": "Uses df command",
                            },
                            "2": {
                                "id": 2,
                                "name": "CPU Check",
                                "description": "Check CPU usage",
                                "group": "Compute",
                                "tags": ["cpu"],
                                "technicalNotes": "",
                            },
                        },
                    }
                },
            )
        )

        result = await get_diagnosticsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["diagnosticsources"]) == 2
        assert data["diagnosticsources"][0]["name"] in ["Disk Check", "CPU Check"]

    @respx.mock
    async def test_get_diagnosticsources_with_name_filter(self, client):
        """get_diagnosticsources filters by name client-side."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Disk Check",
                                "description": "Check disk",
                                "group": "Storage",
                            },
                            "2": {
                                "id": 2,
                                "name": "CPU Check",
                                "description": "Check CPU",
                                "group": "Compute",
                            },
                        },
                    }
                },
            )
        )

        result = await get_diagnosticsources(client, name_filter="Disk")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["name"] == "Disk Check"

    @respx.mock
    async def test_get_diagnosticsources_with_group_filter(self, client):
        """get_diagnosticsources filters by group client-side."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [1, 2],
                        "byId": {
                            "1": {
                                "id": 1,
                                "name": "Disk Check",
                                "description": "Check disk",
                                "group": "Storage",
                            },
                            "2": {
                                "id": 2,
                                "name": "CPU Check",
                                "description": "Check CPU",
                                "group": "Compute",
                            },
                        },
                    }
                },
            )
        )

        result = await get_diagnosticsources(client, group_filter="Compute")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["group"] == "Compute"

    @respx.mock
    async def test_get_diagnosticsources_empty_response(self, client):
        """get_diagnosticsources handles empty data envelope."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"allIds": [], "byId": {}}},
            )
        )

        result = await get_diagnosticsources(client)

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["diagnosticsources"] == []

    @respx.mock
    async def test_get_diagnosticsources_handles_error(self, client):
        """get_diagnosticsources returns error on API failure."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources"
        ).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_diagnosticsources(client)

        assert "Error:" in result[0].text


class TestGetDiagnosticSource:
    """Tests for get_diagnosticsource tool."""

    @respx.mock
    async def test_get_diagnosticsource_returns_details(self, client):
        """get_diagnosticsource returns detailed source info."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "allIds": [10],
                        "byId": {
                            "10": {
                                "id": 10,
                                "name": "Disk Check",
                                "description": "Check disk utilization",
                                "group": "Storage",
                                "tags": ["disk"],
                                "technicalNotes": "Uses df",
                                "appliesToScript": "isLinux()",
                                "script": {
                                    "type": "groovy",
                                    "groovyScript": "println 'hello'",
                                },
                            }
                        },
                    }
                },
            )
        )

        result = await get_diagnosticsource(client, source_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Disk Check"
        assert data["group"] == "Storage"
        assert data["script"]["type"] == "groovy"

    @respx.mock
    async def test_get_diagnosticsource_direct_response(self, client):
        """get_diagnosticsource handles direct (non-envelope) response."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources/10"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Disk Check",
                    "description": "Direct response",
                    "group": "Storage",
                },
            )
        )

        result = await get_diagnosticsource(client, source_id=10)

        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Disk Check"

    @respx.mock
    async def test_get_diagnosticsource_not_found(self, client):
        """get_diagnosticsource returns error for missing source."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/exchange/toolbox/exchangeDiagnosticSources/999"
        ).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_diagnosticsource(client, source_id=999)

        assert "Error:" in result[0].text


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
