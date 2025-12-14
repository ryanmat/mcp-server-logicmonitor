# Description: Access group tools for LogicMonitor MCP server.
# Description: Provides access group query functions for RBAC.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_access_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List access groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with access group data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/accessgroup", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "tenant_id": item.get("tenantId"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "access_groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_access_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific access group.

    Args:
        client: LogicMonitor API client.
        group_id: Access group ID.

    Returns:
        List of TextContent with access group details or error.
    """
    try:
        result = await client.get(f"/setting/accessgroup/{group_id}")

        group = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "tenant_id": result.get("tenantId"),
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)
