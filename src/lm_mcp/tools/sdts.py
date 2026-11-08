# Description: SDT (Scheduled Downtime) tools for LogicMonitor MCP server.
# Description: Provides SDT list, create, update, and delete functions.

from __future__ import annotations

import time
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

# LM API v3 renamed Device* SDT types to Resource* for POST/create endpoints.
# GET/filter endpoints still accept the old names. Map before sending POST body.
_SDT_TYPE_API_MAP: dict[str, str] = {
    "DeviceSDT": "ResourceSDT",
    "DeviceGroupSDT": "ResourceGroupSDT",
    "DeviceDataSourceSDT": "ResourceDataSourceSDT",
    "DeviceDataSourceInstanceSDT": "ResourceDataSourceInstanceSDT",
    "DeviceDataSourceInstanceGroupSDT": "ResourceDataSourceInstanceGroupSDT",
    "DeviceBatchJobSDT": "ResourceBatchJobSDT",
    "DeviceClusterAlertDefSDT": "ResourceClusterAlertDefSDT",
    "DeviceEventSourceSDT": "ResourceEventSourceSDT",
}


def _sdt_row(item: dict) -> dict:
    """Project one /sdt/sdts row onto the list_sdts fields."""
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "device": item.get("deviceDisplayName"),
        "start_time": item.get("startDateTime"),
        "end_time": item.get("endDateTime"),
        "comment": item.get("comment"),
    }


async def list_sdts(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_group_id: int | None = None,
    sdt_type: str | None = None,
    admin: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
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
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with SDT data or error.
    """
    clauses = []
    if device_id is not None:
        clauses.append(f"deviceId:{device_id}")
    if device_group_id is not None:
        clauses.append(f"deviceGroupId:{device_group_id}")

    return await list_tool(
        client,
        "/sdt/sdts",
        key="sdts",
        project=_sdt_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"type:": sdt_type, "admin~": admin},
        clauses=clauses,
    )


@require_write_permission
async def create_sdt(
    client: LogicMonitorClient,
    sdt_type: str,
    device_id: int | None = None,
    device_group_id: int | None = None,
    datasource_id: int | None = None,
    duration_minutes: int = 60,
    comment: str = "",
) -> list[TextContent]:
    """Create a scheduled downtime in LogicMonitor.

    Args:
        client: LogicMonitor API client.
        sdt_type: Type of SDT (DeviceSDT, DeviceGroupSDT, DeviceDataSourceSDT, etc.).
        device_id: Device ID (for Device* SDT types).
        device_group_id: Device group ID (for DeviceGroupSDT).
        datasource_id: Datasource ID (for DeviceDataSourceSDT).
        duration_minutes: Duration in minutes.
        comment: Optional comment for the SDT.

    Returns:
        List of TextContent with result or error.
    """
    try:
        now = int(time.time() * 1000)
        end_time = now + (duration_minutes * 60 * 1000)

        api_type = _SDT_TYPE_API_MAP.get(sdt_type, sdt_type)
        body: dict = {
            "type": api_type,
            "startDateTime": now,
            "endDateTime": end_time,
        }

        if comment:
            body["comment"] = comment

        # Map SDT type to required body parameters
        if sdt_type == "DeviceGroupSDT" and device_group_id is not None:
            body["deviceGroupId"] = device_group_id
        elif sdt_type.startswith("Device") and device_id is not None:
            body["deviceId"] = device_id
            if sdt_type == "DeviceDataSourceSDT" and datasource_id is not None:
                body["dataSourceId"] = datasource_id

        result = await client.post("/sdt/sdts", json_body=body)

        # Check for API error in response (LogicMonitor returns 200 with error body)
        if "errorMessage" in result or "errorCode" in result:
            error_msg = result.get("errorMessage", "Unknown API error")
            suggestion = (
                f"Check SDT type and parameters (sent type={api_type}). "
                "Cloud resources (collector_id=-2, deviceType=4) may not support "
                "DeviceSDT. Use DeviceGroupSDT on the parent group instead."
            )
            return format_response(
                {
                    "success": False,
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": error_msg,
                    "suggestion": suggestion,
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
    client: LogicMonitorClient,
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


@require_write_permission
async def update_sdt(
    client: LogicMonitorClient,
    sdt_id: str,
    end_date_time: int | None = None,
    start_date_time: int | None = None,
    comment: str | None = None,
) -> list[TextContent]:
    """Update a scheduled downtime in LogicMonitor.

    Uses fetch-modify-PUT pattern: fetches the current SDT, applies changes,
    and PUTs the full object back. This preserves all fields not being updated.

    Args:
        client: LogicMonitor API client.
        sdt_id: SDT ID to update.
        end_date_time: New end time in epoch milliseconds.
        start_date_time: New start time in epoch milliseconds.
        comment: New SDT comment.

    Returns:
        List of TextContent with updated SDT info or error.
    """
    try:
        if end_date_time is None and start_date_time is None and comment is None:
            return format_response(
                {
                    "error": True,
                    "code": "INVALID_REQUEST",
                    "message": "No updates provided",
                }
            )

        current = await client.get(f"/sdt/sdts/{sdt_id}")
        payload = dict(current)

        if end_date_time is not None:
            payload["endDateTime"] = end_date_time
        if start_date_time is not None:
            payload["startDateTime"] = start_date_time
        if comment is not None:
            payload["comment"] = comment

        result = await client.put(f"/sdt/sdts/{sdt_id}", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"SDT {sdt_id} updated",
                "sdt": {
                    "id": result.get("id"),
                    "type": result.get("type"),
                    "start_time": result.get("startDateTime"),
                    "end_time": result.get("endDateTime"),
                    "comment": result.get("comment"),
                },
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
    client: LogicMonitorClient,
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
                "code": "INVALID_REQUEST",
                "message": "No device IDs provided",
                "suggestion": "Provide at least one device ID",
            }
        )

    if len(device_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": f"Too many devices ({len(device_ids)}). Max {BULK_OPERATION_LIMIT}.",
                "suggestion": "Split into smaller batches",
            }
        )

    if duration_minutes > MAX_SDT_DURATION_MINUTES:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
                "message": f"Duration {duration_minutes}m exceeds max {MAX_SDT_DURATION_MINUTES}m",
                "suggestion": "Use shorter duration or schedule recurring SDT",
            }
        )

    now = int(time.time() * 1000)
    end_time = now + (duration_minutes * 60 * 1000)

    results = {"success": [], "failed": []}

    api_type = _SDT_TYPE_API_MAP.get("DeviceSDT", "DeviceSDT")

    for device_id in device_ids:
        try:
            body = {
                "type": api_type,
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
    client: LogicMonitorClient,
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
                "code": "INVALID_REQUEST",
                "message": "No SDT IDs provided",
                "suggestion": "Provide at least one SDT ID",
            }
        )

    if len(sdt_ids) > BULK_OPERATION_LIMIT:
        return format_response(
            {
                "error": True,
                "code": "INVALID_REQUEST",
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


def _active_sdt_row(item: dict) -> dict:
    """Project one /sdt/sdts row onto the get_active_sdts fields."""
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "device": item.get("deviceDisplayName"),
        "device_group": item.get("deviceGroupFullPath"),
        "start_time": item.get("startDateTime"),
        "end_time": item.get("endDateTime"),
        "comment": item.get("comment"),
        "created_by": item.get("admin"),
    }


async def get_active_sdts(
    client: LogicMonitorClient,
    device_id: int | None = None,
    device_group_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get currently active SDTs.

    Args:
        client: LogicMonitor API client.
        device_id: Filter by device ID.
        device_group_id: Filter by device group ID.
        limit: Maximum number of SDTs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with active SDT data or error.
    """
    # Filter to only active SDTs (current time within start/end)
    now = int(time.time() * 1000)
    clauses = [f"startDateTime<:{now}", f"endDateTime>:{now}"]

    if device_id:
        clauses.append(f"deviceId:{device_id}")
    if device_group_id:
        clauses.append(f"deviceGroupId:{device_group_id}")

    return await list_tool(
        client,
        "/sdt/sdts",
        key="active_sdts",
        project=_active_sdt_row,
        limit=limit,
        offset=offset,
        clauses=clauses,
    )


def _upcoming_sdt_row(item: dict) -> dict:
    """Project one /sdt/sdts row onto the get_upcoming_sdts fields."""
    return {
        "id": item.get("id"),
        "type": item.get("type"),
        "device": item.get("deviceDisplayName"),
        "device_group": item.get("deviceGroupFullPath"),
        "start_time": item.get("startDateTime"),
        "end_time": item.get("endDateTime"),
        "comment": item.get("comment"),
    }


async def get_upcoming_sdts(
    client: LogicMonitorClient,
    hours_ahead: int = 24,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get SDTs scheduled to start within a time window.

    Args:
        client: LogicMonitor API client.
        hours_ahead: How many hours ahead to look (default 24).
        limit: Maximum number of SDTs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with upcoming SDT data or error.
    """
    now = int(time.time() * 1000)
    future = now + (hours_ahead * 60 * 60 * 1000)

    # Filter to SDTs starting in the future within the window
    return await list_tool(
        client,
        "/sdt/sdts",
        key="upcoming_sdts",
        project=_upcoming_sdt_row,
        limit=limit,
        offset=offset,
        clauses=[f"startDateTime>:{now}", f"startDateTime<:{future}"],
        extra={"hours_ahead": hours_ahead},
    )
