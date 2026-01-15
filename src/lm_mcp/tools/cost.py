# Description: Cost optimization tools for LogicMonitor MCP server.
# Description: Provides cloud cost analysis and recommendations.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_cloud_cost_accounts(
    client: "LogicMonitorClient",
    provider: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List cloud accounts configured for cost tracking.

    Args:
        client: LogicMonitor API client.
        provider: Filter by cloud provider (aws, azure, gcp).
        limit: Maximum number of accounts to return.

    Returns:
        List of TextContent with cloud account data or error.
    """
    try:
        params: dict = {"size": limit}

        if provider:
            params["filter"] = f"provider:{provider}"

        result = await client.get("/cost/cloudaccounts", params=params)

        accounts = []
        for item in result.get("items", []):
            accounts.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "provider": item.get("provider"),
                    "account_id": item.get("accountId"),
                    "status": item.get("status"),
                    "last_updated": item.get("lastUpdatedOn"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(accounts),
                "cloud_accounts": accounts,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_cost_recommendations(
    client: "LogicMonitorClient",
    cloud_account_id: int | None = None,
    recommendation_type: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get cost optimization recommendations.

    Args:
        client: LogicMonitor API client.
        cloud_account_id: Filter by specific cloud account.
        recommendation_type: Filter by type (rightsizing, idle, unused, etc.).
        limit: Maximum number of recommendations to return.

    Returns:
        List of TextContent with recommendations or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if cloud_account_id:
            filters.append(f"cloudAccountId:{cloud_account_id}")
        if recommendation_type:
            filters.append(f"type:{recommendation_type}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/cost/recommendations", params=params)

        recommendations = []
        for item in result.get("items", []):
            recommendations.append(
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "resource_name": item.get("resourceName"),
                    "resource_type": item.get("resourceType"),
                    "current_cost": item.get("currentCost"),
                    "projected_savings": item.get("projectedSavings"),
                    "recommendation": item.get("recommendation"),
                    "confidence": item.get("confidence"),
                    "status": item.get("status"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(recommendations),
                "recommendations": recommendations,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_cost_summary(
    client: "LogicMonitorClient",
    cloud_account_id: int | None = None,
    time_range: str = "last30days",
) -> list[TextContent]:
    """Get cost summary and trends.

    Args:
        client: LogicMonitor API client.
        cloud_account_id: Filter by specific cloud account.
        time_range: Time range for summary (last7days, last30days, last90days).

    Returns:
        List of TextContent with cost summary or error.
    """
    try:
        params: dict = {"timeRange": time_range}

        if cloud_account_id:
            params["cloudAccountId"] = cloud_account_id

        result = await client.get("/cost/summary", params=params)

        return format_response(
            {
                "time_range": time_range,
                "total_cost": result.get("totalCost"),
                "cost_trend": result.get("costTrend"),
                "cost_by_service": result.get("costByService", []),
                "cost_by_region": result.get("costByRegion", []),
                "projected_monthly": result.get("projectedMonthlyCost"),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_resource_cost(
    client: "LogicMonitorClient",
    device_id: int,
    time_range: str = "last30days",
) -> list[TextContent]:
    """Get cost data for a specific resource/device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to get cost for.
        time_range: Time range for cost data (last7days, last30days, last90days).

    Returns:
        List of TextContent with resource cost data or error.
    """
    try:
        params: dict = {"timeRange": time_range}
        result = await client.get(f"/device/devices/{device_id}/cost", params=params)

        return format_response(
            {
                "device_id": device_id,
                "time_range": time_range,
                "total_cost": result.get("totalCost"),
                "cost_breakdown": result.get("costBreakdown", []),
                "cost_trend": result.get("costTrend", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_idle_resources(
    client: "LogicMonitorClient",
    cloud_account_id: int | None = None,
    resource_type: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get list of idle/underutilized resources.

    Args:
        client: LogicMonitor API client.
        cloud_account_id: Filter by specific cloud account.
        resource_type: Filter by resource type (ec2, rds, ebs, etc.).
        limit: Maximum number of resources to return.

    Returns:
        List of TextContent with idle resources or error.
    """
    try:
        params: dict = {"size": limit}

        filters = ["status:idle"]
        if cloud_account_id:
            filters.append(f"cloudAccountId:{cloud_account_id}")
        if resource_type:
            filters.append(f"resourceType:{resource_type}")

        params["filter"] = ",".join(filters)

        result = await client.get("/cost/resources", params=params)

        resources = []
        for item in result.get("items", []):
            resources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "resource_type": item.get("resourceType"),
                    "cloud_account": item.get("cloudAccountName"),
                    "region": item.get("region"),
                    "utilization": item.get("utilization"),
                    "monthly_cost": item.get("monthlyCost"),
                    "idle_since": item.get("idleSince"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(resources),
                "idle_resources": resources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_cost_recommendation_categories(
    client: "LogicMonitorClient",
) -> list[TextContent]:
    """Get cost recommendation categories (v224 Cost Optimization API).

    Returns list of recommendation categories with counts and potential savings.

    Args:
        client: LogicMonitor API client.

    Returns:
        List of TextContent with recommendation categories or error.
    """
    try:
        result = await client.get("/cost-optimization/recommendations/categories")

        categories = []
        for item in result.get("items", []):
            categories.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "count": item.get("count"),
                    "potential_savings": item.get("potentialSavings"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "categories": categories,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_cost_recommendation(
    client: "LogicMonitorClient",
    recommendation_id: int,
) -> list[TextContent]:
    """Get a specific cost recommendation by ID (v224 Cost Optimization API).

    Args:
        client: LogicMonitor API client.
        recommendation_id: ID of the recommendation to retrieve.

    Returns:
        List of TextContent with recommendation details or error.
    """
    try:
        result = await client.get(f"/cost-optimization/recommendations/{recommendation_id}")

        return format_response(
            {
                "id": result.get("id"),
                "category": result.get("category"),
                "resource_name": result.get("resourceName"),
                "resource_type": result.get("resourceType"),
                "current_configuration": result.get("currentConfiguration"),
                "recommended_configuration": result.get("recommendedConfiguration"),
                "current_cost": result.get("currentCost"),
                "projected_cost": result.get("projectedCost"),
                "projected_savings": result.get("projectedSavings"),
                "confidence": result.get("confidence"),
                "status": result.get("status"),
                "details": result.get("details"),
            }
        )
    except Exception as e:
        return handle_error(e)
