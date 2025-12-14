# Description: Collector management tools for LogicMonitor MCP server.
# Description: Provides collector and collector group query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_collectors(
    client: "LogicMonitorClient",
    hostname_filter: str | None = None,
    collector_group_id: int | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List collectors from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        hostname_filter: Filter by hostname (supports wildcards).
        collector_group_id: Filter by collector group ID.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "hostname~prod,collectorGroupId:1"
        limit: Maximum number of collectors to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with collector data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if hostname_filter:
                filters.append(f"hostname~{hostname_filter}")
            if collector_group_id is not None:
                filters.append(f"collectorGroupId:{collector_group_id}")

            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/setting/collector/collectors", params=params)

        collectors = []
        for item in result.get("items", []):
            collectors.append(
                {
                    "id": item.get("id"),
                    "hostname": item.get("hostname"),
                    "status": item.get("status"),
                    "device_count": item.get("numberOfHosts"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(collectors)) < total

        return format_response(
            {
                "total": total,
                "count": len(collectors),
                "offset": offset,
                "has_more": has_more,
                "collectors": collectors,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_collector(
    client: "LogicMonitorClient",
    collector_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific collector.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID.

    Returns:
        List of TextContent with collector details or error.
    """
    try:
        result = await client.get(f"/setting/collector/collectors/{collector_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_collector_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List collector groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        filter: Raw filter expression for advanced queries (overrides name_filter).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~prod,autoBalance:true"
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with collector group data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        elif name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/collector/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "num_of_collectors": item.get("numOfCollectors"),
                    "auto_balance": item.get("autoBalance"),
                    "auto_balance_strategy": item.get("autoBalanceStrategy"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "collector_groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_collector_group(
    client: "LogicMonitorClient",
    group_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific collector group.

    Args:
        client: LogicMonitor API client.
        group_id: Collector group ID.

    Returns:
        List of TextContent with collector group details or error.
    """
    try:
        result = await client.get(f"/setting/collector/groups/{group_id}")

        group = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "num_of_collectors": result.get("numOfCollectors"),
            "auto_balance": result.get("autoBalance"),
            "auto_balance_strategy": result.get("autoBalanceStrategy"),
            "auto_balance_instance_count_threshold": result.get(
                "autoBalanceInstanceCountThreshold"
            ),
            "custom_properties": [
                {"name": p.get("name"), "value": p.get("value")}
                for p in result.get("customProperties", [])
            ],
        }

        return format_response(group)
    except Exception as e:
        return handle_error(e)
