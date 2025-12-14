# Description: Tests for ops notes and audit log MCP tools.
# Description: Validates audit log and ops note query/creation functions.

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
        """get_audit_logs returns properly formatted log list."""
        from lm_mcp.tools.ops import get_audit_logs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "log1",
                            "username": "admin@company.com",
                            "description": "User logged in",
                            "happenedOn": 1700000000000,
                            "happenedOnLocal": "2023-11-14 10:00:00",
                            "ip": "192.168.1.100",
                            "sessionId": "sess123",
                        },
                        {
                            "id": "log2",
                            "username": "user@company.com",
                            "description": "Created device",
                            "happenedOn": 1700000100000,
                            "happenedOnLocal": "2023-11-14 10:01:40",
                            "ip": "192.168.1.101",
                            "sessionId": "sess456",
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
        assert data["audit_logs"][0]["username"] == "admin@company.com"
        assert data["audit_logs"][1]["description"] == "Created device"

    @respx.mock
    async def test_get_audit_logs_with_username_filter(self, client):
        """get_audit_logs passes username filter to API."""
        from lm_mcp.tools.ops import get_audit_logs

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_audit_logs(client, username_filter="admin*")

        assert "filter" in route.calls[0].request.url.params
        assert "username~admin*" in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_get_audit_logs_with_keyword_filter(self, client):
        """get_audit_logs passes keyword filter to API."""
        from lm_mcp.tools.ops import get_audit_logs

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_audit_logs(client, keyword_filter="login")

        assert "filter" in route.calls[0].request.url.params
        assert "_all~*login*" in route.calls[0].request.url.params["filter"]


class TestGetOpsNotes:
    """Tests for get_ops_notes tool."""

    @respx.mock
    async def test_get_ops_notes_returns_list(self, client):
        """get_ops_notes returns properly formatted notes list."""
        from lm_mcp.tools.ops import get_ops_notes

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/opsnotes").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "note1",
                            "note": "Scheduled maintenance",
                            "tags": [{"name": "maintenance"}],
                            "happenedOnInSec": 1700000000,
                            "createdBy": "admin",
                            "scopes": [],
                        },
                        {
                            "id": "note2",
                            "note": "Network upgrade",
                            "tags": [{"name": "upgrade"}, {"name": "network"}],
                            "happenedOnInSec": 1700000100,
                            "createdBy": "netadmin",
                            "scopes": [{"type": "device", "deviceId": 100}],
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_ops_notes(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["ops_notes"]) == 2
        assert data["ops_notes"][0]["note"] == "Scheduled maintenance"
        assert data["ops_notes"][1]["created_by"] == "netadmin"

    @respx.mock
    async def test_get_ops_notes_with_tag_filter(self, client):
        """get_ops_notes passes tag filter to API."""
        from lm_mcp.tools.ops import get_ops_notes

        route = respx.get("https://test.logicmonitor.com/santaba/rest/setting/opsnotes").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_ops_notes(client, tag_filter="maintenance*")

        assert "filter" in route.calls[0].request.url.params
        assert "tags~maintenance*" in route.calls[0].request.url.params["filter"]


class TestGetOpsNote:
    """Tests for get_ops_note tool."""

    @respx.mock
    async def test_get_ops_note_returns_details(self, client):
        """get_ops_note returns detailed note info."""
        from lm_mcp.tools.ops import get_ops_note

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/opsnotes/note123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "note123",
                    "note": "Scheduled maintenance window",
                    "tags": [{"name": "maintenance"}, {"name": "planned"}],
                    "happenedOnInSec": 1700000000,
                    "createdBy": "admin",
                    "scopes": [
                        {"type": "device", "deviceId": 100, "groupId": None},
                        {"type": "deviceGroup", "deviceId": None, "groupId": 50},
                    ],
                },
            )
        )

        result = await get_ops_note(client, note_id="note123")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == "note123"
        assert data["note"] == "Scheduled maintenance window"
        assert len(data["scopes"]) == 2
        assert data["scopes"][0]["device_id"] == 100
        assert data["scopes"][1]["group_id"] == 50

    @respx.mock
    async def test_get_ops_note_not_found(self, client):
        """get_ops_note returns error for missing note."""
        from lm_mcp.tools.ops import get_ops_note

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/opsnotes/invalid").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Note not found"})
        )

        result = await get_ops_note(client, note_id="invalid")

        assert "Error:" in result[0].text


class TestAddOpsNote:
    """Tests for add_ops_note tool."""

    @respx.mock
    async def test_add_ops_note_creates_note(self, client, monkeypatch):
        """add_ops_note creates a new note."""
        from lm_mcp.tools.ops import add_ops_note

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/opsnotes").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "newnote123",
                    "note": "Deployment completed",
                    "tags": [{"name": "deployment"}],
                },
            )
        )

        result = await add_ops_note(client, note="Deployment completed", tags=["deployment"])

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["id"] == "newnote123"
        assert data["note"] == "Deployment completed"

    @respx.mock
    async def test_add_ops_note_with_scopes(self, client, monkeypatch):
        """add_ops_note creates note with device and group scopes."""
        from lm_mcp.tools.ops import add_ops_note

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        route = respx.post("https://test.logicmonitor.com/santaba/rest/setting/opsnotes").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "scopednote",
                    "note": "Scoped note",
                    "tags": [],
                },
            )
        )

        await add_ops_note(client, note="Scoped note", device_ids=[100, 101], group_ids=[50])

        request_body = json.loads(route.calls[0].request.content)
        assert request_body["note"] == "Scoped note"
        assert len(request_body["scopes"]) == 3
        assert {"type": "device", "deviceId": 100} in request_body["scopes"]
        assert {"type": "device", "deviceId": 101} in request_body["scopes"]
        assert {"type": "deviceGroup", "groupId": 50} in request_body["scopes"]

    @respx.mock
    async def test_add_ops_note_blocked_without_write_permission(self, client, monkeypatch):
        """add_ops_note is blocked when write operations disabled."""
        from lm_mcp.tools.ops import add_ops_note

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await add_ops_note(client, note="Test note")

        assert "Error:" in result[0].text
        assert "disabled" in result[0].text.lower()
