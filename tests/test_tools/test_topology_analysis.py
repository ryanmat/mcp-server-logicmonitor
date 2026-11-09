# Description: Tests for topology-based analysis tools.
# Description: Validates analyze_blast_radius for downstream impact assessment.

import json
import logging

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
        max_retries=0,
    )


BASE_URL = "https://test.logicmonitor.com/santaba/rest"
ALERT_URL = f"{BASE_URL}/alert/alerts"


class TestAnalyzeBlastRadius:
    """Tests for analyze_blast_radius tool."""

    @respx.mock
    async def test_single_depth_neighbors(self, client):
        """Finds neighbors at depth 1."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 2, "displayName": "switch-01"},
                        {"id": 3, "displayName": "switch-02"},
                    ],
                },
            )
        )
        # Alert checks for each neighbor
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 2
        assert data["device_id"] == 1
        assert data["neighbor_count"] == 2
        assert data["dependent_count"] == 0
        assert data["unreadable"] == []

    @respx.mock
    async def test_multi_depth_traversal(self, client):
        """Traverses neighbors at multiple depths."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 2, "displayName": "switch-01"}]},
            )
        )
        respx.get(f"{BASE_URL}/topology/devices/2/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 3, "displayName": "server-01"}]},
            )
        )
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await analyze_blast_radius(client, device_id=1, depth=2)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 2
        # Device 2 at depth 1, device 3 at depth 2
        depths = {d["device_id"]: d["depth"] for d in data["affected_devices"]}
        assert depths[2] == 1
        assert depths[3] == 2
        assert data["neighbor_count"] == 1
        assert data["dependent_count"] == 1

    @respx.mock
    async def test_no_neighbors(self, client):
        """Device with no neighbors returns zero blast radius."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(200, json={"items": []})
        )

        result = await analyze_blast_radius(client, device_id=1)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 0
        assert data["neighbor_count"] == 0
        assert data["unreadable"] == []

    @respx.mock
    async def test_alert_lookup_failure_marks_degraded(self, client):
        """A failed per-device alert lookup is surfaced, not silently treated as healthy."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(200, json={"items": [{"id": 2, "displayName": "sw"}]})
        )
        # The per-device alert query fails -> the device's alert status is unknown.
        respx.get(ALERT_URL).mock(return_value=httpx.Response(500, json={"errorMessage": "boom"}))

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        assert data["degraded"] is True
        dev = data["affected_devices"][0]
        assert dev["alert_status_unavailable"] is True
        # Not a confident "healthy" -- the critical status is unknown.
        assert dev["has_critical"] is None

    @respx.mock
    async def test_depth_capped_at_three(self, client):
        """Depth is capped at maximum of 3."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(200, json={"items": []})
        )

        result = await analyze_blast_radius(client, device_id=1, depth=10)

        data = json.loads(result[0].text)
        assert data["depth"] == 3

    @respx.mock
    async def test_critical_alerts_are_counted(self, client):
        """A neighbor with a critical alert counts toward critical_alert_count."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 2, "displayName": "switch-01"}]},
            )
        )
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": "LMA1", "severity": 4, "cleared": False}],
                    "total": 1,
                },
            )
        )

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        assert data["critical_alert_count"] == 1

    @respx.mock
    async def test_avoids_revisiting_source_device(self, client):
        """Source device is not included in affected devices."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {"id": 2, "displayName": "switch-01"},
                        {"id": 1, "displayName": "source-device"},
                    ],
                },
            )
        )
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        device_ids = [d["device_id"] for d in data["affected_devices"]]
        assert 1 not in device_ids
        assert data["total_affected_devices"] == 1

    @respx.mock
    async def test_response_structure(self, client):
        """Response has all expected fields."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(200, json={"items": []})
        )

        result = await analyze_blast_radius(client, device_id=1)

        data = json.loads(result[0].text)
        assert "device_id" in data
        assert "depth" in data
        assert "total_affected_devices" in data
        assert "neighbor_count" in data
        assert "dependent_count" in data
        assert "unreadable" in data
        assert "affected_devices" in data
        assert "critical_path_devices" in data
        assert "blast_radius_score" not in data

    @respx.mock
    async def test_topology_api_fallback(self, client):
        """Falls back to device neighbors endpoint on topology failure."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )
        respx.get(f"{BASE_URL}/device/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"id": 2, "displayName": "neighbor-01"}]},
            )
        )
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 1

    @respx.mock
    async def test_error_handling(self, client):
        """Unexpected errors are returned as error response."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get(f"{BASE_URL}/device/devices/1/neighbors").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await analyze_blast_radius(client, device_id=1)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 0
        assert data["unreadable"] == [1]


class TestBlastRadiusUnreadable:
    """R2.3: a neighbor read neither path answers is logged and reported, never a zero."""

    @respx.mock
    async def test_route_missing_on_both_paths_is_unreadable(self, client, caplog):
        """The live portal answers both paths with errorCode 1400, a route it lacks."""
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        missing = {"errorMessage": "HTTP 404 Not Found", "errorCode": 1400, "errorDetail": None}
        respx.get(f"{BASE_URL}/topology/devices/1786/neighbors").mock(
            return_value=httpx.Response(404, json=missing)
        )
        respx.get(f"{BASE_URL}/device/devices/1786/neighbors").mock(
            return_value=httpx.Response(404, json=missing)
        )

        with caplog.at_level(logging.WARNING, logger="lm_mcp.tools.topology_analysis"):
            result = await analyze_blast_radius(client, device_id=1786, depth=2)

        data = json.loads(result[0].text)
        assert data["unreadable"] == [1786]
        assert data["neighbor_count"] == 0
        assert "warning" in data
        records = [r for r in caplog.records if r.name == "lm_mcp.tools.topology_analysis"]
        assert [r.levelno for r in records] == [logging.WARNING]
        assert "1786" in records[0].getMessage()
        assert records[0].exc_info is not None

    @respx.mock
    async def test_one_unreadable_neighbor_leaves_the_rest_counted(self, client):
        from lm_mcp.tools.topology_analysis import analyze_blast_radius

        respx.get(f"{BASE_URL}/topology/devices/1/neighbors").mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": 2, "displayName": "a"}, {"id": 3, "displayName": "b"}]}
            )
        )
        respx.get(f"{BASE_URL}/topology/devices/2/neighbors").mock(
            return_value=httpx.Response(200, json={"items": [{"id": 4, "displayName": "c"}]})
        )
        respx.get(f"{BASE_URL}/topology/devices/3/neighbors").mock(
            return_value=httpx.Response(500, json={"errorMessage": "boom"})
        )
        respx.get(f"{BASE_URL}/device/devices/3/neighbors").mock(
            return_value=httpx.Response(500, json={"errorMessage": "boom"})
        )
        respx.get(ALERT_URL).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        result = await analyze_blast_radius(client, device_id=1, depth=2)

        data = json.loads(result[0].text)
        assert data["neighbor_count"] == 2
        assert data["dependent_count"] == 1
        assert data["unreadable"] == [3]
