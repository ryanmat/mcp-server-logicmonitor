# Description: Dashboard tools for LogicMonitor MCP server.
# Description: Provides get_dashboards, get_dashboard, get_dashboard_widgets, create_dashboard.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_dashboards(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List dashboards from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by dashboard name (supports wildcards).
        group_id: Filter by dashboard group ID.
        limit: Maximum number of dashboards to return.

    Returns:
        List of TextContent with dashboard data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if name_filter:
            filters.append(f"name~{name_filter}")
        if group_id is not None:
            filters.append(f"groupId:{group_id}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/dashboard/dashboards", params=params)

        dashboards = []
        for item in result.get("items", []):
            dashboards.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "group_id": item.get("groupId"),
                    "group_name": item.get("groupFullPath"),
                    "widget_count": item.get("widgetsConfig", {}).get("count", 0)
                    if isinstance(item.get("widgetsConfig"), dict)
                    else len(item.get("widgetsConfig", [])),
                    "owner": item.get("owner"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(dashboards),
                "dashboards": dashboards,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_dashboard(
    client: "LogicMonitorClient",
    dashboard_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID.

    Returns:
        List of TextContent with dashboard details or error.
    """
    try:
        result = await client.get(f"/dashboard/dashboards/{dashboard_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_dashboard_widgets(
    client: "LogicMonitorClient",
    dashboard_id: int,
    limit: int = 100,
) -> list[TextContent]:
    """Get widgets for a specific dashboard.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID.
        limit: Maximum number of widgets to return.

    Returns:
        List of TextContent with widget data or error.
    """
    try:
        params: dict = {"size": limit}

        result = await client.get(f"/dashboard/dashboards/{dashboard_id}/widgets", params=params)

        widgets = []
        for item in result.get("items", []):
            widgets.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                    "column": item.get("columnIdx"),
                    "row_span": item.get("rowSpan"),
                    "col_span": item.get("colSpan"),
                }
            )

        return format_response(
            {
                "dashboard_id": dashboard_id,
                "total": result.get("total", 0),
                "count": len(widgets),
                "widgets": widgets,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_dashboard(
    client: "LogicMonitorClient",
    name: str,
    group_id: int = 1,
    description: str | None = None,
    sharable: bool = True,
) -> list[TextContent]:
    """Create a new dashboard.

    Args:
        client: LogicMonitor API client.
        name: Dashboard name.
        group_id: Dashboard group ID (default: 1 for root).
        description: Dashboard description.
        sharable: Whether dashboard is sharable (default: True).

    Returns:
        List of TextContent with created dashboard details or error.
    """
    try:
        payload: dict = {
            "name": name,
            "groupId": group_id,
            "sharable": sharable,
        }

        if description:
            payload["description"] = description

        result = await client.post("/dashboard/dashboards", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Dashboard '{name}' created successfully",
                "dashboard": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "group_id": result.get("groupId"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)
