# Description: Portal administration reads for LogicMonitor MCP server.
# Description: Provides get_tenants, the portal's tenant names.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_tenants(client: LogicMonitorClient) -> list[TextContent]:
    """List the portal's tenant names, as GET /tenants answers them: names only, no paging.

    Args:
        client: LogicMonitor API client.

    Returns:
        List of TextContent with the names and their count, or error.
    """
    try:
        result = await client.get("/tenants")
        tenants = result.get("tenants") or []
        return format_response({"tenants": tenants, "count": len(tenants)})
    except Exception as e:
        return handle_error(e)
