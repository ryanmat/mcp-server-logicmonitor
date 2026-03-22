# Description: Collector management tools for LogicMonitor MCP server.
# Description: Provides collector and collector group query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_collectors(
    client: LogicMonitorClient,
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
        wildcards_stripped = False

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if hostname_filter:
                clean_hostname, was_modified = sanitize_filter_value(hostname_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"hostname~{quote_filter_value(clean_hostname)}")
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

        response = {
            "total": total,
            "count": len(collectors),
            "offset": offset,
            "has_more": has_more,
            "collectors": collectors,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_collector(
    client: LogicMonitorClient,
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
    client: LogicMonitorClient,
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
        wildcards_stripped = False

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        elif name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f"name~{quote_filter_value(clean_name)}"

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

        response = {
            "total": result.get("total", 0),
            "count": len(groups),
            "collector_groups": groups,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_collector_group(
    client: LogicMonitorClient,
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


@require_write_permission
async def update_collector(
    client: LogicMonitorClient,
    collector_id: int,
    description: str | None = None,
    collector_group_id: int | None = None,
    enable_failback: bool | None = None,
    escalation_chain_id: int | None = None,
) -> list[TextContent]:
    """Update a collector in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID to update.
        description: New description.
        collector_group_id: New collector group ID.
        enable_failback: Enable automatic failback.
        escalation_chain_id: Escalation chain ID for collector down alerts.

    Returns:
        List of TextContent with updated collector details or error.
    """
    try:
        body: dict = {}

        if description is not None:
            body["description"] = description
        if collector_group_id is not None:
            body["collectorGroupId"] = collector_group_id
        if enable_failback is not None:
            body["enableFailBack"] = enable_failback
        if escalation_chain_id is not None:
            body["escalatingChainId"] = escalation_chain_id

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "NO_CHANGES",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(f"/setting/collector/collectors/{collector_id}", json_body=body)

        return format_response(
            {
                "message": "Collector updated successfully",
                "collector": {
                    "id": result.get("id"),
                    "hostname": result.get("hostname"),
                    "collector_group_id": result.get("collectorGroupId"),
                    "collector_group_name": result.get("collectorGroupName"),
                    "description": result.get("description"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_collector(
    client: LogicMonitorClient,
    collector_id: int,
) -> list[TextContent]:
    """Delete a collector from LogicMonitor.

    Blocks deletion if the collector still has devices assigned to prevent
    orphaning monitored resources.

    Args:
        client: LogicMonitor API client.
        collector_id: Collector ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        collector = await client.get(f"/setting/collector/collectors/{collector_id}")
        hostname = collector.get("hostname", f"ID:{collector_id}")
        device_count = collector.get("numberOfHosts", 0)

        if device_count > 0:
            return format_response(
                {
                    "error": True,
                    "code": "COLLECTOR_HAS_DEVICES",
                    "message": f"Collector '{hostname}' has {device_count} devices assigned. "
                    "Move or delete devices before removing the collector.",
                    "collector_id": collector_id,
                    "device_count": device_count,
                }
            )

        await client.delete(f"/setting/collector/collectors/{collector_id}")

        return format_response(
            {
                "success": True,
                "message": f"Collector '{hostname}' deleted",
                "collector_id": collector_id,
            }
        )
    except Exception as e:
        return handle_error(e)
