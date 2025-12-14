# Description: Tests for netscan MCP tools.

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


class TestGetNetscans:
    @respx.mock
    async def test_get_netscans_returns_list(self, client):
        from lm_mcp.tools.netscans import get_netscans

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/netscans").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Office Network Scan",
                            "description": "Scan office subnet",
                            "method": "nmap",
                            "collectorId": 1,
                            "groupId": 1,
                            "nextStart": "2024-01-01 00:00:00",
                            "schedule": "daily",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_netscans(client)
        data = json.loads(result[0].text)
        assert data["netscans"][0]["name"] == "Office Network Scan"


class TestGetNetscan:
    @respx.mock
    async def test_get_netscan_returns_details(self, client):
        from lm_mcp.tools.netscans import get_netscan

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/netscans/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Office Network Scan",
                    "description": "Scan office subnet",
                    "method": "nmap",
                    "collectorId": 1,
                    "collectorGroupId": 1,
                    "collectorGroupName": "US-East",
                    "groupId": 1,
                    "group": "Discovered Devices",
                    "subnet": "192.168.1.0/24",
                    "schedule": "daily",
                },
            )
        )

        result = await get_netscan(client, netscan_id=1)
        data = json.loads(result[0].text)
        assert data["subnet"] == "192.168.1.0/24"


class TestRunNetscan:
    @respx.mock
    async def test_run_netscan_blocked_by_default(self, client, monkeypatch):
        from lm_mcp.tools.netscans import run_netscan

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")

        result = await run_netscan(client, netscan_id=1)
        assert "Error:" in result[0].text

    @respx.mock
    async def test_run_netscan_succeeds_when_enabled(self, client, monkeypatch):
        from lm_mcp.tools.netscans import run_netscan

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")

        respx.post("https://test.logicmonitor.com/santaba/rest/setting/netscans/1/executenow").mock(
            return_value=httpx.Response(200, json={"status": "started"})
        )

        result = await run_netscan(client, netscan_id=1)
        data = json.loads(result[0].text)
        assert data["success"] is True
