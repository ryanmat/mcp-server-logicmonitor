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
    limit: int = 50,
) -> list[TextContent]:
    """List reports from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by report name (supports wildcards).
        group_id: Filter by report group ID.
        report_type: Filter by report type (e.g., 'Alert', 'Host metric').
        limit: Maximum number of reports to return.

    Returns:
        List of TextContent with report data or error.
    """
    try:
        params: dict = {"size": limit}

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

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(reports),
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
