# Description: Tests for service MCP tools.
# Description: Covers list and get operations for service monitoring resources.

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


class TestGetServices:
    @respx.mock
    async def test_get_services_returns_list(self, client):
        from lm_mcp.tools.services import get_services

        respx.get("https://test.logicmonitor.com/santaba/rest/service/services").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "E-Commerce",
                            "description": "E-Commerce service",
                            "groupId": 1,
                            "alertStatus": "none",
                            "alertStatusPriority": 0,
                            "sdtStatus": "none",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_services(client)
        data = json.loads(result[0].text)
        assert data["services"][0]["name"] == "E-Commerce"


class TestGetService:
    @respx.mock
    async def test_get_service_returns_details(self, client):
        from lm_mcp.tools.services import get_service

        respx.get("https://test.logicmonitor.com/santaba/rest/service/services/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "E-Commerce",
                    "description": "E-Commerce service",
                    "groupId": 1,
                    "alertStatus": "none",
                    "alertStatusPriority": 0,
                    "sdtStatus": "none",
                    "individualAlertLevel": "warn",
                },
            )
        )

        result = await get_service(client, service_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "E-Commerce"


class TestGetServiceGroups:
    @respx.mock
    async def test_get_service_groups_returns_list(self, client):
        from lm_mcp.tools.services import get_service_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/service/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production Services",
                            "description": "Production",
                            "parentId": 0,
                            "fullPath": "Production Services",
                            "numOfServices": 5,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_service_groups(client)
        data = json.loads(result[0].text)
        assert data["service_groups"][0]["name"] == "Production Services"
