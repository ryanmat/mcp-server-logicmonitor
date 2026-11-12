# Description: Device management tools for LogicMonitor MCP server.
# Description: Device and group CRUD, Active Discovery, the device delta and unmonitored devices.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    portal_url,
    require_write_permission,
    validation_error,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# Device status -> the hostStatus filter clause get_devices sends for it.
# The v3 API returns hostStatus as a word and filters on the quoted word. A numeric
# code matches nothing on a live portal, and an unquoted word is rejected as an
# invalid filter. The clauses are written out in full so the hostStatus guard in
# tests/test_hoststatus_words.py reads them as they go on the wire.
DEVICE_STATUS_FILTERS = {
    "normal": 'hostStatus:"normal"',
    "dead": 'hostStatus:"dead"',
    "dead-collector": 'hostStatus:"dead-collector"',
    "unmonitored": 'hostStatus:"unmonitored"',
    "disabled": 'hostStatus:"disabled"',
}


def _device_row(item: dict) -> dict:
    """Project one /device/devices row onto the get_devices fields."""
    return {
        "id": item.get("id"),
        "name": item.get("displayName"),
        "status": item.get("hostStatus"),
        "collector_id": item.get("currentCollectorId"),
    }


async def get_devices(
    client: LogicMonitorClient,
    group_id: int | None = None,
    name_filter: str | None = None,
    hostname_filter: str | None = None,
    status: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List devices from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: Filter by device group ID.
        name_filter: Filter by display name (supports wildcards).
        hostname_filter: Filter by hostname or IP address (the 'name' field).
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
    clauses = []
    if group_id:
        # hostGroupIds:N matches membership in the id list; ~N is a
        # substring match that also returns groups 16, 60 and 160 for 6.
        clauses.append(f"hostGroupIds:{group_id}")
    if status and status.lower() in DEVICE_STATUS_FILTERS:
        clauses.append(DEVICE_STATUS_FILTERS[status.lower()])

    return await list_tool(
        client,
        "/device/devices",
        key="devices",
        project=_device_row,
        limit=min(limit, 1000),
        offset=offset,
        filter=filter,
        named={"displayName~": name_filter, "name~": hostname_filter},
        clauses=clauses,
    )


async def get_device(
    client: LogicMonitorClient,
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
        result["portal_url"] = portal_url("device", device_id)
        return format_response(result)
    except Exception as e:
        return handle_error(e)


def _delta_row(item: dict) -> dict:
    """Project one device delta row onto the get_devices fields and the change it records:
    "updated" on a read with a delta id, "" on the read that starts the delta."""
    return {**_device_row(item), "change": item.get("status")}


async def get_device_delta(
    client: LogicMonitorClient,
    delta_id: str | None = None,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List devices through the device delta.

    Without delta_id it lists the devices whose display name contains name_filter, or every
    device, and starts a delta whose id it returns; each such read starts another. With
    delta_id it lists the devices changed since that delta started, every change since then on
    each read, and takes no name_filter, since the portal answered a filtered read there with an
    empty page that left out a changed device.

    Args:
        client: LogicMonitor API client.
        delta_id: The delta_id an earlier read returned.
        name_filter: Keep devices whose display name contains this text (without delta_id).
        limit: Maximum number of devices to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the devices and the delta_id, or error.
    """
    if delta_id and name_filter:
        return validation_error(
            "INVALID_REQUEST",
            "name_filter applies only to a read without delta_id",
            suggestion="Leave name_filter out when passing delta_id.",
        )
    return await list_tool(
        client,
        f"/device/devices/delta/{delta_id}" if delta_id else "/device/devices/delta",
        key="devices",
        project=_delta_row,
        limit=limit,
        offset=offset,
        named={"displayName~": name_filter},
        carry={"deltaId": "delta_id"},
    )


async def get_unmonitored_devices(
    client: LogicMonitorClient,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List the portal's unmonitored devices, found by a NetScan and not monitored, rows as
    the API returns them.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of devices to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the devices or error.
    """
    return await list_tool(
        client,
        "/device/unmonitoreddevices",
        key="devices",
        project=dict,
        limit=limit,
        offset=offset,
    )


def _device_group_row(item: dict) -> dict:
    """Project one /device/groups row onto the get_device_groups fields."""
    group = {
        "id": item.get("id"),
        "name": item.get("name"),
        "parent_id": item.get("parentId"),
        "device_count": item.get("numOfHosts"),
    }
    applies_to = item.get("appliesTo")
    if applies_to:
        group["applies_to"] = applies_to
    return group


async def get_device_groups(
    client: LogicMonitorClient,
    parent_id: int | None = None,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List device groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        parent_id: Filter by parent group ID.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with group data or error.
    """
    return await list_tool(
        client,
        "/device/groups",
        key="groups",
        project=_device_group_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
        clauses=[f"parentId:{parent_id}"] if parent_id is not None else [],
    )


async def get_device_group(
    client: LogicMonitorClient,
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific device group.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID.

    Returns:
        List of TextContent with group details or error.
    """
    try:
        result = await client.get(f"/device/groups/{group_id}")
        result["portal_url"] = portal_url("device_group", group_id)
        return format_response(result)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_device(
    client: LogicMonitorClient,
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
    client: LogicMonitorClient,
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
            # Fetch existing properties to merge (prevents silent data loss)
            existing = await client.get(f"/device/devices/{device_id}")
            existing_props = {p["name"]: p["value"] for p in existing.get("customProperties", [])}
            # Merge: new values override existing, existing values preserved
            existing_props.update(custom_properties)
            body["customProperties"] = [{"name": k, "value": v} for k, v in existing_props.items()]

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/device/devices/{device_id}", json_body=body)

        response = {
            "message": "Device updated successfully",
            "device": {
                "id": result.get("id"),
                "name": result.get("displayName"),
                "description": result.get("description"),
            },
        }

        # Warn if group change was requested on a K8S-managed device
        if host_group_ids is not None and result.get("deviceType") == 8:
            actual_groups = result.get("hostGroupIds", "")
            requested = ",".join(str(gid) for gid in host_group_ids)
            if actual_groups != requested:
                response["warning"] = (
                    "host_group_ids change may not persist. This is a Kubernetes-managed "
                    "device (deviceType=8) and Argus controls group membership. "
                    f"Requested: [{requested}], actual: [{actual_groups}]"
                )

        return format_response(response)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device(
    client: LogicMonitorClient,
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
        device_type = device.get("deviceType", 0)
        host_status = device.get("hostStatus", "unknown")
        collector_id = device.get("currentCollectorId")
        group_ids = device.get("hostGroupIds", "")

        params = {}
        if delete_hard:
            params["deleteHard"] = "true"

        await client.delete(f"/device/devices/{device_id}", params=params or None)

        response = {
            "success": True,
            "message": f"Device '{device_name}' deleted",
            "device_id": device_id,
            "hard_delete": delete_hard,
            "recoverable": not delete_hard,
        }

        # Include context about what was deleted for audit trail
        warnings = []
        if device_type == 8:
            warnings.append(
                "This was a Kubernetes-managed device (deviceType=8). "
                "Argus may recreate it on the next sync cycle."
            )
        if host_status == "normal":
            warnings.append("Device was in normal/healthy state when deleted.")
        if warnings:
            response["warnings"] = warnings

        response["deleted_device"] = {
            "name": device_name,
            "type": device_type,
            "status": host_status,
            "collector_id": collector_id,
            "group_ids": group_ids,
        }

        return format_response(response)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def recover_device(
    client: LogicMonitorClient,
    device_id: int,
) -> list[TextContent]:
    """Recover a soft-deleted device from LogicMonitor.

    Restores a device that was previously soft-deleted. Only works within
    the recovery window (before the device is permanently purged).

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to recover.

    Returns:
        List of TextContent with recovery confirmation or error.
    """
    try:
        result = await client.request(
            "PATCH",
            f"/device/devices/{device_id}",
            json_body={},
            params={"recover": "true"},
        )
        device_name = result.get("displayName") or result.get("name", f"ID:{device_id}")
        return format_response(
            {
                "success": True,
                "message": f"Device '{device_name}' recovered",
                "device_id": result.get("id", device_id),
                "device_name": device_name,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def run_auto_discovery(
    client: LogicMonitorClient,
    device_id: int,
) -> list[TextContent]:
    """Schedule Active Discovery on one device, so its collector looks for instances now.

    The portal answers an empty object; the discovery itself runs on the collector.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.

    Returns:
        List of TextContent with the scheduling result or error.
    """
    try:
        await client.post(f"/device/devices/{device_id}/scheduleAutoDiscovery")
        return format_response(
            {
                "success": True,
                "device_id": device_id,
                "message": f"Active Discovery scheduled for device {device_id}",
            }
        )
    except Exception as e:
        return handle_error(e)


# Maximum items for bulk operations to prevent accidental mass changes
BULK_OPERATION_LIMIT = 100


@require_write_permission
async def bulk_delete_devices(
    client: LogicMonitorClient,
    device_ids: list[int],
    delete_hard: bool = False,
) -> list[TextContent]:
    """Delete multiple devices in a single operation.

    Soft deletes by default (recoverable). Includes audit context for each
    deleted device including device type warnings for Kubernetes-managed devices.

    Args:
        client: LogicMonitor API client.
        device_ids: List of device IDs to delete (max 100).
        delete_hard: If True, permanently delete. Default: soft delete.

    Returns:
        List of TextContent with results summary or error.
    """
    if not device_ids:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": "No device IDs provided",
                "suggestion": "Provide at least one device ID",
            }
        )

    if len(device_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": f"Too many devices ({len(device_ids)}). Max {BULK_OPERATION_LIMIT}.",
                "suggestion": "Split into smaller batches",
            }
        )

    results: dict = {"success": [], "failed": [], "warnings": []}

    params = {"deleteHard": "true"} if delete_hard else {}

    for device_id in device_ids:
        try:
            device = await client.get(f"/device/devices/{device_id}")
            device_name = device.get("displayName") or device.get("name", f"ID:{device_id}")
            device_type = device.get("deviceType", 0)

            await client.delete(f"/device/devices/{device_id}", params=params or None)

            results["success"].append({"id": device_id, "name": device_name})

            if device_type == 8:
                results["warnings"].append(
                    f"Device {device_id} ({device_name}) was Kubernetes-managed "
                    "(deviceType=8). Argus may recreate it on the next sync cycle."
                )
        except Exception as e:
            results["failed"].append({"id": device_id, "error": str(e)})

    response: dict = {
        "total": len(device_ids),
        "succeeded": len(results["success"]),
        "failed": len(results["failed"]),
        "hard_delete": delete_hard,
        "success_ids": [r["id"] for r in results["success"]],
        "failures": results["failed"],
    }

    if results["warnings"]:
        response["warnings"] = results["warnings"]

    return format_response(response)


@require_write_permission
async def create_device_group(
    client: LogicMonitorClient,
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
async def update_device_group(
    client: LogicMonitorClient,
    group_id: int,
    name: str | None = None,
    description: str | None = None,
    applies_to: str | None = None,
    parent_id: int | None = None,
    disable_alerting: bool | None = None,
    custom_properties: dict[str, str] | None = None,
) -> list[TextContent]:
    """Update an existing device group in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID to update.
        name: New group name.
        description: New group description.
        applies_to: New AppliesTo expression for dynamic membership.
        parent_id: New parent group ID (moves the group).
        disable_alerting: Disable alerting for all devices in this group.
        custom_properties: Custom properties to set/update (merged with existing).

    Returns:
        List of TextContent with updated group details or error.
    """
    try:
        body: dict = {}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if applies_to is not None:
            body["appliesTo"] = applies_to
        if parent_id is not None:
            body["parentId"] = parent_id
        if disable_alerting is not None:
            body["disableAlerting"] = disable_alerting
        if custom_properties is not None:
            existing = await client.get(f"/device/groups/{group_id}")
            existing_props = {p["name"]: p["value"] for p in existing.get("customProperties", [])}
            existing_props.update(custom_properties)
            body["customProperties"] = [{"name": k, "value": v} for k, v in existing_props.items()]

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/device/groups/{group_id}", json_body=body)

        return format_response(
            {
                "message": "Device group updated successfully",
                "group": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "parent_id": result.get("parentId"),
                    "full_path": result.get("fullPath"),
                    "device_count": result.get("numOfHosts"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device_group(
    client: LogicMonitorClient,
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
