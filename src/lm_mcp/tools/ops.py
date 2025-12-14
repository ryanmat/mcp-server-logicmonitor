# Description: Ops notes and audit log tools for LogicMonitor MCP server.
# Description: Provides get_audit_logs, get_ops_notes, get_ops_note, add_ops_note.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_audit_logs(
    client: "LogicMonitorClient",
    username_filter: str | None = None,
    keyword_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get audit log entries from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        username_filter: Filter by username (supports wildcards).
        keyword_filter: Filter by keyword in description.
        limit: Maximum number of entries to return.

    Returns:
        List of TextContent with audit log data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if username_filter:
            filters.append(f"username~{username_filter}")
        if keyword_filter:
            filters.append(f"_all~*{keyword_filter}*")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/setting/accesslogs", params=params)

        entries = []
        for item in result.get("items", []):
            entries.append(
                {
                    "id": item.get("id"),
                    "username": item.get("username"),
                    "description": item.get("description"),
                    "happened_on": item.get("happenedOn"),
                    "happened_on_local": item.get("happenedOnLocal"),
                    "ip": item.get("ip"),
                    "session_id": item.get("sessionId"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(entries),
                "audit_logs": entries,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_ops_notes(
    client: "LogicMonitorClient",
    tag_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List ops notes from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        tag_filter: Filter by tag (supports wildcards).
        limit: Maximum number of notes to return.

    Returns:
        List of TextContent with ops notes data or error.
    """
    try:
        params: dict = {"size": limit}

        if tag_filter:
            params["filter"] = f"tags~{tag_filter}"

        result = await client.get("/setting/opsnotes", params=params)

        notes = []
        for item in result.get("items", []):
            notes.append(
                {
                    "id": item.get("id"),
                    "note": item.get("note"),
                    "tags": item.get("tags", []),
                    "happened_on": item.get("happenedOnInSec"),
                    "created_by": item.get("createdBy"),
                    "scopes": item.get("scopes", []),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(notes),
                "ops_notes": notes,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_ops_note(
    client: "LogicMonitorClient",
    note_id: str,
) -> list[TextContent]:
    """Get detailed information about a specific ops note.

    Args:
        client: LogicMonitor API client.
        note_id: Ops note ID.

    Returns:
        List of TextContent with ops note details or error.
    """
    try:
        result = await client.get(f"/setting/opsnotes/{note_id}")

        note = {
            "id": result.get("id"),
            "note": result.get("note"),
            "tags": result.get("tags", []),
            "happened_on": result.get("happenedOnInSec"),
            "created_by": result.get("createdBy"),
            "scopes": [
                {
                    "type": s.get("type"),
                    "group_id": s.get("groupId"),
                    "device_id": s.get("deviceId"),
                }
                for s in result.get("scopes", [])
            ],
        }

        return format_response(note)
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def add_ops_note(
    client: "LogicMonitorClient",
    note: str,
    tags: list[str] | None = None,
    device_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
) -> list[TextContent]:
    """Add a new ops note to LogicMonitor.

    Args:
        client: LogicMonitor API client.
        note: The note text/message.
        tags: Optional list of tags for the note.
        device_ids: Optional list of device IDs to scope the note to.
        group_ids: Optional list of device group IDs to scope the note to.

    Returns:
        List of TextContent with created note info or error.
    """
    try:
        payload: dict = {"note": note}

        if tags:
            payload["tags"] = [{"name": t} for t in tags]

        scopes = []
        if device_ids:
            for did in device_ids:
                scopes.append({"type": "device", "deviceId": did})
        if group_ids:
            for gid in group_ids:
                scopes.append({"type": "deviceGroup", "groupId": gid})
        if scopes:
            payload["scopes"] = scopes

        result = await client.post("/setting/opsnotes", json_body=payload)

        return format_response(
            {
                "success": True,
                "id": result.get("id"),
                "note": result.get("note"),
                "tags": result.get("tags", []),
            }
        )
    except Exception as e:
        return handle_error(e)
