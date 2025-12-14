# Description: Audit log tools for LogicMonitor MCP server.
# Description: Provides access to system audit logs and activity tracking.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_audit_logs(
    client: "LogicMonitorClient",
    username: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get audit logs from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        username: Filter by username who performed the action.
        action: Filter by action type (create, update, delete, login, etc.).
        resource_type: Filter by resource type (device, dashboard, alert, etc.).
        start_time: Start time filter (epoch seconds).
        end_time: End time filter (epoch seconds).
        limit: Maximum number of logs to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with audit log data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}

        filters = []
        if username:
            filters.append(f"username:{username}")
        if action:
            filters.append(f"happenedOn:{action}")
        if resource_type:
            filters.append(f"description~{resource_type}")
        if start_time:
            filters.append(f"happenedOnLocal>:{start_time}")
        if end_time:
            filters.append(f"happenedOnLocal<:{end_time}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        logs = []
        for item in result.get("items", []):
            logs.append(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "ip_address": item.get("ip"),
                    "action": item.get("happenedOn"),
                    "description": item.get("description"),
                    "timestamp": item.get("happenedOnLocal"),
                    "session_id": item.get("sessionId"),
                }
            )

        total = result.get("total", 0)
        has_more = (offset + len(logs)) < total

        return format_response(
            {
                "total": total,
                "count": len(logs),
                "offset": offset,
                "has_more": has_more,
                "audit_logs": logs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_api_token_audit(
    client: "LogicMonitorClient",
    token_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get API token usage audit logs.

    Args:
        client: LogicMonitor API client.
        token_id: Filter by specific API token ID.
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with API token audit data or error.
    """
    try:
        params: dict = {"size": limit}

        if token_id:
            params["filter"] = f"apiTokenId:{token_id}"

        result = await client.get("/setting/accesslogs", params=params)

        # Filter to API token related entries
        logs = []
        for item in result.get("items", []):
            desc = item.get("description", "").lower()
            if "api" in desc or "token" in desc or item.get("username", "").startswith("api."):
                logs.append(
                    {
                        "id": item.get("id"),
                        "username": item.get("username"),
                        "ip_address": item.get("ip"),
                        "action": item.get("happenedOn"),
                        "description": item.get("description"),
                        "timestamp": item.get("happenedOnLocal"),
                    }
                )

        return format_response(
            {
                "total": len(logs),
                "count": len(logs),
                "api_token_logs": logs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_login_audit(
    client: "LogicMonitorClient",
    username: str | None = None,
    success_only: bool = False,
    failed_only: bool = False,
    limit: int = 50,
) -> list[TextContent]:
    """Get login/authentication audit logs.

    Args:
        client: LogicMonitor API client.
        username: Filter by specific username.
        success_only: Only show successful logins.
        failed_only: Only show failed login attempts.
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with login audit data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = ["happenedOn:login"]
        if username:
            filters.append(f"username:{username}")

        params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        logs = []
        for item in result.get("items", []):
            desc = item.get("description", "").lower()
            is_success = "success" in desc or "logged in" in desc
            is_failed = "fail" in desc or "invalid" in desc

            if success_only and not is_success:
                continue
            if failed_only and not is_failed:
                continue

            logs.append(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "ip_address": item.get("ip"),
                    "status": "success" if is_success else "failed" if is_failed else "unknown",
                    "description": item.get("description"),
                    "timestamp": item.get("happenedOnLocal"),
                }
            )

        return format_response(
            {
                "total": len(logs),
                "count": len(logs),
                "login_logs": logs,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_change_audit(
    client: "LogicMonitorClient",
    resource_type: str | None = None,
    change_type: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get configuration change audit logs.

    Args:
        client: LogicMonitor API client.
        resource_type: Filter by resource type (device, dashboard, user, etc.).
        change_type: Filter by change type (create, update, delete).
        limit: Maximum number of logs to return.

    Returns:
        List of TextContent with change audit data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if change_type:
            filters.append(f"happenedOn:{change_type}")
        if resource_type:
            filters.append(f"description~{resource_type}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        logs = []
        for item in result.get("items", []):
            action = item.get("happenedOn", "").lower()
            # Filter to actual changes (not logins, views, etc.)
            if action in ["create", "add", "update", "delete", "remove", "modify"]:
                logs.append(
                    {
                        "id": item.get("id"),
                        "username": item.get("username"),
                        "action": item.get("happenedOn"),
                        "description": item.get("description"),
                        "timestamp": item.get("happenedOnLocal"),
                        "ip_address": item.get("ip"),
                    }
                )

        return format_response(
            {
                "total": len(logs),
                "count": len(logs),
                "change_logs": logs,
            }
        )
    except Exception as e:
        return handle_error(e)
