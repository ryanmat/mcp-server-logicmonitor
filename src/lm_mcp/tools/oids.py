# Description: OID tools for LogicMonitor MCP server.
# Description: Provides SNMP OID query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _oid_row(item: dict) -> dict:
    """Project one /setting/oids row onto the get_oids fields."""
    return {
        "id": item.get("id"),
        "oid": item.get("oid"),
        "name": item.get("name"),
        "category": item.get("category"),
        "description": item.get("description"),
        "datapoint_type": item.get("datapointType"),
    }


async def get_oids(
    client: LogicMonitorClient,
    oid_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List OIDs from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        oid_filter: Filter by OID value (supports wildcards).
        limit: Maximum number of OIDs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with OID data or error.
    """
    return await list_tool(
        client,
        "/setting/oids",
        key="oids",
        project=_oid_row,
        limit=limit,
        offset=offset,
        named={"oid~": oid_filter},
    )


async def get_oid(
    client: LogicMonitorClient,
    oid_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific OID.

    Args:
        client: LogicMonitor API client.
        oid_id: OID ID.

    Returns:
        List of TextContent with OID details or error.
    """
    try:
        result = await client.get(f"/setting/oids/{oid_id}")

        oid = {
            "id": result.get("id"),
            "oid": result.get("oid"),
            "name": result.get("name"),
            "category": result.get("category"),
            "description": result.get("description"),
            "datapoint_type": result.get("datapointType"),
            "datapoint_description": result.get("datapointDescription"),
        }

        return format_response(oid)
    except Exception as e:
        return handle_error(e)
