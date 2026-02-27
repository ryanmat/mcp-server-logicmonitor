# Description: Tests for remediation source MCP tools.
# Description: Validates remediation source read functions and registry integration.

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
