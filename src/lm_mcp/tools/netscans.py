# Description: Netscan tools for LogicMonitor MCP server.
# Description: Provides network discovery scan query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _netscan_row(item: dict) -> dict:
    """Project one /setting/netscans row onto the get_netscans fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "method": item.get("method"),
        "collector_id": item.get("collectorId"),
        "collector_group_id": item.get("collectorGroupId"),
        "group_id": item.get("groupId"),
        "next_start": item.get("nextStart"),
        "schedule": item.get("schedule"),
    }


async def get_netscans(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List netscans from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by netscan name (supports wildcards).
        limit: Maximum number of netscans to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with netscan data or error.
    """
    return await list_tool(
        client,
        "/setting/netscans",
        key="netscans",
        project=_netscan_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
    )


async def get_netscan(
    client: LogicMonitorClient,
    netscan_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific netscan.

    Args:
        client: LogicMonitor API client.
        netscan_id: Netscan ID.

    Returns:
        List of TextContent with netscan details or error.
    """
    try:
        result = await client.get(f"/setting/netscans/{netscan_id}")

        netscan = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "method": result.get("method"),
            "collector_id": result.get("collectorId"),
            "collector_group_id": result.get("collectorGroupId"),
            "collector_group_name": result.get("collectorGroupName"),
            "group_id": result.get("groupId"),
            "group": result.get("group"),
            "subnet": result.get("subnet"),
            "exclude_dup_type": result.get("excludeDuplicateType"),
            "schedule": result.get("schedule"),
            "next_start": result.get("nextStart"),
            "next_start_epoch": result.get("nextStartEpoch"),
            "credentials": result.get("credentials", {}),
        }

        return format_response(netscan)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def run_netscan(
    client: LogicMonitorClient,
    netscan_id: int,
) -> list[TextContent]:
    """Execute a netscan immediately.

    Args:
        client: LogicMonitor API client.
        netscan_id: Netscan ID to execute.

    Returns:
        List of TextContent with execution status or error.
    """
    try:
        result = await client.post(f"/setting/netscans/{netscan_id}/executenow")

        return format_response(
            {
                "success": True,
                "netscan_id": netscan_id,
                "message": "Netscan execution started",
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)
