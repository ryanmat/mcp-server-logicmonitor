# Description: Device management tools for LogicMonitor MCP server.
# Description: Provides get_devices, get_device, get_device_groups functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_devices(
    client: "LogicMonitorClient",
    group_id: int | None = None,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List devices from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: Filter by device group ID.
        name_filter: Filter by device name (supports wildcards).
        limit: Maximum number of devices to return.

    Returns:
        List of TextContent with device data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if group_id:
            filters.append(f"hostGroupIds~{group_id}")
        if name_filter:
            filters.append(f"displayName~{name_filter}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/device/devices", params=params)

        devices = []
        for item in result.get("items", []):
            devices.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "status": item.get("hostStatus"),
                    "collector_id": item.get("currentCollectorId"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(devices),
                "devices": devices,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device(
    client: "LogicMonitorClient",
    device_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.

    Returns:
        List of TextContent with device details or error.
    """
    try:
        result = await client.get(f"/device/devices/{device_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_device_groups(
    client: "LogicMonitorClient",
    parent_id: int | None = None,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List device groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        parent_id: Filter by parent group ID.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with group data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if parent_id is not None:
            filters.append(f"parentId:{parent_id}")
        if name_filter:
            filters.append(f"name~{name_filter}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/device/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "device_count": item.get("numOfHosts"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)
