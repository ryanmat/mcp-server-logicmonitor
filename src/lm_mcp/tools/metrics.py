# Description: Metrics and data tools for LogicMonitor MCP server.
# Description: Provides get_device_datasources, get_device_instances, get_device_data, get_graph.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_device_datasources(
    client: "LogicMonitorClient",
    device_id: int,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List DataSources applied to a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID to get DataSources for.
        name_filter: Filter by DataSource name (supports wildcards).
        limit: Maximum number of DataSources to return.

    Returns:
        List of TextContent with DataSource data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"dataSourceName~{name_filter}"

        result = await client.get(f"/device/devices/{device_id}/devicedatasources", params=params)

        datasources = []
        for item in result.get("items", []):
            datasources.append(
                {
                    "id": item.get("id"),
                    "datasource_id": item.get("dataSourceId"),
                    "name": item.get("dataSourceName"),
                    "instance_count": item.get("instanceNumber"),
                    "monitoring_status": item.get("monitoringInstanceNumber"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "total": result.get("total", 0),
                "count": len(datasources),
                "datasources": datasources,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_instances(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    name_filter: str | None = None,
    limit: int = 50,
) -> list[TextContent]:
    """List instances for a DataSource on a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device DataSource ID (from get_device_datasources).
        name_filter: Filter by instance name (supports wildcards).
        limit: Maximum number of instances to return.

    Returns:
        List of TextContent with instance data or error.
    """
    try:
        params: dict = {"size": limit}

        if name_filter:
            params["filter"] = f"displayName~{name_filter}"

        result = await client.get(
            f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances",
            params=params,
        )

        instances = []
        for item in result.get("items", []):
            instances.append(
                {
                    "id": item.get("id"),
                    "name": item.get("displayName"),
                    "description": item.get("description"),
                    "group_name": item.get("groupName"),
                    "lock_description": item.get("lockDescription"),
                    "stop_monitoring": item.get("stopMonitoring"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "device_datasource_id": device_datasource_id,
                "total": result.get("total", 0),
                "count": len(instances),
                "instances": instances,
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_device_data(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    datapoints: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TextContent]:
    """Get metric data for a specific instance.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device DataSource ID.
        instance_id: Instance ID.
        datapoints: Comma-separated list of datapoint names (optional, all if not specified).
        start_time: Start time in epoch seconds (optional, defaults to last hour).
        end_time: End time in epoch seconds (optional, defaults to now).

    Returns:
        List of TextContent with metric data or error.
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
            f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances/{instance_id}/data",
            params=params if params else None,
        )

        return format_response(
            {
                "device_id": device_id,
                "device_datasource_id": device_datasource_id,
                "instance_id": instance_id,
                "datapoints": result.get("dataPoints", []),
                "values": result.get("values", {}),
                "time": result.get("time", []),
            }
        )
    except Exception as e:
        return handle_error(e)


async def get_graph_data(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    graph_id: int,
    start_time: int | None = None,
    end_time: int | None = None,
) -> list[TextContent]:
    """Get graph data for a specific instance.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device DataSource ID.
        instance_id: Instance ID.
        graph_id: Graph ID.
        start_time: Start time in epoch seconds (optional).
        end_time: End time in epoch seconds (optional).

    Returns:
        List of TextContent with graph data or error.
    """
    try:
        params: dict = {}

        if start_time:
            params["start"] = start_time
        if end_time:
            params["end"] = end_time

        result = await client.get(
            f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances/{instance_id}/graphs/{graph_id}/data",
            params=params if params else None,
        )

        return format_response(
            {
                "device_id": device_id,
                "graph_id": graph_id,
                "instance_id": instance_id,
                "lines": result.get("lines", []),
                "timestamps": result.get("timestamps", []),
            }
        )
    except Exception as e:
        return handle_error(e)
