# Description: Tests for Service Insight MCP tools.
# Description: Covers deviceType 6 services, BizService groups and Service Insights rules.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from tests.list_paging import assert_negative_total_reads_as_more, assert_offset_declared_and_sent


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
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


# The sandbox portal's answer to GET /serviceinsights/rules on 2026-11-12 (Step 70 probe): no
# rules. The endpoint (LogicMonitor v247) is not in the public swagger, so no rule's fields
# have been read; the tool returns rows as the API sends them.
_RULES_EMPTY = {"total": 0, "items": [], "searchId": None, "isMin": False}
_RULES = "https://test.logicmonitor.com/santaba/rest/serviceinsights/rules"


class TestGetServiceInsightsRules:
    """R3.8: Service Insights rules page through /serviceinsights/rules, rows as returned."""

    @respx.mock
    async def test_an_empty_portal_is_an_empty_page(self, client):
        from lm_mcp.tools.services import get_service_insights_rules

        route = respx.get(_RULES).mock(return_value=httpx.Response(200, json=_RULES_EMPTY))

        body = json.loads((await get_service_insights_rules(client, limit=5, offset=5))[0].text)

        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("5", "5")
        assert (body["total"], body["has_more"], body["rules"]) == (0, False, [])

    @respx.mock
    async def test_rows_are_returned_as_the_api_sends_them(self, client):
        from lm_mcp.tools.services import get_service_insights_rules

        # An opaque row, not a portal shape: the test checks the row is passed through.
        row = {"id": 1, "anyField": {"nested": [1, 2]}}
        respx.get(_RULES).mock(return_value=httpx.Response(200, json={"total": 1, "items": [row]}))

        body = json.loads((await get_service_insights_rules(client))[0].text)

        assert body["rules"] == [row]

    @respx.mock
    async def test_offset_is_declared_and_sent(self, client):
        from lm_mcp.tools.services import get_service_insights_rules

        await assert_offset_declared_and_sent(
            client, get_service_insights_rules, "/serviceinsights/rules", {}
        )

    @respx.mock
    async def test_negative_total_reads_as_more(self, client):
        from lm_mcp.tools.services import get_service_insights_rules

        await assert_negative_total_reads_as_more(
            client, get_service_insights_rules, "/serviceinsights/rules", {}
        )
