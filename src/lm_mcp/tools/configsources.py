# Description: ConfigSource tools for LogicMonitor MCP server.
# Description: Provides ConfigSource definitions and device config data retrieval.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import (
    format_response,
    handle_error,
    list_tool,
    require_write_permission,
)
from lm_mcp.tools.logicmodules import (
    MODULES,
    create_module,
    delete_module,
    get_module,
    update_module,
)

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def get_configsources(
    client: LogicMonitorClient,
    name_filter: str | None = None,
    applies_to_filter: str | None = None,
    filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """List ConfigSources from LogicMonitor.

    Args:
        client: LogicMonitor API client.
        name_filter: Filter by name (supports wildcards).
        applies_to_filter: Filter by appliesTo expression.
        filter: Raw filter expression for advanced queries (overrides other filters).
            Supports LogicMonitor filter syntax with operators:
            : (equal), !: (not equal), > < >: <: (comparisons),
            ~ (contains), !~ (not contains).
            Examples: "name~Cisco,technology:snmp"
        limit: Maximum number of ConfigSources to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with ConfigSource data or error.
    """
    module = MODULES["configsource"]
    return await list_tool(
        client,
        f"/setting/{module.path}",
        key="configsources",
        project=module.list_row,
        limit=limit,
        offset=offset,
        filter=filter,
        named={"name~": name_filter, "appliesTo~": applies_to_filter},
    )


@require_write_permission
async def create_configsource(
    client: LogicMonitorClient,
    definition: dict,
    overwrite: bool = False,
) -> list[TextContent]:
    """Create a ConfigSource via REST API using a full definition dict.

    Accepts REST API format (the format get_configsource returns with raw=true).
    Use this for creating ConfigSources from exported definitions or from
    scratch. For LM Exchange format imports, use import_configsource instead.

    Args:
        client: LogicMonitor API client.
        definition: Full ConfigSource definition dict in REST API format.
        overwrite: If True, replace the ConfigSource holding the definition's name in
            place (a PUT to its id); nothing is deleted first.

    Returns:
        List of TextContent with created ConfigSource info or error.
    """
    return await create_module(client, "configsource", definition, overwrite)


@require_write_permission
async def update_configsource(
    client: LogicMonitorClient,
    configsource_id: int,
    definition: dict,
    confirm: bool = False,
) -> list[TextContent]:
    """Update an existing ConfigSource via REST API (full replace).

    Internal PUT behind update_logicmodule, which reads the current
    definition, merges the caller's changes and passes the merged full
    definition here; the server registers no tool for it. The LM API
    update is full-replace and can blank any field the definition leaves out.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID to update.
        definition: Full ConfigSource definition dict with all fields.
        confirm: Must be True to proceed; update_logicmodule always passes it.
            Without it the call returns INVALID_REQUEST and writes nothing.

    Returns:
        List of TextContent with updated ConfigSource info or error.
    """
    return await update_module(client, "configsource", configsource_id, definition, confirm)


async def get_configsource(
    client: LogicMonitorClient,
    configsource_id: int,
    raw: bool = False,
) -> list[TextContent]:
    """Get detailed information about a specific ConfigSource.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID.
        raw: Return the REST object whole instead of the summary.

    Returns:
        List of TextContent with ConfigSource details or error.
    """
    return await get_module(client, "configsource", configsource_id, raw)


def _update_reason_row(item: dict) -> dict:
    """Project one updatereasons row onto the get_configsource_update_reasons fields."""
    return {
        "version": item.get("version"),
        "reason": item.get("reason"),
        "date_time": item.get("dateTime"),
        "user_name": item.get("userName"),
    }


async def get_configsource_update_reasons(
    client: LogicMonitorClient,
    configsource_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[TextContent]:
    """Get the update history and reasons for a ConfigSource.

    Returns an audit trail of changes made to the ConfigSource definition,
    including timestamps and reason descriptions.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID.
        limit: Maximum number of entries to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with update reason entries or error.
    """
    return await list_tool(
        client,
        f"/setting/configsources/{configsource_id}/updatereasons",
        key="update_reasons",
        project=_update_reason_row,
        limit=limit,
        offset=offset,
        extra={"configsource_id": configsource_id},
    )


# -- Device config data (instance-level) --------------------------------------


def _device_config_row(item: dict) -> dict:
    """Project one instance config row onto the get_device_config fields."""
    return {
        "id": item.get("id"),
        "version": item.get("version"),
        "poll_timestamp": item.get("pollTimestamp"),
        "change_status": item.get("changeStatus"),
        "config_status": item.get("configStatus"),
        "config_error_message": item.get("configErrMsg"),
        "device_display_name": item.get("deviceDisplayName"),
        "instance_name": item.get("instanceName"),
        "datasource_name": item.get("dataSourceName"),
    }


async def get_device_config(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    limit: int = 10,
    offset: int = 0,
) -> list[TextContent]:
    """List config versions collected for a device instance.

    Returns paginated config snapshots from the LM Config Archive, including
    timestamps and change status. Use get_device_config_version to retrieve
    the full config text and diffs for a specific version.

    Typical workflow: get_device_datasources (filter by ConfigSource name) ->
    get_device_instances -> get_device_config -> get_device_config_version.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID for the ConfigSource
            (from get_device_datasources).
        instance_id: Instance ID (e.g. Running-Config instance).
        limit: Maximum number of config versions to return.
        offset: Number of results to skip for pagination.

    Returns:
        List of TextContent with config version summaries or error.
    """
    return await list_tool(
        client,
        f"/device/devices/{device_id}/devicedatasources"
        f"/{device_datasource_id}/instances/{instance_id}/config",
        key="configs",
        project=_device_config_row,
        limit=limit,
        offset=offset,
        extra={
            "device_id": device_id,
            "device_datasource_id": device_datasource_id,
            "instance_id": instance_id,
        },
    )


async def get_device_config_version(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
    config_id: str,
    start_epoch: int = 0,
) -> list[TextContent]:
    """Get a specific config version with full content and diffs.

    Returns the complete configuration text, line-by-line diffs from the
    previous version, and any alerts triggered by the config change.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID for the ConfigSource.
        instance_id: Instance ID.
        config_id: Config version ID (from get_device_config).
        start_epoch: Epoch timestamp to compare against. Use 0 to compare
            against the immediately previous version. Use a specific epoch
            to see diffs relative to a point in time.

    Returns:
        List of TextContent with config content, diffs, and alerts or error.
    """
    try:
        params: dict = {"startEpoch": start_epoch}

        base = (
            f"/device/devices/{device_id}/devicedatasources"
            f"/{device_datasource_id}/instances/{instance_id}/config/{config_id}"
        )
        result = await client.get(base, params=params)

        # Extract diff entries
        diffs = []
        for diff in result.get("deltaConfig", []):
            diffs.append(
                {
                    "row_number": diff.get("rowNo"),
                    "type": diff.get("type"),
                    "content": diff.get("content"),
                }
            )

        # Extract associated alerts
        alerts = []
        for alert in result.get("alerts", []):
            alerts.append(
                {
                    "alert_id": alert.get("alertId"),
                    "alert_level": alert.get("alertLevel"),
                    "alert_summary": alert.get("alertSummary"),
                    "timestamp": alert.get("timestamp"),
                }
            )

        return format_response(
            {
                "device_id": device_id,
                "instance_id": instance_id,
                "config_id": config_id,
                "version": result.get("version"),
                "poll_timestamp": result.get("pollTimestamp"),
                "change_status": result.get("changeStatus"),
                "compared_with": result.get("comparedWith"),
                "config": result.get("config"),
                "delta_config": diffs,
                "alerts": alerts,
                "device_display_name": result.get("deviceDisplayName"),
                "instance_name": result.get("instanceName"),
                "datasource_name": result.get("dataSourceName"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def collect_device_config(
    client: LogicMonitorClient,
    device_id: int,
    device_datasource_id: int,
    instance_id: int,
) -> list[TextContent]:
    """Trigger an on-demand config collection for a device instance.

    Forces the collector to immediately gather a new config snapshot,
    rather than waiting for the next scheduled collection interval.

    Args:
        client: LogicMonitor API client.
        device_id: Device ID.
        device_datasource_id: Device-DataSource ID for the ConfigSource.
        instance_id: Instance ID.

    Returns:
        List of TextContent with collection confirmation or error.
    """
    try:
        base = (
            f"/device/devices/{device_id}/devicedatasources"
            f"/{device_datasource_id}/instances/{instance_id}"
            "/config/configCollection"
        )
        await client.post(base)

        return format_response(
            {
                "success": True,
                "message": "Config collection triggered",
                "device_id": device_id,
                "device_datasource_id": device_datasource_id,
                "instance_id": instance_id,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def delete_configsource(
    client: LogicMonitorClient,
    configsource_id: int,
) -> list[TextContent]:
    """Delete a ConfigSource from LogicMonitor.

    Removes the ConfigSource definition. Existing collected config data
    is retained on devices but no new configs will be collected.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID to delete.

    Returns:
        List of TextContent with deletion confirmation or error.
    """
    return await delete_module(client, "configsource", configsource_id)
