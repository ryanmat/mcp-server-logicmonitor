# Description: Batch Job monitoring tools for LogicMonitor MCP server.
# Description: Provides batch job and scheduled task monitoring tools.

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


# Batch jobs whose name or description holds one of maintenance, downtime, backup or
# scheduled; /setting/batchjobs matches ~ case-insensitively, | between values as OR and
# || between clauses as OR.
_DOWNTIME_JOB_CLAUSE = (
    'name~"maintenance"|"downtime"|"backup"|"scheduled"'
    '||description~"maintenance"|"downtime"|"backup"|"scheduled"'
)


def _batchjob_row(item: dict) -> dict:
    """Project one /setting/batchjobs row onto the get_batchjobs fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "group": item.get("group"),
        "schedule": item.get("schedule"),
        "timeout": item.get("timeout"),
        "status": item.get("status"),
        "last_run": item.get("lastRunTime"),
    }


async def get_batchjobs(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List batch job monitors from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by job name (supports wildcards).
        status: Filter by status (active, inactive).
        limit: Maximum number of batch jobs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with batch job data or error.
    """
    return await list_tool(
        client,
        "/setting/batchjobs",
        key="batchjobs",
        project=_batchjob_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter, "status:": status},
    )


async def get_batchjob(
    client: LogicMonitorClient,
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


def _device_batchjob_row(item: dict) -> dict:
    """Project one BatchJob devicedatasources row onto the get_device_batchjobs fields."""
    return {
        "id": item.get("id"),
        "datasource_id": item.get("dataSourceId"),
        "name": item.get("dataSourceName"),
        "display_name": item.get("dataSourceDisplayName"),
        "instance_count": item.get("instanceNumber"),
        "monitoring_instance_count": item.get("monitoringInstanceNumber"),
        "stop_monitoring": item.get("stopMonitoring"),
    }


async def get_device_batchjobs(
    client: LogicMonitorClient,
    device_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List BatchJob datasources applied to a specific device.

    BatchJob monitoring binds to devices as devicedatasources of type BJ;
    there is no dedicated device batchjobs REST endpoint. Per-run output
    and exit codes live in the BatchJob instance data (get_device_data).

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        limit: Maximum number of batch job datasources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with device batch job data or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/devicedatasources",
        key="batchjobs",
        project=_device_batchjob_row,
        limit=limit,
        offset=offset,
        clauses=['dataSourceType:"BJ"'],
        extra={
            "device_id": device_id,
            "note": (
                "Per-run output, exit codes, and timing are datapoints on the "
                "BatchJob instance; use get_device_data with the id above as "
                "device_datasource_id."
            ),
        },
    )


def _scheduled_job_row(item: dict) -> dict:
    """Project one /setting/batchjobs row onto the get_scheduled_downtime_jobs fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "schedule": item.get("schedule"),
        "timeout": item.get("timeout"),
        "status": item.get("status"),
    }


async def get_scheduled_downtime_jobs(
    client: LogicMonitorClient,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get scheduled downtime (maintenance window) configurations.

    Note: This provides visibility into scheduled batch jobs that may affect
    monitoring during maintenance windows. The portal returns the batch jobs
    whose name or description contains maintenance, downtime, backup or
    scheduled, so limit and offset page through those jobs only.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of jobs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with scheduled downtime data or error.
    """
    return await list_tool(
        client,
        "/setting/batchjobs",
        key="scheduled_jobs",
        project=_scheduled_job_row,
        limit=limit,
        offset=offset,
        clauses=[_DOWNTIME_JOB_CLAUSE],
    )
