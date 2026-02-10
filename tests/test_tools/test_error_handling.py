# Description: Error handling tests for undertested tool modules.
# Description: Validates error responses for cost, topology, batchjob, and audit tools.

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
        max_retries=0,
    )


class TestCostToolErrors:
    """Error handling tests for cost tools."""

    @respx.mock
    async def test_get_cost_summary_404(self, client):
        """get_cost_summary handles 404 response."""
        from lm_mcp.tools.cost import get_cost_summary

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/summary").mock(
            return_value=httpx.Response(404, json={"errorMessage": "Not found"})
        )

        result = await get_cost_summary(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()

    @respx.mock
    async def test_get_cost_recommendations_500(self, client):
        """get_cost_recommendations handles 500 response."""
        from lm_mcp.tools.cost import get_cost_recommendations

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/recommendations").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Internal server error"})
        )

        result = await get_cost_recommendations(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()

    @respx.mock
    async def test_get_cloud_cost_accounts_403(self, client):
        """get_cloud_cost_accounts handles 403 forbidden response."""
        from lm_mcp.tools.cost import get_cloud_cost_accounts

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/cloudaccounts").mock(
            return_value=httpx.Response(403, json={"errorMessage": "Forbidden"})
        )

        result = await get_cloud_cost_accounts(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()


class TestTopologyToolErrors:
    """Error handling tests for topology tools."""

    @respx.mock
    async def test_get_device_neighbors_404(self, client):
        """get_device_neighbors handles 404 for invalid device."""
        from lm_mcp.tools.topology import get_device_neighbors

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/9999/neighbors"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Device not found"}))

        result = await get_device_neighbors(client, device_id=9999)
        assert "Error" in result[0].text or "error" in result[0].text.lower()

    @respx.mock
    async def test_get_topology_map_500(self, client):
        """get_topology_map handles 500 response."""
        from lm_mcp.tools.topology import get_topology_map

        respx.get("https://test.logicmonitor.com/santaba/rest/topology/topologies").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_topology_map(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()


class TestBatchjobToolErrors:
    """Error handling tests for batchjob tools."""

    @respx.mock
    async def test_get_batchjob_404(self, client):
        """get_batchjob handles 404 for invalid job ID."""
        from lm_mcp.tools.batchjobs import get_batchjob

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/batchjobs/9999"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Not found"}))

        result = await get_batchjob(client, batchjob_id=9999)
        assert "Error" in result[0].text or "error" in result[0].text.lower()

    @respx.mock
    async def test_get_batchjobs_500(self, client):
        """get_batchjobs handles 500 response."""
        from lm_mcp.tools.batchjobs import get_batchjobs

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/batchjobs").mock(
            return_value=httpx.Response(500, json={"errorMessage": "Server error"})
        )

        result = await get_batchjobs(client)
        assert "Error" in result[0].text or "error" in result[0].text.lower()

    @respx.mock
    async def test_get_device_batchjobs_404(self, client):
        """get_device_batchjobs handles 404 for invalid device."""
        from lm_mcp.tools.batchjobs import get_device_batchjobs

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/device/devices/9999/batchjobs"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Device not found"}))

        result = await get_device_batchjobs(client, device_id=9999)
        assert "Error" in result[0].text or "error" in result[0].text.lower()


class TestAuditToolErrors:
    """Tests for audit tool bug fix where happenedOn is epoch int, not string."""

    @respx.mock
    async def test_get_change_audit_handles_int_happenedOn(self, client):
        """get_change_audit handles happenedOn as epoch integer."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "log1",
                            "username": "admin",
                            "happenedOn": 1702500000,
                            "happenedOnLocal": "2023-12-14 10:00:00",
                            "description": '"Action=Update"; "Type=Device"',
                            "ip": "192.168.1.1",
                        },
                        {
                            "id": "log2",
                            "username": "admin",
                            "happenedOn": 1702500060,
                            "happenedOnLocal": "2023-12-14 10:01:00",
                            "description": "User logged in",
                            "ip": "192.168.1.1",
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_change_audit(client)
        assert len(result) == 1
        # Only the Update entry should be included, not the login
        assert "Update" in result[0].text
        assert "logged in" not in result[0].text

    @respx.mock
    async def test_get_change_audit_empty_items(self, client):
        """get_change_audit handles empty results gracefully."""
        from lm_mcp.tools.audit import get_change_audit

        respx.get("https://test.logicmonitor.com/santaba/rest/setting/accesslogs").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        result = await get_change_audit(client)
        assert len(result) == 1
        assert "0" in result[0].text
