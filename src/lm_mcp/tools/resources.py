# Description: Resource/property management tools for LogicMonitor MCP server.
# Description: Reads, sets and deletes the properties of devices and device groups.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.exceptions import NotFoundError
from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _device_property_row(item: dict) -> dict:
    """Project one device properties row onto the get_device_properties fields."""
    return {
        "name": item.get("name"),
        "value": item.get("value"),
        "type": item.get("type"),
        "inherit": item.get("inherit", False),
    }


async def get_device_properties(
    client: LogicMonitorClient,
    device_id: int,
    name_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TextContent]:
    """Get all properties for a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        name_filter: Filter by property name (supports wildcards).
        limit: Maximum number of properties to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with property data or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/properties",
        key="properties",
        project=_device_property_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
        extra={"device_id": device_id},
    )


async def get_device_property(
    client: LogicMonitorClient,
    device_id: int,
    property_name: str,
) -> list[TextContent]:
    """Get a specific property for a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        property_name: Name of the property to retrieve.

    Returns:
        List of TextContent with property details or error.
    """
    try:
        result = await client.get(f"/device/devices/{device_id}/properties/{property_name}")

        return format_response(
            {
                "device_id": device_id,
                "name": result.get("name"),
                "value": result.get("value"),
                "type": result.get("type"),
                "inherit": result.get("inherit", False),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_device_property(
    client: LogicMonitorClient,
    device_id: int,
    property_name: str,
    property_value: str,
) -> list[TextContent]:
    """Update or create a custom property on a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        property_name: Name of the property to update/create.
        property_value: New value for the property.

    Returns:
        List of TextContent with update result or error.
    """
    try:
        result = await _set_property(
            client, f"/device/devices/{device_id}/properties", property_name, property_value
        )
        return format_response(
            {
                "success": True,
                "device_id": device_id,
                "property": _written_property(result, property_name, property_value),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device_property(
    client: LogicMonitorClient,
    device_id: int,
    property_name: str,
) -> list[TextContent]:
    """Delete a property set on the device itself.

    The portal answers not found for a name the device only inherits and refuses a
    system property.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        property_name: Name of the device's own property.

    Returns:
        List of TextContent with the deleted name or error.
    """
    try:
        await client.delete(f"/device/devices/{device_id}/properties/{property_name}")
        return format_response({"success": True, "device_id": device_id, "deleted": property_name})
    except Exception as e:
        return handle_error(e)


def _group_property_row(item: dict) -> dict:
    """Project one device group property: its value in force, its type (custom, inherit or
    system), and each ancestor group holding the same name, nearest first."""
    return {
        "name": item.get("name"),
        "value": item.get("value"),
        "type": item.get("type"),
        "ancestors": [
            {
                "group_id": entry.get("id"),
                "path": entry.get("fullpath"),
                "value": entry.get("value"),
            }
            for entry in item.get("inheritList") or []
        ],
    }


async def get_device_group_properties(
    client: LogicMonitorClient,
    group_id: int,
    property_name: str | None = None,
    name_filter: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TextContent]:
    """Get a device group's properties, its own and those it inherits, or one by name.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID.
        property_name: Read only this property; the page arguments are then unused.
        name_filter: Keep properties whose name contains this text.
        limit: Maximum number of properties to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the properties, or the one property, or error.
    """
    path = f"/device/groups/{group_id}/properties"
    if property_name:
        try:
            result = await client.get(f"{path}/{property_name}")
            return format_response({"group_id": group_id, **_group_property_row(result)})
        except Exception as e:
            return handle_error(e)
    return await list_tool(
        client,
        path,
        key="properties",
        project=_group_property_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
        extra={"group_id": group_id},
    )


@require_write_permission
async def update_device_group_property(
    client: LogicMonitorClient,
    group_id: int,
    property_name: str,
    property_value: str,
) -> list[TextContent]:
    """Set a property on a device group, creating the group's own value when it has none.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID.
        property_name: Name of the property to set.
        property_value: Value to set.

    Returns:
        List of TextContent with the property as written or error.
    """
    try:
        result = await _set_property(
            client, f"/device/groups/{group_id}/properties", property_name, property_value
        )
        return format_response(
            {
                "success": True,
                "group_id": group_id,
                "property": _written_property(result, property_name, property_value),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device_group_property(
    client: LogicMonitorClient,
    group_id: int,
    property_name: str,
) -> list[TextContent]:
    """Delete a property set on the device group itself.

    The portal answers not found for a name the group only inherits and refuses a
    system property.

    Args:
        client: LogicMonitor API client.
        group_id: Device group ID.
        property_name: Name of the group's own property.

    Returns:
        List of TextContent with the deleted name or error.
    """
    try:
        await client.delete(f"/device/groups/{group_id}/properties/{property_name}")
        return format_response({"success": True, "group_id": group_id, "deleted": property_name})
    except Exception as e:
        return handle_error(e)


async def _set_property(
    client: LogicMonitorClient, path: str, property_name: str, property_value: str
) -> dict:
    """PUT the value onto the entity's own property under path; when the entity holds no
    value of its own under that name (404, inherited or absent), POST one.

    Args:
        client: LogicMonitor API client.
        path: The entity's properties path, such as /device/devices/7/properties.
        property_name: Name of the property.
        property_value: Value to write.

    Returns:
        The property record the portal answers.
    """
    try:
        return await client.put(f"{path}/{property_name}", json_body={"value": property_value})
    except NotFoundError:
        return await client.post(path, json_body={"name": property_name, "value": property_value})


def _written_property(result: dict, property_name: str, property_value: str) -> dict:
    """The name, value and type of a property write's answer, the request's name and value
    standing in for any the answer leaves out."""
    return {
        "name": result.get("name", property_name),
        "value": result.get("value", property_value),
        "type": result.get("type"),
    }
