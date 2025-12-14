# Description: PropertySource tools for LogicMonitor MCP server.
# Description: Provides property source query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_propertysources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List PropertySources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Linux,technology:script"
        limit: Maximum number of PropertySources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with PropertySource data or error.
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

        result = await client.get("/setting/propertyrules", params=params)

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
                    "group": item.get("group"),
                    "version": item.get("version"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(sources)) < total

        return format_response(
            {
                "total": total,
                "count": len(sources),
                "offset": offset,
                "has_more": has_more,
                "propertysources": sources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_propertysource(
    client: "LogicMonitorClient",
    propertysource_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific PropertySource.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID.

    Returns:
        List of TextContent with PropertySource details or error.
    """
    try:
        result = await client.get(f"/setting/propertyrules/{propertysource_id}")

        source = {
            "id": result.get("id"),
            "name": result.get("name"),
            "display_name": result.get("displayName"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "technology": result.get("technology"),
            "group": result.get("group"),
            "version": result.get("version"),
            "tags": result.get("tags"),
            "audit_version": result.get("auditVersion"),
            "install_date": result.get("installDate"),
        }

        return format_response(source)
    except Exception as e:
        return handle_error(e)
