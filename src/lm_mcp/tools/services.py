# Description: Service Insight tools for LogicMonitor MCP server.
# Description: Lists business services (deviceType 6 devices) and BizService groups.

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


async def get_services(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List Service Insight business services.

    LogicMonitor models Service Insight services as devices with
    deviceType 6 (this includes APM-created trace services). The legacy
    /service/services API returns websites, not these services.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by service display name (substring match).
        limit: Maximum number of services to return.

    Returns:
        List of TextContent with service data or error.
    """
    try:
        params: dict = {"size": limit, "filter": "deviceType:6"}
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] += f",displayName~{quote_filter_value(clean_name)}"

        result = await client.get("/device/devices", params=params)

        services = []
        for item in result.get("items", []):
            services.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "description": item.get("description"),
                    "group_ids": item.get("hostGroupIds"),
                    "alert_status": item.get("alertStatus"),
                    "alert_status_priority": item.get("alertStatusPriority"),
                    "sdt_status": item.get("sdtStatus"),
                    "host_status": item.get("hostStatus"),
                }
            )

        response = {
            "total": safe_total(result),
            "count": len(services),
            "services": services,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_service(
    client: LogicMonitorClient,
    service_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific Service Insight service.

    Args:
        client: LogicMonitor API client.
        service_id: Service device ID (deviceType 6).

    Returns:
        List of TextContent with service details or error.
    """
    try:
        result = await client.get(f"/device/devices/{service_id}")

        service = {
            "id": result.get("id"),
            "name": result.get("displayName"),
            "hostname": result.get("name"),
            "description": result.get("description"),
            "device_type": result.get("deviceType"),
            "group_ids": result.get("hostGroupIds"),
            "alert_status": result.get("alertStatus"),
            "alert_status_priority": result.get("alertStatusPriority"),
            "alert_disable_status": result.get("alertDisableStatus"),
            "sdt_status": result.get("sdtStatus"),
            "host_status": result.get("hostStatus"),
        }

        if result.get("deviceType") != 6:
            service["note"] = (
                f"Device {service_id} is not a Service Insight service "
                f"(deviceType {result.get('deviceType')}). Use get_device for regular devices."
            )

        return format_response(service)
    except Exception as e:
        return handle_error(e)


async def get_service_groups(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List Service Insight service groups (BizService device groups).

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (substring match).
        limit: Maximum number of groups to return.

    Returns:
        List of TextContent with service group data or error.
    """
    try:
        params: dict = {"size": limit, "filter": 'groupType:"BizService"'}
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] += f",name~{quote_filter_value(clean_name)}"

        result = await client.get("/device/groups", params=params)

        groups = []
        for item in result.get("items", []):
            groups.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parent_id": item.get("parentId"),
                    "full_path": item.get("fullPath"),
                    "num_of_services": item.get("numOfHosts"),
                }
            )

        response = {
            "total": safe_total(result),
            "count": len(groups),
            "service_groups": groups,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)
