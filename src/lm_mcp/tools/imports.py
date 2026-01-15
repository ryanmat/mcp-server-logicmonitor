# Description: Import/Export tools for LogicMonitor MCP server.
# Description: Provides export functionality for LogicModules.

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import TextContent

from lm_mcp.tools import format_response, handle_error, require_write_permission

if TYPE_CHECKING:
    from lm_mcp.client import LogicMonitorClient


async def export_datasource(
    client: "LogicMonitorClient",
    datasource_id: int,
) -> list[TextContent]:
    """Export a DataSource definition as JSON.

    Useful for backing up DataSource configurations or copying between portals.

    Args:
        client: LogicMonitor API client.
        datasource_id: DataSource ID to export.

    Returns:
        List of TextContent with full DataSource definition or error.
    """
    try:
        result = await client.get(f"/setting/datasources/{datasource_id}")
        return format_response(
            {
                "datasource_id": datasource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_eventsource(
    client: "LogicMonitorClient",
    eventsource_id: int,
) -> list[TextContent]:
    """Export an EventSource definition as JSON.

    Args:
        client: LogicMonitor API client.
        eventsource_id: EventSource ID to export.

    Returns:
        List of TextContent with full EventSource definition or error.
    """
    try:
        result = await client.get(f"/setting/eventsources/{eventsource_id}")
        return format_response(
            {
                "eventsource_id": eventsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_configsource(
    client: "LogicMonitorClient",
    configsource_id: int,
) -> list[TextContent]:
    """Export a ConfigSource definition as JSON.

    Args:
        client: LogicMonitor API client.
        configsource_id: ConfigSource ID to export.

    Returns:
        List of TextContent with full ConfigSource definition or error.
    """
    try:
        result = await client.get(f"/setting/configsources/{configsource_id}")
        return format_response(
            {
                "configsource_id": configsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_propertysource(
    client: "LogicMonitorClient",
    propertysource_id: int,
) -> list[TextContent]:
    """Export a PropertySource definition as JSON.

    Args:
        client: LogicMonitor API client.
        propertysource_id: PropertySource ID to export.

    Returns:
        List of TextContent with full PropertySource definition or error.
    """
    try:
        result = await client.get(f"/setting/propertyrules/{propertysource_id}")
        return format_response(
            {
                "propertysource_id": propertysource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_logsource(
    client: "LogicMonitorClient",
    logsource_id: int,
) -> list[TextContent]:
    """Export a LogSource definition as JSON.

    Args:
        client: LogicMonitor API client.
        logsource_id: LogSource ID to export.

    Returns:
        List of TextContent with full LogSource definition or error.
    """
    try:
        result = await client.get(f"/setting/logsources/{logsource_id}")
        return format_response(
            {
                "logsource_id": logsource_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_dashboard(
    client: "LogicMonitorClient",
    dashboard_id: int,
    include_widgets: bool = True,
) -> list[TextContent]:
    """Export a Dashboard definition as JSON including widgets.

    Args:
        client: LogicMonitor API client.
        dashboard_id: Dashboard ID to export.
        include_widgets: Whether to include widget definitions.

    Returns:
        List of TextContent with full Dashboard definition or error.
    """
    try:
        dashboard = await client.get(f"/dashboard/dashboards/{dashboard_id}")

        if include_widgets:
            widgets_result = await client.get(
                f"/dashboard/dashboards/{dashboard_id}/widgets", params={"size": 1000}
            )
            dashboard["widgets_full"] = widgets_result.get("items", [])

        return format_response(
            {
                "dashboard_id": dashboard_id,
                "name": dashboard.get("name"),
                "format": "json",
                "definition": dashboard,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_alert_rule(
    client: "LogicMonitorClient",
    alert_rule_id: int,
) -> list[TextContent]:
    """Export an Alert Rule definition as JSON.

    Args:
        client: LogicMonitor API client.
        alert_rule_id: Alert Rule ID to export.

    Returns:
        List of TextContent with full Alert Rule definition or error.
    """
    try:
        result = await client.get(f"/setting/alert/rules/{alert_rule_id}")
        return format_response(
            {
                "alert_rule_id": alert_rule_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


async def export_escalation_chain(
    client: "LogicMonitorClient",
    escalation_chain_id: int,
) -> list[TextContent]:
    """Export an Escalation Chain definition as JSON.

    Args:
        client: LogicMonitor API client.
        escalation_chain_id: Escalation Chain ID to export.

    Returns:
        List of TextContent with full Escalation Chain definition or error.
    """
    try:
        result = await client.get(f"/setting/alert/chains/{escalation_chain_id}")
        return format_response(
            {
                "escalation_chain_id": escalation_chain_id,
                "name": result.get("name"),
                "format": "json",
                "definition": result,
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_datasource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a DataSource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: DataSource JSON definition to import.

    Returns:
        List of TextContent with imported DataSource info or error.
    """
    try:
        result = await client.post("/setting/datasources/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
                "display_name": result.get("displayName"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_configsource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a ConfigSource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: ConfigSource JSON definition to import.

    Returns:
        List of TextContent with imported ConfigSource info or error.
    """
    try:
        result = await client.post("/setting/configsources/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_eventsource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import an EventSource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: EventSource JSON definition to import.

    Returns:
        List of TextContent with imported EventSource info or error.
    """
    try:
        result = await client.post("/setting/eventsources/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_propertysource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a PropertySource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: PropertySource JSON definition to import.

    Returns:
        List of TextContent with imported PropertySource info or error.
    """
    try:
        result = await client.post("/setting/propertyrules/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_logsource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a LogSource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: LogSource JSON definition to import.

    Returns:
        List of TextContent with imported LogSource info or error.
    """
    try:
        result = await client.post("/setting/logsources/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_topologysource(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a TopologySource from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: TopologySource JSON definition to import.

    Returns:
        List of TextContent with imported TopologySource info or error.
    """
    try:
        result = await client.post("/setting/topologysources/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_jobmonitor(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import a JobMonitor from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: JobMonitor JSON definition to import.

    Returns:
        List of TextContent with imported JobMonitor info or error.
    """
    try:
        result = await client.post("/setting/batchjobs/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)


@require_write_permission
async def import_appliesto_function(
    client: "LogicMonitorClient",
    definition: dict,
) -> list[TextContent]:
    """Import an AppliesTo function from JSON definition (v228 API).

    Args:
        client: LogicMonitor API client.
        definition: AppliesTo function JSON definition to import.

    Returns:
        List of TextContent with imported function info or error.
    """
    try:
        result = await client.post("/setting/functions/importjson", json_body=definition)
        return format_response(
            {
                "imported_id": result.get("id"),
                "name": result.get("name"),
            }
        )
    except Exception as e:
        return handle_error(e)
