# Description: Tests for SDT (Scheduled Downtime) MCP tools.
# Description: Validates list_sdts, create_sdt, delete_sdt functions.

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


class TestListSdts:
    """Tests for list_sdts tool."""

    @respx.mock
    async def test_list_sdts_returns_formatted_response(self, client):
        """list_sdts returns properly formatted SDT list."""
        from lm_mcp.tools.sdts import list_sdts

        respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "SDT_123",
                            "type": "DeviceSDT",
                            "deviceDisplayName": "server01",
                            "startDateTime": 1702400000,
                            "endDateTime": 1702403600,
                            "comment": "Maintenance window",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await list_sdts(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert len(data["sdts"]) == 1

    @respx.mock
    async def test_list_sdts_with_limit(self, client):
        """list_sdts passes size parameter to API."""
        from lm_mcp.tools.sdts import list_sdts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await list_sdts(client, limit=10)

        assert route.calls[0].request.url.params.get("size") == "10"


class TestCreateSdt:
    """Tests for create_sdt tool."""

    @respx.mock
    async def test_create_sdt_blocked_by_default(self, client, monkeypatch):
        """create_sdt is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        result = await create_sdt(
            client,
            sdt_type="DeviceSDT",
            device_id=123,
            duration_minutes=60,
            comment="Test",
        )

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_create_sdt_succeeds_when_enabled(self, client, monkeypatch):
        """create_sdt works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import create_sdt

        respx.post("https://test.logicmonitor.com/santaba/rest/sdt/sdts").mock(
            return_value=httpx.Response(
                200,
                json={"id": "SDT_456", "type": "DeviceSDT"},
            )
        )

        result = await create_sdt(
            client,
            sdt_type="DeviceSDT",
            device_id=123,
            duration_minutes=60,
            comment="Maintenance",
        )

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True


class TestDeleteSdt:
    """Tests for delete_sdt tool."""

    @respx.mock
    async def test_delete_sdt_blocked_by_default(self, client, monkeypatch):
        """delete_sdt is blocked when writes disabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import delete_sdt

        result = await delete_sdt(client, sdt_id="SDT_123")

        assert "Error:" in result[0].text
        assert "Write operations are disabled" in result[0].text

    @respx.mock
    async def test_delete_sdt_succeeds_when_enabled(self, client, monkeypatch):
        """delete_sdt works when writes enabled."""
        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        from importlib import reload

        import lm_mcp.config

        reload(lm_mcp.config)

        from lm_mcp.tools.sdts import delete_sdt

        respx.delete("https://test.logicmonitor.com/santaba/rest/sdt/sdts/SDT_123").mock(
            return_value=httpx.Response(200, json={})
        )

        result = await delete_sdt(client, sdt_id="SDT_123")

        assert "Error:" not in result[0].text
        data = json.loads(result[0].text)
        assert data["success"] is True
