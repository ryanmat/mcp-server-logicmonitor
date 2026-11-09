# Description: LogSource tools for LogicMonitor MCP server.
# Description: Provides get_logsources, get_logsource for querying LogSource definitions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
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


async def get_logsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List LogSources from LogicMonitor.

    LogSources define how logs are collected from resources.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by LogSource name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~syslog,logType:EventLog"
        limit: Maximum number of LogSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with LogSource data or error.
    """
    module = MODULES["logsource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="logsources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


@require_write_permission
async def create_logsource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a LogSource via REST API using a full definition dict.

    Accepts REST API format (the format get_logsource returns with raw=true).
    Use this for creating LogSources from exported definitions or from
    scratch. For LM Exchange format imports, use import_logsource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full LogSource definition dict in REST API format.
        overwrite: If True, replace the LogSource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created LogSource info or error.
    """
    return await create_module(client, "logsource", definition, overwrite)


@require_write_permission
async def update_logsource(
    client: LogicMonitorClient,
    logsource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing LogSource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID to update.
        definition: Full LogSource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated LogSource info or error.
    """
    return await update_module(client, "logsource", logsource_id, definition, confirm)


async def get_logsource(
    client: LogicMonitorClient,
    logsource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific LogSource.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with LogSource details or error.
    """
    return await get_module(client, "logsource", logsource_id, raw)


def _device_logsource_row(item: dict) -> dict:
    """Project one devicelogsources row onto the get_device_logsources fields."""
    return {
        "id": item.get("id"),
        "logsource_id": item.get("logSourceId"),
        "logsource_name": item.get("logSourceName"),
        "device_id": item.get("deviceId"),
        "device_name": item.get("deviceDisplayName"),
        "status": item.get("status"),
        "last_collection_time": item.get("lastCollectTime"),
    }


async def get_device_logsources(
    client: LogicMonitorClient,
    device_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get LogSources applied to a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of LogSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with device LogSource data or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/devicelogsources",
        key="logsources",
        project=_device_logsource_row,
        limit=limit,
        offset=offset,
        extra={"device_id": device_id},
    )


@require_write_permission
async def delete_logsource(
    client: LogicMonitorClient,
    logsource_id: int,
) -> list[TextContent]:
    """Delete a LogSource from LogicMonitor.

    Removes the LogSource definition. Existing collected log data
    is retained but no new logs will be collected by this source.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "logsource", logsource_id)
