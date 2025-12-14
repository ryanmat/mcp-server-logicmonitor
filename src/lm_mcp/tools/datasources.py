# Description: DataSource tools for LogicMonitor MCP server.
# Description: Provides get_datasources, get_datasource for querying LogicModule definitions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_datasources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List DataSources (LogicModules) from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by DataSource name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~CPU,group:Core"
        limit: Maximum number of DataSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with DataSource data or error.
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

        result = await client.get("/setting/datasources", params=params)

        datasources = []
        for item in result.get("items", []):
            datasources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "group": item.get("group"),
                    "collect_method": item.get("collectMethod"),
                    "has_multi_instances": item.get("hasMultiInstances"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(datasources)) < total

        return format_response(
            {
                "total": total,
                "count": len(datasources),
                "offset": offset,
                "has_more": has_more,
                "datasources": datasources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_datasource(
    client: "LogicMonitorClient",
    datasource_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific DataSource.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID.

    Returns:
        List of TextContent with DataSource details or error.
    """
    try:
        result = await client.get(f"/setting/datasources/{datasource_id}")

        # Extract key details for a cleaner response
        datasource = {
            "id": result.get("id"),
            "name": result.get("name"),
            "display_name": result.get("displayName"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "group": result.get("group"),
            "collect_method": result.get("collectMethod"),
            "collect_interval": result.get("collectInterval"),
            "has_multi_instances": result.get("hasMultiInstances"),
            "datapoints": [
                {
                    "id": dp.get("id"),
                    "name": dp.get("name"),
                    "description": dp.get("description"),
                    "type": dp.get("type"),
                    "alert_expr": dp.get("alertExpr"),
                }
                for dp in result.get("dataPoints", [])
            ],
            "graphs": [
                {
                    "id": g.get("id"),
                    "name": g.get("name"),
                    "title": g.get("title"),
                }
                for g in result.get("graphs", [])
            ],
        }

        return format_response(datasource)
    except Exception as e:
        return handle_error(e)
