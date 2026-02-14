# Description: Tests for topology-based analysis tools.
# Description: Validates analyze_blast_radius for downstream impact assessment.

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
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await analyze_blast_radius(client, device_id=1, depth=1)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 2
        assert data["device_id"] == 1
        assert data["blast_radius_score"] >= 20

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
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await analyze_blast_radius(client, device_id=1, depth=2)

        data = json.loads(result[0].text)
        assert data["total_affected_devices"] == 2
        # Device 2 at depth 1, device 3 at depth 2
        depths = {d["device_id"]: d["depth"] for d in data["affected_devices"]}
        assert depths[2] == 1
        assert depths[3] == 2

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
        assert data["blast_radius_score"] == 0

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
    async def test_critical_alerts_increase_score(self, client):
        """Neighbors with critical alerts increase blast radius score."""
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
        assert data["critical_alert_count"] >= 1
        assert data["blast_radius_score"] > 10

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
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

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
        assert "blast_radius_score" in data
        assert "affected_devices" in data
        assert "critical_path_devices" in data

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
        respx.get(ALERT_URL).mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

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
