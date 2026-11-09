# Description: Tests for the availability and error budget tools.
# Description: Validates calculate_availability, its error budget and device resolution.

import json
import logging
import time

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result
from tests.alert_pages import alert_lists


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
        max_retries=0,
    )


# Base epoch for test data (2024-01-15 00:00:00 UTC)
BASE_EPOCH = 1705276800
ALERT_URL = "https://test.logicmonitor.com/santaba/rest/alert/alerts"


def _make_alert(
    alert_id,
    device,
    datasource,
    datapoint="value",
    severity=4,
    start_epoch=None,
    end_epoch=0,
    cleared=False,
):
    """Helper to create mock alert data."""
    return {
        "id": f"LMA{alert_id}",
        "severity": severity,
        "monitorObjectName": device,
        "resourceTemplateName": datasource,
        "dataPointName": datapoint,
        "alertValue": f"Alert {alert_id}",
        "startEpoch": start_epoch or BASE_EPOCH,
        "endEpoch": end_epoch,
        "cleared": cleared,
    }


class TestCalculateAvailability:
    """Tests for calculate_availability tool."""

    @respx.mock
    async def test_no_alerts_full_availability(self, client):
        """No alerts means 100% availability."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await calculate_availability(client)

        data = json.loads(result[0].text)
        assert data["availability_percent"] == 100.0
        assert data["total_downtime_minutes"] == 0
        assert data["incident_count"] == 0

    @respx.mock
    async def test_single_incident_reduces_availability(self, client):
        """A single incident reduces availability below 100%."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 3600  # 1 hour ago
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["availability_percent"] < 100.0
        assert data["total_downtime_minutes"] > 0
        assert data["incident_count"] == 1

    @respx.mock
    async def test_overlapping_incidents_merged(self, client):
        """Overlapping incidents are merged into one."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 7200
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 3600,
                cleared=True,
            ),
            _make_alert(
                2,
                "server01",
                "Memory",
                severity=3,
                start_epoch=recent + 1800,
                end_epoch=recent + 5400,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        dev_data = data["by_device"]["server01"]
        assert dev_data["incident_count"] == 1

    @respx.mock
    async def test_active_alert_counted_as_ongoing(self, client):
        """Active alert (endEpoch=0) counted as ongoing downtime."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 3600
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=0,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["total_downtime_minutes"] > 0

    @respx.mock
    async def test_mttr_calculated(self, client):
        """MTTR (mean time to repair) is calculated correctly."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 14400  # 4 hours ago
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
            _make_alert(
                2,
                "server01",
                "Memory",
                severity=3,
                start_epoch=recent + 7200,
                end_epoch=recent + 9000,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["mttr_minutes"] == 30.0  # 1800 sec = 30 min each

    @respx.mock
    async def test_per_device_breakdown(self, client):
        """Per-device breakdown is included in response."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 7200
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
            _make_alert(
                2,
                "server02",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 3600,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert "server01" in data["by_device"]
        assert "server02" in data["by_device"]

    @respx.mock
    async def test_severity_threshold(self, client):
        """Severity threshold is included in response."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await calculate_availability(client, severity_threshold="critical")

        data = json.loads(result[0].text)
        assert data["severity_threshold"] == "critical"

    @respx.mock
    async def test_longest_incident_tracked(self, client):
        """Longest incident duration is tracked."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 14400
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 7200,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["longest_incident_minutes"] == 120.0

    @respx.mock
    async def test_hours_back_in_response(self, client):
        """Response includes hours_back parameter."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await calculate_availability(client, hours_back=48)

        data = json.loads(result[0].text)
        assert data["hours_back"] == 48

    @respx.mock
    async def test_error_handling(self, client):
        """API errors are returned as error response."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await calculate_availability(client)

        assert is_error_result(result)

    @respx.mock
    async def test_device_id_reads_the_device_alerts(self, client):
        """device_id reads /device/devices/{id}/alerts; the alerts list ignores monitorObjectId."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=42)).mock(
            return_value=httpx.Response(200, json={"id": 42, "displayName": "server42"})
        )
        route = respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=42)).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(client, device_id=42)

        assert json.loads(result[0].text)["device_id"] == 42
        assert route.call_count == 2  # the active read, then the cleared read
        clauses = route.calls[0].request.url.params["filter"].split(",")
        assert clauses[0].startswith("startEpoch>:")
        assert clauses[1:] == ["severity>:3"]

    @respx.mock
    async def test_availability_filters_by_device_id(self, client):
        """calculate_availability only includes alerts for the target device."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 3600  # 1 hour ago

        # Mock device lookup
        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices/100").mock(
            return_value=httpx.Response(
                200,
                json={"id": 100, "displayName": "target-server"},
            )
        )

        # The device-scoped endpoint returns only the target's alerts
        alerts = [_device_alert("A1", 100, "target-server", recent, recent + 300)]
        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=100)).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, device_id=100, hours_back=24)
        data = json.loads(result[0].text)

        # The device's own alert list is the scope, counted under its name
        assert list(data["by_device"]) == ["target-server"]


# Base epoch for metric data
METRIC_BASE = 1705276800
DATA_URL = (
    "https://test.logicmonitor.com/santaba/rest"
    "/device/devices/1/devicedatasources/10/instances/100/data"
)


class TestScoringGuardrails:
    """Tests for best practice guardrails in scoring tools."""

    @respx.mock
    async def test_calculate_availability_measurement_context_low(self, client):
        """Low availability includes measurement_window_context."""
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        recent = now - 3600
        alerts = [
            _make_alert(
                1,
                "server01",
                "CPU",
                severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert "measurement_window_context" in data
        if data["availability_percent"] < 99.9:
            ctx = data["measurement_window_context"]
            assert "measurement_window_hours" in ctx
            assert "recommendations" in ctx
            assert "anti_patterns" in ctx
            assert len(ctx["recommendations"]) > 0


class TestAvailabilitySlo:
    """R2.3: calculate_availability(target_slo=) reports the error budget for its window."""

    @staticmethod
    def _outage(minutes):
        """One cleared incident of the given minutes, inside a 30-day window."""
        start = int(time.time()) - 30 * 24 * 3600 + 1000
        return [
            {
                "id": "a1",
                "severity": 3,
                "monitorObjectName": "server1",
                "startEpoch": start,
                "endEpoch": start + minutes * 60,
                "cleared": True,
            }
        ]

    @pytest.mark.parametrize(
        ("target", "minutes", "status", "consumed_percent"),
        [
            (99.9, 0, "healthy", 0.0),
            (99.9, 30, "warning", 69.44),
            (99.9, 40, "critical", 92.59),
            (99.9, 100, "exhausted", 231.48),
            (99.0, 60, "healthy", 13.89),
        ],
        ids=["no-downtime", "warning", "critical", "exhausted", "99.0"],
    )
    @respx.mock
    async def test_budget_follows_the_downtime(
        self, client, target, minutes, status, consumed_percent
    ):
        from lm_mcp.tools.scoring import calculate_availability

        cleared = self._outage(minutes) if minutes else []
        respx.get(ALERT_URL).mock(side_effect=alert_lists([], cleared))

        result = await calculate_availability(client, hours_back=720, target_slo=target)

        budget = json.loads(result[0].text)["error_budget"]
        assert budget["target_slo"] == target
        assert budget["period_days"] == 30
        assert budget["total_budget_minutes"] == round(43200 * (1 - target / 100), 2)
        assert budget["consumed_minutes"] == minutes
        assert budget["budget_consumed_percent"] == consumed_percent
        assert budget["status"] == status

    @respx.mock
    async def test_burn_rate_and_projected_exhaustion(self, client):
        """60 minutes of a 432-minute budget over 30 days: 372 left, gone in 186 days."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(side_effect=alert_lists([], self._outage(60)))

        result = await calculate_availability(client, hours_back=720, target_slo=99.0)

        budget = json.loads(result[0].text)["error_budget"]
        assert budget["remaining_minutes"] == 372.0
        assert budget["burn_rate"] == 0.1389
        assert budget["projected_exhaustion_days"] == 186.0

    @respx.mock
    async def test_a_100_percent_slo_without_downtime_is_healthy(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(side_effect=alert_lists([]))

        result = await calculate_availability(client, hours_back=720, target_slo=100.0)

        budget = json.loads(result[0].text)["error_budget"]
        assert budget["total_budget_minutes"] == 0.0
        assert budget["status"] == "healthy"
        assert budget["projected_exhaustion_days"] is None

    @respx.mock
    async def test_no_budget_without_a_target(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(side_effect=alert_lists([], self._outage(30)))

        result = await calculate_availability(client, hours_back=720)

        assert "error_budget" not in json.loads(result[0].text)

    @pytest.mark.parametrize("target", [0.0, -1.0, 100.5])
    @respx.mock
    async def test_target_outside_0_to_100_is_refused_before_any_read(self, client, target):
        from lm_mcp.tools.scoring import calculate_availability
        from tests.envelope import envelope

        result = await calculate_availability(client, target_slo=target)

        assert envelope(result)["code"] == "INVALID_REQUEST"
        assert len(respx.calls) == 0

    def test_calculate_error_budget_is_not_registered(self):
        from lm_mcp.registry import TOOLS, get_tool_handler

        tool = next(t for t in TOOLS if t.name == "calculate_availability")
        assert "target_slo" in tool.inputSchema["properties"]
        assert "calculate_error_budget" not in {t.name for t in TOOLS}
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_handler("calculate_error_budget")


DEVICE_URL_TEMPLATE = "https://test.logicmonitor.com/santaba/rest/device/devices/{id}"


class TestCalculateAvailabilityDeviceLookup:
    """Regression tests for the device-lookup silent-failure fix.

    Prior behavior: a 404/403 on the device lookup proceeded with
    unfiltered alerts, producing availability numbers for a different
    device set than the caller asked for. Now a device that does not exist
    returns NOT_FOUND and any other lookup failure returns the code
    lm_error_code gives it (a 403 is AUTH_FAILED), both before any alert is read.
    """

    @respx.mock
    async def test_404_on_device_lookup_returns_structured_error(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=99999)).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await calculate_availability(client, device_id=99999, hours_back=24)

        text = result[0].text
        assert is_error_result(result)
        assert "device 99999" in text.lower() or "99999" in text

    @respx.mock
    async def test_403_on_device_lookup_returns_structured_error(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=42)).mock(
            return_value=httpx.Response(403, json={"errorMessage": "Forbidden"})
        )

        result = await calculate_availability(client, device_id=42, hours_back=24)

        assert is_error_result(result)

    @respx.mock
    async def test_successful_device_lookup_reads_device_alerts(self, client):
        """Happy path: the device resolves, then its own alerts are read by id."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=100)).mock(
            side_effect=alert_lists(
                [_device_alert("a1", 100, "server1", int(time.time()) - 1000, 0)]
            )
        )
        respx.get(DEVICE_URL_TEMPLATE.format(id=100)).mock(
            return_value=httpx.Response(
                200, json={"id": 100, "displayName": "server1", "hostStatus": "normal"}
            )
        )

        result = await calculate_availability(client, device_id=100, hours_back=24)

        data = json.loads(result[0].text)
        assert "error" not in data or data.get("error") is False
        assert list(data["by_device"]) == ["server1"]


DEVICES_URL = "https://test.logicmonitor.com/santaba/rest/device/devices"
DEVICE_ALERTS_URL_TEMPLATE = DEVICES_URL + "/{id}/alerts"


def _device_alert(alert_id, device_id, name, start_epoch, end_epoch, severity=3):
    """An alert as /device/devices/{id}/alerts returns it: the id is the device's."""
    return {
        "id": f"LMA{alert_id}",
        "severity": severity,
        "monitorObjectId": device_id,
        "monitorObjectType": "device",
        "monitorObjectName": name,
        "startEpoch": start_epoch,
        "endEpoch": end_epoch,
        "cleared": end_epoch > 0,
    }


class TestAvailabilityResolvesDevice:
    """R4.3: calculate_availability resolves the device first and reads its alerts by id."""

    @respx.mock
    async def test_unknown_device_name_is_an_error_not_full_availability(self, client):
        from lm_mcp.tools import ErrorContent
        from lm_mcp.tools.scoring import calculate_availability

        route = respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(client, device_name="nope")

        assert isinstance(result[0], ErrorContent)
        assert "not found" in result[0].text.lower()
        assert "nope" in result[0].text
        assert route.calls[0].request.url.params["filter"] == 'displayName:"nope"'

    @respx.mock
    async def test_unknown_device_id_is_not_found(self, client):
        from lm_mcp.tools import ErrorContent
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=99999)).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        result = await calculate_availability(client, device_id=99999)

        assert isinstance(result[0], ErrorContent)
        assert "not found" in result[0].text.lower()
        assert "99999" in result[0].text

    @respx.mock
    async def test_device_id_counts_alerts_recorded_under_an_earlier_name(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        respx.get(DEVICE_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"id": 5, "displayName": "web-02"})
        )
        alerts = [
            _device_alert(1, 5, "web-01", now - 7200, now - 6600),
            _device_alert(2, 5, "web-02", now - 3600, now - 3000),
        ]
        route = respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=5)).mock(
            side_effect=alert_lists(alerts)
        )

        result = await calculate_availability(client, device_id=5, hours_back=24)

        data = json.loads(result[0].text)
        assert data["incident_count"] == 2
        assert list(data["by_device"]) == ["web-02"]
        assert data["by_device"]["web-02"]["incident_count"] == 2
        assert data["device_resolved"] is True
        assert data["device_id"] == 5
        assert "monitorObject" not in route.calls[0].request.url.params["filter"]

    @respx.mock
    async def test_device_name_resolves_to_the_device_alerts(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 5, "displayName": "web-02"}], "total": 1}
            )
        )
        alerts = [
            _device_alert(1, 5, "web-01", now - 7200, now - 6600),
            _device_alert(2, 5, "web-02", now - 3600, now - 3000),
        ]
        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=5)).mock(side_effect=alert_lists(alerts))

        result = await calculate_availability(client, device_name="web-02", hours_back=24)

        data = json.loads(result[0].text)
        assert data["incident_count"] == 2
        assert data["device_id"] == 5

    @respx.mock
    async def test_resolved_device_without_alerts_is_fully_available(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"id": 5, "displayName": "web-02"})
        )
        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(client, device_id=5)

        data = json.loads(result[0].text)
        assert data["availability_percent"] == 100.0
        assert data["incident_count"] == 0
        assert data["device_resolved"] is True
        assert data["truncated"] is False

    @respx.mock
    async def test_capped_window_is_declared(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        alerts = [
            _make_alert(
                i, f"dev-{i % 7}", "DS", severity=3, start_epoch=now - 7200 + i, end_epoch=now - 60
            )
            for i in range(6000)
        ]
        respx.get(ALERT_URL).mock(side_effect=alert_lists(alerts, lower_bound=True))

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["truncated"] is True
        assert data["api_total"] is None


class TestResolveDevice:
    """R4.3: _resolve_device separates a missing device from a failed lookup by code."""

    @respx.mock
    async def test_missing_device_id_is_device_not_found(self, client):
        from lm_mcp.tools.scoring import _resolve_device

        respx.get(DEVICE_URL_TEMPLATE.format(id=99999)).mock(
            return_value=httpx.Response(404, json={"errorMessage": "Device not found"})
        )

        assert (await _resolve_device(client, 99999, None))["code"] == "NOT_FOUND"

    @respx.mock
    async def test_missing_device_name_is_device_not_found(self, client):
        from lm_mcp.tools.scoring import _resolve_device

        respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        assert (await _resolve_device(client, None, "nope"))["code"] == "NOT_FOUND"

    @respx.mock
    async def test_forbidden_lookup_is_auth_failed(self, client):
        from lm_mcp.tools.scoring import _resolve_device

        respx.get(DEVICE_URL_TEMPLATE.format(id=42)).mock(
            return_value=httpx.Response(403, json={"errorMessage": "Forbidden"})
        )

        assert (await _resolve_device(client, 42, None))["code"] == "AUTH_FAILED"

    @respx.mock
    async def test_resolved_device_carries_id_and_name(self, client):
        from lm_mcp.tools.scoring import _resolve_device

        respx.get(DEVICES_URL).mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 5, "displayName": "web-02"}], "total": 1}
            )
        )

        assert await _resolve_device(client, None, "web-02") == {"id": 5, "displayName": "web-02"}


class TestAvailabilityDeviceWithGroup:
    """R4.3: a device and a group together have no single scope, so they are refused."""

    @pytest.mark.parametrize(
        "device_args", [{"device_id": 5}, {"device_name": "web-02"}], ids=["id", "name"]
    )
    @respx.mock
    async def test_device_with_group_is_refused_before_any_read(self, client, device_args):
        from lm_mcp.tools import ErrorContent
        from lm_mcp.tools.scoring import calculate_availability

        result = await calculate_availability(client, group_id=7, **device_args)

        assert isinstance(result[0], ErrorContent)
        assert "group_id" in result[0].text
        assert "not both" in result[0].text
        assert len(respx.calls) == 0

    @respx.mock
    async def test_group_alone_reads_the_group_alerts(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(f"{DEVICES_URL.rsplit('/', 1)[0]}/groups/7").mock(
            return_value=httpx.Response(200, json={"id": 7, "fullPath": "Sites/East"})
        )
        route = respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(client, group_id=7)

        data = json.loads(result[0].text)
        assert data["availability_percent"] == 100.0
        assert 'monitorObjectGroups~"Sites/East"' in route.calls[0].request.url.params["filter"]


class TestClearedAlerts:
    """R4.3: availability reads cleared alerts beside the active ones."""

    @respx.mock
    async def test_cleared_incident_counts_as_downtime(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        respx.get(DEVICE_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"id": 5, "displayName": "web-02"})
        )
        cleared = [_device_alert(1, 5, "web-02", now - 7200, now - 3600)]
        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=5)).mock(
            side_effect=alert_lists([], cleared)
        )

        result = await calculate_availability(client, device_id=5, hours_back=24)

        data = json.loads(result[0].text)
        assert data["incident_count"] == 1
        assert data["total_downtime_minutes"] == 60.0
        assert data["availability_percent"] < 100.0

    @pytest.mark.parametrize(
        ("call", "url"),
        [
            ("availability_portal", ALERT_URL),
            ("availability_device", DEVICE_ALERTS_URL_TEMPLATE.format(id=5)),
        ],
        ids=["availability-portal", "availability-device"],
    )
    @respx.mock
    async def test_cleared_read_repeats_the_active_clauses(self, client, call, url):
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(DEVICE_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"id": 5, "displayName": "web-02"})
        )
        route = respx.get(url).mock(side_effect=alert_lists([]))

        if call == "availability_portal":
            await calculate_availability(client, hours_back=24, severity_threshold="critical")
        else:
            await calculate_availability(client, device_id=5, hours_back=24)

        filters = [c.request.url.params["filter"].split(",") for c in route.calls]
        assert len(filters) == 2
        active, cleared = filters
        assert "cleared:true" not in active
        assert cleared == [*active, "cleared:true"]

    @respx.mock
    async def test_alert_in_both_lists_counts_once_as_cleared(self, client):
        from lm_mcp.tools.scoring import calculate_availability

        now = int(time.time())
        respx.get(DEVICE_URL_TEMPLATE.format(id=5)).mock(
            return_value=httpx.Response(200, json={"id": 5, "displayName": "web-02"})
        )
        # Cleared between the two reads: open in the active read, closed in the cleared one.
        active = [_device_alert(1, 5, "web-02", now - 7200, 0)]
        cleared = [_device_alert(1, 5, "web-02", now - 7200, now - 3600)]
        respx.get(DEVICE_ALERTS_URL_TEMPLATE.format(id=5)).mock(
            side_effect=alert_lists(active, cleared)
        )

        result = await calculate_availability(client, device_id=5, hours_back=24)

        data = json.loads(result[0].text)
        assert data["incident_count"] == 1
        assert data["total_downtime_minutes"] == 60.0

    @respx.mock
    async def test_failed_device_lookup_logs_a_warning(self, client, caplog):
        from lm_mcp.tools.scoring import _resolve_device

        respx.get(DEVICE_URL_TEMPLATE.format(id=42)).mock(
            return_value=httpx.Response(403, json={"errorMessage": "Forbidden"})
        )

        with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.scoring"):
            result = await _resolve_device(client, 42, None)

        assert result["code"] == "AUTH_FAILED"
        records = [r for r in caplog.records if r.name == "lm_mcp.tools.scoring"]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert "device 42" in records[0].getMessage()
        assert records[0].exc_info is not None
