# Description: Tests for user and role MCP tools.
# Description: Covers list and get operations for user accounts and role definitions.

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


class TestGetUsers:
    @respx.mock
    async def test_get_users_returns_list(self, client):
        from lm_mcp.tools.users import get_users

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin@example.com",
                            "email": "admin@example.com",
                            "firstName": "Admin",
                            "lastName": "User",
                            "status": "active",
                            "roles": [{"name": "administrator"}],
                            "twoFAEnabled": True,
                            "apionly": False,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_users(client)
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["users"][0]["username"] == "admin@example.com"


class TestGetUser:
    @respx.mock
    async def test_get_user_returns_details(self, client):
        from lm_mcp.tools.users import get_user

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "username": "admin@example.com",
                    "email": "admin@example.com",
                    "firstName": "Admin",
                    "lastName": "User",
                    "status": "active",
                    "roles": [{"id": 1, "name": "administrator"}],
                    "twoFAEnabled": True,
                    "apionly": False,
                    "phone": "555-1234",
                    "lastLoginOn": 1700000000,
                },
            )
        )

        result = await get_user(client, user_id=1)
        data = json.loads(result[0].text)
        assert data["username"] == "admin@example.com"
        assert data["roles"][0]["name"] == "administrator"


class TestGetRoles:
    @respx.mock
    async def test_get_roles_returns_list(self, client):
        from lm_mcp.tools.users import get_roles

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/roles").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "administrator",
                            "description": "Full access",
                            "requireEULA": False,
                            "twoFARequired": True,
                            "associatedUserCount": 5,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_roles(client)
        data = json.loads(result[0].text)
        assert data["roles"][0]["name"] == "administrator"


class TestGetRole:
    @respx.mock
    async def test_get_role_returns_details(self, client):
        from lm_mcp.tools.users import get_role

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/roles/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "administrator",
                    "description": "Full access",
                    "requireEULA": False,
                    "twoFARequired": True,
                    "privileges": [{"objectType": "dashboard", "operation": "write"}],
                },
            )
        )

        result = await get_role(client, role_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "administrator"
        assert len(data["privileges"]) == 1


class TestGetUsersFilters:
    """Tests for get_users filter parameters."""

    @respx.mock
    async def test_get_users_with_raw_filter(self, client):
        """get_users passes raw filter expression to API."""
        from lm_mcp.tools.users import get_users

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_users(client, filter="username~admin,status:active")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "username~admin,status:active"

    @respx.mock
    async def test_get_users_with_offset(self, client):
        """get_users passes offset for pagination."""
        from lm_mcp.tools.users import get_users

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_users(client, offset=25)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "25"

    @respx.mock
    async def test_get_users_pagination_info(self, client):
        """get_users returns pagination info."""
        from lm_mcp.tools.users import get_users

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "username": "admin"}],
                    "total": 100,
                },
            )
        )

        result = await get_users(client, limit=10, offset=0)

        data = json.loads(result[0].text)
        assert data["total"] == 100
        assert data["has_more"] is True
        assert data["offset"] == 0


class TestGetRolesFilters:
    """Tests for get_roles filter parameters."""

    @respx.mock
    async def test_get_roles_with_raw_filter(self, client):
        """get_roles passes raw filter expression to API."""
        from lm_mcp.tools.users import get_roles

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/roles").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_roles(client, filter="name~admin,twoFARequired:true")

        params = dict(route.calls[0].request.url.params)
        assert params["filter"] == "name~admin,twoFARequired:true"

    @respx.mock
    async def test_get_roles_with_offset(self, client):
        """get_roles passes offset for pagination."""
        from lm_mcp.tools.users import get_roles

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/roles").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_roles(client, offset=10)

        params = dict(route.calls[0].request.url.params)
        assert params["offset"] == "10"
