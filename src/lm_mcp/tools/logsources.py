# Description: LogSource tools for LogicMonitor MCP server.
# Description: Provides get_logsources, get_logsource for querying LogSource definitions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_logsources(
    client: "LogicMonitorClient",
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
    try:
        params: dict = {"size": limit, "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if name_filter:
                filters.append(f"name~{name_filter}")
            if applies_to_filter:
                filters.append(f"appliesTo~{applies_to_filter}")

            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/setting/logsources", params=params)

        logsources = []
        for item in result.get("items", []):
            logsources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "group": item.get("group"),
                    "log_type": item.get("logType"),
                    "collect_method": item.get("collectMethod"),
                    "version": item.get("version"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(logsources)) < total

        return format_response(
            {
                "total": total,
                "count": len(logsources),
                "offset": offset,
                "has_more": has_more,
                "logsources": logsources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_logsource(
    client: "LogicMonitorClient",
    logsource_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific LogSource.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID.

    Returns:
        List of TextContent with LogSource details or error.
    """
    try:
        result = await client.get(f"/setting/logsources/{logsource_id}")

        logsource = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "group": result.get("group"),
            "log_type": result.get("logType"),
            "collect_method": result.get("collectMethod"),
            "version": result.get("version"),
            "filters": result.get("filters", []),
            "log_file_path": result.get("logFilePath"),
            "log_file_format": result.get("logFileFormat"),
            "log_source_type": result.get("logSourceType"),
        }

        return format_response(logsource)
    except Exception as e:
        return handle_error(e)


async def get_device_logsources(
    client: "LogicMonitorClient",
    device_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """Get LogSources applied to a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of LogSources to return.

    Returns:
        List of TextContent with device LogSource data or error.
    """
    try:
        params: dict = {"size": limit}
        result = await client.get(f"/device/devices/{device_id}/devicelogsources", params=params)

        logsources = []
        for item in result.get("items", []):
            logsources.append(
                {
                    "id": item.get("id"),
                    "logsource_id": item.get("logSourceId"),
                    "logsource_name": item.get("logSourceName"),
                    "device_id": item.get("deviceId"),
                    "device_name": item.get("deviceDisplayName"),
                    "status": item.get("status"),
                    "last_collection_time": item.get("lastCollectTime"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "total": result.get("total", 0),
                "count": len(logsources),
                "logsources": logsources,
            }
        )
    except Exception as e:
        return handle_error(e)
