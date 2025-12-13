# Description: SDT (Scheduled Downtime) tools for LogicMonitor MCP server.
# Description: Provides list_sdts, create_sdt, delete_sdt functions.

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def list_sdts(
    client: "LogicMonitorClient",
    limit: int = 50,
) -> list[TextContent]:
    """List scheduled downtimes from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of SDTs to return.

    Returns:
        List of TextContent with SDT data or error.
    """
    try:
        params = {"size": limit}
        result = await client.get("/sdt/sdts", params=params)

        sdts = []
        for item in result.get("items", []):
            sdts.append(
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "device": item.get("deviceDisplayName"),
                    "start_time": item.get("startDateTime"),
                    "end_time": item.get("endDateTime"),
                    "comment": item.get("comment"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(sdts),
                "sdts": sdts,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_sdt(
    client: "LogicMonitorClient",
    sdt_type: str,
    device_id: int | None = None,
    device_group_id: int | None = None,
    duration_minutes: int = 60,
    comment: str = "",
) -> list[TextContent]:
    """Create a scheduled downtime in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        sdt_type: Type of SDT (DeviceSDT, DeviceGroupSDT, etc.).
        device_id: Device ID for DeviceSDT.
        device_group_id: Device group ID for DeviceGroupSDT.
        duration_minutes: Duration in minutes.
        comment: Optional comment for the SDT.

    Returns:
        List of TextContent with result or error.
    """
    try:
        now = int(time.time() * 1000)
        end_time = now + (duration_minutes * 60 * 1000)

        body = {
            "type": sdt_type,
            "startDateTime": now,
            "endDateTime": end_time,
        }

        if comment:
            body["comment"] = comment

        if sdt_type == "DeviceSDT" and device_id:
            body["deviceId"] = device_id
        elif sdt_type == "DeviceGroupSDT" and device_group_id:
            body["deviceGroupId"] = device_group_id

        result = await client.post("/sdt/sdts", json_body=body)

        return format_response(
            {
                "success": True,
                "message": f"SDT created for {duration_minutes} minutes",
                "sdt_id": result.get("id"),
                "result": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_sdt(
    client: "LogicMonitorClient",
    sdt_id: str,
) -> list[TextContent]:
    """Delete a scheduled downtime from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        sdt_id: SDT ID to delete.

    Returns:
        List of TextContent with result or error.
    """
    try:
        await client.delete(f"/sdt/sdts/{sdt_id}")

        return format_response(
            {
                "success": True,
                "message": f"SDT {sdt_id} deleted",
            }
        )
    except Exception as e:
        return handle_error(e)
