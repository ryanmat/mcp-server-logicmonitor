# Description: Metrics and data tools for LogicMonitor MCP server.
# Description: Provides datasource/instance queries, instance CRUD, metric data, and graph data.

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
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'dataSourceName~{quote_filter_value(clean_name)}'

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

        response = {
            "device_id": device_id,
            "total": result.get("total", 0),
            "count": len(datasources),
            "datasources": datasources,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
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
        wildcards_stripped = False

        if name_filter:
            clean_name, was_modified = sanitize_filter_value(name_filter)
            wildcards_stripped = wildcards_stripped or was_modified
            params["filter"] = f'displayName~{quote_filter_value(clean_name)}'

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

        response = {
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "total": result.get("total", 0),
            "count": len(instances),
            "instances": instances,
        }
        if wildcards_stripped:
            response["note"] = WILDCARD_STRIP_NOTE
        return format_response(response)
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


# -- Instance management (write) -----------------------------------------------


@require_write_permission
async def add_device_instance(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    display_name: str,
    wild_value: str,
    description: str | None = None,
) -> list[TextContent]:
    """Add a monitored instance to a DataSource on a device.

    Used for DataSources without Active Discovery (e.g. ServiceStatus)
    where instances must be added manually.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID (from get_device_datasources).
        display_name: Display name for the instance.
        wild_value: Wildcard value used by the DataSource to query this instance
            (e.g. "nginx.service" for ServiceStatus).
        description: Optional instance description.

    Returns:
        List of TextContent with created instance details or error.
    """
    try:
        body: dict = {
            "displayName": display_name,
            "wildValue": wild_value,
        }
        if description:
            body["description"] = description

        result = await client.post(
            f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances",
            json_body=body,
        )

        return format_response(
            {
                "message": f"Instance '{display_name}' created",
                "instance": {
                    "id": result.get("id"),
                    "display_name": result.get("displayName"),
                    "wild_value": result.get("wildValue"),
                    "description": result.get("description"),
                    "device_id": result.get("deviceId"),
                    "device_datasource_id": result.get("deviceDataSourceId"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def update_device_instance(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    display_name: str | None = None,
    description: str | None = None,
    stop_monitoring: bool | None = None,
    disable_alerting: bool | None = None,
) -> list[TextContent]:
    """Update an existing monitored instance.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID to update.
        display_name: New display name.
        description: New description.
        stop_monitoring: Enable or disable monitoring for this instance.
        disable_alerting: Enable or disable alerting for this instance.

    Returns:
        List of TextContent with updated instance details or error.
    """
    try:
        body: dict = {}

        if display_name is not None:
            body["displayName"] = display_name
        if description is not None:
            body["description"] = description
        if stop_monitoring is not None:
            body["stopMonitoring"] = stop_monitoring
        if disable_alerting is not None:
            body["disableAlerting"] = disable_alerting

        if not body:
            return format_response(
                {
                    "error": True,
                    "code": "NO_CHANGES",
                    "message": "No updates provided",
                }
            )

        result = await client.patch(
            f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances/{instance_id}",
            json_body=body,
        )

        return format_response(
            {
                "message": "Instance updated",
                "instance": {
                    "id": result.get("id"),
                    "display_name": result.get("displayName"),
                    "description": result.get("description"),
                    "stop_monitoring": result.get("stopMonitoring"),
                },
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_device_instance(
    client: "LogicMonitorClient",
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
) -> list[TextContent]:
    """Delete a monitored instance from a DataSource on a device.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID.
        instance_id: Instance ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    try:
        base = f"/device/devices/{device_id}/devicedatasources/{device_datasource_id}/instances"

        # Fetch instance info for confirmation message
        instance = await client.get(f"{base}/{instance_id}")
        instance_name = instance.get("displayName", f"ID:{instance_id}")

        await client.delete(f"{base}/{instance_id}")

        return format_response(
            {
                "success": True,
                "message": f"Instance '{instance_name}' deleted",
                "instance_id": instance_id,
                "display_name": instance_name,
            }
        )
    except Exception as e:
        return handle_error(e)
