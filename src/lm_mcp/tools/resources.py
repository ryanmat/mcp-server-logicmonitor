# Description: Resource/property management tools for LogicMonitor MCP server.
# Description: Provides get_device_properties, get_device_property, update_device_property.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_device_properties(
    client: "LogicMonitorClient",
    device_id: int,
    name_filter: str | None = None,
    limit: int = 100,
) -> list[TextContent]:
    """Get all properties for a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        name_filter: Filter by property name (supports wildcards).
        limit: Maximum number of properties to return.

    Returns:
        List of TextContent with property data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get(f"/device/devices/{device_id}/properties", params=params)

        properties = []
        for item in result.get("items", []):
            properties.append(
                {
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "type": item.get("type"),
                    "inherit": item.get("inherit", False),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "total": result.get("total", 0),
                "count": len(properties),
                "properties": properties,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_property(
    client: "LogicMonitorClient",
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
    client: "LogicMonitorClient",
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

        result = await client.put(
            f"/device/devices/{device_id}/properties/{property_name}",
            json_body=payload,
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
