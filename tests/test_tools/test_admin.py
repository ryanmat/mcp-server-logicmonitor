# Description: Tests for admin MCP tools (Dashboard Groups, API Tokens, Access Groups, OIDs).
# Description: Covers CRUD operations and error handling for administrative resources.

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result


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


class TestDashboardGroups:
    @respx.mock
    async def test_get_dashboard_groups_returns_list(self, client):
        from lm_mcp.tools.dashboard_groups import get_dashboard_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/groups").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production",
                            "description": "Production dashboards",
                            "parentId": 0,
                            "fullPath": "Production",
                            "numOfDashboards": 10,
                            "numOfDirectDashboards": 5,
                            "numOfDirectSubGroups": 2,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_dashboard_groups(client)
        data = json.loads(result[0].text)
        assert data["dashboard_groups"][0]["name"] == "Production"

    @respx.mock
    async def test_get_dashboard_group_returns_details(self, client):
        from lm_mcp.tools.dashboard_groups import get_dashboard_group

        respx.get("https://test.logicmonitor.com/santaba/rest/dashboard/groups/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Production",
                    "description": "Production dashboards",
                    "parentId": 0,
                    "fullPath": "Production",
                    "numOfDashboards": 10,
                    "widgetTokens": [{"name": "token1", "value": "value1"}],
                },
            )
        )

        result = await get_dashboard_group(client, group_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "Production"


# One token as a live portal returns it: roles are role names with no id, accessKey is masked,
# createdOn is in epoch seconds, and a token never used has lastUsedOn 0.
LIVE_API_TOKEN = {
    "id": 100,
    "accessId": "a1b2c3d4e5f6g7h8i9j0",
    "accessKey": "*****",
    "adminId": 1,
    "adminName": "admin",
    "createdBy": "admin",
    "createdOn": 1700000000,
    "lastAuthIp": "",
    "lastUsedOn": 0,
    "note": "CI/CD token",
    "roles": ["manager", "lm_logs_administrator"],
    "status": 2,
    "userPermission": "write",
}

LIVE_API_TOKEN_OUTPUT = {
    "id": 100,
    "admin_id": 1,
    "admin_name": "admin",
    "note": "CI/CD token",
    "status": 2,
    "created_on": 1700000000,
    "last_used_on": 0,
    "roles": ["manager", "lm_logs_administrator"],
}

API_TOKENS_URL = "https://test.logicmonitor.com/santaba/rest/setting/admins/apitokens"


class TestApiTokens:
    @respx.mock
    async def test_get_api_tokens_returns_live_shape(self, client):
        """R5: a token's roles are returned as the role names the API sends."""
        from lm_mcp.tools.api_tokens import get_api_tokens

        respx.get(API_TOKENS_URL).mock(
            return_value=httpx.Response(200, json={"items": [LIVE_API_TOKEN], "total": 1})
        )

        result = await get_api_tokens(client)
        data = json.loads(result[0].text)
        assert data["api_tokens"] == [LIVE_API_TOKEN_OUTPUT]

    @respx.mock
    async def test_get_api_token_returns_live_shape_for_admin(self, client):
        """R5: the per-admin read returns the same role names as the list."""
        from lm_mcp.tools.api_tokens import get_api_token

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/1/apitokens/100").mock(
            return_value=httpx.Response(200, json=LIVE_API_TOKEN)
        )

        result = await get_api_token(client, admin_id=1, token_id=100)
        assert json.loads(result[0].text) == LIVE_API_TOKEN_OUTPUT

    @respx.mock
    async def test_get_api_token_returns_live_shape_by_id(self, client):
        """R5: the portal-wide read by id returns the same role names as the list."""
        from lm_mcp.tools.api_tokens import get_api_token

        respx.get(API_TOKENS_URL).mock(
            return_value=httpx.Response(200, json={"items": [LIVE_API_TOKEN], "total": 1})
        )

        result = await get_api_token(client, token_id=100)
        assert json.loads(result[0].text) == LIVE_API_TOKEN_OUTPUT

    @respx.mock
    async def test_tools_return_live_shape_through_execute_tool(self, monkeypatch, client):
        """R5: both registered tools return token data, not an error, through the dispatcher."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        respx.get(API_TOKENS_URL).mock(
            return_value=httpx.Response(200, json={"items": [LIVE_API_TOKEN], "total": 1})
        )

        with patch("lm_mcp.server.get_client", return_value=client):
            from lm_mcp.server import execute_tool

            listed = await execute_tool("get_api_tokens", {"limit": 25})
            fetched = await execute_tool("get_api_token", {"token_id": 100})

        assert not is_error_result(listed)
        assert not is_error_result(fetched)
        assert json.loads(listed[0].text)["api_tokens"] == [LIVE_API_TOKEN_OUTPUT]
        assert json.loads(fetched[0].text) == LIVE_API_TOKEN_OUTPUT

    @respx.mock
    async def test_get_api_tokens_returns_list(self, client):
        from lm_mcp.tools.api_tokens import get_api_tokens

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/1/apitokens").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 100,
                            "adminId": 1,
                            "adminName": "admin",
                            "note": "CI/CD token",
                            "status": 2,
                            "createdOn": 1700000000,
                            "lastUsedOn": 1700100000,
                            "roles": ["administrator"],
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_api_tokens(client, admin_id=1)
        data = json.loads(result[0].text)
        assert data["api_tokens"][0]["note"] == "CI/CD token"
        assert data["api_tokens"][0]["roles"] == ["administrator"]

    @respx.mock
    async def test_get_api_token_returns_details(self, client):
        from lm_mcp.tools.api_tokens import get_api_token

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/1/apitokens/100").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 100,
                    "adminId": 1,
                    "adminName": "admin",
                    "note": "CI/CD token",
                    "status": 2,
                    "roles": ["administrator"],
                },
            )
        )

        result = await get_api_token(client, admin_id=1, token_id=100)
        data = json.loads(result[0].text)
        assert data["note"] == "CI/CD token"
        assert data["roles"] == ["administrator"]

    @respx.mock
    async def test_get_api_tokens_without_admin_lists_portal_wide(self, client):
        """admin_id is optional; omitted, tokens are listed across the portal."""
        from lm_mcp.tools.api_tokens import get_api_tokens

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/admins/apitokens"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 100,
                            "adminId": 1,
                            "adminName": "admin",
                            "note": "CI/CD token",
                            "status": 2,
                            "roles": ["administrator"],
                        },
                        {
                            "id": 101,
                            "adminId": 7,
                            "adminName": "svc-backup",
                            "note": "backup job",
                            "status": 2,
                            "roles": ["manager"],
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_api_tokens(client, limit=25)
        data = json.loads(result[0].text)
        assert route.called
        assert route.calls.last.request.url.params["size"] == "25"
        assert [t["admin_id"] for t in data["api_tokens"]] == [1, 7]
        assert [t["roles"] for t in data["api_tokens"]] == [["administrator"], ["manager"]]
        assert data["total"] == 2

    @respx.mock
    async def test_get_api_token_without_admin_fetches_by_id(self, client):
        """Omitted admin_id, the token is fetched by id through the portal-wide filter."""
        from lm_mcp.tools.api_tokens import get_api_token

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/admins/apitokens"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 100,
                            "adminId": 1,
                            "adminName": "admin",
                            "note": "CI/CD token",
                            "status": 2,
                            "roles": ["administrator"],
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_api_token(client, token_id=100)
        data = json.loads(result[0].text)
        assert route.calls.last.request.url.params["filter"] == "id:100"
        assert data["id"] == 100
        assert data["admin_id"] == 1
        assert data["roles"] == ["administrator"]

    @respx.mock
    async def test_get_api_token_without_admin_reports_missing_id(self, client):
        """An id the portal-wide filter does not match is a not-found error, not empty data."""
        from lm_mcp.tools.api_tokens import get_api_token

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/apitokens").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_api_token(client, token_id=999)
        assert result[0].text.startswith("Error: API token 999 not found")


class TestAccessGroups:
    @respx.mock
    async def test_get_access_groups_returns_list(self, client):
        from lm_mcp.tools.access_groups import get_access_groups

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accessgroup").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "US Operations",
                            "description": "US team access",
                            "tenantId": 0,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_access_groups(client)
        data = json.loads(result[0].text)
        assert data["access_groups"][0]["name"] == "US Operations"

    @respx.mock
    async def test_get_access_group_returns_details(self, client):
        from lm_mcp.tools.access_groups import get_access_group

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accessgroup/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "US Operations",
                    "description": "US team access",
                    "tenantId": 0,
                },
            )
        )

        result = await get_access_group(client, group_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "US Operations"


class TestOids:
    @respx.mock
    async def test_get_oids_returns_list(self, client):
        from lm_mcp.tools.oids import get_oids

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/oids").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "oid": "1.3.6.1.2.1.1.1",
                            "name": "sysDescr",
                            "category": "System",
                            "description": "System description",
                            "datapointType": "string",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_oids(client)
        data = json.loads(result[0].text)
        assert data["oids"][0]["name"] == "sysDescr"

    @respx.mock
    async def test_get_oid_returns_details(self, client):
        from lm_mcp.tools.oids import get_oid

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/oids/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "oid": "1.3.6.1.2.1.1.1",
                    "name": "sysDescr",
                    "category": "System",
                    "description": "System description",
                    "datapointType": "string",
                    "datapointDescription": "A textual description of the entity",
                },
            )
        )

        result = await get_oid(client, oid_id=1)
        data = json.loads(result[0].text)
        assert data["oid"] == "1.3.6.1.2.1.1.1"
