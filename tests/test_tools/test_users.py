# Description: Tests for user and role MCP tools.
# Description: Covers CRUD operations for user accounts and role definitions.

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


class TestCreateUser:
    """Tests for create_user tool."""

    @respx.mock
    async def test_create_user_blocked_without_write(self, client, monkeypatch):
        """create_user is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.users import create_user

        result = await create_user(
            client,
            username="new@example.com",
            email="new@example.com",
            first_name="New",
            last_name="User",
            roles=[1],
        )
        assert "Error:" in result[0].text
        assert "disabled" in result[0].text.lower()

    @respx.mock
    async def test_create_user_success(self, client, monkeypatch):
        """create_user creates a user with correct body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import create_user

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 99,
                    "username": "new@example.com",
                    "email": "new@example.com",
                    "firstName": "New",
                    "lastName": "User",
                },
            )
        )

        result = await create_user(
            client,
            username="new@example.com",
            email="new@example.com",
            first_name="New",
            last_name="User",
            roles=[1, 2],
            phone="555-9999",
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["user_id"] == 99

        body = json.loads(route.calls[0].request.content)
        assert body["username"] == "new@example.com"
        assert body["firstName"] == "New"
        assert body["lastName"] == "User"
        assert body["roles"] == [{"id": 1}, {"id": 2}]
        assert body["phone"] == "555-9999"

    @respx.mock
    async def test_create_user_api_error(self, client, monkeypatch):
        """create_user handles API errors."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import create_user

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/admins").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Internal error"})
        )

        result = await create_user(
            client,
            username="fail@example.com",
            email="fail@example.com",
            first_name="Fail",
            last_name="User",
            roles=[1],
        )
        assert "Error:" in result[0].text


class TestUpdateUser:
    """Tests for update_user tool."""

    @respx.mock
    async def test_update_user_blocked_without_write(self, client, monkeypatch):
        """update_user is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.users import update_user

        result = await update_user(client, user_id=1, email="updated@example.com")
        assert "Error:" in result[0].text

    @respx.mock
    async def test_update_user_no_changes(self, client, monkeypatch):
        """update_user returns error when no updates provided."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import update_user

        result = await update_user(client, user_id=1)
        assert "No updates provided" in result[0].text

    @respx.mock
    async def test_update_user_success(self, client, monkeypatch):
        """update_user sends correct PATCH body."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import update_user

        route = respx.patch("https://test.logicmonitor.com/santaba/rest/setting/admins/1").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "email": "updated@example.com", "firstName": "Updated"},
            )
        )

        result = await update_user(client, user_id=1, email="updated@example.com", roles=[3])

        data = json.loads(result[0].text)
        assert data["success"] is True

        body = json.loads(route.calls[0].request.content)
        assert body["email"] == "updated@example.com"
        assert body["roles"] == [{"id": 3}]


class TestDeleteUser:
    """Tests for delete_user tool."""

    @respx.mock
    async def test_delete_user_blocked_without_write(self, client, monkeypatch):
        """delete_user is blocked when write operations disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp.tools.users import delete_user

        result = await delete_user(client, user_id=1)
        assert "Error:" in result[0].text

    @respx.mock
    async def test_delete_user_success(self, client, monkeypatch):
        """delete_user fetches user info then deletes."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import delete_user

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/5").mock(
            return_value=httpx.Response(200, json={"id": 5, "username": "gone@example.com"})
        )
        respx.delete("https://test.logicmonitor.com/santaba/rest/setting/admins/5").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_user(client, user_id=5)
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "gone@example.com" in data["message"]

    @respx.mock
    async def test_delete_user_not_found(self, client, monkeypatch):
        """delete_user handles 404."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp.tools.users import delete_user

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/admins/999").mock(
            return_value=httpx.Response(404, json={"errorMessage": "User not found"})
        )

        result = await delete_user(client, user_id=999)
        assert "Error:" in result[0].text
