# Description: Device management tools for LogicMonitor MCP server.
# Description: Provides device and device group CRUD functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# Device status mapping for LogicMonitor
DEVICE_STATUS_MAP = {
    "normal": 0,
    "dead": 1,
    "dead-collector": 2,
    "unmonitored": 3,
    "disabled": 4,
}


async def get_devices(
    client: "LogicMonitorClient",
    group_id: int | None = None,
    name_filter: str | None = None,
    status: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List devices from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: Filter by device group ID.
        name_filter: Filter by device name (supports wildcards).
        status: Filter by device status (normal, dead, dead-collector, unmonitored, disabled).
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "systemProperties.name:system.hostname",
            "customProperties.name:env,customProperties.value:prod"
        limit: Maximum number of devices to return (max 1000).
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with device data or error.
    """
    try:
        params: dict = {"size": min(limit, 1000), "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if group_id:
                filters.append(f"hostGroupIds~{group_id}")
            if name_filter:
                filters.append(f"displayName~{name_filter}")
            if status and status.lower() in DEVICE_STATUS_MAP:
                filters.append(f"hostStatus:{DEVICE_STATUS_MAP[status.lower()]}")

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

        total = result.get("total", 0)
        has_more = (offset + len(devices)) < total

        return format_response(
            {
                "total": total,
                "count": len(devices),
                "offset": offset,
                "has_more": has_more,
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


@require_write_permission
async def create_device(
    client: "LogicMonitorClient",
    name: str,
    display_name: str,
    preferred_collector_id: int,
    host_group_ids: list[int] | None = None,
    description: str | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Create a new device in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Device hostname or IP address.
        display_name: Display name for the device.
        preferred_collector_id: Collector ID to assign to the device.
        host_group_ids: List of device group IDs to assign.
        description: Device description.
        custom_properties: Custom properties as key-value pairs.

    Returns:
        List of TextContent with created device details or error.
    """
    try:
        body: dict = {
            "name": name,
            "displayName": display_name,
            "preferredCollectorId": preferred_collector_id,
        }

        if host_group_ids:
            body["hostGroupIds"] = ",".join(str(gid) for gid in host_group_ids)

        if description:
            body["description"] = description

        if custom_properties:
            body["customProperties"] = [
                {"name": k, "value": v} for k, v in custom_properties.items()
            ]

        result = await client.post("/device/devices", json_body=body)

        return format_response(
            {
                "message": "Device created successfully",
                "device": {
                    "id": result.get("id"),
                    "name": result.get("displayName"),
                    "host": result.get("name"),
                    "collector_id": result.get("currentCollectorId"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_device(
    client: "LogicMonitorClient",
    device_id: int,
    display_name: str | None = None,
    description: str | None = None,
    host_group_ids: list[int] | None = None,
    preferred_collector_id: int | None = None,
    disable_alerting: bool | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Update an existing device in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to update.
        display_name: New display name.
        description: New description.
        host_group_ids: New list of device group IDs.
        preferred_collector_id: New preferred collector ID.
        disable_alerting: Disable alerting for this device.
        custom_properties: Custom properties to set/update.

    Returns:
        List of TextContent with updated device details or error.
    """
    try:
        body: dict = {}

        if display_name is not None:
            body["displayName"] = display_name
        if description is not None:
            body["description"] = description
        if host_group_ids is not None:
            body["hostGroupIds"] = ",".join(str(gid) for gid in host_group_ids)
        if preferred_collector_id is not None:
            body["preferredCollectorId"] = preferred_collector_id
        if disable_alerting is not None:
            body["disableAlerting"] = disable_alerting
        if custom_properties is not None:
            body["customProperties"] = [
                {"name": k, "value": v} for k, v in custom_properties.items()
            ]

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "NO_CHANGES",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/device/devices/{device_id}", json_body=body)

        return format_response(
            {
                "message": "Device updated successfully",
                "device": {
                    "id": result.get("id"),
                    "name": result.get("displayName"),
                    "description": result.get("description"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device(
    client: "LogicMonitorClient",
    device_id: int,
    delete_hard: bool = False,
) -> list[TextContent]:
    """Delete a device from LogicMonitor.

    WARNING: This removes the device and all its monitoring data.
    By default, uses soft delete (recoverable from Recently Deleted).

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to delete.
        delete_hard: If True, permanently delete. If False (default), move to Recently Deleted.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        # Get device info first for confirmation
        device = await client.get(f"/device/devices/{device_id}")
        device_name = device.get("displayName") or device.get("name", f"ID:{device_id}")

        params = {}
        if delete_hard:
            params["deleteHard"] = "true"

        await client.delete(f"/device/devices/{device_id}", params=params or None)

        return format_response(
            {
                "success": True,
                "message": f"Device '{device_name}' deleted",
                "device_id": device_id,
                "hard_delete": delete_hard,
                "recoverable": not delete_hard,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_device_group(
    client: "LogicMonitorClient",
    name: str,
    parent_id: int = 1,
    description: str | None = None,
    applies_to: str | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Create a new device group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name: Group name.
        parent_id: Parent group ID (default 1 = root).
        description: Group description.
        applies_to: AppliesTo expression for dynamic group membership.
        custom_properties: Custom properties as key-value pairs.

    Returns:
        List of TextContent with created group details or error.
    """
    try:
        body: dict = {
            "name": name,
            "parentId": parent_id,
        }

        if description:
            body["description"] = description
        if applies_to:
            body["appliesTo"] = applies_to
        if custom_properties:
            body["customProperties"] = [
                {"name": k, "value": v} for k, v in custom_properties.items()
            ]

        result = await client.post("/device/groups", json_body=body)

        return format_response(
            {
                "message": "Device group created successfully",
                "group": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "parent_id": result.get("parentId"),
                    "full_path": result.get("fullPath"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device_group(
    client: "LogicMonitorClient",
    group_id: int,
    delete_children: bool = False,
    delete_hard: bool = False,
) -> list[TextContent]:
    """Delete a device group from LogicMonitor.

    WARNING: If delete_children is True, this will delete ALL devices and subgroups.
    By default, fails if group contains devices (safe mode).

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID to delete.
        delete_children: If True, delete all child devices and subgroups. Default False.
        delete_hard: If True, permanently delete. If False (default), move to Recently Deleted.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        # Get group info first for confirmation and impact assessment
        group = await client.get(f"/device/groups/{group_id}")
        group_name = group.get("name", f"ID:{group_id}")
        full_path = group.get("fullPath", group_name)
        device_count = group.get("numOfHosts", 0)
        subgroup_count = group.get("numOfDirectSubGroups", 0)

        # Safety check: warn about impact if deleting children
        if delete_children and (device_count > 0 or subgroup_count > 0):
            impact_warning = f"IMPACT: {device_count} devices, {subgroup_count} subgroups deleted"
        else:
            impact_warning = None

        params: dict = {}
        if delete_children:
            params["deleteChildren"] = "true"
        if delete_hard:
            params["deleteHard"] = "true"

        await client.delete(f"/device/groups/{group_id}", params=params or None)

        response = {
            "success": True,
            "message": f"Device group '{full_path}' deleted",
            "group_id": group_id,
            "delete_children": delete_children,
            "hard_delete": delete_hard,
            "recoverable": not delete_hard,
        }

        if impact_warning:
            response["impact"] = impact_warning

        return format_response(response)
    except Exception as e:
        return handle_error(e)
