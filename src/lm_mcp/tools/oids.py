# Description: OID tools for LogicMonitor MCP server.
# Description: Provides SNMP OID query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_oids(
    client: "LogicMonitorClient",
    oid_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List OIDs from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        oid_filter: Filter by OID value (supports wildcards).
        limit: Maximum number of OIDs to return.

    Returns:
        List of TextContent with OID data or error.
    """
    try:
        params: dict = {"size": limit}

        if oid_filter:
            params["filter"] = f"oid~{oid_filter}"

        result = await client.get("/setting/oids", params=params)

        oids = []
        for item in result.get("items", []):
            oids.append(
                {
                    "id": item.get("id"),
                    "oid": item.get("oid"),
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "description": item.get("description"),
                    "datapoint_type": item.get("datapointType"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(oids),
                "oids": oids,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_oid(
    client: "LogicMonitorClient",
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
