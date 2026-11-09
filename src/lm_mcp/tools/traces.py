# Description: APM tools for LogicMonitor MCP server: the APM service list and a service's alerts.
# Description: APM services are deviceType 6 devices; the device tools read their other data.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import SEVERITY_MAP, list_tool

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


def _apm_service_row(item: dict) -> dict:
    """Project one deviceType 6 /device/devices row onto the get_apm_services fields."""
    return {
        "id": item.get("id"),
        "name": item.get("displayName"),
        "hostname": item.get("name"),
        "host_group_ids": item.get("hostGroupIds"),
    }


def _apm_alert_row(item: dict) -> dict:
    """Project one alert row onto the get_apm_service_alerts fields."""
    return {
        "id": item.get("id"),
        "severity": item.get("severity"),
        "monitor_object": item.get("monitorObjectName"),
        "datapoint": item.get("dataPointName"),
        "alert_value": item.get("alertValue"),
    }


async def get_apm_services(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List APM trace services (deviceType 6 devices).

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by service display name (substring match).
        limit: Maximum number of services to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with one page of APM services or error.
    """
    return await list_tool(
        client,
        "/device/devices",
        key="services",
        project=_apm_service_row,
        limit=limit,
        offset=offset,
        named={"displayName~": name_filter},
        clauses=["deviceType:6"],
    )


async def get_apm_service_alerts(
    client: LogicMonitorClient,
    service_id: int,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get the alerts on one APM service.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        severity: Filter by severity (critical, error, warning, info).
        limit: Maximum number of alerts to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with one page of the service's alerts or error.
    """
    clauses = []
    if severity and severity.lower() in SEVERITY_MAP:
        clauses.append(f"severity:{SEVERITY_MAP[severity.lower()]}")
    return await list_tool(
        client,
        f"/device/devices/{service_id}/alerts",
        key="alerts",
        project=_apm_alert_row,
        limit=limit,
        offset=offset,
        clauses=clauses,
        extra={"service_id": service_id},
    )
