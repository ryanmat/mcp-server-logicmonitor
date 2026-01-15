# Description: Tests for LogicModule MCP tools (ConfigSources, EventSources, etc.).
# Description: Covers list, get, and audit operations across all LogicModule types.

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


class TestConfigSources:
    @respx.mock
    async def test_get_configsources_returns_list(self, client):
        from lm_mcp.tools.configsources import get_configsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Cisco_IOS_Config",
                            "displayName": "Cisco IOS Config",
                            "description": "Cisco config",
                            "appliesTo": "hasCategory('Cisco')",
                            "technology": "Cisco IOS config collection",
                            "collectMethod": "script",
                            "collectInterval": 86400,
                            "version": 1,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_configsources(client)
        data = json.loads(result[0].text)
        assert data["configsources"][0]["name"] == "Cisco_IOS_Config"

    @respx.mock
    async def test_get_configsource_returns_details(self, client):
        from lm_mcp.tools.configsources import get_configsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/configsources/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Cisco_IOS_Config",
                    "displayName": "Cisco IOS Config",
                    "appliesTo": "hasCategory('Cisco')",
                    "configChecks": [{"name": "check1"}],
                },
            )
        )

        result = await get_configsource(client, configsource_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "Cisco_IOS_Config"


class TestEventSources:
    @respx.mock
    async def test_get_eventsources_returns_list(self, client):
        from lm_mcp.tools.eventsources import get_eventsources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Windows_Events",
                            "displayName": "Windows Events",
                            "description": "Windows event log",
                            "appliesTo": "isWindows()",
                            "technology": "Windows",
                            "group": "Windows",
                            "version": 1,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_eventsources(client)
        data = json.loads(result[0].text)
        assert data["eventsources"][0]["name"] == "Windows_Events"

    @respx.mock
    async def test_get_eventsource_returns_details(self, client):
        from lm_mcp.tools.eventsources import get_eventsource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/eventsources/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "Windows_Events",
                    "displayName": "Windows Events",
                    "filters": [{"name": "Error", "type": "eventlog"}],
                },
            )
        )

        result = await get_eventsource(client, eventsource_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "Windows_Events"


class TestPropertySources:
    @respx.mock
    async def test_get_propertysources_returns_list(self, client):
        from lm_mcp.tools.propertysources import get_propertysources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "SNMP_SysInfo",
                            "displayName": "SNMP System Info",
                            "appliesTo": "hasSNMP()",
                            "technology": "SNMP",
                            "version": 1,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_propertysources(client)
        data = json.loads(result[0].text)
        assert data["propertysources"][0]["name"] == "SNMP_SysInfo"

    @respx.mock
    async def test_get_propertysource_returns_details(self, client):
        from lm_mcp.tools.propertysources import get_propertysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/propertyrules/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "SNMP_SysInfo",
                    "displayName": "SNMP System Info",
                    "appliesTo": "hasSNMP()",
                },
            )
        )

        result = await get_propertysource(client, propertysource_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "SNMP_SysInfo"


class TestTopologySources:
    @respx.mock
    async def test_get_topologysources_returns_list(self, client):
        from lm_mcp.tools.topologysources import get_topologysources

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/topologysources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "VMware_Topology",
                            "displayName": "VMware Topology",
                            "appliesTo": "hasCategory('VMware')",
                            "version": 1,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_topologysources(client)
        data = json.loads(result[0].text)
        assert data["topologysources"][0]["name"] == "VMware_Topology"

    @respx.mock
    async def test_get_topologysource_returns_details(self, client):
        from lm_mcp.tools.topologysources import get_topologysource

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/topologysources/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "VMware_Topology",
                    "displayName": "VMware Topology",
                    "appliesTo": "hasCategory('VMware')",
                },
            )
        )

        result = await get_topologysource(client, topologysource_id=1)
        data = json.loads(result[0].text)
        assert data["name"] == "VMware_Topology"
