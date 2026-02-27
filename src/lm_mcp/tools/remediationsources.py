# Description: Remediation source tools for LogicMonitor MCP server.
# Description: Provides read access to Exchange Toolbox remediation sources.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_remediationsources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_filter: str | None = None,
) -> list[TextContent]:
    """List remediation sources from LogicMonitor Exchange Toolbox.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by source name (client-side substring match).
        group_filter: Filter by group (client-side substring match).

    Returns:
        List of TextContent with remediation source data or error.
    """
    try:
        result = await client.post(
            "/exchange/toolbox/exchangeRemediationSources", json_body={}
        )

        # Unwrap Exchange Toolbox envelope
        data = result.get("data", {})
        by_id = data.get("byId", {})
        sources = list(by_id.values())

        # Apply client-side filters
        if name_filter:
            name_lower = name_filter.lower()
            sources = [s for s in sources if name_lower in s.get("name", "").lower()]
        if group_filter:
            group_lower = group_filter.lower()
            sources = [s for s in sources if group_lower in s.get("group", "").lower()]

        formatted = []
        for src in sources:
            formatted.append(
                {
                    "id": src.get("id"),
                    "name": src.get("name"),
                    "description": src.get("description"),
                    "group": src.get("group"),
                    "tags": src.get("tags", []),
                    "technical_notes": src.get("technicalNotes"),
                }
            )

        return format_response(
            {
                "count": len(formatted),
                "remediationsources": formatted,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_remediationsource(
    client: "LogicMonitorClient",
    source_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific remediation source.

    Args:
        client: LogicMonitor API client.
        source_id: Remediation source ID.

    Returns:
        List of TextContent with source details or error.
    """
    try:
        result = await client.post(
            f"/exchange/toolbox/exchangeRemediationSources/{source_id}", json_body={}
        )

        # Handle envelope or direct response
        if "data" in result and "byId" in result.get("data", {}):
            by_id = result["data"]["byId"]
            source = by_id.get(str(source_id), {})
        else:
            source = result

        detail = {
            "id": source.get("id"),
            "name": source.get("name"),
            "description": source.get("description"),
            "group": source.get("group"),
            "tags": source.get("tags", []),
            "technical_notes": source.get("technicalNotes"),
            "applies_to": source.get("appliesToScript"),
            "script": source.get("script"),
        }

        return format_response(detail)
    except Exception as e:
        return handle_error(e)
