# Description: Tests for collector MCP tools.
# Description: Validates get_collectors, get_collector functions.

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


class TestGetCollectors:
    """Tests for get_collectors tool."""

    @respx.mock
    async def test_get_collectors_returns_formatted_response(self, client):
        """get_collectors returns properly formatted collector list."""
        from lm_mcp.tools.collectors import get_collectors

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "hostname": "collector01.example.com",
                            "status": 1,
                            "numberOfHosts": 50,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_collectors(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["collectors"][0]["hostname"] == "collector01.example.com"

    @respx.mock
    async def test_get_collectors_with_limit(self, client):
        """get_collectors passes size parameter to API."""
        from lm_mcp.tools.collectors import get_collectors

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collectors(client, limit=10)

        assert route.calls[0].request.url.params.get("size") == "10"


class TestGetCollector:
    """Tests for get_collector tool."""

    @respx.mock
    async def test_get_collector_returns_details(self, client):
        """get_collector returns single collector details."""
        from lm_mcp.tools.collectors import get_collector

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/5").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 5,
                    "hostname": "collector05.example.com",
                    "status": 1,
                    "numberOfHosts": 100,
                    "platform": "linux",
                },
            )
        )

        result = await get_collector(client, collector_id=5)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 5

    @respx.mock
    async def test_get_collector_not_found(self, client):
        """get_collector returns error for missing collector."""
        from lm_mcp.tools.collectors import get_collector

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors/999"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Collector not found"}))

        result = await get_collector(client, collector_id=999)

        assert "Error:" in result[0].text
