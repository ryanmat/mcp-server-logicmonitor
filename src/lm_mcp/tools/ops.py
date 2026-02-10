# Description: Ops notes and audit log tools for LogicMonitor MCP server.
# Description: Provides get_audit_logs, get_ops_notes, get_ops_note, add_ops_note.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    require_write_permission,
    sanitize_filter_value,
)

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
        wildcards_stripped = False

        filters = []
        if username_filter:
            clean_username, was_modified = sanitize_filter_value(username_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f'username~{quote_filter_value(clean_username)}')
        if keyword_filter:
            clean_keyword, was_modified = sanitize_filter_value(keyword_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            filters.append(f'_all~{quote_filter_value(clean_keyword)}')

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

        response = {
            "total": result.get("total", 0),
            "count": len(entries),
            "audit_logs": entries,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
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
        wildcards_stripped = False

        if tag_filter:
            clean_tag, was_modified = sanitize_filter_value(tag_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'tags~{quote_filter_value(clean_tag)}'

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

        response = {
            "total": result.get("total", 0),
            "count": len(notes),
            "ops_notes": notes,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
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
