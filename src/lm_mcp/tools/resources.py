# Description: Resource/property management tools for LogicMonitor MCP server.
# Description: Provides get_device_properties, get_device_property, update_device_property.

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
        payload = {"value": property_value}

        try:
            result = await client.put(
                f"/device/devices/{device_id}/properties/{property_name}",
                json_body=payload,
            )
        except NotFoundError:
            # Property doesn't exist yet — create it via POST
            result = await client.post(
                f"/device/devices/{device_id}/properties",
                json_body={"name": property_name, "value": property_value},
            )

        return format_response(
            {
                "success": True,
                "device_id": device_id,
                "property": {
                    "name": result.get("name", property_name),
                    "value": result.get("value", property_value),
                    "type": result.get("type"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)
