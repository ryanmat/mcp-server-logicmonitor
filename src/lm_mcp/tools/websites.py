# Description: Website/Synthetic monitoring tools for LogicMonitor MCP server.
# Description: Provides get_websites, get_website, get_website_groups, get_website_data.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_websites(
    client: "LogicMonitorClient",
    name_filter: str | None = None,
    group_id: int | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List websites/synthetic checks from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by website name (supports wildcards).
        group_id: Filter by website group ID.
        limit: Maximum number of websites to return.

    Returns:
        List of TextContent with website data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if name_filter:
            filters.append(f"name~{name_filter}")
        if group_id is not None:
            filters.append(f"groupId:{group_id}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/website/websites", params=params)

        websites = []
        for item in result.get("items", []):
            websites.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                    "group_id": item.get("groupId"),
                    "status": item.get("status"),
                    "alert_status": item.get("alertStatus"),
                    "overall_status": item.get("overallAlertLevel"),
                    "polling_interval": item.get("pollingInterval"),
                    "host": item.get("host") or item.get("domain"),
                }
            )

        return format_response(
            {
                "total": result.get("total", 0),
                "count": len(websites),
                "websites": websites,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_website(
    client: "LogicMonitorClient",
    website_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific website.

    Args:
        client: LogicMonitor API client.
        website_id: Website ID.

    Returns:
        List of TextContent with website details or error.
    """
    try:
        result = await client.get(f"/website/websites/{website_id}")

        website = {
            "id": result.get("id"),
            "name": result.get("name"),
            "type": result.get("type"),
            "description": result.get("description"),
            "group_id": result.get("groupId"),
            "status": result.get("status"),
            "alert_status": result.get("alertStatus"),
            "host": result.get("host") or result.get("domain"),
            "polling_interval": result.get("pollingInterval"),
            "use_default_alert_setting": result.get("useDefaultAlertSetting"),
            "use_default_location_setting": result.get("useDefaultLocationSetting"),
            "checkpoints": [
                {
                    "id": cp.get("id"),
                    "geo_info": cp.get("geoInfo"),
                    "smg_id": cp.get("smgId"),
                }
                for cp in result.get("checkpoints", [])
            ],
            "steps": [
                {
                    "url": step.get("url"),
                    "http_method": step.get("HTTPMethod"),
                    "status_code": step.get("statusCode"),
                    "timeout": step.get("timeout"),
                }
                for step in result.get("steps", [])
            ],
        }

        return format_response(website)
    except Exception as e:
        return handle_error(e)


async def get_website_groups(
    client: "LogicMonitorClient",
    parent_id: int | None = None,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List website groups from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        parent_id: Filter by parent group ID.
        name_filter: Filter by group name (supports wildcards).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with group data or error.
    """
    try:
        params: dict = {"size": limit}

        filters = []
        if parent_id is not None:
            filters.append(f"parentId:{parent_id}")
        if name_filter:
            filters.append(f"name~{name_filter}")

        if filters:
            params["filter"] = ",".join(filters)

        result = await client.get("/website/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parent_id": item.get("parentId"),
                    "full_path": item.get("fullPath"),
                    "website_count": item.get("numOfWebsites"),
                    "has_websites_disabled": item.get("hasWebsitesDisabled"),
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


async def get_website_data(
    client: "LogicMonitorClient",
    website_id: int,
    checkpoint_id: int,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TextContent]:
    """Get monitoring data for a website checkpoint.

    Args:
        client: LogicMonitor API client.
        website_id: Website ID.
        checkpoint_id: Checkpoint (location) ID.
        start_time: Start time in epoch seconds (optional).
        end_time: End time in epoch seconds (optional).

    Returns:
        List of TextContent with website data or error.
    """
    try:
        params: dict = {}

        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        result = await client.get(
            f"/website/websites/{website_id}/checkpoints/{checkpoint_id}/data",
            params=params if params else None,
        )

        return format_response(
            {
                "website_id": website_id,
                "checkpoint_id": checkpoint_id,
                "datapoints": result.get("dataPoints", []),
                "values": result.get("values", {}),
                "time": result.get("time", []),
            }
        )
    except Exception as e:
        return handle_error(e)
