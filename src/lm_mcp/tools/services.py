# Description: Service Insight tools for LogicMonitor MCP server.
# Description: Lists business services (deviceType 6 devices), BizService groups and rules.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _service_row(item: dict) -> dict:
    """Project one deviceType 6 /device/devices row onto the get_services fields."""
    return {
        "id": item.get("id"),
        "name": item.get("displayName"),
        "description": item.get("description"),
        "group_ids": item.get("hostGroupIds"),
        "alert_status": item.get("alertStatus"),
        "alert_status_priority": item.get("alertStatusPriority"),
        "sdt_status": item.get("sdtStatus"),
        "host_status": item.get("hostStatus"),
    }


async def get_services(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List Service Insight business services.

    LogicMonitor models Service Insight services as devices with
    deviceType 6 (this includes APM-created trace services). The legacy
    /service/services API returns websites, not these services.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by service display name (substring match).
        limit: Maximum number of services to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with service data or error.
    """
    return await list_tool(
        client,
        "/device/devices",
        key="services",
        project=_service_row,
        limit=limit,
        offset=offset,
        named={"displayName~": name_filter},
        clauses=["deviceType:6"],
    )


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


def _service_group_row(item: dict) -> dict:
    """Project one BizService /device/groups row onto the get_service_groups fields."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "parent_id": item.get("parentId"),
        "full_path": item.get("fullPath"),
        "num_of_services": item.get("numOfHosts"),
    }


async def get_service_groups(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List Service Insight service groups (BizService device groups).

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by group name (substring match).
        limit: Maximum number of groups to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with service group data or error.
    """
    return await list_tool(
        client,
        "/device/groups",
        key="service_groups",
        project=_service_group_row,
        limit=limit,
        offset=offset,
        named={"name~": name_filter},
        clauses=['groupType:"BizService"'],
    )


async def get_service_insights_rules(
    client: LogicMonitorClient,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List the portal's Service Insights rules, rows as the API returns them.

    Args:
        client: LogicMonitor API client.
        limit: Maximum number of rules to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with the rules or error.
    """
    return await list_tool(
        client,
        "/serviceinsights/rules",
        key="rules",
        project=dict,
        limit=limit,
        offset=offset,
    )
