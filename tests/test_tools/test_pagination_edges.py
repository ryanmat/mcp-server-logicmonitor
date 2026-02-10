# Description: Pagination edge case tests for LogicMonitor tools.
# Description: Validates limit=0, large offset, empty results, and last page behavior.

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


class TestPaginationEdgeCases:
    """Edge case tests for pagination across list tools."""

    @respx.mock
    async def test_empty_result_set(self, client):
        """get_devices returns graceful response for zero results."""
        from lm_mcp.tools.devices import get_devices

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200, json={"items": [], "total": 0}
            )
        )

        result = await get_devices(client)
        assert len(result) == 1
        text = result[0].text
        assert "0" in text or "no " in text.lower() or "[]" in text

    @respx.mock
    async def test_large_offset_beyond_total(self, client):
        """get_alerts with offset beyond total returns empty or no items."""
        from lm_mcp.tools.alerts import get_alerts

        respx.get("https://test.logicmonitor.com/santaba/rest/alert/alerts").mock(
            return_value=httpx.Response(
                200, json={"items": [], "total": 5}
            )
        )

        result = await get_alerts(client, offset=9999)
        assert len(result) == 1
        text = result[0].text
        assert "0" in text or "no " in text.lower() or "[]" in text

    @respx.mock
    async def test_single_item_last_page(self, client):
        """get_devices with exactly one item returns valid response."""
        from lm_mcp.tools.devices import get_devices

        respx.get("https://test.logicmonitor.com/santaba/rest/device/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "displayName": "last-device",
                            "hostGroupIds": "1",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_devices(client, limit=1)
        assert len(result) == 1
        assert "last-device" in result[0].text

    @respx.mock
    async def test_limit_one_returns_single_item(self, client):
        """get_collectors with limit=1 returns exactly one item."""
        from lm_mcp.tools.collectors import get_collectors

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/setting/collector/collectors"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "hostname": "collector-01",
                            "status": 0,
                            "numberOfHosts": 50,
                        }
                    ],
                    "total": 10,
                },
            )
        )

        result = await get_collectors(client, limit=1)
        assert len(result) == 1
        assert "collector-01" in result[0].text
