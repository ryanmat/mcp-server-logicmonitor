# Description: Collector management tools for LogicMonitor MCP server.
# Description: Provides get_collectors, get_collector functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_collectors(
    client: "LogicMonitorClient",
    limit: int = 50,
) -> list[TextContent]:
    """List collectors from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of collectors to return.

    Returns:
        List of TextContent with collector data or error.
    """
    try:
        params = {"size": limit}
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

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(collectors),
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
