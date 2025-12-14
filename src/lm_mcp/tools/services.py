# Description: Service and topology tools for LogicMonitor MCP server.
# Description: Provides service query functions for LM Service Insight.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_services(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List services from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by service name (supports wildcards).
        limit: Maximum number of services to return.

    Returns:
        List of TextContent with service data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/service/services", params=params)

        services = []
        for item in result.get("items", []):
            services.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "group_id": item.get("groupId"),
                    "alert_status": item.get("alertStatus"),
                    "alert_status_priority": item.get("alertStatusPriority"),
                    "sdt_status": item.get("sdtStatus"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(services),
                "services": services,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_service(
    client: "LogicMonitorClient",
    service_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific service.

    Args:
        client: LogicMonitor API client.
        service_id: Service ID.

    Returns:
        List of TextContent with service details or error.
    """
    try:
        result = await client.get(f"/service/services/{service_id}")

        service = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "group_id": result.get("groupId"),
            "alert_status": result.get("alertStatus"),
            "alert_status_priority": result.get("alertStatusPriority"),
            "sdt_status": result.get("sdtStatus"),
            "individual_alert_level": result.get("individualAlertLevel"),
            "individual_sdt_at": result.get("individualSdtAt"),
        }

        return format_response(service)
    except Exception as e:
        return handle_error(e)


async def get_service_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List service groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with service group data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/service/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parent_id": item.get("parentId"),
                    "full_path": item.get("fullPath"),
                    "num_of_services": item.get("numOfServices"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "service_groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)
