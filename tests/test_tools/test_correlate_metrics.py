# Description: Tests for correlate_metrics, the Pearson correlation of metric series.
# Description: Covers the correlation matrix, source limits, labels and sample counts.

import json

import httpx
import pytest
import respx

from lm_mcp.auth.bearer import BearerAuth
from lm_mcp.client import LogicMonitorClient
from lm_mcp.tools import is_error_result


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


class TestCorrelateMetrics:
    """Tests for correlate_metrics tool."""

    @respx.mock
    async def test_perfect_positive_correlation(self, client):
        """Perfectly correlated metrics return r=1."""
        from lm_mcp.tools.correlation import correlate_metrics

        for dev_id in [1, 2]:
            respx.get(
                f"https://test.logicmonitor.com/santaba/rest"
                f"/device/devices/{dev_id}/devicedatasources/10/instances/100/data"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dataPoints": ["cpu"],
                        "values": [[float(10 + i * 5)] for i in range(10)],
                        "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(10)],
                    },
                )
            )

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        data = json.loads(result[0].text)
        assert data["correlation_matrix"][0][1] == 1.0
        assert len(data["strong_correlations"]) > 0

    @respx.mock
    async def test_negative_correlation(self, client):
        """Inversely correlated metrics return negative r."""
        from lm_mcp.tools.correlation import correlate_metrics

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": [[float(10 + i * 5)] for i in range(10)],
                    "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(10)],
                },
            )
        )
        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/2/devicedatasources/10/instances/100/data"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dataPoints": ["cpu"],
                    "values": [[float(100 - i * 5)] for i in range(10)],
                    "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(10)],
                },
            )
        )

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        data = json.loads(result[0].text)
        assert data["correlation_matrix"][0][1] < -0.7

    @respx.mock
    async def test_too_many_sources_rejected(self, client):
        """More than 10 sources returns error."""
        from lm_mcp.tools.correlation import correlate_metrics

        sources = [
            {"device_id": i, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"}
            for i in range(11)
        ]

        result = await correlate_metrics(client, sources=sources)

        assert "Error:" in result[0].text or "Maximum 10" in result[0].text

    @respx.mock
    async def test_fewer_than_two_sources_rejected(self, client):
        """Fewer than 2 sources returns error."""
        from lm_mcp.tools.correlation import correlate_metrics

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        assert "Error:" in result[0].text or "At least 2" in result[0].text

    @respx.mock
    async def test_diagonal_is_one(self, client):
        """Diagonal of correlation matrix is all 1.0."""
        from lm_mcp.tools.correlation import correlate_metrics

        for dev_id in [1, 2, 3]:
            respx.get(
                f"https://test.logicmonitor.com/santaba/rest"
                f"/device/devices/{dev_id}/devicedatasources/10/instances/100/data"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dataPoints": ["cpu"],
                        "values": [[float(10 + i + dev_id)] for i in range(10)],
                        "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(10)],
                    },
                )
            )

        sources = [
            {"device_id": d, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"}
            for d in [1, 2, 3]
        ]

        result = await correlate_metrics(client, sources=sources)

        data = json.loads(result[0].text)
        for i in range(3):
            assert data["correlation_matrix"][i][i] == 1.0

    @respx.mock
    async def test_response_includes_labels(self, client):
        """Response includes labels for each source."""
        from lm_mcp.tools.correlation import correlate_metrics

        for dev_id in [1, 2]:
            respx.get(
                f"https://test.logicmonitor.com/santaba/rest"
                f"/device/devices/{dev_id}/devicedatasources/10/instances/100/data"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dataPoints": ["cpu"],
                        "values": [[50.0 + i] for i in range(5)],
                        "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(5)],
                    },
                )
            )

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        data = json.loads(result[0].text)
        assert "labels" in data
        assert len(data["labels"]) == 2

    @respx.mock
    async def test_sample_count_in_response(self, client):
        """Response includes the sample count used for correlation."""
        from lm_mcp.tools.correlation import correlate_metrics

        for dev_id in [1, 2]:
            respx.get(
                f"https://test.logicmonitor.com/santaba/rest"
                f"/device/devices/{dev_id}/devicedatasources/10/instances/100/data"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dataPoints": ["cpu"],
                        "values": [[50.0 + i] for i in range(8)],
                        "time": [(BASE_EPOCH + i * 300) * 1000 for i in range(8)],
                    },
                )
            )

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        data = json.loads(result[0].text)
        assert data["sample_count"] == 8

    @respx.mock
    async def test_insufficient_data(self, client):
        """Insufficient overlapping data returns error."""
        from lm_mcp.tools.correlation import correlate_metrics

        for dev_id in [1, 2]:
            respx.get(
                f"https://test.logicmonitor.com/santaba/rest"
                f"/device/devices/{dev_id}/devicedatasources/10/instances/100/data"
            ).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "dataPoints": ["cpu"],
                        "values": [[50.0]],
                        "time": [BASE_EPOCH * 1000],
                    },
                )
            )

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        assert "Insufficient" in result[0].text or "Error:" in result[0].text

    @respx.mock
    async def test_error_handling(self, client):
        """API errors are returned as error response."""
        from lm_mcp.tools.correlation import correlate_metrics

        respx.get(
            "https://test.logicmonitor.com/santaba/rest"
            "/device/devices/1/devicedatasources/10/instances/100/data"
        ).mock(return_value=httpx.Response(500, json={"errorMessage": "error"}))

        sources = [
            {"device_id": 1, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
            {"device_id": 2, "device_datasource_id": 10, "instance_id": 100, "datapoint": "cpu"},
        ]

        result = await correlate_metrics(client, sources=sources)

        assert is_error_result(result)
