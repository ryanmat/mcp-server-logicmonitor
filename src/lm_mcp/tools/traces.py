# Description: APM trace tools for LogicMonitor MCP server.
# Description: Provides service discovery, metrics, alerts, and properties for APM services.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    WILDCARD_STRIP_NOTE,
    format_response,
    handle_error,
    quote_filter_value,
    sanitize_filter_value,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient

# Severity mapping for alert filtering (matches alerts.py)
SEVERITY_MAP = {
    "critical": 4,
    "error": 3,
    "warning": 2,
    "info": 1,
}


async def get_trace_services(
    client: "LogicMonitorClient",
    namespace: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List APM trace services (deviceType:6 devices).

    Args:
        client: LogicMonitor API client.
        namespace: Filter by service display name (substring match).
        limit: Maximum number of services to return.

    Returns:
        List of TextContent with APM service data or error.
    """
    try:
        params: dict = {"size": limit, "filter": "deviceType:6"}
        wildcards_stripped = False

        if namespace:
            clean, was_modified = sanitize_filter_value(namespace)
            wildcards_stripped = was_modified
            params["filter"] += (
                f",displayName~{quote_filter_value(clean)}"
            )

        result = await client.get("/device/devices", params=params)

        services = []
        for item in result.get("items", []):
            services.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "hostname": item.get("name"),
                    "host_group_ids": item.get("hostGroupIds"),
                }
            )

        response = {
            "total": result.get("total", 0),
            "count": len(services),
            "services": services,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_trace_service(
    client: "LogicMonitorClient",
    service_id: int,
) -> list[TextContent]:
    """Get detailed information about a specific APM service.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.

    Returns:
        List of TextContent with full service detail or error.
    """
    try:
        result = await client.get(f"/device/devices/{service_id}")
        return format_response(result)
    except Exception as e:
        return handle_error(e)


async def get_trace_service_alerts(
    client: "LogicMonitorClient",
    service_id: int,
    severity: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get alerts for an APM service.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        severity: Filter by severity (critical, error, warning, info).
        limit: Maximum number of alerts to return.

    Returns:
        List of TextContent with alert data or error.
    """
    try:
        params: dict = {"size": limit}

        if severity and severity.lower() in SEVERITY_MAP:
            params["filter"] = (
                f"severity:{SEVERITY_MAP[severity.lower()]}"
            )

        result = await client.get(
            f"/device/devices/{service_id}/alerts", params=params
        )

        alerts = []
        for item in result.get("items", []):
            alerts.append(
                {
                    "id": item.get("id"),
                    "severity": item.get("severity"),
                    "monitor_object": item.get("monitorObjectName"),
                    "datapoint": item.get("dataPointName"),
                    "alert_value": item.get("alertValue"),
                }
            )

        return format_response(
            {
                "service_id": service_id,
                "total": result.get("total", 0),
                "count": len(alerts),
                "alerts": alerts,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_trace_service_datasources(
    client: "LogicMonitorClient",
    service_id: int,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List datasources applied to an APM service.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        name_filter: Filter by datasource name (substring match).
        limit: Maximum number of datasources to return.

    Returns:
        List of TextContent with datasource data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = was_modified
            params["filter"] = (
                f"dataSourceName~{quote_filter_value(clean)}"
            )

        result = await client.get(
            f"/device/devices/{service_id}/devicedatasources",
            params=params,
        )

        datasources = []
        for item in result.get("items", []):
            datasources.append(
                {
                    "id": item.get("id"),
                    "datasource_id": item.get("dataSourceId"),
                    "name": item.get("dataSourceName"),
                    "instance_count": item.get("instanceNumber"),
                    "monitoring_count": item.get(
                        "monitoringInstanceNumber"
                    ),
                }
            )

        response = {
            "service_id": service_id,
            "total": result.get("total", 0),
            "count": len(datasources),
            "datasources": datasources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_trace_operations(
    client: "LogicMonitorClient",
    service_id: int,
    device_datasource_id: int,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List operations (instances) for an APM service datasource.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        device_datasource_id: Device datasource ID (from get_trace_service_datasources).
        name_filter: Filter by operation name (substring match).
        limit: Maximum number of operations to return.

    Returns:
        List of TextContent with operation data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = was_modified
            params["filter"] = (
                f"displayName~{quote_filter_value(clean)}"
            )

        result = await client.get(
            f"/device/devices/{service_id}/devicedatasources/{device_datasource_id}/instances",
            params=params,
        )

        operations = []
        for item in result.get("items", []):
            operations.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "description": item.get("description"),
                    "group_name": item.get("groupName"),
                    "stop_monitoring": item.get("stopMonitoring"),
                }
            )

        response = {
            "service_id": service_id,
            "device_datasource_id": device_datasource_id,
            "total": result.get("total", 0),
            "count": len(operations),
            "operations": operations,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)


async def get_trace_service_metrics(
    client: "LogicMonitorClient",
    service_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TextContent]:
    """Get APM service-level metrics (Duration, ErrorOperationCount, etc.).

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        device_datasource_id: Device datasource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated datapoint names (all if not specified).
        start_time: Start time in epoch seconds.
        end_time: End time in epoch seconds.

    Returns:
        List of TextContent with time-series metric data or error.
    """
    try:
        params: dict = {}

        if datapoints:
            params["datapoints"] = datapoints
        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        result = await client.get(
            f"/device/devices/{service_id}/devicedatasources/{device_datasource_id}/instances/{instance_id}/data",
            params=params if params else None,
        )

        return format_response(
            {
                "service_id": service_id,
                "device_datasource_id": device_datasource_id,
                "instance_id": instance_id,
                "datapoints": result.get("dataPoints", []),
                "values": result.get("values", {}),
                "time": result.get("time", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_trace_operation_metrics(
    client: "LogicMonitorClient",
    service_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TextContent]:
    """Get operation-level metrics for a specific APM operation.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        device_datasource_id: Device datasource ID.
        instance_id: Operation instance ID.
        datapoints: Comma-separated datapoint names (all if not specified).
        start_time: Start time in epoch seconds.
        end_time: End time in epoch seconds.

    Returns:
        List of TextContent with time-series metric data or error.
    """
    try:
        params: dict = {}

        if datapoints:
            params["datapoints"] = datapoints
        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        result = await client.get(
            f"/device/devices/{service_id}/devicedatasources/{device_datasource_id}/instances/{instance_id}/data",
            params=params if params else None,
        )

        return format_response(
            {
                "service_id": service_id,
                "device_datasource_id": device_datasource_id,
                "instance_id": instance_id,
                "datapoints": result.get("dataPoints", []),
                "values": result.get("values", {}),
                "time": result.get("time", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_trace_service_properties(
    client: "LogicMonitorClient",
    service_id: int,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """Get properties for an APM service.

    Args:
        client: LogicMonitor API client.
        service_id: APM service device ID.
        name_filter: Filter by property name (substring match).
        limit: Maximum number of properties to return.

    Returns:
        List of TextContent with property data or error.
    """
    try:
        params: dict = {"size": limit}
        wildcards_stripped = False

        if name_filter:
            clean, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = was_modified
            params["filter"] = f"name~{quote_filter_value(clean)}"

        result = await client.get(
            f"/device/devices/{service_id}/properties", params=params
        )

        properties = []
        for item in result.get("items", []):
            properties.append(
                {
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "type": item.get("type"),
                }
            )

        response = {
            "service_id": service_id,
            "total": result.get("total", 0),
            "count": len(properties),
            "properties": properties,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
    except Exception as e:
        return handle_error(e)
