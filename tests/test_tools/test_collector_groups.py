# Description: Tests for collector group MCP tools.
# Description: Covers list and get operations for collector group resources.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        api_version=3,
    )


class TestGetCollectorGroups:
    @respx.mock
    async def test_get_collector_groups_returns_list(self, client):
        from lm_mcp.tools.collectors import get_collector_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "US-East Collectors",
                            "description": "East coast",
                            "numOfCollectors": 5,
                            "autoBalance": True,
                            "autoBalanceStrategy": "roundRobin",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_collector_groups(client)
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["collector_groups"][0]["name"] == "US-East Collectors"

    @respx.mock
    async def test_get_collector_groups_with_filter(self, client):
        from lm_mcp.tools.collectors import get_collector_groups

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_collector_groups(client, name_filter="US*")
        assert "filter" in route.calls[0].request.url.params


class TestGetCollectorGroup:
    @respx.mock
    async def test_get_collector_group_returns_details(self, client):
        from lm_mcp.tools.collectors import get_collector_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/groups/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "US-East Collectors",
                    "description": "East coast",
                    "numOfCollectors": 5,
                    "autoBalance": True,
                    "autoBalanceStrategy": "roundRobin",
                    "autoBalanceInstanceCountThreshold": 10000,
                    "customProperties": [{"name": "region", "value": "us-east-1"}],
                },
            )
        )

        result = await get_collector_group(client, group_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "US-East Collectors"
        assert len(data["custom_properties"]) == 1
