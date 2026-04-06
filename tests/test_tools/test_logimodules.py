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


class TestConfigSourceUpdateReasons:
    @respx.mock
    async def test_get_update_reasons_returns_list(self, client):
        from lm_mcp.tools.configsources import get_configsource_update_reasons

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/1/updatereasons"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "version": 2,
                            "reason": "Updated SSH timeout",
                            "dateTime": "2026-03-20T10:00:00Z",
                            "userName": "admin",
                        },
                        {
                            "version": 1,
                            "reason": "Initial import",
                            "dateTime": "2026-03-01T08:00:00Z",
                            "userName": "admin",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_configsource_update_reasons(client, configsource_id=1)
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["update_reasons"][0]["reason"] == "Updated SSH timeout"
        assert data["update_reasons"][1]["version"] == 1

    @respx.mock
    async def test_get_update_reasons_empty(self, client):
        from lm_mcp.tools.configsources import get_configsource_update_reasons

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/99/updatereasons"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        result = await get_configsource_update_reasons(client, configsource_id=99)
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["count"] == 0
        assert data["update_reasons"] == []

    @respx.mock
    async def test_get_update_reasons_api_error(self, client):
        from lm_mcp.tools.configsources import get_configsource_update_reasons

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/configsources/999/updatereasons"
        ).mock(
            return_value=httpx.Response(
                404,
                json={"errorMessage": "No such ConfigSource", "errorCode": 1404},
            )
        )

        result = await get_configsource_update_reasons(client, configsource_id=999)
        assert "Error" in result[0].text


class TestDeviceConfig:
    @respx.mock
    async def test_get_device_config_returns_versions(self, client):
        from lm_mcp.tools.configsources import get_device_config

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200/config"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "cfg-001",
                            "version": 3,
                            "pollTimestamp": 1711929600000,
                            "changeStatus": "Change",
                            "configStatus": 0,
                            "configErrMsg": "",
                            "deviceDisplayName": "switch-core-01",
                            "instanceName": "Running-Config",
                            "dataSourceName": "SSH_Exec_Standard",
                        },
                        {
                            "id": "cfg-000",
                            "version": 2,
                            "pollTimestamp": 1711843200000,
                            "changeStatus": "Add",
                            "configStatus": 0,
                            "configErrMsg": "",
                            "deviceDisplayName": "switch-core-01",
                            "instanceName": "Running-Config",
                            "dataSourceName": "SSH_Exec_Standard",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_device_config(
            client, device_id=42, device_datasource_id=100, instance_id=200
        )
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["configs"][0]["id"] == "cfg-001"
        assert data["configs"][0]["change_status"] == "Change"
        assert data["configs"][1]["change_status"] == "Add"
        assert data["device_id"] == 42

    @respx.mock
    async def test_get_device_config_empty(self, client):
        from lm_mcp.tools.configsources import get_device_config

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200/config"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"items": [], "total": 0},
            )
        )

        result = await get_device_config(
            client, device_id=42, device_datasource_id=100, instance_id=200
        )
        data = json.loads(result[0].text)
        assert data["total"] == 0
        assert data["configs"] == []

    @respx.mock
    async def test_get_device_config_api_error(self, client):
        from lm_mcp.tools.configsources import get_device_config

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/999/devicedatasources/100/instances/200/config"
        ).mock(
            return_value=httpx.Response(
                404,
                json={"errorMessage": "No such device", "errorCode": 1404},
            )
        )

        result = await get_device_config(
            client, device_id=999, device_datasource_id=100, instance_id=200
        )
        assert "Error" in result[0].text

    @respx.mock
    async def test_get_device_config_version_returns_content(self, client):
        from lm_mcp.tools.configsources import get_device_config_version

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200/config/cfg-001"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "cfg-001",
                    "version": 3,
                    "pollTimestamp": 1711929600000,
                    "changeStatus": "Change",
                    "comparedWith": "cfg-000",
                    "config": (
                        "hostname switch-core-01\nip ssh version 2\nservice password-encryption"
                    ),
                    "deltaConfig": [
                        {"rowNo": 2, "type": "add", "content": "ip ssh version 2"},
                    ],
                    "alerts": [
                        {
                            "alertId": "LMD123",
                            "alertLevel": 3,
                            "alertSummary": "Config changed",
                            "timestamp": 1711929600000,
                        }
                    ],
                    "deviceDisplayName": "switch-core-01",
                    "instanceName": "Running-Config",
                    "dataSourceName": "SSH_Exec_Standard",
                },
            )
        )

        result = await get_device_config_version(
            client,
            device_id=42,
            device_datasource_id=100,
            instance_id=200,
            config_id="cfg-001",
        )
        data = json.loads(result[0].text)
        assert "ip ssh version 2" in data["config"]
        assert data["change_status"] == "Change"
        assert data["compared_with"] == "cfg-000"
        assert len(data["delta_config"]) == 1
        assert data["delta_config"][0]["type"] == "add"
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["alert_level"] == 3

    @respx.mock
    async def test_get_device_config_version_with_start_epoch(self, client):
        from lm_mcp.tools.configsources import get_device_config_version

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200/config/cfg-001"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "cfg-001",
                    "version": 3,
                    "pollTimestamp": 1711929600000,
                    "changeStatus": "Change",
                    "config": "hostname switch-core-01",
                    "deltaConfig": [],
                    "alerts": [],
                },
            )
        )

        result = await get_device_config_version(
            client,
            device_id=42,
            device_datasource_id=100,
            instance_id=200,
            config_id="cfg-001",
            start_epoch=1711843200,
        )
        data = json.loads(result[0].text)
        assert data["config_id"] == "cfg-001"
        # Verify startEpoch param was sent
        assert "startEpoch" in str(route.calls[0].request.url)

    @respx.mock
    async def test_get_device_config_version_api_error(self, client):
        from lm_mcp.tools.configsources import get_device_config_version

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200/config/bad-id"
        ).mock(
            return_value=httpx.Response(
                404,
                json={"errorMessage": "Config not found", "errorCode": 1404},
            )
        )

        result = await get_device_config_version(
            client,
            device_id=42,
            device_datasource_id=100,
            instance_id=200,
            config_id="bad-id",
        )
        assert "Error" in result[0].text


class TestCollectDeviceConfig:
    @respx.mock
    async def test_collect_write_blocked(self, client, monkeypatch):
        from lm_mcp.tools.configsources import collect_device_config

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "false")
        from lm_mcp import config as config_mod

        config_mod._config = None

        result = await collect_device_config(
            client, device_id=42, device_datasource_id=100, instance_id=200
        )
        assert "Write operations are disabled" in result[0].text
        config_mod._config = None

    @respx.mock
    async def test_collect_success(self, client, monkeypatch):
        from lm_mcp.tools.configsources import collect_device_config

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp import config as config_mod

        config_mod._config = None

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200"
            "/config/configCollection"
        ).mock(return_value=httpx.Response(200, json={}))

        result = await collect_device_config(
            client, device_id=42, device_datasource_id=100, instance_id=200
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["message"] == "Config collection triggered"
        config_mod._config = None

    @respx.mock
    async def test_collect_api_error(self, client, monkeypatch):
        from lm_mcp.tools.configsources import collect_device_config

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp import config as config_mod

        config_mod._config = None

        respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200"
            "/config/configCollection"
        ).mock(
            return_value=httpx.Response(
                403,
                json={"errorMessage": "Permission denied", "errorCode": 1403},
            )
        )

        result = await collect_device_config(
            client, device_id=42, device_datasource_id=100, instance_id=200
        )
        assert "Error" in result[0].text
        config_mod._config = None

    @respx.mock
    async def test_collect_body_verification(self, client, monkeypatch):
        from lm_mcp.tools.configsources import collect_device_config

        monkeypatch.setenv("LM_PORTAL", "test.logicmonitor.com")
        monkeypatch.setenv("LM_BEARER_TOKEN", "test-token")
        monkeypatch.setenv("LM_ENABLE_WRITE_OPERATIONS", "true")
        from lm_mcp import config as config_mod

        config_mod._config = None

        route = respx.post(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/42/devicedatasources/100/instances/200"
            "/config/configCollection"
        ).mock(return_value=httpx.Response(200, json={}))

        await collect_device_config(client, device_id=42, device_datasource_id=100, instance_id=200)
        assert route.called
        config_mod._config = None


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
