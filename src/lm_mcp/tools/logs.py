# Description: LM Logs read tools: pipelines, tracked queries, query groups, partitions and usage.
# Description: Each tool reads one LM Logs GET path of the REST API.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, list_tool

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _pipeline_row(item: dict) -> dict:
    """Project one /logpipelines row onto the get_log_pipelines fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "query": item.get("query"),
        "partitions": item.get("partitions") or [],
    }


async def get_log_pipelines(client: LogicMonitorClient) -> list[TextContent]:
    """List every LM Logs pipeline with its query and partitions.

    /logpipelines answered with all its rows both at size=1 and at offset=1 on a live
    read, so the tool reads it once and takes no paging arguments.

    Args:
        client: LogicMonitor API client.

    Returns:
        List of TextContent with total and pipelines, or an error envelope.
    """
    try:
        result = await client.get("/logpipelines")
        items = result.get("items", [])
        pipelines = [_pipeline_row(item) for item in items]
        return format_response({"total": result.get("total", len(items)), "pipelines": pipelines})
    except Exception as e:
        return handle_error(e)


async def get_tracked_log_queries(
    client: LogicMonitorClient, limit: int = 50, offset: int = 0
) -> list[TextContent]:
    """List the portal's tracked log queries, each row as the API returns it.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of tracked queries to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of tracked_queries, or an error envelope.
    """
    return await list_tool(
        client, "/tracked/log", key="tracked_queries", project=dict, limit=limit, offset=offset
    )


def _query_group_row(item: dict) -> dict:
    """Project one /log/logquerygroups row onto the get_log_query_groups fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "parent_id": item.get("parentId"),
        "owner_id": item.get("ownerId"),
        "group_type": item.get("groupType"),
        "user_permission": item.get("userPermission"),
        "log_queries": item.get("logQuery") or [],
    }


async def get_log_query_groups(
    client: LogicMonitorClient, limit: int = 50, offset: int = 0
) -> list[TextContent]:
    """List the saved log query groups and the queries each holds.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of query_groups, or an error envelope.
    """
    return await list_tool(
        client,
        "/log/logquerygroups",
        key="query_groups",
        project=_query_group_row,
        limit=limit,
        offset=offset,
    )


def _contract(contract: dict | None) -> dict[str, Any] | None:
    """Project a partition's contract onto snake-case fields, or None when it has none."""
    if not contract:
        return None
    return {
        "id": contract.get("id"),
        "state": contract.get("state"),
        "sku": contract.get("sku"),
        "retention": contract.get("retention"),
        "usage_limit": contract.get("usageLimit"),
        "stop_ingestion_on_limit": contract.get("stopIngestionOnLimit"),
        "limit_reached_at": contract.get("limitReachedAt"),
        "from_epoch": contract.get("fromEpoch"),
        "to_epoch": contract.get("toEpoch"),
    }


def _partition_row(item: dict) -> dict:
    """Project one /log/partitions row onto the get_log_partitions fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "tenant": item.get("tenant"),
        "active": item.get("active"),
        "paused_at": item.get("pausedAt"),
        "priority": item.get("priority"),
        "criteria": item.get("criteria"),
        "active_contract": _contract(item.get("activeContract")),
    }


async def get_log_partitions(
    client: LogicMonitorClient, limit: int = 50, offset: int = 0
) -> list[TextContent]:
    """List the LM Logs partitions with their state and active contract.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of partitions to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the page of partitions, or an error envelope.
    """
    return await list_tool(
        client,
        "/log/partitions",
        key="partitions",
        project=_partition_row,
        limit=limit,
        offset=offset,
    )


async def get_log_usage(client: LogicMonitorClient) -> list[TextContent]:
    """Read the portal's LM Logs usage figure from /log/usage.

    Args:
        client: LogicMonitor API client.

    Returns:
        List of TextContent with usage as the API returns it, or an error envelope.
    """
    try:
        result = await client.get("/log/usage")
        return format_response({"usage": result.get("usage")})
    except Exception as e:
        return handle_error(e)
