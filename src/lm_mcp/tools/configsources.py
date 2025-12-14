# Description: ConfigSource tools for LogicMonitor MCP server.
# Description: Provides configuration source query functions.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_configsources(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List ConfigSources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        limit: Maximum number of ConfigSources to return.

    Returns:
        List of TextContent with ConfigSource data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"name~{name_filter}"

        result = await client.get("/setting/configsources", params=params)

        sources = []
        for item in result.get("items", []):
            sources.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "display_name": item.get("displayName"),
                    "description": item.get("description"),
                    "applies_to": item.get("appliesTo"),
                    "technology": item.get("technology"),
                    "collect_method": item.get("collectMethod"),
                    "collect_interval": item.get("collectInterval"),
                    "version": item.get("version"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(sources),
                "configsources": sources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_configsource(
    client: "LogicMonitorClient",
    configsource_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific ConfigSource.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID.

    Returns:
        List of TextContent with ConfigSource details or error.
    """
    try:
        result = await client.get(f"/setting/configsources/{configsource_id}")

        source = {
            "id": result.get("id"),
            "name": result.get("name"),
            "display_name": result.get("displayName"),
            "description": result.get("description"),
            "applies_to": result.get("appliesTo"),
            "technology": result.get("technology"),
            "collect_method": result.get("collectMethod"),
            "collect_interval": result.get("collectInterval"),
            "version": result.get("version"),
            "tags": result.get("tags"),
            "audit_version": result.get("auditVersion"),
            "install_date": result.get("installDate"),
            "config_checks": result.get("configChecks", []),
        }

        return format_response(source)
    except Exception as e:
        return handle_error(e)
