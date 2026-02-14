# Description: Tool registry for LogicMonitor MCP server.
# Description: Defines all MCP tools with schemas and handlers.

from __future__ import annotations

from typing import Any

from mcp.types import Tool, ToolAnnotations

# Annotation presets for tool categorization
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
_DELETE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)
_EXPORT = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
_IMPORT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
_SESSION_READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
_SESSION_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

# Tool definitions organized by category
TOOLS: list[Tool] = []

# Devices
TOOLS.extend(
    [
        Tool(
            name="get_devices",
            description="List devices (resources) from LogicMonitor with optional filtering",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Filter by device group ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by device name (substring match)",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["normal", "dead", "dead-collector", "unmonitored", "disabled"],
                        "description": "Filter by device status",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Syntax: field:value, field~value. Example: systemProperties.name:val",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results (max 1000)",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_device",
            description="Get detailed information about a specific device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_groups",
            description="List device/resource groups from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "integer", "description": "Filter by parent group ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="create_device",
            description="Create a new device/resource (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Device hostname or IP address"},
                    "display_name": {"type": "string", "description": "Display name"},
                    "preferred_collector_id": {"type": "integer", "description": "Collector ID"},
                    "host_group_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Group IDs",
                    },
                    "description": {"type": "string", "description": "Device description"},
                    "custom_properties": {"type": "object", "description": "Custom properties"},
                },
                "required": ["name", "display_name", "preferred_collector_id"],
            },
        ),
        Tool(
            name="update_device",
            description="Update an existing device/resource (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID to update"},
                    "display_name": {"type": "string", "description": "New display name"},
                    "description": {"type": "string", "description": "New description"},
                    "host_group_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "New group IDs",
                    },
                    "preferred_collector_id": {
                        "type": "integer",
                        "description": "New collector ID",
                    },
                    "disable_alerting": {"type": "boolean", "description": "Disable alerting"},
                    "custom_properties": {"type": "object", "description": "Custom properties"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="delete_device",
            description=(
                "Delete a device/resource (requires write permission). Soft delete by default."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID to delete"},
                    "delete_hard": {
                        "type": "boolean",
                        "default": False,
                        "description": "Permanently delete",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="create_device_group",
            description="Create a new device/resource group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Group name"},
                    "parent_id": {
                        "type": "integer",
                        "default": 1,
                        "description": "Parent group ID (1=root)",
                    },
                    "description": {"type": "string", "description": "Group description"},
                    "applies_to": {
                        "type": "string",
                        "description": "AppliesTo expression for dynamic membership",
                    },
                    "custom_properties": {"type": "object", "description": "Custom properties"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="delete_device_group",
            description="Delete a device/resource group (requires write permission). Shows impact.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Group ID to delete"},
                    "delete_children": {
                        "type": "boolean",
                        "default": False,
                        "description": "Delete child devices/groups",
                    },
                    "delete_hard": {
                        "type": "boolean",
                        "default": False,
                        "description": "Permanently delete",
                    },
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# Alerts
TOOLS.extend(
    [
        Tool(
            name="get_alerts",
            description="Get alerts from LogicMonitor with optional filtering",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "error", "warning", "info"],
                        "description": "Filter by severity",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "acknowledged"],
                        "description": "Filter by status",
                    },
                    "cleared": {"type": "boolean", "description": "Filter by cleared status"},
                    "acked": {"type": "boolean", "description": "Filter by acknowledged status"},
                    "sdted": {"type": "boolean", "description": "Filter by SDT status"},
                    "start_epoch": {
                        "type": "integer",
                        "description": "Filter alerts started after this epoch timestamp",
                    },
                    "end_epoch": {
                        "type": "integer",
                        "description": "Filter alerts started before this epoch timestamp",
                    },
                    "datapoint": {
                        "type": "string",
                        "description": "Filter by datapoint name (substring match)",
                    },
                    "instance": {
                        "type": "string",
                        "description": "Filter by instance name (substring match)",
                    },
                    "datasource": {
                        "type": "string",
                        "description": "Filter by datasource/template name (substring match)",
                    },
                    "device": {
                        "type": "string",
                        "description": "Filter by device name (substring match)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: severity:4,cleared:false",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results (max 1000)",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_alert_details",
            description="Get detailed information about a specific alert",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID (with or without LMA prefix)",
                    },
                },
                "required": ["alert_id"],
            },
        ),
        Tool(
            name="acknowledge_alert",
            description="Acknowledge an alert (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID (with or without LMA prefix)",
                    },
                    "note": {"type": "string", "description": "Optional acknowledgment note"},
                },
                "required": ["alert_id"],
            },
        ),
        Tool(
            name="add_alert_note",
            description="Add a note to an alert without acknowledging (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID (with or without LMA prefix)",
                    },
                    "note": {"type": "string", "description": "Note text to add"},
                },
                "required": ["alert_id", "note"],
            },
        ),
        Tool(
            name="bulk_acknowledge_alerts",
            description="Acknowledge multiple alerts at once (max 100, requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Alert IDs (max 100)",
                    },
                    "note": {"type": "string", "description": "Optional acknowledgment note"},
                },
                "required": ["alert_ids"],
            },
        ),
    ]
)

# SDTs (Scheduled Downtime)
TOOLS.extend(
    [
        Tool(
            name="list_sdts",
            description="List scheduled downtimes from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Filter by device ID",
                    },
                    "device_group_id": {
                        "type": "integer",
                        "description": "Filter by device group ID",
                    },
                    "sdt_type": {
                        "type": "string",
                        "enum": ["DeviceSDT", "DeviceGroupSDT", "DeviceDataSourceSDT"],
                        "description": "Filter by SDT type",
                    },
                    "admin": {
                        "type": "string",
                        "description": "Filter by admin username (substring match)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: type:DeviceSDT,admin~john",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="create_sdt",
            description="Create a scheduled downtime (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "sdt_type": {
                        "type": "string",
                        "enum": ["DeviceSDT", "DeviceGroupSDT"],
                        "description": "SDT type",
                    },
                    "device_id": {"type": "integer", "description": "Device ID (for DeviceSDT)"},
                    "device_group_id": {
                        "type": "integer",
                        "description": "Device group ID (for DeviceGroupSDT)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "default": 60,
                        "description": "Duration in minutes",
                    },
                    "comment": {"type": "string", "description": "SDT comment"},
                },
                "required": ["sdt_type"],
            },
        ),
        Tool(
            name="delete_sdt",
            description="Delete a scheduled downtime (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "sdt_id": {"type": "string", "description": "SDT ID to delete"},
                },
                "required": ["sdt_id"],
            },
        ),
        Tool(
            name="bulk_create_device_sdt",
            description=(
                "Create SDT for multiple devices/resources (max 100, requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Device IDs (max 100)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "default": 60,
                        "description": "Duration (max 7 days)",
                    },
                    "comment": {"type": "string", "description": "SDT comment"},
                },
                "required": ["device_ids"],
            },
        ),
        Tool(
            name="bulk_delete_sdt",
            description="Delete multiple SDTs at once (max 100, requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "sdt_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "SDT IDs (max 100)",
                    },
                },
                "required": ["sdt_ids"],
            },
        ),
        Tool(
            name="get_active_sdts",
            description="Get currently active SDTs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Filter by device ID"},
                    "device_group_id": {"type": "integer", "description": "Filter by group ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_upcoming_sdts",
            description="Get SDTs scheduled to start within a time window",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_ahead": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours ahead to look",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
    ]
)

# Collectors
TOOLS.extend(
    [
        Tool(
            name="get_collectors",
            description="List collectors from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hostname_filter": {
                        "type": "string",
                        "description": "Filter by hostname (substring match)",
                    },
                    "collector_group_id": {
                        "type": "integer",
                        "description": "Filter by collector group ID",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: hostname~prod,collectorGroupId:1",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_collector",
            description="Get detailed information about a specific collector",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="get_collector_groups",
            description="List collector groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by name (substring)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides name_filter). "
                        "Example: name~prod,autoBalance:true",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_collector_group",
            description="Get details about a specific collector group",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Collector group ID"},
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# Metrics and Data
TOOLS.extend(
    [
        Tool(
            name="get_device_datasources",
            description="Get datasources applied to a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_instances",
            description="Get instances of a datasource on a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
                "required": ["device_id", "device_datasource_id"],
            },
        ),
        Tool(
            name="get_device_data",
            description="Get metric data for a device/resource datasource instance",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "datapoints": {
                        "type": "string",
                        "description": "Comma-separated datapoint names (optional, all if omitted)",
                    },
                    "start_time": {
                        "type": "integer",
                        "description": "Start time in epoch seconds (optional)",
                    },
                    "end_time": {
                        "type": "integer",
                        "description": "End time in epoch seconds (optional)",
                    },
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
            },
        ),
        Tool(
            name="get_graph_data",
            description="Get graph image data for visualization",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "graph_id": {"type": "integer", "description": "Graph ID"},
                    "start_time": {
                        "type": "integer",
                        "description": "Start time in epoch seconds (optional)",
                    },
                    "end_time": {
                        "type": "integer",
                        "description": "End time in epoch seconds (optional)",
                    },
                },
                "required": ["device_id", "device_datasource_id", "instance_id", "graph_id"],
            },
        ),
    ]
)

# Dashboards
TOOLS.extend(
    [
        Tool(
            name="get_dashboards",
            description="List dashboards from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "group_id": {"type": "integer", "description": "Filter by group ID"},
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~prod,owner:admin",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_dashboard",
            description="Get detailed information about a specific dashboard",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                },
                "required": ["dashboard_id"],
            },
        ),
        Tool(
            name="get_dashboard_widgets",
            description="Get widgets configured on a dashboard",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                },
                "required": ["dashboard_id"],
            },
        ),
        Tool(
            name="get_widget",
            description="Get details about a specific widget",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                    "widget_id": {"type": "integer", "description": "Widget ID"},
                },
                "required": ["dashboard_id", "widget_id"],
            },
        ),
        Tool(
            name="create_dashboard",
            description="Create a new dashboard (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Dashboard name"},
                    "group_id": {
                        "type": "integer",
                        "default": 1,
                        "description": "Dashboard group ID",
                    },
                    "description": {"type": "string", "description": "Dashboard description"},
                    "sharable": {
                        "type": "boolean",
                        "default": True,
                        "description": "Make dashboard sharable",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_dashboard",
            description="Update an existing dashboard (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID to update"},
                    "name": {"type": "string", "description": "New name"},
                    "description": {"type": "string", "description": "New description"},
                    "group_id": {"type": "integer", "description": "New group ID"},
                    "sharable": {"type": "boolean", "description": "Make dashboard sharable"},
                },
                "required": ["dashboard_id"],
            },
        ),
        Tool(
            name="delete_dashboard",
            description="Delete a dashboard (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID to delete"},
                },
                "required": ["dashboard_id"],
            },
        ),
        Tool(
            name="add_widget",
            description="Add a widget to a dashboard (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                    "name": {"type": "string", "description": "Widget name"},
                    "widget_type": {
                        "type": "string",
                        "description": "Widget type (cgraph, sgraph, text, etc.)",
                    },
                    "column_index": {
                        "type": "integer",
                        "default": 0,
                        "description": "Column position (0-11)",
                    },
                    "row_span": {"type": "integer", "default": 1, "description": "Row span"},
                    "col_span": {
                        "type": "integer",
                        "default": 6,
                        "description": "Column span (1-12)",
                    },
                    "description": {"type": "string", "description": "Widget description"},
                    "config": {"type": "object", "description": "Widget configuration"},
                },
                "required": ["dashboard_id", "name", "widget_type"],
            },
        ),
        Tool(
            name="update_widget",
            description="Update a widget (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                    "widget_id": {"type": "integer", "description": "Widget ID"},
                    "name": {"type": "string", "description": "New name"},
                    "description": {"type": "string", "description": "New description"},
                    "config": {"type": "object", "description": "New configuration"},
                },
                "required": ["dashboard_id", "widget_id"],
            },
        ),
        Tool(
            name="delete_widget",
            description="Delete a widget from a dashboard (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                    "widget_id": {"type": "integer", "description": "Widget ID to delete"},
                },
                "required": ["dashboard_id", "widget_id"],
            },
        ),
    ]
)

# Dashboard Groups
TOOLS.extend(
    [
        Tool(
            name="get_dashboard_groups",
            description="List dashboard groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_dashboard_group",
            description="Get details about a specific dashboard group",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Dashboard group ID"},
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# Websites
TOOLS.extend(
    [
        Tool(
            name="get_websites",
            description="List websites from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "group_id": {"type": "integer", "description": "Filter by website group ID"},
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~prod,type:webcheck",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_website",
            description="Get detailed information about a specific website",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {"type": "integer", "description": "Website ID"},
                },
                "required": ["website_id"],
            },
        ),
        Tool(
            name="get_website_groups",
            description="List website groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "integer", "description": "Filter by parent group ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_website_data",
            description="Get synthetic check data for a website",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {"type": "integer", "description": "Website ID"},
                    "checkpoint_id": {"type": "integer", "description": "Checkpoint ID"},
                    "start_time": {
                        "type": "integer",
                        "description": "Start time in epoch seconds (optional)",
                    },
                    "end_time": {
                        "type": "integer",
                        "description": "End time in epoch seconds (optional)",
                    },
                },
                "required": ["website_id"],
            },
        ),
        Tool(
            name="create_website",
            description="Create a website check in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the website check"},
                    "website_type": {
                        "type": "string",
                        "enum": ["webcheck", "pingcheck"],
                        "description": "Type of check",
                    },
                    "domain": {"type": "string", "description": "Domain or host to check"},
                    "description": {"type": "string", "description": "Optional description"},
                    "group_id": {"type": "integer", "description": "Website group ID"},
                    "polling_interval": {
                        "type": "integer",
                        "default": 5,
                        "description": "Check interval in minutes",
                    },
                    "is_internal": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether this is an internal website",
                    },
                },
                "required": ["name", "website_type", "domain"],
            },
        ),
        Tool(
            name="update_website",
            description="Update a website check in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {"type": "integer", "description": "Website ID to update"},
                    "name": {"type": "string", "description": "Updated name"},
                    "description": {"type": "string", "description": "Updated description"},
                    "polling_interval": {
                        "type": "integer",
                        "description": "Updated polling interval in minutes",
                    },
                    "is_internal": {
                        "type": "boolean",
                        "description": "Updated internal website flag",
                    },
                    "disable_alerting": {
                        "type": "boolean",
                        "description": "Whether to disable alerting",
                    },
                },
                "required": ["website_id"],
            },
        ),
        Tool(
            name="delete_website",
            description="Delete a website check from LogicMonitor (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {"type": "integer", "description": "Website ID to delete"},
                },
                "required": ["website_id"],
            },
        ),
        Tool(
            name="create_website_group",
            description="Create a website group in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the website group"},
                    "parent_id": {"type": "integer", "description": "Parent group ID (optional)"},
                    "description": {"type": "string", "description": "Optional description"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="delete_website_group",
            description="Delete a website group from LogicMonitor (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Group ID to delete"},
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# Reports
TOOLS.extend(
    [
        Tool(
            name="get_reports",
            description="List reports from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "group_id": {"type": "integer", "description": "Filter by group ID"},
                    "report_type": {"type": "string", "description": "Filter by type"},
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~monthly,type~Alert",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_report",
            description="Get detailed information about a specific report",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer", "description": "Report ID"},
                },
                "required": ["report_id"],
            },
        ),
        Tool(
            name="get_report_groups",
            description="List report groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_scheduled_reports",
            description="Get reports with schedules configured",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Only enabled schedules",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="run_report",
            description="Run/execute a report (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer", "description": "Report ID to run"},
                    "notify_email": {
                        "type": "string",
                        "description": "Email to notify when complete",
                    },
                },
                "required": ["report_id"],
            },
        ),
        Tool(
            name="create_report",
            description="Create a new report (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Report name"},
                    "report_type": {"type": "string", "description": "Report type"},
                    "group_id": {"type": "integer", "default": 1, "description": "Report group ID"},
                    "description": {"type": "string", "description": "Report description"},
                    "format": {"type": "string", "default": "PDF", "description": "Output format"},
                    "schedule_enabled": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable schedule",
                    },
                    "schedule_cron": {
                        "type": "string",
                        "description": "Cron expression for schedule",
                    },
                },
                "required": ["name", "report_type"],
            },
        ),
        Tool(
            name="update_report_schedule",
            description="Update a report's schedule (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer", "description": "Report ID to update"},
                    "enabled": {"type": "boolean", "description": "Enable/disable schedule"},
                    "schedule_type": {"type": "string", "description": "Schedule type"},
                    "cron": {"type": "string", "description": "Cron expression"},
                    "timezone": {"type": "string", "description": "Timezone"},
                },
                "required": ["report_id"],
            },
        ),
        Tool(
            name="delete_report",
            description="Delete a report (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer", "description": "Report ID to delete"},
                },
                "required": ["report_id"],
            },
        ),
    ]
)

# Escalation Chains
TOOLS.extend(
    [
        Tool(
            name="get_escalation_chains",
            description="List escalation chains",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_escalation_chain",
            description="Get details about a specific escalation chain",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Escalation chain ID"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="get_recipient_groups",
            description="List recipient groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_recipient_group",
            description="Get details about a specific recipient group",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Recipient group ID"},
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="create_escalation_chain",
            description="Create an escalation chain (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the escalation chain"},
                    "description": {"type": "string", "description": "Optional description"},
                    "enable_throttling": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable alert throttling",
                    },
                    "throttling_period": {
                        "type": "integer",
                        "description": "Throttling period in minutes",
                    },
                    "throttling_alerts": {
                        "type": "integer",
                        "description": "Number of alerts before throttling",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_escalation_chain",
            description="Update an escalation chain (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Escalation chain ID"},
                    "name": {"type": "string", "description": "Updated name"},
                    "description": {"type": "string", "description": "Updated description"},
                    "enable_throttling": {
                        "type": "boolean",
                        "description": "Updated throttling setting",
                    },
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="delete_escalation_chain",
            description="Delete an escalation chain (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Escalation chain ID"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="create_recipient_group",
            description="Create a recipient group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the recipient group"},
                    "description": {"type": "string", "description": "Optional description"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_recipient_group",
            description="Update a recipient group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Recipient group ID"},
                    "name": {"type": "string", "description": "Updated name"},
                    "description": {"type": "string", "description": "Updated description"},
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="delete_recipient_group",
            description="Delete a recipient group (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Recipient group ID"},
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# Alert Rules
TOOLS.extend(
    [
        Tool(
            name="get_alert_rules",
            description="List alert rules",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_alert_rule",
            description="Get details about a specific alert rule",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="create_alert_rule",
            description="Create an alert rule in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the alert rule"},
                    "priority": {
                        "type": "integer",
                        "description": "Priority level (lower = higher priority)",
                    },
                    "escalation_chain_id": {
                        "type": "integer",
                        "description": "Escalation chain ID for the rule",
                    },
                    "level_str": {
                        "type": "string",
                        "enum": ["Critical", "Error", "Warning", "All"],
                        "description": "Alert level filter",
                    },
                    "devices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of device patterns to match",
                    },
                    "device_groups": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of device group patterns to match",
                    },
                    "datasource": {"type": "string", "description": "DataSource pattern to match"},
                    "suppress_alert_clear": {
                        "type": "boolean",
                        "default": False,
                        "description": "Suppress alert clear notifications",
                    },
                },
                "required": ["name", "priority", "escalation_chain_id"],
            },
        ),
        Tool(
            name="update_alert_rule",
            description="Update an alert rule in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID to update"},
                    "name": {"type": "string", "description": "Updated name"},
                    "priority": {"type": "integer", "description": "Updated priority level"},
                    "escalation_chain_id": {
                        "type": "integer",
                        "description": "Updated escalation chain ID",
                    },
                    "level_str": {"type": "string", "description": "Updated alert level filter"},
                    "suppress_alert_clear": {
                        "type": "boolean",
                        "description": "Updated suppress alert clear setting",
                    },
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="delete_alert_rule",
            description="Delete an alert rule from LogicMonitor (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID to delete"},
                },
                "required": ["rule_id"],
            },
        ),
    ]
)

# Users and Roles
TOOLS.extend(
    [
        Tool(
            name="get_users",
            description="List users from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by username (substring match)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides name_filter). "
                        "Example: username~admin,status:active",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_user",
            description="Get details about a specific user",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "User ID"},
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="get_roles",
            description="List roles",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by role name (substring match)",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides name_filter). "
                        "Example: name~admin,twoFARequired:true",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_role",
            description="Get details about a specific role",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "role_id": {"type": "integer", "description": "Role ID"},
                },
                "required": ["role_id"],
            },
        ),
    ]
)

# Access Groups
TOOLS.extend(
    [
        Tool(
            name="get_access_groups",
            description="List access groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_access_group",
            description="Get details about a specific access group",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Access group ID"},
                },
                "required": ["group_id"],
            },
        ),
    ]
)

# API Tokens
TOOLS.extend(
    [
        Tool(
            name="get_api_tokens",
            description="List API tokens",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_api_token",
            description="Get details about a specific API token",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "token_id": {"type": "integer", "description": "API token ID"},
                },
                "required": ["token_id"],
            },
        ),
    ]
)

# Resources and Properties
TOOLS.extend(
    [
        Tool(
            name="get_device_properties",
            description="Get all properties of a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by property name (substring match)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100,
                        "description": "Max results",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_property",
            description="Get a specific property of a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "property_name": {"type": "string", "description": "Property name"},
                },
                "required": ["device_id", "property_name"],
            },
        ),
        Tool(
            name="update_device_property",
            description="Update or create a device/resource property (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "property_name": {"type": "string", "description": "Property name"},
                    "property_value": {"type": "string", "description": "Property value"},
                },
                "required": ["device_id", "property_name", "property_value"],
            },
        ),
    ]
)

# Datasources
TOOLS.extend(
    [
        Tool(
            name="get_datasources",
            description="List datasources from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~CPU,group:Core",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_datasource",
            description="Get details about a specific datasource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                },
                "required": ["datasource_id"],
            },
        ),
    ]
)

# ConfigSources, EventSources, PropertySources, TopologySources, LogSources
TOOLS.extend(
    [
        Tool(
            name="get_configsources",
            description="List ConfigSources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~Cisco,technology:snmp",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_configsource",
            description="Get details about a specific ConfigSource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "configsource_id": {"type": "integer", "description": "ConfigSource ID"},
                },
                "required": ["configsource_id"],
            },
        ),
        Tool(
            name="get_eventsources",
            description="List EventSources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~Windows,group:Events",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_eventsource",
            description="Get details about a specific EventSource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "eventsource_id": {"type": "integer", "description": "EventSource ID"},
                },
                "required": ["eventsource_id"],
            },
        ),
        Tool(
            name="get_propertysources",
            description="List PropertySources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~Linux,technology:script",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_propertysource",
            description="Get details about a specific PropertySource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "propertysource_id": {"type": "integer", "description": "PropertySource ID"},
                },
                "required": ["propertysource_id"],
            },
        ),
        Tool(
            name="get_topologysources",
            description="List TopologySources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~Network,technology:snmp",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_topologysource",
            description="Get details about a specific TopologySource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "topologysource_id": {"type": "integer", "description": "TopologySource ID"},
                },
                "required": ["topologysource_id"],
            },
        ),
        Tool(
            name="get_logsources",
            description="List LogSources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (substring)"},
                    "applies_to_filter": {
                        "type": "string",
                        "description": "Filter by appliesTo expression",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Example: name~syslog,logType:EventLog",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_logsource",
            description="Get details about a specific LogSource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "logsource_id": {"type": "integer", "description": "LogSource ID"},
                },
                "required": ["logsource_id"],
            },
        ),
        Tool(
            name="get_device_logsources",
            description="Get LogSources applied to a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
                "required": ["device_id"],
            },
        ),
    ]
)

# Network Scans
TOOLS.extend(
    [
        Tool(
            name="get_netscans",
            description="List network scans",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_netscan",
            description="Get details about a specific network scan",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "netscan_id": {"type": "integer", "description": "Netscan ID"},
                },
                "required": ["netscan_id"],
            },
        ),
        Tool(
            name="run_netscan",
            description="Execute a network scan (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "netscan_id": {"type": "integer", "description": "Netscan ID to run"},
                },
                "required": ["netscan_id"],
            },
        ),
    ]
)

# OIDs
TOOLS.extend(
    [
        Tool(
            name="get_oids",
            description="List OID definitions",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "oid_filter": {"type": "string", "description": "Filter by OID (substring)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_oid",
            description="Get details about a specific OID",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "oid_id": {"type": "integer", "description": "OID ID"},
                },
                "required": ["oid_id"],
            },
        ),
    ]
)

# Services
TOOLS.extend(
    [
        Tool(
            name="get_services",
            description="List services from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_service",
            description="Get details about a specific service",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {"type": "integer", "description": "Service ID"},
                },
                "required": ["service_id"],
            },
        ),
        Tool(
            name="get_service_groups",
            description="List service groups",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
    ]
)

# Ops Notes
TOOLS.extend(
    [
        Tool(
            name="get_ops_notes",
            description="List ops notes",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_ops_note",
            description="Get details about a specific ops note",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "Ops note ID"},
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="add_ops_note",
            description="Add an ops note (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "Note text"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
                    "device_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Device IDs to scope the note to",
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Device group IDs to scope the note to",
                    },
                },
                "required": ["note"],
            },
        ),
    ]
)

# Audit Logs
TOOLS.extend(
    [
        Tool(
            name="get_audit_logs",
            description="Get audit logs from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Filter by username"},
                    "action": {"type": "string", "description": "Filter by action type"},
                    "resource_type": {
                        "type": "string",
                        "description": "Filter by resource type",
                    },
                    "start_time": {
                        "type": "integer",
                        "description": "Start time in epoch seconds (optional)",
                    },
                    "end_time": {
                        "type": "integer",
                        "description": "End time in epoch seconds (optional)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_api_token_audit",
            description="Get API token usage audit logs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "token_id": {
                        "type": "integer",
                        "description": "Filter by API token ID",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_login_audit",
            description="Get login/authentication audit logs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Filter by username"},
                    "success_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Only successful logins",
                    },
                    "failed_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Only failed logins",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_change_audit",
            description="Get configuration change audit logs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "description": "Filter by resource type"},
                    "change_type": {"type": "string", "description": "Filter by change type"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
    ]
)

# Topology
TOOLS.extend(
    [
        Tool(
            name="get_topology_map",
            description="Get network topology map data",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_group_id": {
                        "type": "integer",
                        "description": "Filter by device group ID",
                    },
                    "include_connections": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include connection data",
                    },
                    "limit": {"type": "integer", "default": 100, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_device_neighbors",
            description="Get neighboring devices/resources based on topology",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "depth": {
                        "type": "integer",
                        "default": 1,
                        "description": "Depth of neighbor search",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_interfaces",
            description="Get network interfaces for a device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_network_flows",
            description="Get network flow data (NetFlow/sFlow)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "source_ip": {"type": "string", "description": "Filter by source IP"},
                    "dest_ip": {"type": "string", "description": "Filter by destination IP"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_device_connections",
            description="Get device/resource relationships and connections",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                },
                "required": ["device_id"],
            },
        ),
    ]
)

# Batch Jobs
TOOLS.extend(
    [
        Tool(
            name="get_batchjobs",
            description="List batch jobs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_batchjob",
            description="Get details about a specific batch job",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "batchjob_id": {"type": "integer", "description": "Batch job ID"},
                },
                "required": ["batchjob_id"],
            },
        ),
        Tool(
            name="get_batchjob_history",
            description="Get execution history for a batch job",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "batchjob_id": {"type": "integer", "description": "Batch job ID"},
                    "limit": {"type": "integer", "default": 20, "description": "Max results"},
                },
                "required": ["device_id", "batchjob_id"],
            },
        ),
        Tool(
            name="get_device_batchjobs",
            description="Get batch jobs for a specific device (resource)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_scheduled_downtime_jobs",
            description="Get batch jobs related to SDT automation",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
    ]
)

# Cost/Cloud
TOOLS.extend(
    [
        Tool(
            name="get_cost_summary",
            description="Get cloud cost summary",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "cloud_account_id": {
                        "type": "integer",
                        "description": "Filter by cloud account ID",
                    },
                    "time_range": {
                        "type": "string",
                        "default": "last30days",
                        "description": "Time range (e.g. last7days, last30days, last90days)",
                    },
                },
            },
        ),
        Tool(
            name="get_resource_cost",
            description="Get cost data for a specific resource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "time_range": {
                        "type": "string",
                        "default": "last30days",
                        "description": "Time range (e.g. last7days, last30days, last90days)",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_cost_recommendations",
            description="Get cost optimization recommendations",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "cloud_account_id": {
                        "type": "integer",
                        "description": "Filter by cloud account ID",
                    },
                    "recommendation_type": {
                        "type": "string",
                        "description": "Filter by recommendation type",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_idle_resources",
            description="Get idle/underutilized resources",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "cloud_account_id": {
                        "type": "integer",
                        "description": "Filter by cloud account ID",
                    },
                    "resource_type": {
                        "type": "string",
                        "description": "Filter by resource type",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_cloud_cost_accounts",
            description="Get cloud accounts with cost data",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_cost_recommendation_categories",
            description="Get cost recommendation categories with counts and savings",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_cost_recommendation",
            description="Get a specific cost recommendation by ID (v224 API)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "recommendation_id": {
                        "type": "integer",
                        "description": "ID of the recommendation to retrieve",
                    },
                },
                "required": ["recommendation_id"],
            },
        ),
    ]
)

# Imports/Exports
TOOLS.extend(
    [
        Tool(
            name="export_datasource",
            description="Export a datasource definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                },
                "required": ["datasource_id"],
            },
        ),
        Tool(
            name="export_dashboard",
            description="Export a dashboard definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                },
                "required": ["dashboard_id"],
            },
        ),
        Tool(
            name="export_alert_rule",
            description="Export an alert rule definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_rule_id": {"type": "integer", "description": "Alert rule ID"},
                },
                "required": ["alert_rule_id"],
            },
        ),
        Tool(
            name="export_escalation_chain",
            description="Export an escalation chain definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "escalation_chain_id": {
                        "type": "integer",
                        "description": "Escalation chain ID",
                    },
                },
                "required": ["escalation_chain_id"],
            },
        ),
        Tool(
            name="export_configsource",
            description="Export a ConfigSource definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "configsource_id": {"type": "integer", "description": "ConfigSource ID"},
                },
                "required": ["configsource_id"],
            },
        ),
        Tool(
            name="export_eventsource",
            description="Export an EventSource definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "eventsource_id": {"type": "integer", "description": "EventSource ID"},
                },
                "required": ["eventsource_id"],
            },
        ),
        Tool(
            name="export_propertysource",
            description="Export a PropertySource definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "propertysource_id": {"type": "integer", "description": "PropertySource ID"},
                },
                "required": ["propertysource_id"],
            },
        ),
        Tool(
            name="export_logsource",
            description="Export a LogSource definition",
            annotations=_EXPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "logsource_id": {"type": "integer", "description": "LogSource ID"},
                },
                "required": ["logsource_id"],
            },
        ),
        Tool(
            name="import_datasource",
            description="Import a DataSource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "DataSource JSON definition"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_configsource",
            description="Import a ConfigSource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "ConfigSource JSON definition"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_eventsource",
            description="Import an EventSource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "EventSource JSON definition"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_propertysource",
            description="Import a PropertySource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "PropertySource JSON"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_logsource",
            description="Import a LogSource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "LogSource JSON definition"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_topologysource",
            description="Import a TopologySource from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "TopologySource JSON"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_jobmonitor",
            description="Import a JobMonitor from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "JobMonitor JSON definition"},
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_appliesto_function",
            description="Import an AppliesTo function from JSON (requires write permission)",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "AppliesTo function JSON"},
                },
                "required": ["definition"],
            },
        ),
    ]
)

# Ingestion APIs (require LMv1 authentication)
TOOLS.extend(
    [
        Tool(
            name="ingest_logs",
            description="Ingest log entries into LogicMonitor (requires LMv1 auth)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "logs": {
                        "type": "array",
                        "description": "Array of log entries to ingest",
                        "items": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "description": "Log message"},
                                "_lm.resourceId": {
                                    "type": "object",
                                    "description": "Resource mapping (e.g., system.hostname)",
                                },
                                "timestamp": {
                                    "type": "integer",
                                    "description": "Epoch milliseconds (optional)",
                                },
                            },
                            "required": ["message"],
                        },
                    },
                },
                "required": ["logs"],
            },
        ),
        Tool(
            name="push_metrics",
            description="Push custom metrics into LogicMonitor (requires LMv1 auth)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "object",
                        "description": "Metric payload with resource mapping and datapoints",
                        "properties": {
                            "resourceIds": {
                                "type": "object",
                                "description": "Resource mapping (e.g., system.hostname)",
                            },
                            "dataSource": {
                                "type": "string",
                                "description": "Datasource name for metrics",
                            },
                            "dataSourceGroup": {
                                "type": "string",
                                "description": "Datasource group name (optional)",
                            },
                            "instances": {
                                "type": "array",
                                "description": "Instance data with datapoints",
                            },
                        },
                        "required": ["resourceIds", "dataSource"],
                    },
                },
                "required": ["metrics"],
            },
        ),
    ]
)

# Correlation and Analysis
TOOLS.extend(
    [
        Tool(
            name="correlate_alerts",
            description=(
                "Correlate alerts by device, datasource, and temporal proximity. "
                "Groups alerts into clusters to identify related issues."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "default": 4,
                        "description": "Hours to look back (default: 4)",
                    },
                    "device": {
                        "type": "string",
                        "description": "Filter by device name (substring match)",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": "Filter by device group ID",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Filter by severity (critical, error, warning, info)",
                        "enum": ["critical", "error", "warning", "info"],
                    },
                    "limit": {
                        "type": "integer",
                        "default": 500,
                        "description": "Max alerts to fetch (default: 500)",
                    },
                },
            },
        ),
        Tool(
            name="get_alert_statistics",
            description=(
                "Aggregate alert counts by severity, device, datasource, and time bucket. "
                "Returns statistical summary over a time window."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back (default: 24)",
                    },
                    "device": {
                        "type": "string",
                        "description": "Filter by device name (substring match)",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": "Filter by device group ID",
                    },
                    "bucket_size_hours": {
                        "type": "integer",
                        "default": 1,
                        "description": "Size of each time bucket in hours (default: 1)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 1000,
                        "description": "Max alerts to fetch (default: 1000)",
                    },
                },
            },
        ),
        Tool(
            name="get_metric_anomalies",
            description=(
                "Detect metric anomalies using z-score analysis. "
                "Identifies data points deviating significantly from the mean."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "datapoints": {
                        "type": "string",
                        "description": "Comma-separated datapoint names (optional, all if omitted)",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back (default: 24)",
                    },
                    "threshold": {
                        "type": "number",
                        "default": 2.0,
                        "description": "Z-score threshold for anomaly detection (default: 2.0)",
                    },
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
            },
        ),
    ]
)

# Baselines
TOOLS.extend(
    [
        Tool(
            name="save_baseline",
            description=(
                "Save a metric baseline from historical data. "
                "Computes mean, min, max, stddev per datapoint and stores "
                "as a session variable for later comparison."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "baseline_name": {
                        "type": "string",
                        "description": "Name for the stored baseline",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours of historical data to use",
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                    "baseline_name",
                ],
            },
        ),
        Tool(
            name="compare_to_baseline",
            description=(
                "Compare current metrics against a stored baseline. "
                "Reports deviation percentage and status (normal, elevated, "
                "reduced, anomalous) per datapoint."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "baseline_name": {
                        "type": "string",
                        "description": "Name of the stored baseline",
                    },
                    "device_id": {
                        "type": "integer",
                        "description": (
                            "Override device ID (uses baseline if omitted)"
                        ),
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": (
                            "Override device-datasource ID"
                        ),
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": (
                            "Override instance ID"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 1,
                        "description": "Hours of recent data to compare",
                    },
                },
                "required": ["baseline_name"],
            },
        ),
    ]
)

# ML/Statistical Analysis
TOOLS.extend(
    [
        Tool(
            name="forecast_metric",
            description=(
                "Forecast when a metric will breach a threshold using linear "
                "regression. Analyzes historical data to predict trend direction "
                "and estimated breach time."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Threshold value that constitutes a breach",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 168,
                        "description": "Hours of historical data for regression",
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                    "threshold",
                ],
            },
        ),
        Tool(
            name="correlate_metrics",
            description=(
                "Compute Pearson correlation between multiple metric series. "
                "Builds an NxN correlation matrix and highlights strong "
                "correlations (|r| > 0.7). Maximum 10 sources."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "device_id": {"type": "integer"},
                                "device_datasource_id": {"type": "integer"},
                                "instance_id": {"type": "integer"},
                                "datapoint": {"type": "string"},
                            },
                            "required": [
                                "device_id",
                                "device_datasource_id",
                                "instance_id",
                                "datapoint",
                            ],
                        },
                        "description": "List of metric sources to correlate",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours of data to analyze",
                    },
                },
                "required": ["sources"],
            },
        ),
        Tool(
            name="detect_change_points",
            description=(
                "Detect regime shifts in metric data using the CUSUM algorithm. "
                "Identifies points where the mean value changes significantly."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours of data to analyze",
                    },
                    "sensitivity": {
                        "type": "number",
                        "default": 1.0,
                        "description": (
                            "Detection sensitivity (lower = more sensitive)"
                        ),
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                ],
            },
        ),
        Tool(
            name="score_alert_noise",
            description=(
                "Score alert noise level using Shannon entropy and flap detection. "
                "Produces a score from 0 (quiet) to 100 (extremely noisy) with "
                "recommendations for tuning."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
                    "device": {
                        "type": "string",
                        "description": "Optional device name filter",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": "Optional device group ID filter",
                    },
                },
            },
        ),
        Tool(
            name="detect_seasonality",
            description=(
                "Detect periodic patterns in metric data using autocorrelation. "
                "Identifies dominant periods (1h, 4h, 12h, 24h, 168h) and "
                "peak activity hours."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 168,
                        "description": "Hours of data to analyze (default 1 week)",
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                ],
            },
        ),
        Tool(
            name="calculate_availability",
            description=(
                "Calculate availability percentage from alert history. "
                "Computes SLA-style uptime metrics, MTTR, and per-device "
                "breakdown from cleared and active alerts."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID filter",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": "Optional device group ID filter",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 720,
                        "description": "Hours to look back (default 30 days)",
                    },
                    "severity_threshold": {
                        "type": "string",
                        "default": "error",
                        "description": (
                            "Minimum severity for downtime "
                            "(critical, error, warning, info)"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="analyze_blast_radius",
            description=(
                "Analyze the blast radius of a device failure using topology "
                "data. Traverses neighbors to identify downstream impact and "
                "scores overall blast radius (0-100)."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID to analyze",
                    },
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "description": "Max traversal depth (1-3)",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="correlate_changes",
            description=(
                "Cross-reference alert spikes with audit/change logs. "
                "Identifies changes that may have triggered alert increases "
                "using configurable correlation windows."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
                    "correlation_window_minutes": {
                        "type": "integer",
                        "default": 30,
                        "description": (
                            "Minutes after a change to look for alert spikes"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="score_device_health",
            description=(
                "Compute a composite health score (0-100) for a device "
                "instance. Uses z-score analysis of latest values against "
                "historical data with configurable weights."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 4,
                        "description": "Hours of historical data for baseline",
                    },
                    "weights": {
                        "type": "object",
                        "description": (
                            "Optional dict of datapoint_name -> weight"
                        ),
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                ],
            },
        ),
        Tool(
            name="classify_trend",
            description=(
                "Classify metric trends as stable, increasing, decreasing, "
                "cyclic, or volatile. Uses linear regression slope, coefficient "
                "of variation, and autocorrelation."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted)"
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours of data to analyze",
                    },
                },
                "required": [
                    "device_id",
                    "device_datasource_id",
                    "instance_id",
                ],
            },
        ),
    ]
)

# Session Management
TOOLS.extend(
    [
        Tool(
            name="get_session_context",
            description="Get current session context (last results, variables, history)",
            annotations=_SESSION_READ,
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="set_session_variable",
            description="Set a user-defined session variable for use across tool calls",
            annotations=_SESSION_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name"},
                    "value": {
                        "description": "Variable value (string, number, boolean, array, or object)",
                    },
                },
                "required": ["name", "value"],
            },
        ),
        Tool(
            name="get_session_variable",
            description="Get a user-defined session variable",
            annotations=_SESSION_READ,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name to retrieve"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="delete_session_variable",
            description="Delete a user-defined session variable",
            annotations=_SESSION_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name to delete"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="clear_session_context",
            description="Clear all session context (last results, variables, and history)",
            annotations=_SESSION_WRITE,
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_session_history",
            description="List recent tool call history",
            annotations=_SESSION_READ,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum entries to return (max 50)",
                    },
                },
            },
        ),
    ]
)


# Map tool names to their handler functions
def get_tool_handler(tool_name: str) -> Any:
    """Get the handler function for a tool.

    Args:
        tool_name: Name of the tool.

    Returns:
        The async handler function for the tool.

    Raises:
        ValueError: If tool not found.
    """
    from lm_mcp.tools import (
        access_groups,
        alert_rules,
        alerts,
        api_tokens,
        audit,
        baselines,
        batchjobs,
        collectors,
        configsources,
        correlation,
        cost,
        dashboard_groups,
        dashboards,
        datasources,
        devices,
        escalations,
        event_correlation,
        eventsources,
        forecasting,
        imports,
        ingestion,
        logsources,
        metrics,
        netscans,
        oids,
        ops,
        propertysources,
        reports,
        resources,
        scoring,
        sdts,
        services,
        session,
        topology,
        topology_analysis,
        topologysources,
        users,
        websites,
    )

    handlers = {
        # Devices
        "get_devices": devices.get_devices,
        "get_device": devices.get_device,
        "get_device_groups": devices.get_device_groups,
        "create_device": devices.create_device,
        "update_device": devices.update_device,
        "delete_device": devices.delete_device,
        "create_device_group": devices.create_device_group,
        "delete_device_group": devices.delete_device_group,
        # Alerts
        "get_alerts": alerts.get_alerts,
        "get_alert_details": alerts.get_alert_details,
        "acknowledge_alert": alerts.acknowledge_alert,
        "add_alert_note": alerts.add_alert_note,
        "bulk_acknowledge_alerts": alerts.bulk_acknowledge_alerts,
        # SDTs
        "list_sdts": sdts.list_sdts,
        "create_sdt": sdts.create_sdt,
        "delete_sdt": sdts.delete_sdt,
        "bulk_create_device_sdt": sdts.bulk_create_device_sdt,
        "bulk_delete_sdt": sdts.bulk_delete_sdt,
        "get_active_sdts": sdts.get_active_sdts,
        "get_upcoming_sdts": sdts.get_upcoming_sdts,
        # Collectors
        "get_collectors": collectors.get_collectors,
        "get_collector": collectors.get_collector,
        "get_collector_groups": collectors.get_collector_groups,
        "get_collector_group": collectors.get_collector_group,
        # Metrics
        "get_device_datasources": metrics.get_device_datasources,
        "get_device_instances": metrics.get_device_instances,
        "get_device_data": metrics.get_device_data,
        "get_graph_data": metrics.get_graph_data,
        # Dashboards
        "get_dashboards": dashboards.get_dashboards,
        "get_dashboard": dashboards.get_dashboard,
        "get_dashboard_widgets": dashboards.get_dashboard_widgets,
        "get_widget": dashboards.get_widget,
        "create_dashboard": dashboards.create_dashboard,
        "update_dashboard": dashboards.update_dashboard,
        "delete_dashboard": dashboards.delete_dashboard,
        "add_widget": dashboards.add_widget,
        "update_widget": dashboards.update_widget,
        "delete_widget": dashboards.delete_widget,
        # Dashboard Groups
        "get_dashboard_groups": dashboard_groups.get_dashboard_groups,
        "get_dashboard_group": dashboard_groups.get_dashboard_group,
        # Websites
        "get_websites": websites.get_websites,
        "get_website": websites.get_website,
        "get_website_groups": websites.get_website_groups,
        "get_website_data": websites.get_website_data,
        "create_website": websites.create_website,
        "update_website": websites.update_website,
        "delete_website": websites.delete_website,
        "create_website_group": websites.create_website_group,
        "delete_website_group": websites.delete_website_group,
        # Reports
        "get_reports": reports.get_reports,
        "get_report": reports.get_report,
        "get_report_groups": reports.get_report_groups,
        "get_scheduled_reports": reports.get_scheduled_reports,
        "run_report": reports.run_report,
        "create_report": reports.create_report,
        "update_report_schedule": reports.update_report_schedule,
        "delete_report": reports.delete_report,
        # Escalation Chains
        "get_escalation_chains": escalations.get_escalation_chains,
        "get_escalation_chain": escalations.get_escalation_chain,
        "get_recipient_groups": escalations.get_recipient_groups,
        "get_recipient_group": escalations.get_recipient_group,
        "create_escalation_chain": escalations.create_escalation_chain,
        "update_escalation_chain": escalations.update_escalation_chain,
        "delete_escalation_chain": escalations.delete_escalation_chain,
        "create_recipient_group": escalations.create_recipient_group,
        "update_recipient_group": escalations.update_recipient_group,
        "delete_recipient_group": escalations.delete_recipient_group,
        # Alert Rules
        "get_alert_rules": alert_rules.get_alert_rules,
        "get_alert_rule": alert_rules.get_alert_rule,
        "create_alert_rule": alert_rules.create_alert_rule,
        "update_alert_rule": alert_rules.update_alert_rule,
        "delete_alert_rule": alert_rules.delete_alert_rule,
        # Users
        "get_users": users.get_users,
        "get_user": users.get_user,
        "get_roles": users.get_roles,
        "get_role": users.get_role,
        # Access Groups
        "get_access_groups": access_groups.get_access_groups,
        "get_access_group": access_groups.get_access_group,
        # API Tokens
        "get_api_tokens": api_tokens.get_api_tokens,
        "get_api_token": api_tokens.get_api_token,
        # Resources
        "get_device_properties": resources.get_device_properties,
        "get_device_property": resources.get_device_property,
        "update_device_property": resources.update_device_property,
        # Datasources
        "get_datasources": datasources.get_datasources,
        "get_datasource": datasources.get_datasource,
        # ConfigSources
        "get_configsources": configsources.get_configsources,
        "get_configsource": configsources.get_configsource,
        # EventSources
        "get_eventsources": eventsources.get_eventsources,
        "get_eventsource": eventsources.get_eventsource,
        # PropertySources
        "get_propertysources": propertysources.get_propertysources,
        "get_propertysource": propertysources.get_propertysource,
        # TopologySources
        "get_topologysources": topologysources.get_topologysources,
        "get_topologysource": topologysources.get_topologysource,
        # LogSources
        "get_logsources": logsources.get_logsources,
        "get_logsource": logsources.get_logsource,
        "get_device_logsources": logsources.get_device_logsources,
        # Netscans
        "get_netscans": netscans.get_netscans,
        "get_netscan": netscans.get_netscan,
        "run_netscan": netscans.run_netscan,
        # OIDs
        "get_oids": oids.get_oids,
        "get_oid": oids.get_oid,
        # Services
        "get_services": services.get_services,
        "get_service": services.get_service,
        "get_service_groups": services.get_service_groups,
        # Ops Notes
        "get_ops_notes": ops.get_ops_notes,
        "get_ops_note": ops.get_ops_note,
        "add_ops_note": ops.add_ops_note,
        # Audit (ops module has get_audit_logs too, but audit module is more specific)
        "get_audit_logs": audit.get_audit_logs,
        "get_api_token_audit": audit.get_api_token_audit,
        "get_login_audit": audit.get_login_audit,
        "get_change_audit": audit.get_change_audit,
        # Topology
        "get_topology_map": topology.get_topology_map,
        "get_device_neighbors": topology.get_device_neighbors,
        "get_device_interfaces": topology.get_device_interfaces,
        "get_network_flows": topology.get_network_flows,
        "get_device_connections": topology.get_device_connections,
        # Batch Jobs
        "get_batchjobs": batchjobs.get_batchjobs,
        "get_batchjob": batchjobs.get_batchjob,
        "get_batchjob_history": batchjobs.get_batchjob_history,
        "get_device_batchjobs": batchjobs.get_device_batchjobs,
        "get_scheduled_downtime_jobs": batchjobs.get_scheduled_downtime_jobs,
        # Cost
        "get_cost_summary": cost.get_cost_summary,
        "get_resource_cost": cost.get_resource_cost,
        "get_cost_recommendations": cost.get_cost_recommendations,
        "get_idle_resources": cost.get_idle_resources,
        "get_cloud_cost_accounts": cost.get_cloud_cost_accounts,
        "get_cost_recommendation_categories": cost.get_cost_recommendation_categories,
        "get_cost_recommendation": cost.get_cost_recommendation,
        # Imports/Exports
        "export_datasource": imports.export_datasource,
        "export_dashboard": imports.export_dashboard,
        "export_alert_rule": imports.export_alert_rule,
        "export_escalation_chain": imports.export_escalation_chain,
        "export_configsource": imports.export_configsource,
        "export_eventsource": imports.export_eventsource,
        "export_propertysource": imports.export_propertysource,
        "export_logsource": imports.export_logsource,
        "import_datasource": imports.import_datasource,
        "import_configsource": imports.import_configsource,
        "import_eventsource": imports.import_eventsource,
        "import_propertysource": imports.import_propertysource,
        "import_logsource": imports.import_logsource,
        "import_topologysource": imports.import_topologysource,
        "import_jobmonitor": imports.import_jobmonitor,
        "import_appliesto_function": imports.import_appliesto_function,
        # Ingestion
        "ingest_logs": ingestion.ingest_logs,
        "push_metrics": ingestion.push_metrics,
        # Correlation and Analysis
        "correlate_alerts": correlation.correlate_alerts,
        "get_alert_statistics": correlation.get_alert_statistics,
        "get_metric_anomalies": correlation.get_metric_anomalies,
        # Baselines
        "save_baseline": baselines.save_baseline,
        "compare_to_baseline": baselines.compare_to_baseline,
        # ML/Statistical Analysis
        "forecast_metric": forecasting.forecast_metric,
        "correlate_metrics": correlation.correlate_metrics,
        "detect_change_points": forecasting.detect_change_points,
        "score_alert_noise": scoring.score_alert_noise,
        "detect_seasonality": forecasting.detect_seasonality,
        "classify_trend": forecasting.classify_trend,
        "calculate_availability": scoring.calculate_availability,
        "analyze_blast_radius": topology_analysis.analyze_blast_radius,
        "correlate_changes": event_correlation.correlate_changes,
        "score_device_health": scoring.score_device_health,
        # Session
        "get_session_context": session.get_session_context,
        "set_session_variable": session.set_session_variable,
        "get_session_variable": session.get_session_variable,
        "delete_session_variable": session.delete_session_variable,
        "clear_session_context": session.clear_session_context,
        "list_session_history": session.list_session_history,
    }

    if tool_name not in handlers:
        raise ValueError(f"Unknown tool: {tool_name}")

    return handlers[tool_name]
