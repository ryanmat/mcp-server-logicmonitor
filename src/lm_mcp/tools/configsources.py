# Description: ConfigSource tools for LogicMonitor MCP server.
# Description: Provides configuration source query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_configsources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List ConfigSources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Cisco,technology:snmp"
        limit: Maximum number of ConfigSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with ConfigSource data or error.
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
                filters.append(f'name~{quote_filter_value(clean_name)}')
            if applies_to_filter:
                clean_val, was_modified = sanitize_filter_value(applies_to_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f'appliesTo~{quote_filter_value(clean_val)}')

            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/setting/configsources", params=params)

        sources = []
        for item in result.get("items", []):
            sources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "technology": item.get("technology"),
                    "collect_method": item.get("collectMethod"),
                    "collect_interval": item.get("collectInterval"),
                    "version": item.get("version"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(sources)) < total

        response = {
            "total": total,
            "count": len(sources),
            "offset": offset,
            "has_more": has_more,
            "configsources": sources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_configsource(
    client: "LogicMonitorClient",
    configsource_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific ConfigSource.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID.

    Returns:
        List of TextContent with ConfigSource details or error.
    """
    try:
        result = await client.get(f"/setting/configsources/{configsource_id}")

        source = {
            "id": result.get("id"),
            "name": result.get("name"),
            "display_name": result.get("displayName"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "technology": result.get("technology"),
            "collect_method": result.get("collectMethod"),
            "collect_interval": result.get("collectInterval"),
            "version": result.get("version"),
            "tags": result.get("tags"),
            "audit_version": result.get("auditVersion"),
            "install_date": result.get("installDate"),
            "config_checks": result.get("configChecks", []),
        }

        return format_response(source)
    except Exception as e:
        return handle_error(e)
