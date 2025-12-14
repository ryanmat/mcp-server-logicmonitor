# Description: Tool registry for LogicMonitor MCP server.
# Description: Defines all MCP tools with schemas and handlers.

from __future__ import annotations

from typing import Any

from mcp.types import Tool

# Tool definitions organized by category
TOOLS: list[Tool] = []

# Devices
TOOLS.extend(
    [
        Tool(
            name="get_devices",
            description="List devices from LogicMonitor with optional filtering",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Filter by device group ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by device name (supports wildcards)",
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
            description="Get detailed information about a specific device",
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
            description="List device groups from LogicMonitor",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "integer", "description": "Filter by parent group ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (wildcards)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="create_device",
            description="Create a new device (requires write permission)",
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
            description="Update an existing device (requires write permission)",
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
            description="Delete a device (requires write permission). Uses soft delete by default.",
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
            description="Create a new device group (requires write permission)",
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
            description="Delete a device group (requires write permission). Shows impact.",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="create_sdt",
            description="Create a scheduled downtime (requires write permission)",
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
            description="Create SDT for multiple devices (max 100, requires write permission)",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_collector",
            description="Get detailed information about a specific collector",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_collector_group",
            description="Get details about a specific collector group",
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
            description="Get datasources applied to a device",
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
            description="Get instances of a datasource on a device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
                "required": ["device_id", "datasource_id"],
            },
        ),
        Tool(
            name="get_device_data",
            description="Get metric data for a device datasource instance",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "datapoint": {"type": "string", "description": "Specific datapoint name"},
                    "period": {
                        "type": "number",
                        "default": 1,
                        "description": "Time period in hours",
                    },
                },
                "required": ["device_id", "datasource_id", "instance_id"],
            },
        ),
        Tool(
            name="get_graph_data",
            description="Get graph image data for visualization",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "graph_id": {"type": "integer", "description": "Graph ID"},
                    "period": {
                        "type": "number",
                        "default": 24,
                        "description": "Time period in hours",
                    },
                },
                "required": ["device_id", "datasource_id", "instance_id", "graph_id"],
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "group_id": {"type": "integer", "description": "Filter by group ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_dashboard",
            description="Get detailed information about a specific dashboard",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_id": {"type": "integer", "description": "Filter by parent group ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_dashboard_group",
            description="Get details about a specific dashboard group",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_website",
            description="Get detailed information about a specific website",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "website_id": {"type": "integer", "description": "Website ID"},
                    "checkpoint_id": {"type": "integer", "description": "Checkpoint ID"},
                    "period": {
                        "type": "number",
                        "default": 1,
                        "description": "Time period in hours",
                    },
                },
                "required": ["website_id"],
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "group_id": {"type": "integer", "description": "Filter by group ID"},
                    "report_type": {"type": "string", "description": "Filter by type"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_report",
            description="Get detailed information about a specific report",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_scheduled_reports",
            description="Get reports with schedules configured",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID"},
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
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_user",
            description="Get details about a specific user",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_role",
            description="Get details about a specific role",
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
            description="Get all properties of a device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "property_type": {
                        "type": "string",
                        "enum": ["custom", "system", "auto", "inherit"],
                        "description": "Filter by property type",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_property",
            description="Get a specific property of a device",
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
            description="Update or create a device property (requires write permission)",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_datasource",
            description="Get details about a specific datasource",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_configsource",
            description="Get details about a specific ConfigSource",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_eventsource",
            description="Get details about a specific EventSource",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_propertysource",
            description="Get details about a specific PropertySource",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_topologysource",
            description="Get details about a specific TopologySource",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_logsource",
            description="Get details about a specific LogSource",
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
            description="Get LogSources applied to a device",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {"type": "string", "description": "Filter by name (wildcards)"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_oid",
            description="Get details about a specific OID",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "Note text"},
                    "scope": {"type": "string", "default": "global", "description": "Note scope"},
                    "scope_id": {"type": "integer", "description": "Scope ID (device/group ID)"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"},
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
            inputSchema={
                "type": "object",
                "properties": {
                    "username_filter": {"type": "string", "description": "Filter by username"},
                    "action_filter": {"type": "string", "description": "Filter by action type"},
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_api_token_audit",
            description="Get API token usage audit logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_login_audit",
            description="Get login/authentication audit logs",
            inputSchema={
                "type": "object",
                "properties": {
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
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_change_audit",
            description="Get configuration change audit logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {"type": "string", "description": "Filter by resource type"},
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Hours to look back",
                    },
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
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Center device ID"},
                    "group_id": {"type": "integer", "description": "Filter by group ID"},
                    "algorithm": {
                        "type": "string",
                        "default": "IP_ADDRESS",
                        "description": "Layout algorithm",
                    },
                },
            },
        ),
        Tool(
            name="get_device_neighbors",
            description="Get neighboring devices based on topology",
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
            description="Get network interfaces for a device",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "period_hours": {
                        "type": "integer",
                        "default": 1,
                        "description": "Time period in hours",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_connections",
            description="Get device relationships/connections",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "Batch job ID"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="get_batchjob_history",
            description="Get execution history for a batch job",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "Batch job ID"},
                    "limit": {"type": "integer", "default": 20, "description": "Max results"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="get_device_batchjobs",
            description="Get batch jobs for a specific device",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "default": "month",
                        "description": "Time period (day, week, month)",
                    },
                },
            },
        ),
        Tool(
            name="get_resource_cost",
            description="Get cost data for a specific resource",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {"type": "integer", "description": "Resource ID"},
                    "period": {"type": "string", "default": "month", "description": "Time period"},
                },
                "required": ["resource_id"],
            },
        ),
        Tool(
            name="get_cost_recommendations",
            description="Get cost optimization recommendations",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_idle_resources",
            description="Get idle/underutilized resources",
            inputSchema={
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "default": 10,
                        "description": "Utilization threshold (%)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_cloud_cost_accounts",
            description="Get cloud accounts with cost data",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
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
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Alert rule ID"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="export_escalation_chain",
            description="Export an escalation chain definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Escalation chain ID"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="export_configsource",
            description="Export a ConfigSource definition",
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
            inputSchema={
                "type": "object",
                "properties": {
                    "logsource_id": {"type": "integer", "description": "LogSource ID"},
                },
                "required": ["logsource_id"],
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
        batchjobs,
        collectors,
        configsources,
        cost,
        dashboard_groups,
        dashboards,
        datasources,
        devices,
        escalations,
        eventsources,
        imports,
        logsources,
        metrics,
        netscans,
        oids,
        ops,
        propertysources,
        reports,
        resources,
        sdts,
        services,
        topology,
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
        # Alert Rules
        "get_alert_rules": alert_rules.get_alert_rules,
        "get_alert_rule": alert_rules.get_alert_rule,
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
        # Imports/Exports
        "export_datasource": imports.export_datasource,
        "export_dashboard": imports.export_dashboard,
        "export_alert_rule": imports.export_alert_rule,
        "export_escalation_chain": imports.export_escalation_chain,
        "export_configsource": imports.export_configsource,
        "export_eventsource": imports.export_eventsource,
        "export_propertysource": imports.export_propertysource,
        "export_logsource": imports.export_logsource,
    }

    if tool_name not in handlers:
        raise ValueError(f"Unknown tool: {tool_name}")

    return handlers[tool_name]
