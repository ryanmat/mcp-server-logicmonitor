# Description: Dashboard group tools for LogicMonitor MCP server.
# Description: Provides dashboard group query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

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
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'name~{quote_filter_value(clean_name)}'

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

        response = {
            "total": result.get("total", 0),
            "count": len(groups),
            "dashboard_groups": groups,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
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


@require_write_permission
async def create_dashboard_group(
    client: "LogicMonitorClient",
    name: str,
    parent_id: int | None = None,
    description: str | None = None,
) -> list[TextContent]:
    """Create a dashboard group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Name of the dashboard group.
        parent_id: Parent group ID (optional).
        description: Optional description.

    Returns:
        List of TextContent with result or error.
    """
    try:
        body: dict = {"name": name}

        if parent_id is not None:
            body["parentId"] = parent_id
        if description:
            body["description"] = description

        result = await client.post("/dashboard/groups", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"Dashboard group '{name}' created",
                "group_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_dashboard_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Delete a dashboard group from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: ID of the group to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/dashboard/groups/{group_id}")

        return format_response(
            {
                "success": True,
                "message": f"Dashboard group {group_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
