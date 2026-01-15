# Description: Tests for Cost optimization MCP tools.
# Description: Validates cloud cost analysis and recommendation functions.

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


class TestGetCloudCostAccounts:
    """Tests for get_cloud_cost_accounts tool."""

    @respx.mock
    async def test_get_cloud_cost_accounts_returns_list(self, client):
        """get_cloud_cost_accounts returns properly formatted list."""
        from lm_mcp.tools.cost import get_cloud_cost_accounts

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/cloudaccounts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Production AWS",
                            "provider": "aws",
                            "accountId": "123456789",
                            "status": "active",
                            "lastUpdatedOn": 1702400000,
                        },
                        {
                            "id": 2,
                            "name": "Dev Azure",
                            "provider": "azure",
                            "accountId": "subscription-id",
                            "status": "active",
                            "lastUpdatedOn": 1702400000,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_cloud_cost_accounts(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["cloud_accounts"]) == 2
        assert data["cloud_accounts"][0]["provider"] == "aws"

    @respx.mock
    async def test_get_cloud_cost_accounts_with_provider_filter(self, client):
        """get_cloud_cost_accounts filters by provider."""
        from lm_mcp.tools.cost import get_cloud_cost_accounts

        route = respx.get("https://test.logicmonitor.com/santaba/rest/cost/cloudaccounts").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0})
        )

        await get_cloud_cost_accounts(client, provider="aws")

        assert "filter" in route.calls[0].request.url.params
        assert "provider:aws" in route.calls[0].request.url.params.get("filter", "")


class TestGetCostRecommendations:
    """Tests for get_cost_recommendations tool."""

    @respx.mock
    async def test_get_cost_recommendations_returns_list(self, client):
        """get_cost_recommendations returns recommendations."""
        from lm_mcp.tools.cost import get_cost_recommendations

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/recommendations").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "type": "rightsizing",
                            "resourceName": "web-server-01",
                            "resourceType": "ec2",
                            "currentCost": 100.00,
                            "projectedSavings": 40.00,
                            "recommendation": "Downsize from m5.xlarge to m5.large",
                            "confidence": "high",
                            "status": "open",
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_cost_recommendations(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["recommendations"][0]["type"] == "rightsizing"
        assert data["recommendations"][0]["projected_savings"] == 40.00


class TestGetCostSummary:
    """Tests for get_cost_summary tool."""

    @respx.mock
    async def test_get_cost_summary_returns_summary(self, client):
        """get_cost_summary returns cost summary data."""
        from lm_mcp.tools.cost import get_cost_summary

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/summary").mock(
            return_value=httpx.Response(
                200,
                json={
                    "totalCost": 5000.00,
                    "costTrend": "increasing",
                    "costByService": [
                        {"service": "EC2", "cost": 3000.00},
                        {"service": "RDS", "cost": 1500.00},
                    ],
                    "costByRegion": [{"region": "us-east-1", "cost": 4000.00}],
                    "projectedMonthlyCost": 5500.00,
                },
            )
        )

        result = await get_cost_summary(client, time_range="last30days")

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total_cost"] == 5000.00
        assert data["projected_monthly"] == 5500.00


class TestGetIdleResources:
    """Tests for get_idle_resources tool."""

    @respx.mock
    async def test_get_idle_resources_returns_list(self, client):
        """get_idle_resources returns idle resources."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get("https://test.logicmonitor.com/santaba/rest/cost/resources").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "unused-ebs-vol",
                            "resourceType": "ebs",
                            "cloudAccountName": "Production AWS",
                            "region": "us-east-1",
                            "utilization": 0,
                            "monthlyCost": 50.00,
                            "idleSince": 1702400000,
                        }
                    ],
                    "total": 1,
                },
            )
        )

        result = await get_idle_resources(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["idle_resources"][0]["resource_type"] == "ebs"
        assert data["idle_resources"][0]["utilization"] == 0


class TestGetCostRecommendationCategories:
    """Tests for get_cost_recommendation_categories tool (v224 API)."""

    @respx.mock
    async def test_get_cost_recommendation_categories_returns_list(self, client):
        """get_cost_recommendation_categories returns category list."""
        from lm_mcp.tools.cost import get_cost_recommendation_categories

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/categories"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "rightsizing",
                            "name": "Rightsizing",
                            "description": "Resize over-provisioned resources",
                            "count": 15,
                            "potentialSavings": 500.00,
                        },
                        {
                            "id": "idle",
                            "name": "Idle Resources",
                            "description": "Unused or underutilized resources",
                            "count": 8,
                            "potentialSavings": 200.00,
                        },
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_cost_recommendation_categories(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 2
        assert len(data["categories"]) == 2
        assert data["categories"][0]["id"] == "rightsizing"
        assert data["categories"][1]["potential_savings"] == 200.00


class TestGetCostRecommendation:
    """Tests for get_cost_recommendation tool (v224 API)."""

    @respx.mock
    async def test_get_cost_recommendation_returns_single(self, client):
        """get_cost_recommendation returns single recommendation by ID."""
        from lm_mcp.tools.cost import get_cost_recommendation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/123"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 123,
                    "category": "rightsizing",
                    "resourceName": "web-server-01",
                    "resourceType": "EC2 Instance",
                    "currentConfiguration": "m5.xlarge",
                    "recommendedConfiguration": "m5.large",
                    "currentCost": 150.00,
                    "projectedCost": 75.00,
                    "projectedSavings": 75.00,
                    "confidence": "high",
                    "status": "open",
                    "details": {
                        "cpuUtilization": 15.5,
                        "memoryUtilization": 22.3,
                    },
                },
            )
        )

        result = await get_cost_recommendation(client, recommendation_id=123)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["id"] == 123
        assert data["category"] == "rightsizing"
        assert data["projected_savings"] == 75.00
        assert data["recommended_configuration"] == "m5.large"

    @respx.mock
    async def test_get_cost_recommendation_not_found(self, client):
        """get_cost_recommendation handles not found error."""
        from lm_mcp.tools.cost import get_cost_recommendation

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/999"
        ).mock(return_value=httpx.Response(404, json={"errorMessage": "Not found"}))

        result = await get_cost_recommendation(client, recommendation_id=999)

        assert len(result) == 1
        assert "error" in result[0].text.lower() or "404" in result[0].text
