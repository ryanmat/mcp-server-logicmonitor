# Description: Tests for collector group MCP tools.
# Description: Covers CRUD operations for collector group resources.

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


class TestCreateCollectorGroup:
    """Tests for create_collector_group tool."""

    @respx.mock
    async def test_create_collector_group_blocked_without_write(self, client, monkeypatch):
        """create_collector_group is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.collectors import create_collector_group

        result = await create_collector_group(client, name="New Group")
        assert "Error:" in result[0].text
        assert "disabled" in result[0].text.lower()

    @respx.mock
    async def test_create_collector_group_success(self, client, monkeypatch):
        """create_collector_group creates group with correct body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import create_collector_group

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups"
        ).mock(return_value=httpx.Response(200, json={"id": 10, "name": "Prod Collectors"}))

        result = await create_collector_group(
            client,
            name="Prod Collectors",
            description="Production",
            auto_balance=True,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["group_id"] == 10

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "Prod Collectors"
        assert body["description"] == "Production"
        assert body["autoBalance"] is True

    @respx.mock
    async def test_create_collector_group_with_properties(self, client, monkeypatch):
        """create_collector_group passes custom properties."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import create_collector_group

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups"
        ).mock(return_value=httpx.Response(200, json={"id": 11, "name": "Tagged"}))

        await create_collector_group(
            client, name="Tagged", custom_properties={"region": "us-east-1"}
        )

        body = json.loads(route.calls[0].request.content)
        assert {"name": "region", "value": "us-east-1"} in body["customProperties"]


class TestUpdateCollectorGroup:
    """Tests for update_collector_group tool."""

    @respx.mock
    async def test_update_collector_group_blocked_without_write(self, client, monkeypatch):
        """update_collector_group is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.collectors import update_collector_group

        result = await update_collector_group(client, group_id=1, name="Updated")
        assert "Error:" in result[0].text

    @respx.mock
    async def test_update_collector_group_no_changes(self, client, monkeypatch):
        """update_collector_group returns error when no updates provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import update_collector_group

        result = await update_collector_group(client, group_id=1)
        assert "No updates provided" in result[0].text

    @respx.mock
    async def test_update_collector_group_success(self, client, monkeypatch):
        """update_collector_group sends correct PATCH body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import update_collector_group

        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups/1"
        ).mock(return_value=httpx.Response(200, json={"id": 1, "name": "Renamed Group"}))

        result = await update_collector_group(client, group_id=1, name="Renamed Group")

        data = json.loads(result[0].text)
        assert data["success"] is True

        body = json.loads(route.calls[0].request.content)
        assert body["name"] == "Renamed Group"

    @respx.mock
    async def test_update_collector_group_merges_properties(self, client, monkeypatch):
        """update_collector_group merges custom properties with existing."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import update_collector_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/groups/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "customProperties": [{"name": "region", "value": "us-east-1"}],
                },
            )
        )
        route = respx.patch(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/groups/1"
        ).mock(return_value=httpx.Response(200, json={"id": 1}))

        await update_collector_group(client, group_id=1, custom_properties={"env": "prod"})

        body = json.loads(route.calls[0].request.content)
        props = {p["name"]: p["value"] for p in body["customProperties"]}
        assert props["region"] == "us-east-1"
        assert props["env"] == "prod"


class TestDeleteCollectorGroup:
    """Tests for delete_collector_group tool."""

    @respx.mock
    async def test_delete_collector_group_blocked_without_write(self, client, monkeypatch):
        """delete_collector_group is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.collectors import delete_collector_group

        result = await delete_collector_group(client, group_id=1)
        assert "Error:" in result[0].text

    @respx.mock
    async def test_delete_collector_group_blocked_with_collectors(self, client, monkeypatch):
        """delete_collector_group blocks when collectors are assigned."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import delete_collector_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/groups/1").mock(
            return_value=httpx.Response(
                200, json={"id": 1, "name": "Busy Group", "numOfCollectors": 3}
            )
        )

        result = await delete_collector_group(client, group_id=1)
        assert "3 collectors assigned" in result[0].text
        assert "Move collectors" in result[0].text

    @respx.mock
    async def test_delete_collector_group_success(self, client, monkeypatch):
        """delete_collector_group succeeds when group is empty."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.collectors import delete_collector_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/collector/groups/2").mock(
            return_value=httpx.Response(
                200, json={"id": 2, "name": "Empty Group", "numOfCollectors": 0}
            )
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/collector/groups/2").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_collector_group(client, group_id=2)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "Empty Group" in data["message"]
