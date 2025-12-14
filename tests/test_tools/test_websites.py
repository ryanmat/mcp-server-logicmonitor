# Description: Tests for website/synthetic MCP tools.
# Description: Validates get_websites, get_website, get_website_groups, get_website_data.

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


class TestGetWebsites:
    """Tests for get_websites tool."""

    @respx.mock
    async def test_get_websites_returns_list(self, client):
        """get_websites returns properly formatted website list."""
        from lm_mcp.tools.websites import get_websites

        respx.get("https://test.logicmonitor.com/santaba/rest/website/websites").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Main Website",
                            "type": "webcheck",
                            "description": "Main website monitoring",
                            "groupId": 1,
                            "status": "active",
                            "alertStatus": "none",
                            "overallAlertLevel": "none",
                            "pollingInterval": 5,
                            "host": "www.example.com",
                        },
                        {
                            "id": 2,
                            "name": "API Endpoint",
                            "type": "pingcheck",
                            "description": "API health check",
                            "groupId": 1,
                            "status": "active",
                            "alertStatus": "none",
                            "overallAlertLevel": "none",
                            "pollingInterval": 1,
                            "host": "api.example.com",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_websites(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["websites"]) == 2
        assert data["websites"][0]["name"] == "Main Website"
        assert data["websites"][1]["name"] == "API Endpoint"

    @respx.mock
    async def test_get_websites_with_name_filter(self, client):
        """get_websites passes name filter to API."""
        from lm_mcp.tools.websites import get_websites

        route = respx.get("https://test.logicmonitor.com/santaba/rest/website/websites").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_websites(client, name_filter="Main*")

        assert "filter" in route.calls[0].request.url.params

    @respx.mock
    async def test_get_websites_with_group_filter(self, client):
        """get_websites filters by group ID."""
        from lm_mcp.tools.websites import get_websites

        route = respx.get("https://test.logicmonitor.com/santaba/rest/website/websites").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_websites(client, group_id=5)

        assert "filter" in route.calls[0].request.url.params


class TestGetWebsite:
    """Tests for get_website tool."""

    @respx.mock
    async def test_get_website_returns_details(self, client):
        """get_website returns detailed website info."""
        from lm_mcp.tools.websites import get_website

        respx.get("https://test.logicmonitor.com/santaba/rest/website/websites/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "name": "Main Website",
                    "type": "webcheck",
                    "description": "Main website monitoring",
                    "groupId": 1,
                    "status": "active",
                    "alertStatus": "none",
                    "host": "www.example.com",
                    "pollingInterval": 5,
                    "useDefaultAlertSetting": True,
                    "useDefaultLocationSetting": True,
                    "checkpoints": [
                        {"id": 1, "geoInfo": "US - Los Angeles", "smgId": 1},
                        {"id": 2, "geoInfo": "EU - London", "smgId": 2},
                    ],
                    "steps": [
                        {
                            "url": "https://www.example.com",
                            "HTTPMethod": "GET",
                            "statusCode": "200",
                            "timeout": 30,
                        }
                    ],
                },
            )
        )

        result = await get_website(client, website_id=100)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 100
        assert data["name"] == "Main Website"
        assert len(data["checkpoints"]) == 2
        assert len(data["steps"]) == 1

    @respx.mock
    async def test_get_website_not_found(self, client):
        """get_website returns error for missing website."""
        from lm_mcp.tools.websites import get_website

        respx.get("https://test.logicmonitor.com/santaba/rest/website/websites/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Website not found"})
        )

        result = await get_website(client, website_id=999)

        assert "Error:" in result[0].text


class TestGetWebsiteGroups:
    """Tests for get_website_groups tool."""

    @respx.mock
    async def test_get_website_groups_returns_list(self, client):
        """get_website_groups returns group list."""
        from lm_mcp.tools.websites import get_website_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/website/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production",
                            "description": "Production websites",
                            "parentId": 0,
                            "fullPath": "Production",
                            "numOfWebsites": 10,
                            "hasWebsitesDisabled": False,
                        },
                        {
                            "id": 2,
                            "name": "Staging",
                            "description": "Staging websites",
                            "parentId": 0,
                            "fullPath": "Staging",
                            "numOfWebsites": 5,
                            "hasWebsitesDisabled": False,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_website_groups(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["groups"]) == 2
        assert data["groups"][0]["name"] == "Production"

    @respx.mock
    async def test_get_website_groups_with_parent_filter(self, client):
        """get_website_groups filters by parent ID."""
        from lm_mcp.tools.websites import get_website_groups

        route = respx.get("https://test.logicmonitor.com/santaba/rest/website/groups").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_website_groups(client, parent_id=1)

        assert "filter" in route.calls[0].request.url.params


class TestGetWebsiteData:
    """Tests for get_website_data tool."""

    @respx.mock
    async def test_get_website_data_returns_metrics(self, client):
        """get_website_data returns website monitoring data."""
        from lm_mcp.tools.websites import get_website_data

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/website/websites/100/checkpoints/1/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["ResponseTime", "StatusCode"],
                    "values": {
                        "ResponseTime": [150, 145, 160],
                        "StatusCode": [200, 200, 200],
                    },
                    "time": [1702500000, 1702500300, 1702500600],
                },
            )
        )

        result = await get_website_data(client, website_id=100, checkpoint_id=1)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["website_id"] == 100
        assert data["checkpoint_id"] == 1
        assert "ResponseTime" in data["datapoints"]
        assert len(data["time"]) == 3

    @respx.mock
    async def test_get_website_data_with_time_range(self, client):
        """get_website_data passes time range parameters."""
        from lm_mcp.tools.websites import get_website_data

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/website/websites/100/checkpoints/1/data"
        ).mock(return_value=httpx.Response(200, json={"dataPoints": [], "values": {}, "time": []}))

        await get_website_data(
            client,
            website_id=100,
            checkpoint_id=1,
            start_time=1702500000,
            end_time=1702503600,
        )

        params = route.calls[0].request.url.params
        assert "start" in params
        assert "end" in params

    @respx.mock
    async def test_get_website_data_handles_error(self, client):
        """get_website_data handles 404 error gracefully."""
        from lm_mcp.tools.websites import get_website_data

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/website/websites/999/checkpoints/1/data"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Not found"}))

        result = await get_website_data(client, website_id=999, checkpoint_id=1)

        assert "Error:" in result[0].text
