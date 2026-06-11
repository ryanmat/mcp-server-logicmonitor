# Description: Cost optimization tools for LogicMonitor MCP server.
# Description: Provides cloud cost analysis and recommendations.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    safe_total,
    sanitize_filter_value,
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
    try:
        params: dict = {"size": limit, "offset": offset}
        wildcards_stripped = False

        filters = []
        if category:
            clean_category, was_modified = sanitize_filter_value(category)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"recommendationCategory:{quote_filter_value(clean_category)}")
        if status:
            clean_status, was_modified = sanitize_filter_value(status)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f"recommendationStatus:{quote_filter_value(clean_status.upper())}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/cost-optimization/recommendations", params=params)

        recommendations = [_project_recommendation(item) for item in result.get("items", [])]

        response = {
            "total": safe_total(result),
            "count": len(recommendations),
            "recommendations": recommendations,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


# Category enum-name markers that identify idle/waste recommendation types
# (e.g. EC2_IDLE, AZURE_VM_UNDERUTILIZED, EBS_UNATTACHED, AZURE_VM_STOPPED).
_IDLE_CATEGORY_MARKERS = ("_IDLE", "_UNDERUTILIZED", "_UNATTACHED", "_STOPPED")


async def get_idle_resources(
    client: LogicMonitorClient,
    provider: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get idle/underutilized cloud resources from cost recommendations.

    Resolves idle-type categories dynamically from the Cost Optimization
    categories endpoint (enum names containing _IDLE, _UNDERUTILIZED,
    _UNATTACHED, _STOPPED), then queries recommendations with an OR
    filter on their description strings. The recommendation filter
    matches descriptions, not enum names.

    Args:
        client: LogicMonitor API client.
        provider: Narrow to one cloud provider (aws, azure, gcp).
        limit: Maximum number of recommendations to fetch.

    Returns:
        List of TextContent with idle resources or error.
    """
    try:
        categories = await client.get("/cost-optimization/recommendations/categories")
        idle_descriptions = [
            item.get("description")
            for item in categories.get("items", [])
            if item.get("description")
            and any(marker in str(item.get("name", "")) for marker in _IDLE_CATEGORY_MARKERS)
        ]

        if not idle_descriptions:
            return format_response(
                {
                    "total": 0,
                    "count": 0,
                    "idle_resources": [],
                    "note": "No idle-type recommendation categories available on this portal.",
                }
            )

        or_values = "|".join(quote_filter_value(desc) for desc in idle_descriptions)
        params: dict = {"size": limit, "filter": f"recommendationCategory:{or_values}"}

        result = await client.get("/cost-optimization/recommendations", params=params)

        resources = []
        for item in result.get("items", []):
            if provider and str(item.get("cloudProvider", "")).lower() != provider.lower():
                continue
            # Defensive re-filter: the API matches description strings, so keep
            # only items whose category resolved from the idle-type enum names.
            if item.get("recommendationCategory") not in idle_descriptions:
                continue
            resources.append(_project_recommendation(item))

        response: dict = {
            "total": safe_total(result),
            "count": len(resources),
            "idle_resources": resources,
        }
        if provider:
            response["provider"] = provider.lower()
            response["note"] = (
                "Provider filtering is applied client-side after fetching; "
                "increase limit if results appear truncated."
            )
        return format_response(response)
    except Exception as e:
        return handle_error(e)


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
