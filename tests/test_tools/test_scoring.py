# Description: Tests for scoring and availability analysis tools.
# Description: Validates score_alert_noise, calculate_availability, score_device_health.

import json
import time

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


# Base epoch for test data (2024-01-15 00:00:00 UTC)
BASE_EPOCH = 1705276800
ALERT_URL = "https://test.logicmonitor.com/santaba/rest/alert/alerts"


def _make_alert(
    alert_id, device, datasource, datapoint="value",
    severity=4, start_epoch=None, end_epoch=0, cleared=False,
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


class TestScoreAlertNoise:
    """Tests for score_alert_noise tool."""

    @respx.mock
    async def test_no_alerts_zero_noise(self, client):
        """No alerts produces noise score of 0."""
        from lm_mcp.tools.scoring import score_alert_noise

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["noise_score"] == 0
        assert data["total_alerts"] == 0

    @respx.mock
    async def test_single_alert_low_noise(self, client):
        """Single alert produces low noise score."""
        from lm_mcp.tools.scoring import score_alert_noise

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"items": [_make_alert(1, "s1", "CPU")], "total": 1},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["noise_score"] <= 30
        assert data["total_alerts"] == 1

    @respx.mock
    async def test_flapping_alerts_detected(self, client):
        """Flapping alerts (clear + re-fire within 30 min) are detected."""
        from lm_mcp.tools.scoring import score_alert_noise

        alerts = [
            _make_alert(
                1, "s1", "CPU", "value",
                start_epoch=BASE_EPOCH,
                end_epoch=BASE_EPOCH + 300,
                cleared=True,
            ),
            _make_alert(
                2, "s1", "CPU", "value",
                start_epoch=BASE_EPOCH + 600,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 2},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["flap_count"] > 0
        assert len(data["flapping_alerts"]) > 0

    @respx.mock
    async def test_repeat_alerts_increase_noise(self, client):
        """Repeated alerts from same source increase noise."""
        from lm_mcp.tools.scoring import score_alert_noise

        alerts = [
            _make_alert(i, "s1", "CPU", "value", start_epoch=BASE_EPOCH + i * 60)
            for i in range(10)
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 10},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["total_alerts"] == 10
        assert data["repeat_ratio"] > 0

    @respx.mock
    async def test_top_noisy_devices(self, client):
        """Top noisy devices are ranked by alert count."""
        from lm_mcp.tools.scoring import score_alert_noise

        alerts = [
            _make_alert(1, "noisy-server", "CPU"),
            _make_alert(2, "noisy-server", "Memory"),
            _make_alert(3, "noisy-server", "Disk"),
            _make_alert(4, "quiet-server", "CPU"),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 4},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["top_noisy_devices"][0]["device"] == "noisy-server"
        assert data["top_noisy_devices"][0]["count"] == 3

    @respx.mock
    async def test_top_noisy_datasources(self, client):
        """Top noisy datasources are ranked by alert count."""
        from lm_mcp.tools.scoring import score_alert_noise

        alerts = [
            _make_alert(1, "s1", "CPU"),
            _make_alert(2, "s2", "CPU"),
            _make_alert(3, "s3", "CPU"),
            _make_alert(4, "s1", "Memory"),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 4},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert data["top_noisy_datasources"][0]["datasource"] == "CPU"
        assert data["top_noisy_datasources"][0]["count"] == 3

    @respx.mock
    async def test_recommendations_present(self, client):
        """Response always includes recommendations."""
        from lm_mcp.tools.scoring import score_alert_noise

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0

    @respx.mock
    async def test_device_filter_passed(self, client):
        """Device filter is passed to the API."""
        from lm_mcp.tools.scoring import score_alert_noise

        route = respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await score_alert_noise(client, device="server01")

        params = dict(route.calls[0].request.url.params)
        assert "monitorObjectName" in params.get("filter", "")

    @respx.mock
    async def test_group_id_filter_passed(self, client):
        """Group ID filter is passed to the API."""
        from lm_mcp.tools.scoring import score_alert_noise

        route = respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await score_alert_noise(client, group_id=5)

        params = dict(route.calls[0].request.url.params)
        assert "hostGroupIds" in params.get("filter", "")

    @respx.mock
    async def test_hours_back_in_response(self, client):
        """Response includes hours_back parameter."""
        from lm_mcp.tools.scoring import score_alert_noise

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await score_alert_noise(client, hours_back=48)

        data = json.loads(result[0].text)
        assert data["hours_back"] == 48

    @respx.mock
    async def test_error_handling(self, client):
        """API errors are returned as error response."""
        from lm_mcp.tools.scoring import score_alert_noise

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await score_alert_noise(client)

        assert "Error:" in result[0].text

    @respx.mock
    async def test_noise_score_bounded(self, client):
        """Noise score is bounded between 0 and 100."""
        from lm_mcp.tools.scoring import score_alert_noise

        # Many diverse alerts to push entropy up
        alerts = [
            _make_alert(i, f"server{i}", f"DS{i}", f"dp{i}")
            for i in range(50)
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 50},
            )
        )

        result = await score_alert_noise(client)

        data = json.loads(result[0].text)
        assert 0 <= data["noise_score"] <= 100


class TestCalculateAvailability:
    """Tests for calculate_availability tool."""

    @respx.mock
    async def test_no_alerts_full_availability(self, client):
        """No alerts means 100% availability."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 1},
            )
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 3600,
                cleared=True,
            ),
            _make_alert(
                2, "server01", "Memory", severity=3,
                start_epoch=recent + 1800,
                end_epoch=recent + 5400,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 2},
            )
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=0,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 1},
            )
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
            _make_alert(
                2, "server01", "Memory", severity=3,
                start_epoch=recent + 7200,
                end_epoch=recent + 9000,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 2},
            )
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 1800,
                cleared=True,
            ),
            _make_alert(
                2, "server02", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 3600,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 2},
            )
        )

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert "server01" in data["by_device"]
        assert "server02" in data["by_device"]

    @respx.mock
    async def test_severity_threshold(self, client):
        """Severity threshold is included in response."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(
            client, severity_threshold="critical"
        )

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
                1, "server01", "CPU", severity=3,
                start_epoch=recent,
                end_epoch=recent + 7200,
                cleared=True,
            ),
        ]
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200, json={"items": alerts, "total": 1},
            )
        )

        result = await calculate_availability(client, hours_back=24)

        data = json.loads(result[0].text)
        assert data["longest_incident_minutes"] == 120.0

    @respx.mock
    async def test_hours_back_in_response(self, client):
        """Response includes hours_back parameter."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await calculate_availability(client, hours_back=48)

        data = json.loads(result[0].text)
        assert data["hours_back"] == 48

    @respx.mock
    async def test_error_handling(self, client):
        """API errors are returned as error response."""
        from lm_mcp.tools.scoring import calculate_availability

        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                500, json={"errorMessage": "Server error"}
            )
        )

        result = await calculate_availability(client)

        assert "Error:" in result[0].text

    @respx.mock
    async def test_device_id_filter(self, client):
        """Device ID filter is passed to the API."""
        from lm_mcp.tools.scoring import calculate_availability

        route = respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await calculate_availability(client, device_id=42)

        params = dict(route.calls[0].request.url.params)
        assert "monitorObjectId:42" in params.get("filter", "")


# Base epoch for metric data
METRIC_BASE = 1705276800
DATA_URL = (
    "https://test.logicmonitor.com/santaba/rest"
    "/device/devices/1/devicedatasources/10/instances/100/data"
)


class TestScoreDeviceHealth:
    """Tests for score_device_health tool."""

    @respx.mock
    async def test_healthy_device(self, client):
        """Normal data produces healthy score."""
        from lm_mcp.tools.scoring import score_device_health

        values = [[50.0]] * 20
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(20)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert data["health_score"] >= 80
        assert data["status"] == "healthy"

    @respx.mock
    async def test_anomalous_data_low_score(self, client):
        """Data with anomalous latest value produces low health score."""
        from lm_mcp.tools.scoring import score_device_health

        # 19 normal values around 50, then a spike to 500
        values = [[50.0]] * 19 + [[500.0]]
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(20)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert data["health_score"] < 80
        assert data["anomaly_count"] >= 1

    @respx.mock
    async def test_empty_data_returns_unknown(self, client):
        """No metric data returns unknown status."""
        from lm_mcp.tools.scoring import score_device_health

        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={"dataPoints": [], "values": [], "time": []},
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert data["status"] == "unknown"

    @respx.mock
    async def test_multiple_datapoints(self, client):
        """Multiple datapoints each contribute to health score."""
        from lm_mcp.tools.scoring import score_device_health

        values = [[50.0, 70.0]] * 20
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu", "memory"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(20)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert len(data["contributing_factors"]) == 2

    @respx.mock
    async def test_factors_sorted_by_impact(self, client):
        """Contributing factors are sorted by weighted impact."""
        from lm_mcp.tools.scoring import score_device_health

        # cpu normal, memory has spike
        values = [[50.0, 70.0]] * 19 + [[50.0, 300.0]]
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu", "memory"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(20)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        factors = data["contributing_factors"]
        assert factors[0]["datapoint"] == "memory"

    @respx.mock
    async def test_response_structure(self, client):
        """Response includes all expected fields."""
        from lm_mcp.tools.scoring import score_device_health

        values = [[50.0]] * 10
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(10)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert "health_score" in data
        assert "status" in data
        assert "contributing_factors" in data
        assert "anomaly_count" in data
        assert data["device_id"] == 1

    @respx.mock
    async def test_health_score_bounded(self, client):
        """Health score is bounded between 0 and 100."""
        from lm_mcp.tools.scoring import score_device_health

        # Extreme anomaly to test lower bound
        values = [[50.0]] * 19 + [[99999.0]]
        respx.get(DATA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": values,
                    "time": [
                        (METRIC_BASE + i * 300) * 1000 for i in range(20)
                    ],
                },
            )
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        data = json.loads(result[0].text)
        assert 0 <= data["health_score"] <= 100

    @respx.mock
    async def test_error_handling(self, client):
        """API errors are returned as error response."""
        from lm_mcp.tools.scoring import score_device_health

        respx.get(DATA_URL).mock(
            return_value=httpx.Response(500, json={"errorMessage": "error"})
        )

        result = await score_device_health(
            client, device_id=1, device_datasource_id=10, instance_id=100,
        )

        assert "Error:" in result[0].text
