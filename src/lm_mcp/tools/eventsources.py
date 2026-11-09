# Description: EventSource tools for LogicMonitor MCP server.
# Description: Provides event source query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
)
from lm_mcp.tools.logicmodules import (
    MODULES,
    create_module,
    delete_module,
    get_module,
    update_module,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_eventsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List EventSources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Windows,group:Events"
        limit: Maximum number of EventSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with EventSource data or error.
    """
    module = MODULES["eventsource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="eventsources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


@require_write_permission
async def create_eventsource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create an EventSource via REST API using a full definition dict.

    Accepts REST API format (the format get_eventsource returns with raw=true).
    Use this for creating EventSources from exported definitions or from
    scratch. For LM Exchange format imports, use import_eventsource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full EventSource definition dict in REST API format.
        overwrite: If True, replace the EventSource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created EventSource info or error.
    """
    return await create_module(client, "eventsource", definition, overwrite)


@require_write_permission
async def update_eventsource(
    client: LogicMonitorClient,
    eventsource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing EventSource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out.

    Args:
        client: LogicMonitor API client.
        eventsource_id: EventSource ID to update.
        definition: Full EventSource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated EventSource info or error.
    """
    return await update_module(client, "eventsource", eventsource_id, definition, confirm)


async def get_eventsource(
    client: LogicMonitorClient,
    eventsource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific EventSource.

    Args:
        client: LogicMonitor API client.
        eventsource_id: EventSource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with EventSource details or error.
    """
    return await get_module(client, "eventsource", eventsource_id, raw)


def _device_eventsource_row(item: dict) -> dict:
    """Project one deviceeventsources row onto the get_device_eventsources fields."""
    return {
        "id": item.get("id"),
        "eventsource_id": item.get("eventSourceId"),
        "name": item.get("eventSourceDisplayName") or item.get("dataSourceDisplayName", ""),
        "alerting_disabled": item.get("alertDisableStatus", "none"),
        "alert_status": item.get("alertStatus", "none"),
    }


async def get_device_eventsources(
    client: LogicMonitorClient,
    device_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get EventSources applied to a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum results.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with device EventSource associations or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/deviceeventsources",
        key="eventsources",
        project=_device_eventsource_row,
        limit=limit,
        offset=offset,
        extra={"device_id": device_id},
    )


@require_write_permission
async def update_device_eventsource(
    client: LogicMonitorClient,
    device_id: int,
    device_eventsource_id: int,
    disable_alerting: bool | None = None,
) -> list[TextContent]:
    """Update a device-level EventSource association.

    Allows enabling or disabling alerting for an EventSource on a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_eventsource_id: Device-EventSource association ID (from get_device_eventsources).
        disable_alerting: Set True to disable alerting, False to enable.

    Returns:
        List of TextContent with updated association or error.
    """
    try:
        body: dict = {}

        if disable_alerting is not None:
            body["disableAlerting"] = disable_alerting

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(
            f"/device/devices/{device_id}/deviceeventsources/{device_eventsource_id}",
            json_body=body,
        )

        return format_response(
            {
                "message": "Device EventSource updated successfully",
                "device_id": device_id,
                "device_eventsource_id": device_eventsource_id,
                "name": result.get("eventSourceDisplayName")
                or result.get("dataSourceDisplayName", ""),
                "alerting_disabled": result.get("alertDisableStatus", ""),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_eventsource(
    client: LogicMonitorClient,
    eventsource_id: int,
) -> list[TextContent]:
    """Delete an EventSource from LogicMonitor.

    Removes the EventSource definition. Existing collected event data
    is retained on devices but no new events will be collected.

    Args:
        client: LogicMonitor API client.
        eventsource_id: EventSource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "eventsource", eventsource_id)
