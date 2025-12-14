# Description: Tests for Audit log MCP tools.
# Description: Validates audit log access functions.

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


class TestGetAuditLogs:
    """Tests for get_audit_logs tool."""

    @respx.mock
    async def test_get_audit_logs_returns_list(self, client):
        """get_audit_logs returns properly formatted list."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "ip": "192.168.1.1",
                            "happenedOn": "login",
                            "description": "User logged in successfully",
                            "happenedOnLocal": 1702400000,
                            "sessionId": "abc123",
                        },
                        {
                            "id": 2,
                            "username": "admin",
                            "ip": "192.168.1.1",
                            "happenedOn": "update",
                            "description": "Updated device server01",
                            "happenedOnLocal": 1702400100,
                            "sessionId": "abc123",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_audit_logs(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["audit_logs"]) == 2
        assert data["audit_logs"][0]["username"] == "admin"

    @respx.mock
    async def test_get_audit_logs_with_username_filter(self, client):
        """get_audit_logs filters by username."""
        from lm_mcp.tools.audit import get_audit_logs

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_audit_logs(client, username="admin")

        assert "filter" in route.calls[0].request.url.params
        assert "username:admin" in route.calls[0].request.url.params.get("filter", "")

    @respx.mock
    async def test_get_audit_logs_pagination(self, client):
        """get_audit_logs supports pagination."""
        from lm_mcp.tools.audit import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": 1, "username": "admin"}],
                    "total": 100,
                },
            )
        )

        result = await get_audit_logs(client, limit=10, offset=0)

        data = json.loads(result[0].text)
        assert data["has_more"] is True
        assert data["offset"] == 0


class TestGetLoginAudit:
    """Tests for get_login_audit tool."""

    @respx.mock
    async def test_get_login_audit_returns_logins(self, client):
        """get_login_audit returns login events."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "ip": "192.168.1.1",
                            "happenedOn": "login",
                            "description": "User logged in successfully",
                            "happenedOnLocal": 1702400000,
                        },
                        {
                            "id": 2,
                            "username": "baduser",
                            "ip": "10.0.0.1",
                            "happenedOn": "login",
                            "description": "Login failed - invalid password",
                            "happenedOnLocal": 1702400100,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_login_audit(client)

        data = json.loads(result[0].text)
        assert len(data["login_logs"]) == 2
        assert data["login_logs"][0]["status"] == "success"
        assert data["login_logs"][1]["status"] == "failed"

    @respx.mock
    async def test_get_login_audit_failed_only(self, client):
        """get_login_audit can filter to failed logins."""
        from lm_mcp.tools.audit import get_login_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "description": "User logged in successfully",
                            "happenedOn": "login",
                        },
                        {
                            "id": 2,
                            "username": "baduser",
                            "description": "Login failed",
                            "happenedOn": "login",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_login_audit(client, failed_only=True)

        data = json.loads(result[0].text)
        assert len(data["login_logs"]) == 1
        assert data["login_logs"][0]["username"] == "baduser"


class TestGetChangeAudit:
    """Tests for get_change_audit tool."""

    @respx.mock
    async def test_get_change_audit_returns_changes(self, client):
        """get_change_audit returns configuration changes."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "username": "admin",
                            "happenedOn": "create",
                            "description": "Created device server01",
                            "happenedOnLocal": 1702400000,
                            "ip": "192.168.1.1",
                        },
                        {
                            "id": 2,
                            "username": "admin",
                            "happenedOn": "delete",
                            "description": "Deleted dashboard test",
                            "happenedOnLocal": 1702400100,
                            "ip": "192.168.1.1",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_change_audit(client)

        data = json.loads(result[0].text)
        assert len(data["change_logs"]) == 2
        assert data["change_logs"][0]["action"] == "create"
        assert data["change_logs"][1]["action"] == "delete"
