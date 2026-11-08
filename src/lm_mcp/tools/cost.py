# Description: Cost optimization tools for LogicMonitor MCP server.
# Description: Provides cloud cost analysis and recommendations.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _project_recommendation(item: dict) -> dict:
    """Project a Cost Optimization recommendation item to snake_case."""
    return {
        "id": item.get("id"),
        "recommendation_id": item.get("recommendationId"),
        "category": item.get("recommendationCategory"),
        "resource_id": item.get("resourceId"),
        "resource_name": item.get("resourceDisplayName"),
        "cloud_provider": item.get("cloudProvider"),
        "cloud_service_type": item.get("cloudServiceType"),
        "recommendation": item.get("recommendation"),
        "criteria": item.get("criteria"),
        "annual_savings": item.get("annualSavings"),
        "status": item.get("recommendationStatus"),
        "console_url": item.get("providerConsoleUrl"),
    }


async def get_cost_recommendations(
    client: LogicMonitorClient,
    category: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get cost optimization recommendations.

    The category filter matches the category DESCRIPTION string (e.g.
    "Idle AWS EC2 instances"), not the enum name; the API silently
    ignores unknown values. Use get_cost_recommendation_categories to
    list valid descriptions.

    Args:
        client: LogicMonitor API client.
        category: Filter by category description string.
        status: Filter by recommendation status (e.g. active).
        limit: Maximum number of recommendations to return.
        offset: Results to skip for pagination.

    Returns:
        List of TextContent with recommendations or error.
    """
    return await list_tool(
        client,
        "/cost-optimization/recommendations",
        key="recommendations",
        project=_project_recommendation,
        limit=limit,
        offset=offset,
        named={
            "recommendationCategory:": category,
            "recommendationStatus:": status.upper() if status else None,
        },
    )


async def get_cost_recommendation_categories(
    client: LogicMonitorClient,
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
    client: LogicMonitorClient,
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
