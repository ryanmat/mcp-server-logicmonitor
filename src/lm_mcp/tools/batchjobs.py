# Description: Batch Job monitoring tools for LogicMonitor MCP server.
# Description: Provides batch job and scheduled task monitoring tools.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_batchjobs(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List batch job monitors from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by job name (supports wildcards).
        status: Filter by status (active, inactive).
        limit: Maximum number of batch jobs to return.

    Returns:
        List of TextContent with batch job data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if name_filter:
            filters.append(f"name~{name_filter}")
        if status:
            filters.append(f"status:{status}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/batchjobs", params=params)

        jobs = []
        for item in result.get("items", []):
            jobs.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "group": item.get("group"),
                    "schedule": item.get("schedule"),
                    "timeout": item.get("timeout"),
                    "status": item.get("status"),
                    "last_run": item.get("lastRunTime"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(jobs),
                "batchjobs": jobs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_batchjob(
    client: "LogicMonitorClient",
    batchjob_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific batch job.

    Args:
        client: LogicMonitor API client.
        batchjob_id: Batch job ID.

    Returns:
        List of TextContent with batch job details or error.
    """
    try:
        result = await client.get(f"/setting/batchjobs/{batchjob_id}")

        batchjob = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "group": result.get("group"),
            "schedule": result.get("schedule"),
            "timeout": result.get("timeout"),
            "status": result.get("status"),
            "script": result.get("script"),
            "script_type": result.get("scriptType"),
            "applies_to": result.get("appliesTo"),
            "alert_effective_ival": result.get("alertEffectiveIval"),
        }

        return format_response(batchjob)
    except Exception as e:
        return handle_error(e)


async def get_device_batchjobs(
    client: "LogicMonitorClient",
    device_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """Get batch jobs configured for a specific device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of batch jobs to return.

    Returns:
        List of TextContent with device batch job data or error.
    """
    try:
        params: dict = {"size": limit}
        result = await client.get(f"/device/devices/{device_id}/batchjobs", params=params)

        jobs = []
        for item in result.get("items", []):
            jobs.append(
                {
                    "id": item.get("id"),
                    "batchjob_id": item.get("batchJobId"),
                    "batchjob_name": item.get("batchJobName"),
                    "device_id": item.get("deviceId"),
                    "device_name": item.get("deviceDisplayName"),
                    "status": item.get("status"),
                    "last_run_time": item.get("lastRunTime"),
                    "last_run_status": item.get("lastRunStatus"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "total": result.get("total", 0),
                "count": len(jobs),
                "batchjobs": jobs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_batchjob_history(
    client: "LogicMonitorClient",
    device_id: int,
    batchjob_id: int,
    limit: int = 50,
) -> list[TextContent]:
    """Get execution history for a batch job on a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        batchjob_id: Batch job ID.
        limit: Maximum number of history records to return.

    Returns:
        List of TextContent with batch job history or error.
    """
    try:
        params: dict = {"size": limit}
        result = await client.get(
            f"/device/devices/{device_id}/batchjobs/{batchjob_id}/history", params=params
        )

        history = []
        for item in result.get("items", []):
            history.append(
                {
                    "id": item.get("id"),
                    "run_time": item.get("runTime"),
                    "status": item.get("status"),
                    "exit_code": item.get("exitCode"),
                    "duration": item.get("duration"),
                    "output": item.get("output"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "batchjob_id": batchjob_id,
                "total": result.get("total", 0),
                "count": len(history),
                "history": history,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_scheduled_downtime_jobs(
    client: "LogicMonitorClient",
    limit: int = 50,
) -> list[TextContent]:
    """Get scheduled downtime (maintenance window) configurations.

    Note: This provides visibility into scheduled batch jobs that may affect
    monitoring during maintenance windows.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of jobs to return.

    Returns:
        List of TextContent with scheduled downtime data or error.
    """
    try:
        params: dict = {"size": limit}
        result = await client.get("/setting/batchjobs", params=params)

        # Filter to jobs that appear to be maintenance/downtime related
        jobs = []
        for item in result.get("items", []):
            name = item.get("name", "").lower()
            desc = item.get("description", "").lower()

            # Include if name or description suggests maintenance/downtime
            if any(
                keyword in name or keyword in desc
                for keyword in ["maintenance", "downtime", "backup", "scheduled"]
            ):
                jobs.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "description": item.get("description"),
                        "schedule": item.get("schedule"),
                        "timeout": item.get("timeout"),
                        "status": item.get("status"),
                    }
                )

        return format_response(
            {
                "total": len(jobs),
                "count": len(jobs),
                "scheduled_jobs": jobs,
            }
        )
    except Exception as e:
        return handle_error(e)
