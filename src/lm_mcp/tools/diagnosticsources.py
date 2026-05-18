# Description: Diagnostic source tools for LogicMonitor MCP server.
# Description: Provides read access to public /setting/diagnosticsources REST endpoints.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    safe_total,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_diagnosticsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    group_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List DiagnosticSources from LogicMonitor.

    Calls the public REST endpoint ``/setting/diagnosticsources``. Filters
    and pagination are pushed down to the server. The implementation mirrors
    :func:`get_datasources` so consumers get a consistent shape across
    every LogicModule resource family.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by DiagnosticSource name (substring, server-side).
        group_filter: Filter by group (substring, server-side).
        filter: Raw LM filter expression (overrides typed filters).
        limit: Maximum sources to return per page.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with DiagnosticSource data or error.
    """
    try:
        params: dict = {"size": limit, "offset": offset}
        wildcards_stripped = False

        if filter:
            params["filter"] = filter
        else:
            filters: list[str] = []
            if name_filter:
                clean_name, was_modified = sanitize_filter_value(name_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"name~{quote_filter_value(clean_name)}")
            if group_filter:
                clean_group, was_modified = sanitize_filter_value(group_filter)
                wildcards_stripped = wildcards_stripped or was_modified
                filters.append(f"group~{quote_filter_value(clean_group)}")
            if filters:
                params["filter"] = ",".join(filters)

        result = await client.get("/setting/diagnosticsources", params=params)

        sources = []
        for item in result.get("items", []):
            sources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "group": item.get("group"),
                    "collect_method": item.get("collectMethod"),
                    "tags": item.get("tags", []),
                    "technical_notes": item.get("technicalNotes"),
                }
            )

        total = safe_total(result)
        has_more = (offset + len(sources)) < total

        response = {
            "total": total,
            "count": len(sources),
            "offset": offset,
            "has_more": has_more,
            "diagnosticsources": sources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_diagnosticsource(
    client: LogicMonitorClient,
    source_id: int,
) -> list[TextContent]:
    """Get details for a specific DiagnosticSource.

    Calls ``/setting/diagnosticsources/{id}`` and projects the fields most
    useful to callers (metadata + script content).

    Args:
        client: LogicMonitor API client.
        source_id: DiagnosticSource ID.

    Returns:
        List of TextContent with source details or error.
    """
    try:
        result = await client.get(f"/setting/diagnosticsources/{source_id}")

        detail = {
            "id": result.get("id"),
            "name": result.get("name"),
            "display_name": result.get("displayName"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "group": result.get("group"),
            "collect_method": result.get("collectMethod"),
            "collect_interval": result.get("collectInterval"),
            "tags": result.get("tags", []),
            "technical_notes": result.get("technicalNotes"),
            "datapoints": [
                {
                    "id": dp.get("id"),
                    "name": dp.get("name"),
                    "description": dp.get("description"),
                    "type": dp.get("type"),
                }
                for dp in result.get("dataPoints", [])
            ],
        }

        return format_response(detail)
    except Exception as e:
        return handle_error(e)
