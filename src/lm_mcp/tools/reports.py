# Description: Report management tools for LogicMonitor MCP server.
# Description: Provides get_reports, get_report, get_report_groups, run_report.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_reports(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_id: int | None = None,
    report_type: str | None = None,
    filter: str | None = None,
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
        limit: Maximum number of reports to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with report data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}

        # If raw filter is provided, use it directly (power user mode)
        if filter:
            params["filter"] = filter
        else:
            # Build filter from named parameters
            filters = []
            if name_filter:
                filters.append(f"name~{name_filter}")
            if group_id is not None:
                filters.append(f"groupId:{group_id}")
            if report_type:
                filters.append(f"type~{report_type}")

            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/report/reports", params=params)

        reports = []
        for item in result.get("items", []):
            reports.append(
                {
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
            )

        total = result.get("total", 0)
        has_more = (offset + len(reports)) < total

        return format_response(
            {
                "total": total,
                "count": len(reports),
                "offset": offset,
                "has_more": has_more,
                "reports": reports,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_report(
    client: "LogicMonitorClient",
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


async def get_report_groups(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List report groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with report group data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/report/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "report_count": item.get("numOfReports"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(groups),
                "groups": groups,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def run_report(
    client: "LogicMonitorClient",
    report_id: int,
    notify_email: str | None = None,
) -> list[TextContent]:
    """Run/execute a report.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID to execute.
        notify_email: Optional email to notify when report completes.

    Returns:
        List of TextContent with task info or error.
    """
    try:
        payload: dict = {
            "type": "generateReport",
            "reportId": report_id,
        }

        if notify_email:
            payload["receiveEmails"] = notify_email

        result = await client.post("/functions", json_body=payload)

        return format_response(
            {
                "success": True,
                "report_id": report_id,
                "task_id": result.get("taskId"),
                "message": "Report generation started. Use task_id to check status.",
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_scheduled_reports(
    client: "LogicMonitorClient",
    enabled_only: bool = False,
    limit: int = 50,
) -> list[TextContent]:
    """Get reports with schedules configured.

    Args:
        client: LogicMonitor API client.
        enabled_only: Only return reports with enabled schedules.
        limit: Maximum number of reports to return.

    Returns:
        List of TextContent with scheduled report data or error.
    """
    try:
        params: dict = {"size": limit}

        result = await client.get("/report/reports", params=params)

        scheduled = []
        for item in result.get("items", []):
            schedule = item.get("schedule")
            if schedule:
                if enabled_only and not schedule.get("enabled", False):
                    continue
                scheduled.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": item.get("type"),
                        "schedule_enabled": schedule.get("enabled", False),
                        "schedule_type": schedule.get("type"),
                        "schedule_cron": schedule.get("cron"),
                        "timezone": schedule.get("timezone"),
                        "next_run": schedule.get("nextRunTime"),
                        "last_generated": item.get("lastGenerateOn"),
                    }
                )

        return format_response(
            {
                "total": len(scheduled),
                "count": len(scheduled),
                "scheduled_reports": scheduled,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_report_schedule(
    client: "LogicMonitorClient",
    report_id: int,
    enabled: bool | None = None,
    schedule_type: str | None = None,
    cron: str | None = None,
    timezone: str | None = None,
) -> list[TextContent]:
    """Update a report's schedule configuration.

    Args:
        client: LogicMonitor API client.
        report_id: Report ID to update.
        enabled: Enable or disable the schedule.
        schedule_type: Schedule type (daily, weekly, monthly, custom).
        cron: Cron expression for custom schedules.
        timezone: Timezone for schedule (e.g., America/Los_Angeles).

    Returns:
        List of TextContent with updated schedule or error.
    """
    try:
        # Get current report to preserve other fields
        current = await client.get(f"/report/reports/{report_id}")

        schedule = current.get("schedule", {}) or {}

        if enabled is not None:
            schedule["enabled"] = enabled
        if schedule_type is not None:
            schedule["type"] = schedule_type
        if cron is not None:
            schedule["cron"] = cron
        if timezone is not None:
            schedule["timezone"] = timezone

        current["schedule"] = schedule

        result = await client.put(f"/report/reports/{report_id}", json_body=current)

        return format_response(
            {
                "success": True,
                "message": f"Report {report_id} schedule updated",
                "report": {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "schedule": result.get("schedule"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def create_report(
    client: "LogicMonitorClient",
    name: str,
    report_type: str,
    group_id: int = 1,
    description: str | None = None,
    format: str = "PDF",
    schedule_enabled: bool = False,
    schedule_cron: str | None = None,
) -> list[TextContent]:
    """Create a new report.

    Args:
        client: LogicMonitor API client.
        name: Report name.
        report_type: Report type (Alert, Host Metric, etc.).
        group_id: Report group ID (default: 1 for root).
        description: Report description.
        format: Output format (PDF, CSV, HTML).
        schedule_enabled: Enable scheduled generation.
        schedule_cron: Cron expression for schedule.

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

        if schedule_enabled and schedule_cron:
            payload["schedule"] = {
                "enabled": True,
                "type": "custom",
                "cron": schedule_cron,
            }

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
    client: "LogicMonitorClient",
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
