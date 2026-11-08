# Description: LogSource tools for LogicMonitor MCP server.
# Description: Provides get_logsources, get_logsource for querying LogSource definitions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    list_tool,
    normalize_definition_fields,
    paginated_response,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# The LogSource REST model names its collection method collectionMethod, which
# normalize_definition_fields would otherwise rename to the DataSource field collectMethod.
_REST_FIELDS = frozenset({"collectionMethod"})


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
    try:
        params: dict = {"size": limit, "offset": offset}
        wildcards_stripped = False

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if name_filter:
                clean_name, was_modified = sanitize_filter_value(name_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"name~{quote_filter_value(clean_name)}")
            if applies_to_filter:
                clean_val, was_modified = sanitize_filter_value(applies_to_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"appliesTo~{quote_filter_value(clean_val)}")

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

        response = {
            **paginated_response(logsources, result, offset),
            "logsources": logsources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_logsource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a LogSource via REST API using a full definition dict.

    Accepts REST API format (same format returned by export_logsource).
    Use this for creating LogSources from exported definitions or from
    scratch. For LM Exchange format imports, use import_logsource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full LogSource definition dict in REST API format.
        overwrite: If True, delete existing LogSource with the same name
            before creating.

    Returns:
        List of TextContent with created LogSource info or error.
    """
    try:
        payload = normalize_definition_fields(definition, keep=_REST_FIELDS)
        payload.pop("id", None)

        if overwrite and payload.get("name"):
            existing = await client.get(
                "/setting/logsources",
                params={"filter": f"name:{quote_filter_value(payload['name'])}", "size": 1},
            )
            items = existing.get("items", [])
            if items:
                await client.delete(f"/setting/logsources/{items[0]['id']}")

        result = await client.post("/setting/logsources", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"LogSource '{result.get('name')}' created successfully",
                "logsource": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


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
    if not confirm:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": (
                    "update_logsource is full-replace -- any field omitted from "
                    "`definition` will be BLANKED. Set confirm=true to proceed, OR "
                    "use update_logicmodule(type='logsource', id, changes, mode='preview') "
                    "for a safe partial update with diff preview."
                ),
            }
        )
    try:
        payload = normalize_definition_fields(definition, keep=_REST_FIELDS)
        payload.pop("id", None)

        result = await client.put(f"/setting/logsources/{logsource_id}", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"LogSource '{result.get('name')}' updated successfully",
                "logsource": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_logsource(
    client: LogicMonitorClient,
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
    try:
        ls = await client.get(f"/setting/logsources/{logsource_id}")
        ls_name = ls.get("name", f"ID:{logsource_id}")

        await client.delete(f"/setting/logsources/{logsource_id}")

        return format_response(
            {
                "success": True,
                "message": f"LogSource '{ls_name}' deleted",
                "logsource_id": logsource_id,
            }
        )
    except Exception as e:
        return handle_error(e)
