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


def _recommendation_item(**overrides) -> dict:
    """Live-shaped Cost Optimization recommendation item."""
    item = {
        "id": "397-449492-AZURE_VM_UNDERUTILIZED",
        "recommendationId": 9905,
        "recommendationCategory": "Underutilized Azure VM instances",
        "cloudAccountId": "sub-1",
        "resourceId": 449492,
        "providerConsoleUrl": "https://portal.azure.com/#@x/resource/y",
        "annualSavings": 5220.96,
        "resourceDisplayName": "us-e1:vm:openshift-odf",
        "cloudProvider": "Azure",
        "cloudServiceType": "AZURE_VM",
        "recommendation": "Change Azure VM type to Standard_DC4as_v5",
        "criteria": "Max CPU < 40.00% for the last 14 days",
        "recommendationStatus": "ACTIVE",
    }
    item.update(overrides)
    return item


_CATEGORY_ITEMS = [
    {"name": "EC2_IDLE", "description": "Idle AWS EC2 instances"},
    {"name": "AZURE_VM_UNDERUTILIZED", "description": "Underutilized Azure VM instances"},
    {"name": "EBS_UNATTACHED", "description": "Unattached AWS EBS volumes"},
    # Not idle-type: must be excluded from get_idle_resources resolution
    {"name": "RESERVED_INSTANCE_PURCHASE", "description": "Reserved instance purchase options"},
]


class TestGetCostRecommendations:
    """Tests for get_cost_recommendations tool (Cost Optimization API)."""

    @respx.mock
    async def test_get_cost_recommendations_returns_list(self, client):
        """get_cost_recommendations returns projected recommendations."""
        from lm_mcp.tools.cost import get_cost_recommendations

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations"
        ).mock(
            return_value=httpx.Response(200, json={"items": [_recommendation_item()], "total": 1})
        )

        result = await get_cost_recommendations(client)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["total"] == 1
        rec = data["recommendations"][0]
        assert rec["category"] == "Underutilized Azure VM instances"
        assert rec["annual_savings"] == 5220.96
        assert rec["status"] == "ACTIVE"
        assert rec["cloud_provider"] == "Azure"

    @respx.mock
    async def test_get_cost_recommendations_category_and_status_filters(self, client):
        """Category uses the description string; status is uppercased."""
        from lm_mcp.tools.cost import get_cost_recommendations

        route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations"
        ).mock(return_value=httpx.Response(200, json={"items": [], "total": 0}))

        await get_cost_recommendations(client, category="Idle AWS EC2 instances", status="active")

        sent_filter = route.calls[0].request.url.params["filter"]
        assert 'recommendationCategory:"Idle AWS EC2 instances"' in sent_filter
        assert 'recommendationStatus:"ACTIVE"' in sent_filter


class TestGetIdleResources:
    """Tests for get_idle_resources tool (dynamic category resolution)."""

    @respx.mock
    async def test_get_idle_resources_returns_list(self, client):
        """get_idle_resources resolves idle categories and OR-filters by description."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/categories"
        ).mock(return_value=httpx.Response(200, json={"items": _CATEGORY_ITEMS, "total": 4}))
        rec_route = respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations"
        ).mock(
            return_value=httpx.Response(200, json={"items": [_recommendation_item()], "total": 1})
        )

        result = await get_idle_resources(client)

        data = json.loads(result[0].text)
        assert data["total"] == 1
        assert data["idle_resources"][0]["category"] == "Underutilized Azure VM instances"

        sent_filter = rec_route.calls[0].request.url.params["filter"]
        # OR-joined idle-type descriptions only; non-idle category excluded
        assert sent_filter.startswith("recommendationCategory:")
        assert '"Idle AWS EC2 instances"' in sent_filter
        assert '"Underutilized Azure VM instances"' in sent_filter
        assert '"Unattached AWS EBS volumes"' in sent_filter
        assert "Reserved instance" not in sent_filter
        assert sent_filter.count("|") == 2

    @respx.mock
    async def test_get_idle_resources_provider_filter_client_side(self, client):
        """Provider narrowing is applied client-side on cloudProvider."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/categories"
        ).mock(return_value=httpx.Response(200, json={"items": _CATEGORY_ITEMS, "total": 4}))
        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        _recommendation_item(),
                        _recommendation_item(
                            id="1-2-EC2_IDLE",
                            recommendationCategory="Idle AWS EC2 instances",
                            cloudProvider="AWS",
                            resourceDisplayName="i-0abc",
                        ),
                    ],
                    "total": 2,
                },
            )
        )

        result = await get_idle_resources(client, provider="aws")

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["idle_resources"][0]["cloud_provider"] == "AWS"
        assert data["provider"] == "aws"

    @respx.mock
    async def test_get_idle_resources_no_idle_categories(self, client):
        """Portals without idle-type categories get a clear note, no rec query."""
        from lm_mcp.tools.cost import get_idle_resources

        respx.get(
            "https://test.logicmonitor.com/santaba/rest/cost-optimization/recommendations/categories"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"items": [{"name": "OTHER", "description": "Other"}], "total": 1},
            )
        )

        result = await get_idle_resources(client)

        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert "No idle-type recommendation categories" in data["note"]


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
