# Description: Tests for network intelligence MCP tools.
# Description: Validates interface metrics, device NetFlow, flap and power event tools.

import json
import time
from pathlib import Path

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result
from tests.alert_pages import alert_pages
from tests.envelope import envelope
from tests.list_paging import assert_negative_total_reads_as_more, assert_offset_declared_and_sent


@pytest.fixture
def auth():
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    return LogicMonitorClient(
        base_url="https://test.logicmonitor.com/santaba/rest",
        auth=auth,
        timeout=30,
        max_retries=0,
    )


BASE = "https://test.logicmonitor.com/santaba/rest"


class TestGetInterfaceMetrics:
    @respx.mock
    async def test_a_day_of_minutes_is_read_in_both_pages(self, client):
        """R2.10: the interface's 1,440 samples over two pages all arrive."""
        from lm_mcp.tools.networking import get_interface_metrics
        from tests.metric_pages import day_of_minutes

        respx.get(f"{BASE}/device/devices/123/devicedatasources").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 9001, "dataSourceName": "SNMP_Network_Interfaces"}]},
            )
        )
        respx.get(f"{BASE}/device/devices/123/devicedatasources/9001/instances").mock(
            return_value=httpx.Response(200, json={"items": [{"id": 1, "displayName": "Gi0/1"}]})
        )
        route = respx.get(
            f"{BASE}/device/devices/123/devicedatasources/9001/instances/1/data"
        ).mock(side_effect=day_of_minutes())

        result = await get_interface_metrics(client, device_id=123, interface="Gi0/1")

        data = json.loads(result[0].text)
        assert route.call_count == 2
        assert len(data["time"]) == len(data["values"]) == 1440
        assert data["truncated"] is False

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


class TestGetLinkFlaps:
    @respx.mock
    async def test_identifies_flapping_interfaces(self, client):
        from lm_mcp.tools.networking import get_link_flaps

        now = int(time.time())
        alerts = [
            {
                "id": i,
                "startEpoch": now - 3600 + i * 60,
                "resourceTemplateName": "SNMP_Network_Interfaces",
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
        assert top["datasource"] == "SNMP_Network_Interfaces"

    @respx.mock
    async def test_no_flaps_when_below_threshold(self, client):
        from lm_mcp.tools.networking import get_link_flaps

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "startEpoch": now - 100,
                "resourceTemplateName": "SNMP_Network_Interfaces",
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
                "resourceTemplateName": "APC_UPS_Battery",
                "monitorObjectName": "ups-01",
                "dataPointName": "BatteryStatus",
            },
            {
                "id": 2,
                "severity": 3,
                "startEpoch": now - 200,
                "resourceTemplateName": "Liebert_UPS",
                "monitorObjectName": "ups-02",
                "dataPointName": "RuntimeRemaining",
            },
            {
                "id": 3,
                "severity": 2,
                "startEpoch": now - 300,
                "resourceTemplateName": "CPU",
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
        assert {e["datasource"] for e in data["events"]} == {"APC_UPS_Battery", "Liebert_UPS"}

    @respx.mock
    async def test_custom_patterns_override_defaults(self, client):
        from lm_mcp.tools.networking import get_power_events

        now = int(time.time())
        alerts = [
            {
                "id": 1,
                "startEpoch": now - 100,
                "resourceTemplateName": "CustomPowerSensor",
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
                "resourceTemplateName": "CPU",
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
        assert is_error_result(result)


def _interface_power_alerts(n):
    """Alerts that are both interface flaps and power events, spread over the last hour."""
    now = int(time.time())
    return [
        {
            "id": i,
            "startEpoch": now - 3000 + i % 2900,
            "resourceTemplateName": "SNMP_Network_Interfaces UPS",
            "monitorObjectName": f"sw-{i % 40}",
            "instanceName": f"Gi0/{i % 8}",
            "cleared": True,
        }
        for i in range(n)
    ]


class TestCappedAlertToolsWarn:
    """R4.2: get_link_flaps and get_power_events warn when the alert-window cap binds."""

    @pytest.mark.parametrize("tool_name", ["get_link_flaps", "get_power_events"])
    @respx.mock
    async def test_warns_when_the_cap_binds(self, client, tool_name):
        from lm_mcp.tools import networking
        from lm_mcp.tools.alerts import ALERT_WINDOW_TRUNCATED_WARNING

        respx.get(f"{BASE}/alert/alerts").mock(
            side_effect=alert_pages(_interface_power_alerts(6000), lower_bound=True)
        )

        result = await getattr(networking, tool_name)(client)
        data = json.loads(result[0].text)
        assert data["warning"] == ALERT_WINDOW_TRUNCATED_WARNING
        assert "Truncated at 5000 alerts" in data["warning"]

    @pytest.mark.parametrize("tool_name", ["get_link_flaps", "get_power_events"])
    @respx.mock
    async def test_no_warning_for_a_complete_window(self, client, tool_name):
        from lm_mcp.tools import networking

        respx.get(f"{BASE}/alert/alerts").mock(
            side_effect=alert_pages(_interface_power_alerts(5000), lower_bound=True)
        )

        result = await getattr(networking, tool_name)(client)
        data = json.loads(result[0].text)
        assert "warning" not in data


# NetFlow answers. netflow_disabled and device_missing are live (sandbox, 2026-11-12); the pages
# carry the swagger definitions' properties with placeholder values, and the graph the lines and
# timestamps keys get_graph_data reads, since no portal with NetFlow data was read (see the
# fixture's source entry).
NETFLOW = json.loads((Path(__file__).parent.parent / "fixtures" / "netflow_reads.json").read_text())
_DEVICE_1786 = f"{BASE}/device/devices/1786"


def _window(route: respx.Route) -> tuple[int, int]:
    """The start and end a NetFlow read sent."""
    params = route.calls.last.request.url.params
    return int(params["start"]), int(params["end"])


class TestGetDeviceFlows:
    """R3.7: a device's flows page through /device/devices/{id}/flows over a window."""

    @respx.mock
    async def test_reads_the_device_flows_over_the_window(self, client):
        from lm_mcp.tools.networking import get_device_flows

        route = respx.get(f"{_DEVICE_1786}/flows").mock(
            return_value=httpx.Response(200, json=NETFLOW["flows_page"])
        )
        before = int(time.time())

        body = json.loads(
            (await get_device_flows(client, device_id=1786, hours_back=2, limit=5))[0].text
        )

        start, end = _window(route)
        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("5", "0")
        assert end - start == 7200 and before <= end <= int(time.time())
        assert (body["device_id"], body["window_hours"], body["total"]) == (1786, 2, 1)
        assert body["flows"] == NETFLOW["flows_page"]["items"]

    @respx.mock
    async def test_netflow_disabled_is_feature_disabled(self, client):
        from lm_mcp.tools.networking import get_device_flows

        respx.get(f"{_DEVICE_1786}/flows").mock(
            return_value=httpx.Response(400, json=NETFLOW["netflow_disabled"]["body"])
        )

        error = envelope(await get_device_flows(client, device_id=1786))

        assert error["code"] == "FEATURE_DISABLED"
        assert error["message"].startswith("Netflow disabled")
        assert "Check the request parameters" not in error["message"]

    @respx.mock
    async def test_an_unknown_device_is_not_found(self, client):
        from lm_mcp.tools.networking import get_device_flows

        respx.get(f"{BASE}/device/devices/99999999/flows").mock(
            return_value=httpx.Response(404, json=NETFLOW["device_missing"]["body"])
        )

        error = envelope(await get_device_flows(client, device_id=99999999))

        assert error["code"] == "NOT_FOUND"


class TestGetDeviceTopTalkers:
    """R3.7: a device's top endpoints, top ports or top talkers graph over a window."""

    @pytest.mark.parametrize(
        ("by", "tail", "key", "page"),
        [
            ("endpoint", "endpoints", "endpoints", "endpoints_page"),
            ("port", "ports", "ports", "ports_page"),
        ],
    )
    @respx.mock
    async def test_endpoints_and_ports_page_over_the_window(self, client, by, tail, key, page):
        from lm_mcp.tools.networking import get_device_top_talkers

        route = respx.get(f"{_DEVICE_1786}/{tail}").mock(
            return_value=httpx.Response(200, json=NETFLOW[page])
        )

        body = json.loads(
            (await get_device_top_talkers(client, device_id=1786, by=by, limit=3, offset=6))[0].text
        )

        start, end = _window(route)
        params = route.calls.last.request.url.params
        assert (params["size"], params["offset"]) == ("3", "6")
        assert end - start == 3600
        assert (body["device_id"], body["by"], body["window_hours"]) == (1786, by, 1)
        assert body[key] == NETFLOW[page]["items"]

    @respx.mock
    async def test_the_graph_is_returned_as_read_with_no_paging(self, client):
        from lm_mcp.tools.networking import get_device_top_talkers

        route = respx.get(f"{_DEVICE_1786}/topTalkersGraph").mock(
            return_value=httpx.Response(200, json=NETFLOW["graph"])
        )

        body = json.loads(
            (await get_device_top_talkers(client, device_id=1786, by="graph", hours_back=24))[
                0
            ].text
        )

        start, end = _window(route)
        assert end - start == 86400
        assert "size" not in route.calls.last.request.url.params
        assert body == {
            "device_id": 1786,
            "by": "graph",
            "window_hours": 24,
            "graph": NETFLOW["graph"],
        }

    @respx.mock
    async def test_an_unknown_by_is_refused_before_any_call(self, client):
        from lm_mcp.tools.networking import get_device_top_talkers

        route = respx.get(url__regex=rf"^{_DEVICE_1786}/.*")

        error = envelope(await get_device_top_talkers(client, device_id=1786, by="src_ip"))

        assert error["code"] == "INVALID_REQUEST"
        assert not route.called

    @pytest.mark.parametrize("by", ["endpoint", "port", "graph"])
    @respx.mock
    async def test_netflow_disabled_is_feature_disabled(self, client, by):
        from lm_mcp.tools.networking import get_device_top_talkers

        respx.get(url__regex=rf"^{_DEVICE_1786}/(endpoints|ports|topTalkersGraph)(\?.*)?$").mock(
            return_value=httpx.Response(400, json=NETFLOW["netflow_disabled"]["body"])
        )

        error = envelope(await get_device_top_talkers(client, device_id=1786, by=by))

        assert error["code"] == "FEATURE_DISABLED"


class TestNetflowListPaging:
    """R2.5: the flow, endpoint and port reads declare offset, send it, and read a negative
    total as more."""

    @respx.mock
    async def test_flows_offset_is_declared_and_sent(self, client):
        from lm_mcp.tools.networking import get_device_flows

        await assert_offset_declared_and_sent(
            client, get_device_flows, "/device/devices/7/flows", {"device_id": 7}
        )

    @respx.mock
    async def test_flows_negative_total_reads_as_more(self, client):
        from lm_mcp.tools.networking import get_device_flows

        await assert_negative_total_reads_as_more(
            client, get_device_flows, "/device/devices/7/flows", {"device_id": 7}
        )

    @respx.mock
    async def test_top_talkers_offset_is_declared_and_sent(self, client):
        from lm_mcp.tools.networking import get_device_top_talkers

        await assert_offset_declared_and_sent(
            client, get_device_top_talkers, "/device/devices/7/endpoints", {"device_id": 7}
        )
