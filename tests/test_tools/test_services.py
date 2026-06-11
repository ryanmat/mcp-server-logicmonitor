# Description: Tests for Service Insight MCP tools.
# Description: Covers deviceType 6 service listing, detail, and BizService groups.

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


def _service_item(**overrides) -> dict:
    item = {
        "id": 1966,
        "displayName": "frontend-web",
        "name": "frontend-web",
        "description": "Storefront service",
        "hostGroupIds": "238",
        "alertStatus": "none",
        "alertStatusPriority": 100000,
        "sdtStatus": "none-none-none",
        "alertDisableStatus": "none-none-none",
        "hostStatus": "normal",
        "deviceType": 6,
    }
    item.update(overrides)
    return item


class TestGetServices:
    @respx.mock
    async def test_get_services_returns_list(self, client):
        from lm_mcp.tools.services import get_services

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={"items": [_service_item()], "total": 1},
            )
        )

        result = await get_services(client)
        data = json.loads(result[0].text)
        assert data["services"][0]["name"] == "frontend-web"
        assert data["services"][0]["alert_status"] == "none"
        assert data["services"][0]["host_status"] == "normal"
        assert data["total"] == 1
        # Services are deviceType 6 devices, never the legacy /service/services path
        assert route.calls[0].request.url.params["filter"] == "deviceType:6"

    @respx.mock
    async def test_get_services_name_filter(self, client):
        from lm_mcp.tools.services import get_services

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_services(client, name_filter="frontend")
        sent_filter = route.calls[0].request.url.params["filter"]
        assert sent_filter.startswith("deviceType:6,")
        assert 'displayName~"frontend"' in sent_filter


class TestGetService:
    @respx.mock
    async def test_get_service_returns_details(self, client):
        from lm_mcp.tools.services import get_service

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/1966").mock(
            return_value=httpx.Response(200, json=_service_item())
        )

        result = await get_service(client, service_id=1966)
        data = json.loads(result[0].text)
        assert data["name"] == "frontend-web"
        assert data["device_type"] == 6
        assert "note" not in data

    @respx.mock
    async def test_get_service_flags_non_service_device(self, client):
        from lm_mcp.tools.services import get_service

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/42").mock(
            return_value=httpx.Response(
                200, json=_service_item(id=42, displayName="plain-host", deviceType=0)
            )
        )

        result = await get_service(client, service_id=42)
        data = json.loads(result[0].text)
        assert data["device_type"] == 0
        assert "not a Service Insight service" in data["note"]


class TestGetServiceGroups:
    @respx.mock
    async def test_get_service_groups_returns_list(self, client):
        from lm_mcp.tools.services import get_service_groups

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 238,
                            "name": "petclinic-demo",
                            "description": "Demo services",
                            "parentId": 1,
                            "fullPath": "petclinic-demo",
                            "numOfHosts": 25,
                            "groupType": "BizService",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_service_groups(client)
        data = json.loads(result[0].text)
        assert data["service_groups"][0]["name"] == "petclinic-demo"
        assert data["service_groups"][0]["num_of_services"] == 25
        assert route.calls[0].request.url.params["filter"] == 'groupType:"BizService"'

    @respx.mock
    async def test_get_service_groups_name_filter(self, client):
        from lm_mcp.tools.services import get_service_groups

        route = respx.get("https://test.logicmonitor.com/santaba/rest/device/groups").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_service_groups(client, name_filter="petclinic")
        sent_filter = route.calls[0].request.url.params["filter"]
        assert sent_filter.startswith('groupType:"BizService",')
        assert 'name~"petclinic"' in sent_filter
