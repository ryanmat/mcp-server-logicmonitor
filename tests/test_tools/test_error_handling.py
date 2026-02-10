# Description: Error handling tests for undertested tool modules.
# Description: Validates 404, 500, and 403 responses for cost, topology, and batchjob tools.

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
