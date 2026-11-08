# Description: Report management tools for LogicMonitor MCP server.
# Description: Provides get_reports, get_report, get_report_groups, run_report.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
    strip_readonly,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


# Server-managed fields LogicMonitor sets on a report; strip before a PUT so echoed
# read-only values do not trigger a 400.
_REPORT_READONLY_FIELDS = (
    "lastGenerateOn",
    "lastGenerateSize",
    "lastGeneratePages",
    "lastmodifyUserId",
    "lastmodifyUserName",
    "userPermission",
    "typeAlias",
    "customReportTypeName",
)


def _report_row(item: dict) -> dict:
    """Project one /report/reports row onto the get_reports fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "type": item.get("type"),
        "group_id": item.get("groupId"),
        "group_path": item.get("groupFullPath"),
        "format": item.get("format"),
        "schedule": item.get("schedule"),
        "last_generated": item.get("lastGenerateOn"),
    }


async def get_reports(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    group_id: int | None = None,
    report_type: str | None = None,
    filter: str | None = None,
    include_nextgen: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List reports from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by report name (supports wildcards).
        group_id: Filter by report group ID.
        report_type: Filter by report type (e.g., 'Alert', 'Host metric').
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~monthly,type~Alert"
        include_nextgen: Include NextGen reports (passes showNextGenReports).
        limit: Maximum number of reports to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with report data or error.
    """
    return await list_tool(
        client,
        "/report/reports",
        key="reports",
        project=_report_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "type~": report_type},
        clauses=[f"groupId:{group_id}"] if group_id is not None else [],
        params={"showNextGenReports": "true"} if include_nextgen else None,
    )


async def get_report(
    client: LogicMonitorClient,
    report_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific report.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID.

    Returns:
        List of TextContent with report details or error.
    """
    try:
        result = await client.get(f"/report/reports/{report_id}")

        report = {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description"),
            "type": result.get("type"),
            "group_id": result.get("groupId"),
            "group_path": result.get("groupFullPath"),
            "format": result.get("format"),
            "delivery": result.get("delivery"),
            "schedule": result.get("schedule"),
            "schedule_timezone": result.get("scheduleTimezone"),
            "date_range": result.get("dateRange"),
            "recipients": [
                {
                    "type": r.get("type"),
                    "method": r.get("method"),
                    "address": r.get("addr"),
                }
                for r in result.get("recipients", [])
            ],
            "last_generated": result.get("lastGenerateOn"),
            "last_generate_size": result.get("lastGenerateSize"),
            "last_generate_pages": result.get("lastGeneratePages"),
            "last_modified_by": result.get("lastmodifyUserName"),
        }

        return format_response(report)
    except Exception as e:
        return handle_error(e)


def _report_group_row(item: dict) -> dict:
    """Project one /report/groups row onto the get_report_groups fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "report_count": item.get("numOfReports"),
    }


async def get_report_groups(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List report groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with report group data or error.
    """
    return await list_tool(
        client,
        "/report/groups",
        key="groups",
        project=_report_group_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
    )


@require_write_permission
async def run_report(
    client: LogicMonitorClient,
    report_id: int,
    notify_email: str | None = None,
) -> list[TextContent]:
    """Run/execute a report now.

    Triggers an on-demand generation via the report executions endpoint
    (``POST /report/reports/{id}/executions``). The returned id can be polled at
    ``GET /report/reports/{id}/tasks/{taskId}``.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID to execute.
        notify_email: Optional recipient email(s) to notify when the report completes.

    Returns:
        List of TextContent with execution/task info or error.
    """
    try:
        payload: dict = {}
        if notify_email:
            payload["receiveEmails"] = notify_email

        result = await client.post(f"/report/reports/{report_id}/executions", json_body=payload)

        task_id = None
        if isinstance(result, dict):
            task_id = result.get("id") or result.get("taskId")

        return format_response(
            {
                "success": True,
                "report_id": report_id,
                "task_id": task_id,
                "execution": result,
                "message": "Report generation started.",
            }
        )
    except Exception as e:
        return handle_error(e)


def _scheduled_report_row(item: dict) -> dict:
    """Project one /report/reports row onto the get_scheduled_reports fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": item.get("type"),
        "schedule": item.get("schedule"),
        "schedule_timezone": item.get("scheduleTimezone"),
        "last_generated": item.get("lastGenerateOn"),
    }


async def get_scheduled_reports(
    client: LogicMonitorClient,
    enabled_only: bool = False,
    include_nextgen: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get reports that have a schedule configured.

    The LM report ``schedule`` is a single string (a cron expression; an empty string
    means the report is not scheduled), with the timezone in ``scheduleTimezone``. A
    report is considered scheduled when ``schedule`` is non-empty, and the portal
    filters on that with ``schedule!:""``, so limit and offset page through the
    scheduled reports only.

    Args:
        client: LogicMonitor API client.
        enabled_only: Accepted for compatibility; a non-empty schedule is already an
            active schedule, so this does not further filter.
        include_nextgen: Include NextGen reports (passes showNextGenReports).
        limit: Maximum number of reports to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with scheduled report data or error.
    """
    return await list_tool(
        client,
        "/report/reports",
        key="scheduled_reports",
        project=_scheduled_report_row,
        limit=limit,
        offset=offset,
        clauses=['schedule!:""'],
        params={"showNextGenReports": "true"} if include_nextgen else None,
    )


@require_write_permission
async def update_report_schedule(
    client: LogicMonitorClient,
    report_id: int,
    enabled: bool | None = None,
    cron: str | None = None,
    timezone: str | None = None,
) -> list[TextContent]:
    """Update a report's schedule.

    The LM report schedule is a single ``schedule`` string (a cron expression; an empty
    string disables it) plus a ``scheduleTimezone`` string -- not a nested object.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID to update.
        enabled: Pass False to clear the schedule (disable). True with ``cron`` sets one;
            True alone keeps the existing cron.
        cron: Cron expression for the schedule (e.g. ``"0 8 * * 1"``).
        timezone: Schedule timezone (e.g. America/Los_Angeles) -> scheduleTimezone.

    Returns:
        List of TextContent with the updated schedule or error.
    """
    try:
        # Fetch the current report and preserve its fields, dropping read-only ones so
        # the PUT does not 400 on echoed server-managed values.
        current = await client.get(f"/report/reports/{report_id}")
        payload = strip_readonly(dict(current), _REPORT_READONLY_FIELDS)

        if enabled is False:
            payload["schedule"] = ""
        if cron is not None:
            payload["schedule"] = cron
        if timezone is not None:
            payload["scheduleTimezone"] = timezone

        result = await client.put(f"/report/reports/{report_id}", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Report {report_id} schedule updated",
                "report": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "schedule": result.get("schedule"),
                    "schedule_timezone": result.get("scheduleTimezone"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_report(
    client: LogicMonitorClient,
    name: str,
    report_type: str,
    group_id: int = 1,
    description: str | None = None,
    format: str = "PDF",
    schedule_cron: str | None = None,
    schedule_timezone: str | None = None,
) -> list[TextContent]:
    """Create a new report.

    To schedule the report, pass ``schedule_cron`` (a cron expression); the LM report
    ``schedule`` field is that string, with the timezone in ``scheduleTimezone``.

    Args:
        client: LogicMonitor API client.
        name: Report name.
        report_type: Report type (Alert, Host Metric, etc.).
        group_id: Report group ID (default: 1 for root).
        description: Report description.
        format: Output format (PDF, CSV, HTML).
        schedule_cron: Cron expression to schedule generation (omit for on-demand only).
        schedule_timezone: Schedule timezone (e.g. America/Los_Angeles).

    Returns:
        List of TextContent with created report or error.
    """
    try:
        payload: dict = {
            "name": name,
            "type": report_type,
            "groupId": group_id,
            "format": format.upper(),
        }

        if description:
            payload["description"] = description
        if schedule_cron:
            payload["schedule"] = schedule_cron
        if schedule_timezone:
            payload["scheduleTimezone"] = schedule_timezone

        result = await client.post("/report/reports", json_body=payload)

        return format_response(
            {
                "success": True,
                "message": f"Report '{name}' created",
                "report": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "type": result.get("type"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_report(
    client: LogicMonitorClient,
    report_id: int,
) -> list[TextContent]:
    """Delete a report.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID to delete.

    Returns:
        List of TextContent with deletion result or error.
    """
    try:
        # Get report info first
        report = await client.get(f"/report/reports/{report_id}")
        report_name = report.get("name", f"ID:{report_id}")

        await client.delete(f"/report/reports/{report_id}")

        return format_response(
            {
                "success": True,
                "message": f"Report '{report_name}' deleted",
                "report_id": report_id,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_report_execution(
    client: LogicMonitorClient,
    report_id: int,
    task_id: int,
) -> list[TextContent]:
    """Poll the status of a report generation task started by run_report.

    Wraps GET /report/reports/{id}/tasks/{taskId}, the documented poll
    endpoint for executions triggered via run_report.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID.
        task_id: Task ID returned by run_report.

    Returns:
        List of TextContent with execution status (and result URL when
        generation has finished) or error.
    """
    try:
        result = await client.get(f"/report/reports/{report_id}/tasks/{task_id}")

        response: dict = {
            "report_id": report_id,
            "task_id": task_id,
            "status": result.get("status"),
            "result_url": result.get("resulturl") or result.get("resultUrl"),
            "execution": result,
        }
        return format_response(response)
    except Exception as e:
        return handle_error(e)
