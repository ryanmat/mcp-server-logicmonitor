# Description: Tests for the APM tools that remain after the trace tools fold into device tools.
# Description: Covers get_apm_services, get_apm_service_alerts and the removed trace names.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result

BASE_URL = "https://test.logicmonitor.com/santaba/rest"
DEVICES_URL = f"{BASE_URL}/device/devices"

# The seven trace tools whose reads the device tools already make (spec R2.3, R2.13).
REMOVED_TRACE_TOOLS = (
    "get_trace_services",
    "get_trace_service",
    "get_trace_service_datasources",
    "get_trace_operations",
    "get_trace_service_metrics",
    "get_trace_operation_metrics",
    "get_trace_service_properties",
)


@pytest.fixture
def auth():
    """Create a BearerAuth instance for testing."""
    return BearerAuth("test-token")


@pytest.fixture
def client(auth):
    """Create a LogicMonitorClient instance for testing."""
    return LogicMonitorClient(base_url=BASE_URL, auth=auth, timeout=30, max_retries=0)


def _apm_service(device_id, name, group_ids="238"):
    """A deviceType 6 row as the sandbox portal returned it on 2026-11-09, trimmed."""
    return {
        "id": device_id,
        "displayName": name,
        "name": name,
        "deviceType": 6,
        "hostGroupIds": group_ids,
        "customProperties": [
            {"name": "traces.namespace", "value": "lmryanmatuszewski"},
            {"name": "traces.telemetry.sdk.language", "value": "python"},
        ],
    }


class TestGetApmServices:
    """get_apm_services lists deviceType 6 devices through list_tool."""

    @respx.mock
    async def test_lists_apm_services_as_a_page(self, client):
        from lm_mcp.tools.traces import get_apm_services

        route = respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _apm_service(1967, "lmryanmatuszewski-frontend-web"),
                        _apm_service(271119, "precursor-platform-precursor-api", "2002"),
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_apm_services(client, limit=25, offset=50)

        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert data["services"] == [
            {
                "id": 1967,
                "name": "lmryanmatuszewski-frontend-web",
                "hostname": "lmryanmatuszewski-frontend-web",
                "host_group_ids": "238",
            },
            {
                "id": 271119,
                "name": "precursor-platform-precursor-api",
                "hostname": "precursor-platform-precursor-api",
                "host_group_ids": "2002",
            },
        ]
        params = route.calls[0].request.url.params
        assert params["filter"] == "deviceType:6"
        assert params["size"] == "25"
        assert params["offset"] == "50"

    @respx.mock
    async def test_name_filter_is_stripped_and_quoted(self, client):
        from lm_mcp.tools.traces import get_apm_services

        route = respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_apm_services(client, name_filter="precursor*")

        params = route.calls[0].request.url.params
        assert params["filter"] == 'deviceType:6,displayName~"precursor"'
        assert "note" in json.loads(result[0].text)

    @respx.mock
    async def test_api_error_is_an_error_result(self, client):
        from lm_mcp.tools.traces import get_apm_services

        respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Internal error"})
        )

        assert is_error_result(await get_apm_services(client))


class TestGetApmServiceAlerts:
    """get_apm_service_alerts reads one service's alert list through list_tool."""

    @respx.mock
    async def test_returns_the_service_alerts(self, client):
        from lm_mcp.tools.traces import get_apm_service_alerts

        route = respx.get(f"{DEVICES_URL}/1967/alerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "DS5001",
                            "severity": 4,
                            "monitorObjectName": "lmryanmatuszewski-frontend-web",
                            "dataPointName": "Duration",
                            "alertValue": "500",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_apm_service_alerts(client, service_id=1967, limit=10)

        data = json.loads(result[0].text)
        assert data["service_id"] == 1967
        assert data["total"] == 1
        assert data["alerts"] == [
            {
                "id": "DS5001",
                "severity": 4,
                "monitor_object": "lmryanmatuszewski-frontend-web",
                "datapoint": "Duration",
                "alert_value": "500",
            }
        ]
        params = route.calls[0].request.url.params
        assert params["size"] == "10"
        assert params["offset"] == "0"
        assert "filter" not in params

    @respx.mock
    async def test_severity_becomes_a_clause(self, client):
        from lm_mcp.tools.traces import get_apm_service_alerts

        route = respx.get(f"{DEVICES_URL}/1967/alerts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_apm_service_alerts(client, service_id=1967, severity="critical")

        assert route.calls[0].request.url.params["filter"] == "severity:4"

    @respx.mock
    async def test_missing_service_is_an_error_result(self, client):
        from lm_mcp.tools.traces import get_apm_service_alerts

        respx.get(f"{DEVICES_URL}/999/alerts").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        assert is_error_result(await get_apm_service_alerts(client, service_id=999))


class TestApmRegistration:
    """The service pair stays, two APM tools remain, and seven trace tools leave (R2.3, R2.13)."""

    def test_the_service_pair_and_the_two_apm_tools_are_registered(self):
        from lm_mcp.registry import TOOLS, get_tool_handler

        names = {tool.name for tool in TOOLS}
        for name in ("get_services", "get_service", "get_apm_services", "get_apm_service_alerts"):
            assert name in names
            assert get_tool_handler(name).__name__ == name

    def test_apm_schemas_page_through_list_tool(self):
        from lm_mcp.registry import TOOLS

        by_name = {tool.name: tool for tool in TOOLS}
        services = by_name["get_apm_services"].inputSchema
        alerts = by_name["get_apm_service_alerts"].inputSchema
        assert set(services["properties"]) == {"name_filter", "limit", "offset"}
        assert set(alerts["properties"]) == {"service_id", "severity", "limit", "offset"}
        assert alerts["required"] == ["service_id"]

    @pytest.mark.parametrize("name", [*REMOVED_TRACE_TOOLS, "get_trace_service_alerts"])
    def test_removed_trace_tool_is_not_registered(self, name):
        from lm_mcp.registry import TOOLS, get_tool_handler

        assert name not in {tool.name for tool in TOOLS}
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler(name)
