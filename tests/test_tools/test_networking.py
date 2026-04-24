# Description: Tests for network intelligence MCP tools.
# Description: Validates interface metrics, top talkers, burst, flap, power event tools.

import json
import time

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


BASE = "https://test.logicmonitor.com/santaba/rest"


class TestGetInterfaceMetrics:
    @respx.mock
    async def test_returns_metrics_for_matching_interface(self, client):
        from lm_mcp.tools.networking import get_interface_metrics

        respx.get(f"{BASE}/device/devices/123/devicedatasources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 9001,
                            "dataSourceName": "SNMP_Network_Interfaces",
                            "instanceNumber": 24,
                        },
                        {
                            "id": 9002,
                            "dataSourceName": "CPU",
                            "instanceNumber": 1,
                        },
                    ]
                },
            )
        )
        respx.get(f"{BASE}/device/devices/123/devicedatasources/9001/instances").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "Gi0/1", "displayName": "Gi0/1 Uplink"},
                        {"id": 2, "name": "Gi0/2", "displayName": "Gi0/2"},
                    ]
                },
            )
        )
        respx.get(f"{BASE}/device/devices/123/devicedatasources/9001/instances/1/data").mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["RxRate", "TxRate"],
                    "values": [[100.0, 200.0]],
                    "time": [1700000000000],
                },
            )
        )

        result = await get_interface_metrics(client, device_id=123, interface="Gi0/1")
        data = json.loads(result[0].text)

        assert data["resolved_datasource"] == "SNMP_Network_Interfaces"
        assert data["resolved_datasource_id"] == 9001
        assert data["resolved_instance_id"] == 1
        assert data["datapoints"] == ["RxRate", "TxRate"]

    @respx.mock
    async def test_returns_error_when_no_interface_datasource(self, client):
        from lm_mcp.tools.networking import get_interface_metrics

        respx.get(f"{BASE}/device/devices/456/devicedatasources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 1, "dataSourceName": "CPU"}]},
            )
        )

        result = await get_interface_metrics(client, device_id=456, interface="eth0")
        assert "No Interface-family DataSource found" in result[0].text

    @respx.mock
    async def test_returns_error_when_interface_not_matched(self, client):
        from lm_mcp.tools.networking import get_interface_metrics

        respx.get(f"{BASE}/device/devices/789/devicedatasources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 9001, "dataSourceName": "SNMP_Network_Interfaces"}]},
            )
        )
        respx.get(f"{BASE}/device/devices/789/devicedatasources/9001/instances").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 1, "name": "eth0", "displayName": "eth0"},
                    ]
                },
            )
        )

        result = await get_interface_metrics(client, device_id=789, interface="Gi99")
        assert "not found among instances" in result[0].text


class TestGetTopTalkers:
    @respx.mock
    async def test_ranks_by_bytes(self, client):
        from lm_mcp.tools.networking import get_top_talkers

        respx.get(f"{BASE}/netflow/flows").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"srcIP": "10.0.0.1", "dstIP": "8.8.8.8", "bytes": 1000, "packets": 10},
                        {"srcIP": "10.0.0.1", "dstIP": "8.8.8.8", "bytes": 2000, "packets": 20},
                        {"srcIP": "10.0.0.2", "dstIP": "8.8.8.8", "bytes": 500, "packets": 5},
                    ]
                },
            )
        )

        result = await get_top_talkers(client, exporter_device_id=42, n=2, group_by="src_ip")
        data = json.loads(result[0].text)
        assert data["flows_analyzed"] == 3
        assert data["top_talkers"][0]["key"] == "10.0.0.1"
        assert data["top_talkers"][0]["total_bytes"] == 3000
        assert data["top_talkers"][0]["flow_count"] == 2

    async def test_rejects_invalid_group_by(self, client):
        from lm_mcp.tools.networking import get_top_talkers

        result = await get_top_talkers(client, exporter_device_id=42, group_by="invalid")
        assert "group_by must be one of" in result[0].text

    @respx.mock
    async def test_handles_empty_flows(self, client):
        from lm_mcp.tools.networking import get_top_talkers

        respx.get(f"{BASE}/netflow/flows").mock(
            return_value=httpx.Response(200, json={"items": []})
        )

        result = await get_top_talkers(client, exporter_device_id=42)
        data = json.loads(result[0].text)
        assert data["flows_analyzed"] == 0
        assert "No flows exported" in data["note"]

    @respx.mock
    async def test_group_by_src_dst_pair(self, client):
        from lm_mcp.tools.networking import get_top_talkers

        respx.get(f"{BASE}/netflow/flows").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"srcIP": "10.0.0.1", "dstIP": "8.8.8.8", "bytes": 100, "packets": 1},
                        {"srcIP": "10.0.0.1", "dstIP": "8.8.8.8", "bytes": 200, "packets": 2},
                    ]
                },
            )
        )

        result = await get_top_talkers(client, exporter_device_id=42, group_by="src_dst_pair")
        data = json.loads(result[0].text)
        assert data["top_talkers"][0]["key"] == "10.0.0.1->8.8.8.8"
        assert data["top_talkers"][0]["total_bytes"] == 300


class TestDetectAlertBurst:
    @respx.mock
    async def test_detects_burst(self, client):
        from lm_mcp.tools.networking import detect_alert_burst

        now = int(time.time())
        # 10 alerts across 4 devices within 30 seconds, all same DataSource.
        alerts = [
            {
                "id": i,
                "startEpoch": now - 60 + i * 3,
                "dataSourceName": "SNMP_Network_Interfaces",
                "monitorObjectName": f"switch-{i % 4}",
            }
            for i in range(12)
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 12})
        )

        result = await detect_alert_burst(
            client,
            window_seconds=60,
            min_alerts=10,
            min_devices=3,
        )
        data = json.loads(result[0].text)
        assert data["total_alerts_in_window"] == 12
        assert data["bursts_detected"] >= 1
        assert data["bursts"][0]["datasource"] == "SNMP_Network_Interfaces"
        assert data["bursts"][0]["alert_count"] >= 10

    @respx.mock
    async def test_no_burst_when_below_threshold(self, client):
        from lm_mcp.tools.networking import detect_alert_burst

        now = int(time.time())
        alerts = [
            {
                "id": i,
                "startEpoch": now - 60 + i,
                "dataSourceName": "CPU",
                "monitorObjectName": f"host-{i}",
            }
            for i in range(5)
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 5})
        )

        result = await detect_alert_burst(client, window_seconds=60, min_alerts=10, min_devices=3)
        data = json.loads(result[0].text)
        assert data["bursts_detected"] == 0

    @respx.mock
    async def test_datasource_pattern_filter(self, client):
        from lm_mcp.tools.networking import detect_alert_burst

        now = int(time.time())
        alerts = [
            {
                "id": i,
                "startEpoch": now - 30 + i,
                "dataSourceName": "SNMP_Network_Interfaces" if i < 12 else "CPU",
                "monitorObjectName": f"dev-{i}",
            }
            for i in range(16)
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 16})
        )

        result = await detect_alert_burst(
            client,
            window_seconds=60,
            min_alerts=10,
            min_devices=3,
            datasource_pattern="interface",
        )
        data = json.loads(result[0].text)
        # Only interface alerts should qualify.
        assert data["total_alerts_in_window"] == 12


class TestGetLinkFlaps:
    @respx.mock
    async def test_identifies_flapping_interfaces(self, client):
        from lm_mcp.tools.networking import get_link_flaps

        now = int(time.time())
        alerts = [
            {
                "id": i,
                "startEpoch": now - 3600 + i * 60,
                "dataSourceName": "SNMP_Network_Interfaces",
                "monitorObjectName": "sw1",
                "instanceName": "Gi0/1",
                "cleared": i % 2 == 0,
            }
            for i in range(6)
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 6})
        )

        result = await get_link_flaps(client, min_transitions=4)
        data = json.loads(result[0].text)
        assert data["flapping_interfaces"] >= 1
        top = data["results"][0]
        assert top["device"] == "sw1"
        assert top["interface"] == "Gi0/1"
        assert top["transitions"] >= 4

    @respx.mock
    async def test_no_flaps_when_below_threshold(self, client):
        from lm_mcp.tools.networking import get_link_flaps

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "startEpoch": now - 100,
                "dataSourceName": "SNMP_Network_Interfaces",
                "monitorObjectName": "sw1",
                "instanceName": "Gi0/1",
            }
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 1})
        )

        result = await get_link_flaps(client, min_transitions=4)
        data = json.loads(result[0].text)
        assert data["flapping_interfaces"] == 0


class TestGetPowerEvents:
    @respx.mock
    async def test_matches_default_patterns(self, client):
        from lm_mcp.tools.networking import get_power_events

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "severity": 4,
                "startEpoch": now - 100,
                "dataSourceName": "APC_UPS_Battery",
                "alertName": "UPS On Battery",
                "monitorObjectName": "ups-01",
                "dataPointName": "BatteryStatus",
            },
            {
                "id": 2,
                "severity": 3,
                "startEpoch": now - 200,
                "dataSourceName": "Liebert_UPS",
                "alertName": "Runtime Remaining Low",
                "monitorObjectName": "ups-02",
                "dataPointName": "RuntimeRemaining",
            },
            {
                "id": 3,
                "severity": 2,
                "startEpoch": now - 300,
                "dataSourceName": "CPU",
                "alertName": "CPU high",
                "monitorObjectName": "server-01",
                "dataPointName": "CpuPercent",
            },
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 3})
        )

        result = await get_power_events(client)
        data = json.loads(result[0].text)
        assert data["total_alerts_scanned"] == 3
        assert data["total_power_events"] == 2
        assert "ups" in data["patterns_matched_counts"]

    @respx.mock
    async def test_custom_patterns_override_defaults(self, client):
        from lm_mcp.tools.networking import get_power_events

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "startEpoch": now - 100,
                "dataSourceName": "CustomPowerSensor",
                "alertName": "Power loss",
                "monitorObjectName": "sensor-1",
            }
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 1})
        )

        result = await get_power_events(client, patterns=["customPower"])
        data = json.loads(result[0].text)
        assert data["total_power_events"] == 1

    @respx.mock
    async def test_no_matches_returns_empty(self, client):
        from lm_mcp.tools.networking import get_power_events

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "startEpoch": now - 100,
                "dataSourceName": "CPU",
                "alertName": "CPU high",
                "monitorObjectName": "server-01",
            }
        ]
        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": alerts, "total": 1})
        )

        result = await get_power_events(client)
        data = json.loads(result[0].text)
        assert data["total_power_events"] == 0


class TestNetworkingErrorHandling:
    @respx.mock
    async def test_api_error_on_interface_lookup_returns_error(self, client):
        from lm_mcp.tools.networking import get_interface_metrics

        respx.get(f"{BASE}/device/devices/111/devicedatasources").mock(
            return_value=httpx.Response(500, json={"errorMessage": "boom"})
        )

        result = await get_interface_metrics(client, device_id=111, interface="eth0")
        # handle_error produces a readable error string.
        assert "Error" in result[0].text

    @respx.mock
    async def test_burst_tolerates_empty_alert_list(self, client):
        from lm_mcp.tools.networking import detect_alert_burst

        respx.get(f"{BASE}/alert/alerts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await detect_alert_burst(client)
        data = json.loads(result[0].text)
        assert data["bursts_detected"] == 0
        assert data["total_alerts_in_window"] == 0
