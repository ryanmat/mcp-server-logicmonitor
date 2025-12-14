# Description: Dashboard group tools for LogicMonitor MCP server.
# Description: Provides dashboard group query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_dashboard_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List dashboard groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with dashboard group data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/dashboard/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parent_id": item.get("parentId"),
                    "full_path": item.get("fullPath"),
                    "num_of_dashboards": item.get("numOfDashboards"),
                    "num_of_direct_dashboards": item.get("numOfDirectDashboards"),
                    "num_of_direct_sub_groups": item.get("numOfDirectSubGroups"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "dashboard_groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_dashboard_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific dashboard group.

    Args:
        client: LogicMonitor API client.
        group_id: Dashboard group ID.

    Returns:
        List of TextContent with dashboard group details or error.
    """
    try:
        result = await client.get(f"/dashboard/groups/{group_id}")

        group = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "parent_id": result.get("parentId"),
            "full_path": result.get("fullPath"),
            "num_of_dashboards": result.get("numOfDashboards"),
            "num_of_direct_dashboards": result.get("numOfDirectDashboards"),
            "num_of_direct_sub_groups": result.get("numOfDirectSubGroups"),
            "widget_tokens": result.get("widgetTokens", []),
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)
