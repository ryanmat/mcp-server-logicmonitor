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
    device_id: int | None = None,
    device_group_id: int | None = None,
    sdt_type: str | None = None,
    admin: str | None = None,
    filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List scheduled downtimes from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        device_id: Filter by device ID.
        device_group_id: Filter by device group ID.
        sdt_type: Filter by SDT type (DeviceSDT, DeviceGroupSDT, etc.).
        admin: Filter by admin/creator username (supports wildcards).
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "type:DeviceSDT,admin~john"
        limit: Maximum number of SDTs to return.

    Returns:
        List of TextContent with SDT data or error.
    """
    try:
        params: dict = {"size": limit}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if device_id is not None:
                filters.append(f"deviceId:{device_id}")
            if device_group_id is not None:
                filters.append(f"deviceGroupId:{device_group_id}")
            if sdt_type:
                filters.append(f"type:{sdt_type}")
            if admin:
                filters.append(f"admin~{admin}")

            if filters:
                params["filter"] = ",".join(filters)

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

        # Check for API error in response (LogicMonitor returns 200 with error body)
        if "errorMessage" in result or "errorCode" in result:
            return format_response(
                {
                    "success": False,
                    "error": True,
                    "code": result.get("errorCode", "API_ERROR"),
                    "message": result.get("errorMessage", "Unknown API error"),
                    "suggestion": "Check SDT type and parameters. "
                    "Valid types: DeviceSDT, DeviceGroupSDT",
                }
            )

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


# Maximum items for bulk operations to prevent accidental mass changes
BULK_OPERATION_LIMIT = 100
# Maximum SDT duration (7 days in minutes)
MAX_SDT_DURATION_MINUTES = 10080


@require_write_permission
async def bulk_create_device_sdt(
    client: "LogicMonitorClient",
    device_ids: list[int],
    duration_minutes: int = 60,
    comment: str = "",
) -> list[TextContent]:
    """Create SDT for multiple devices at once.

    Args:
        client: LogicMonitor API client.
        device_ids: List of device IDs to put in SDT. Max 100 per call.
        duration_minutes: Duration in minutes for all SDTs. Max 7 days (10080 min).
        comment: Comment to add to all SDTs.

    Returns:
        List of TextContent with results for each device.
    """
    if not device_ids:
        return format_response(
            {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": "No device IDs provided",
                "suggestion": "Provide at least one device ID",
            }
        )

    if len(device_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "BULK_LIMIT_EXCEEDED",
                "message": f"Too many devices ({len(device_ids)}). Max {BULK_OPERATION_LIMIT}.",
                "suggestion": "Split into smaller batches",
            }
        )

    if duration_minutes > MAX_SDT_DURATION_MINUTES:
        return format_response(
            {
                "error": True,
                "code": "DURATION_EXCEEDED",
                "message": f"Duration {duration_minutes}m exceeds max {MAX_SDT_DURATION_MINUTES}m",
                "suggestion": "Use shorter duration or schedule recurring SDT",
            }
        )

    now = int(time.time() * 1000)
    end_time = now + (duration_minutes * 60 * 1000)

    results = {"success": [], "failed": []}

    for device_id in device_ids:
        try:
            body = {
                "type": "DeviceSDT",
                "deviceId": device_id,
                "startDateTime": now,
                "endDateTime": end_time,
            }
            if comment:
                body["comment"] = comment

            result = await client.post("/sdt/sdts", json_body=body)
            results["success"].append({"device_id": device_id, "sdt_id": result.get("id")})
        except Exception as e:
            results["failed"].append({"device_id": device_id, "error": str(e)})

    return format_response(
        {
            "total": len(device_ids),
            "created": len(results["success"]),
            "failed": len(results["failed"]),
            "duration_minutes": duration_minutes,
            "success": results["success"],
            "failures": results["failed"],
        }
    )


@require_write_permission
async def bulk_delete_sdt(
    client: "LogicMonitorClient",
    sdt_ids: list[str],
) -> list[TextContent]:
    """Delete multiple SDTs at once.

    Args:
        client: LogicMonitor API client.
        sdt_ids: List of SDT IDs to delete. Max 100 per call.

    Returns:
        List of TextContent with results for each SDT.
    """
    if not sdt_ids:
        return format_response(
            {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": "No SDT IDs provided",
                "suggestion": "Provide at least one SDT ID",
            }
        )

    if len(sdt_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "BULK_LIMIT_EXCEEDED",
                "message": f"Too many SDTs ({len(sdt_ids)}). Max {BULK_OPERATION_LIMIT}.",
                "suggestion": "Split into smaller batches",
            }
        )

    results = {"success": [], "failed": []}

    for sdt_id in sdt_ids:
        try:
            await client.delete(f"/sdt/sdts/{sdt_id}")
            results["success"].append(sdt_id)
        except Exception as e:
            results["failed"].append({"sdt_id": sdt_id, "error": str(e)})

    return format_response(
        {
            "total": len(sdt_ids),
            "deleted": len(results["success"]),
            "failed": len(results["failed"]),
            "success_ids": results["success"],
            "failures": results["failed"],
        }
    )


async def get_active_sdts(
    client: "LogicMonitorClient",
    device_id: int | None = None,
    device_group_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get currently active SDTs.

    Args:
        client: LogicMonitor API client.
        device_id: Filter by device ID.
        device_group_id: Filter by device group ID.
        limit: Maximum number of SDTs to return.

    Returns:
        List of TextContent with active SDT data or error.
    """
    try:
        params: dict = {"size": limit}

        # Filter to only active SDTs (current time within start/end)
        now = int(time.time() * 1000)
        filters = [f"startDateTime<:{now}", f"endDateTime>:{now}"]

        if device_id:
            filters.append(f"deviceId:{device_id}")
        if device_group_id:
            filters.append(f"deviceGroupId:{device_group_id}")

        params["filter"] = ",".join(filters)

        result = await client.get("/sdt/sdts", params=params)

        sdts = []
        for item in result.get("items", []):
            sdts.append(
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "device": item.get("deviceDisplayName"),
                    "device_group": item.get("deviceGroupFullPath"),
                    "start_time": item.get("startDateTime"),
                    "end_time": item.get("endDateTime"),
                    "comment": item.get("comment"),
                    "created_by": item.get("admin"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(sdts),
                "active_sdts": sdts,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_upcoming_sdts(
    client: "LogicMonitorClient",
    hours_ahead: int = 24,
    limit: int = 50,
) -> list[TextContent]:
    """Get SDTs scheduled to start within a time window.

    Args:
        client: LogicMonitor API client.
        hours_ahead: How many hours ahead to look (default 24).
        limit: Maximum number of SDTs to return.

    Returns:
        List of TextContent with upcoming SDT data or error.
    """
    try:
        params: dict = {"size": limit}

        now = int(time.time() * 1000)
        future = now + (hours_ahead * 60 * 60 * 1000)

        # Filter to SDTs starting in the future within the window
        params["filter"] = f"startDateTime>:{now},startDateTime<:{future}"

        result = await client.get("/sdt/sdts", params=params)

        sdts = []
        for item in result.get("items", []):
            sdts.append(
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "device": item.get("deviceDisplayName"),
                    "device_group": item.get("deviceGroupFullPath"),
                    "start_time": item.get("startDateTime"),
                    "end_time": item.get("endDateTime"),
                    "comment": item.get("comment"),
                }
            )

        return format_response(
            {
                "hours_ahead": hours_ahead,
                "total": result.get("total", 0),
                "count": len(sdts),
                "upcoming_sdts": sdts,
            }
        )
    except Exception as e:
        return handle_error(e)
