# Description: Tests for diagnostic source MCP tools.
# Description: Validates diagnostic source read functions against /setting/diagnosticsources.

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
        """get_diagnosticsources reads /setting/diagnosticsources and projects items."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "id": 1,
                            "name": "Disk_Check",
                            "displayName": "Disk Check",
                            "description": "Check disk utilization",
                            "appliesTo": "isLinux()",
                            "group": "Storage",
                            "collectMethod": "script",
                            "tags": ["disk", "storage"],
                            "technicalNotes": "Uses df command",
                        },
                        {
                            "id": 2,
                            "name": "CPU_Check",
                            "displayName": "CPU Check",
                            "description": "Check CPU usage",
                            "group": "Compute",
                            "collectMethod": "script",
                            "tags": ["cpu"],
                        },
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["offset"] == 0
        assert data["has_more"] is False
        assert len(data["diagnosticsources"]) == 2
        names = {s["name"] for s in data["diagnosticsources"]}
        assert names == {"Disk_Check", "CPU_Check"}

    @respx.mock
    async def test_get_diagnosticsources_with_name_filter(self, client):
        """name_filter builds a server-side filter clause."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": 1,
                            "name": "Disk_Check",
                            "displayName": "Disk Check",
                            "group": "Storage",
                        }
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client, name_filter="Disk")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "name~" in filter_param
        assert "Disk" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["name"] == "Disk_Check"

    @respx.mock
    async def test_get_diagnosticsources_with_group_filter(self, client):
        """group_filter builds a server-side filter clause."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "id": 2,
                            "name": "CPU_Check",
                            "group": "Compute",
                        }
                    ],
                },
            )
        )

        result = await get_diagnosticsources(client, group_filter="Compute")

        assert route.called
        filter_param = route.calls.last.request.url.params.get("filter", "")
        assert "group~" in filter_param

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["diagnosticsources"][0]["group"] == "Compute"

    @respx.mock
    async def test_get_diagnosticsources_raw_filter_overrides_typed(self, client):
        """Raw filter parameter overrides typed name/group filters."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(return_value=httpx.Response(200, json={"total": 0, "items": []}))

        await get_diagnosticsources(
            client,
            name_filter="ignored",
            filter='collectMethod:"script"',
        )

        params = route.calls.last.request.url.params
        assert params.get("filter") == 'collectMethod:"script"'

    @respx.mock
    async def test_get_diagnosticsources_pagination_passed_to_api(self, client):
        """limit/offset map to size/offset query params."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources"
        ).mock(return_value=httpx.Response(200, json={"total": 200, "items": []}))

        result = await get_diagnosticsources(client, limit=25, offset=50)

        params = route.calls.last.request.url.params
        assert params.get("size") == "25"
        assert params.get("offset") == "50"

        data = json.loads(result[0].text)
        assert data["offset"] == 50
        assert data["has_more"] is True

    @respx.mock
    async def test_get_diagnosticsources_empty_response(self, client):
        """get_diagnosticsources handles an empty items list."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
            return_value=httpx.Response(200, json={"total": 0, "items": []})
        )

        result = await get_diagnosticsources(client)

        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["count"] == 0
        assert data["diagnosticsources"] == []

    @respx.mock
    async def test_get_diagnosticsources_handles_error(self, client):
        """get_diagnosticsources returns a structured error on API failure."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources").mock(
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

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources/10").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 10,
                    "name": "Disk_Check",
                    "displayName": "Disk Check",
                    "description": "Check disk utilization",
                    "appliesTo": "isLinux()",
                    "group": "Storage",
                    "collectMethod": "script",
                    "collectInterval": 300,
                    "tags": ["disk"],
                    "technicalNotes": "Uses df",
                    "dataPoints": [{"id": 1, "name": "usage", "type": 1, "description": "% used"}],
                },
            )
        )

        result = await get_diagnosticsource(client, source_id=10)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 10
        assert data["name"] == "Disk_Check"
        assert data["display_name"] == "Disk Check"
        assert data["group"] == "Storage"
        assert data["collect_interval"] == 300
        assert len(data["datapoints"]) == 1
        assert data["datapoints"][0]["name"] == "usage"

    @respx.mock
    async def test_get_diagnosticsource_not_found(self, client):
        """get_diagnosticsource returns error for missing source."""
        from lm_mcp.tools.diagnosticsources import get_diagnosticsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/diagnosticsources/999").mock(
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
