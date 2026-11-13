# Description: Tool registry for LogicMonitor MCP server.
# Description: Defines all MCP tools with schemas and handlers.

from __future__ import annotations

from typing import Any

from mcp.types import Tool, ToolAnnotations

from lm_mcp.resources.guides import TOOL_CATEGORIES
from lm_mcp.tools import (
    analyze_alerts,
    analyze_metric,
    correlation,
    scoring,
    topology_analysis,
    workflows,
)
from lm_mcp.tools.terraform_imports import IMPORTABLE_TYPES

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
# A tool that runs a script which changes a monitored host, such as a remediation.
_DESTRUCTIVE_RUN = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True
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

# Shape of LM ids passed as strings (SDT and ops note ids carry letters and
# underscores), so a client refuses path characters before the call is made.
_LM_STRING_ID_PATTERN = "^[A-Za-z0-9_-]+$"

# Shape of a name sent as one URL path segment (an uploaded log file, a property): no
# '/', '?' or '#', and no leading dot. Property names holding '/' (Kubernetes labels) are
# refused here, as the portal answers 404 to them on a path and 400 to them encoded.
_PATH_SEGMENT_NAME_PATTERN = "^[A-Za-z0-9_][A-Za-z0-9._-]*$"

# Tool definitions organized by category
TOOLS: list[Tool] = []

# Devices
TOOLS.extend(
    [
        Tool(
            name="get_devices",
            description=(
                "List devices (resources) from LogicMonitor, optionally filtered by name, "
                "hostname, status or device group"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Filter by device group ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by display name (substring match)",
                    },
                    "hostname_filter": {
                        "type": "string",
                        "description": "Filter by hostname or IP address (substring match)",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["normal", "dead", "dead-collector", "unmonitored", "disabled"],
                        "description": "Filter by device status",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Raw filter expression (overrides other filters). "
                        "Syntax: field:value, field~value. String values must be quoted: "
                        'displayName~"server". Custom property queries use dot-notation: '
                        'customProperties.name:"env",customProperties.value:"prod"',
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_device_group",
            description=(
                "Get detailed information about a specific device/resource group,"
                " including appliesTo expression and parent ID"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Device group ID"},
                },
                "required": ["group_id"],
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
            description="Update an existing device/resource (requires write permission). "
            "Custom properties are merged with existing properties (not replaced).",
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
            name="recover_device",
            description=(
                "Recover a soft-deleted device/resource (requires write permission)."
                " Only works within the recovery window."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID to recover"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="run_auto_discovery",
            description=(
                "Run Active Discovery on a device/resource now, so its collector looks for "
                "the device's instances (requires write permission). The portal answers at "
                "once; the discovery runs on the collector afterwards."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_delta",
            description=(
                "List devices/resources through the device delta, to follow what changed. "
                "Without delta_id it lists the devices whose display name contains "
                "name_filter, or every device, and returns a delta_id; each such read starts "
                "a new delta, so keep the first page's. With delta_id it lists the devices "
                "changed since that delta started (change says how), every change since then "
                "on each read. name_filter is refused there, since the portal answered a "
                "filtered read with an empty page that left out a changed device."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "delta_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "The delta_id an earlier read returned",
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by display name (substring), without delta_id",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_unmonitored_devices",
            description=(
                "List the portal's unmonitored devices/resources, found by a NetScan and not "
                "monitored, rows as the API returns them."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="bulk_delete_devices",
            description=(
                "Delete multiple devices/resources in one operation"
                " (max 100, requires write permission). Soft delete by default."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Device IDs to delete (max 100)",
                    },
                    "delete_hard": {
                        "type": "boolean",
                        "default": False,
                        "description": "Permanently delete (default: soft delete)",
                    },
                },
                "required": ["device_ids"],
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
            name="update_device_group",
            description=(
                "Update a device/resource group (requires write permission)."
                " Custom properties are merged with existing."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Device group ID to update"},
                    "name": {"type": "string", "description": "New group name"},
                    "description": {"type": "string", "description": "New group description"},
                    "applies_to": {
                        "type": "string",
                        "description": "New AppliesTo expression for dynamic membership",
                    },
                    "parent_id": {
                        "type": "integer",
                        "description": "New parent group ID (moves the group)",
                    },
                    "disable_alerting": {
                        "type": "boolean",
                        "description": "Disable alerting for all devices in this group",
                    },
                    "custom_properties": {
                        "type": "object",
                        "description": "Custom properties to set/update (merged with existing)",
                    },
                },
                "required": ["group_id"],
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
            description=(
                "Get open or cleared alerts from LogicMonitor, optionally filtered by "
                "severity (critical, error, warning), device, group, datasource or time"
                "\n\nFor Kubernetes clusters, use group_id (from "
                "get_device_groups) instead of device; the device name "
                "filter does not work reliably for K8s resources."
                "\n\nCommon mistakes: startEpoch/endEpoch use SECONDS not "
                "milliseconds. String filter values need double quotes "
                '(e.g., monitorObjectName:"hostname").'
            ),
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
                    "group_id": {
                        "type": "integer",
                        "description": "Filter by device group ID (matches all devices)",
                    },
                    "device_id": {
                        "type": "integer",
                        "description": "Read this device's own alert list; every other "
                        "filter applies there except group_id, which is refused beside it",
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
                    "include_message": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include the full alert message body (needMessage)",
                    },
                },
                "required": ["alert_id"],
            },
        ),
        Tool(
            name="acknowledge_alert",
            description=(
                "Acknowledge an alert (requires write permission)"
                "\n\nCommon mistakes: alert_id works with or without "
                "the LMA prefix."
            ),
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
            name="escalate_alert",
            description=(
                "Escalate an alert along its escalation chain (requires write permission). "
                "The portal refuses an acknowledged alert, and its answer carries no detail, "
                "so the result does not say who was notified."
                "\n\nCommon mistakes: alert_id works with or without the LMA prefix."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "Alert ID (with or without LMA prefix)",
                    },
                },
                "required": ["alert_id"],
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
            name="get_sdts",
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="create_sdt",
            description=(
                "Create a scheduled downtime (requires write permission)"
                "\n\nCommon mistakes: duration_minutes is MINUTES not "
                "hours/seconds. DeviceSDT needs device_id, "
                "DeviceGroupSDT needs device_group_id. "
                "DeviceDataSourceSDT needs device_id + datasource_id. "
                "Cloud resources (collector_id=-2) may not support DeviceSDT; "
                "use DeviceGroupSDT on their parent group instead."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "sdt_type": {
                        "type": "string",
                        "enum": [
                            "DeviceSDT",
                            "DeviceGroupSDT",
                            "DeviceDataSourceSDT",
                            "DeviceDataSourceInstanceSDT",
                            "DeviceDataSourceInstanceGroupSDT",
                            "DeviceBatchJobSDT",
                            "DeviceClusterAlertDefSDT",
                            "DeviceEventSourceSDT",
                            "ServiceSDT",
                            "ServiceGroupSDT",
                            "WebsiteSDT",
                            "WebsiteGroupSDT",
                            "CollectorSDT",
                        ],
                        "description": "SDT type",
                    },
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID (for Device* SDT types)",
                    },
                    "device_group_id": {
                        "type": "integer",
                        "description": "Device group ID (for DeviceGroupSDT)",
                    },
                    "datasource_id": {
                        "type": "integer",
                        "description": "Datasource ID (for DeviceDataSourceSDT)",
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
                    "sdt_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "SDT ID to delete",
                    },
                },
                "required": ["sdt_id"],
            },
        ),
        Tool(
            name="update_sdt",
            description=(
                "Update a scheduled downtime (requires write permission)."
                " Uses fetch-modify-PUT to preserve unmodified fields."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "sdt_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "SDT ID to update",
                    },
                    "end_date_time": {
                        "type": "integer",
                        "description": "New end time in epoch milliseconds",
                    },
                    "start_date_time": {
                        "type": "integer",
                        "description": "New start time in epoch milliseconds",
                    },
                    "comment": {"type": "string", "description": "New SDT comment"},
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
        Tool(
            name="get_collector_events",
            description=(
                "List one collector's events, newest first: agent and sbproxy restarts, "
                "credential rotation, and reports that the collector is unreachable, each with "
                "its time and build. Use it for a collector's recent history; "
                "get_collector_health gives its current state."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="get_collector_log_files",
            description=(
                "List the log files a collector has uploaded to the portal, as zip files with "
                "their size and upload time. A collector uploads them through Send Logs to "
                "LogicMonitor in the portal or the !uploadlog debug command, so an empty list "
                "means nothing was uploaded. Read one with get_collector_log_file."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="get_collector_log_file",
            description=(
                "Read one uploaded collector log file, named as get_collector_log_files lists "
                "it, and return the end of its text: at most max_bytes bytes, starting on a "
                "whole line. truncated says whether earlier lines were left out."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                    "file_name": {
                        "type": "string",
                        "pattern": _PATH_SEGMENT_NAME_PATTERN,
                        "description": "Log file name, such as 82.postcheck.log.zip",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "default": 20000,
                        "minimum": 1,
                        "maximum": 200000,
                        "description": "Most bytes of the log's end to return",
                    },
                },
                "required": ["collector_id", "file_name"],
            },
        ),
        Tool(
            name="get_collector_upgrade_history",
            description=(
                "List the portal's collector version upgrades a page at a time (limit, offset), "
                "each row as the API returns it."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="update_collector",
            description=(
                "Update a collector (requires write permission)."
                " Change group, description, failback, or escalation chain."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID to update"},
                    "description": {"type": "string", "description": "New description"},
                    "collector_group_id": {
                        "type": "integer",
                        "description": "New collector group ID",
                    },
                    "enable_failback": {
                        "type": "boolean",
                        "description": "Enable automatic failback",
                    },
                    "escalation_chain_id": {
                        "type": "integer",
                        "description": "Escalation chain ID for collector down alerts",
                    },
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="run_collector_status_check",
            description=(
                "Trigger a collector status check (requires write permission) and wait up to "
                "45 seconds for its result: script counts and the checks that are not OK. An "
                "unreachable collector refuses the trigger. A check still running after the wait "
                "returns finished false; get_collector_health with the collector_id reads it "
                "later."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="restart_collector",
            description=(
                "Restart a collector (requires write permission). It sends the collector's own "
                "size and config files back with the restart, so neither changes, and returns "
                "the async job id of the restart and the size it kept."
            ),
            annotations=_DESTRUCTIVE_RUN,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="acknowledge_collector_down",
            description=(
                "Acknowledge a down collector's alert with a comment (requires write "
                "permission). The portal refuses it for a collector that is up."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID"},
                    "comment": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Acknowledgement comment",
                    },
                },
                "required": ["collector_id", "comment"],
            },
        ),
        Tool(
            name="delete_collector",
            description=(
                "Delete a collector (requires write permission)."
                " Blocks if devices are still assigned."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {"type": "integer", "description": "Collector ID to delete"},
                },
                "required": ["collector_id"],
            },
        ),
        Tool(
            name="create_collector_group",
            description="Create a collector group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Group name"},
                    "description": {"type": "string", "description": "Description"},
                    "auto_balance": {
                        "type": "boolean",
                        "description": "Enable auto-balancing",
                    },
                    "auto_balance_strategy": {
                        "type": "string",
                        "description": "Auto-balance strategy (e.g., roundRobin)",
                    },
                    "custom_properties": {
                        "type": "object",
                        "description": "Custom properties as key-value pairs",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="update_collector_group",
            description="Update a collector group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Collector group ID to update",
                    },
                    "name": {"type": "string", "description": "New group name"},
                    "description": {"type": "string", "description": "New description"},
                    "auto_balance": {
                        "type": "boolean",
                        "description": "Enable/disable auto-balancing",
                    },
                    "auto_balance_strategy": {
                        "type": "string",
                        "description": "New auto-balance strategy",
                    },
                    "custom_properties": {
                        "type": "object",
                        "description": "Custom properties to merge",
                    },
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="delete_collector_group",
            description=(
                "Delete a collector group (requires write permission)."
                " Blocks if collectors are still assigned."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Collector group ID to delete",
                    },
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
            description=(
                "Get datasources applied to a device (resource)"
                "\n\nCommon mistakes: Returns device-datasource associations "
                "not definitions. The ID returned here is device_datasource_id "
                "for use with get_device_data."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by DataSource name (substring match)",
                    },
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by instance name (substring match)",
                    },
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["device_id", "device_datasource_id"],
            },
        ),
        Tool(
            name="add_device_instance",
            description=(
                "Add a monitored instance to a datasource on a device"
                " (requires write permission)."
                " Used for datasources without Active Discovery"
                " (e.g. ServiceStatus)."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID (from get_device_datasources)",
                    },
                    "display_name": {
                        "type": "string",
                        "description": "Display name for the instance",
                    },
                    "wild_value": {
                        "type": "string",
                        "description": (
                            "Wildcard value used by the datasource"
                            " to query this instance"
                            " (e.g. 'nginx.service' for"
                            " ServiceStatus, a port number"
                            " for Port-)"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional instance description",
                    },
                },
                "required": ["device_id", "device_datasource_id", "display_name", "wild_value"],
            },
        ),
        Tool(
            name="update_device_instance",
            description="Update a monitored instance on a device (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID to update"},
                    "display_name": {"type": "string", "description": "New display name"},
                    "description": {"type": "string", "description": "New description"},
                    "stop_monitoring": {
                        "type": "boolean",
                        "description": "Stop or resume monitoring for this instance",
                    },
                    "disable_alerting": {
                        "type": "boolean",
                        "description": "Disable or enable alerting for this instance",
                    },
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
            },
        ),
        Tool(
            name="delete_device_instance",
            description=(
                "Delete a monitored instance from a datasource"
                " on a device (requires write permission)"
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID to delete"},
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
            },
        ),
        Tool(
            name="get_device_data",
            description=(
                "Get the raw metric values (samples) of a device/resource datasource "
                "instance, such as CPU, memory or disk usage"
                "\n\nCommon mistakes: Returns the last hour unless start_time or "
                "end_time is given. Requires device_datasource_id "
                "(from get_device_datasources) not the datasource definition ID."
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return the REST object with its widgets under "
                        "widgets_full, the template create_dashboard clones, instead of the "
                        "object with its portal link",
                    },
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
                    "limit": {"type": "integer", "default": 100, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
            description="Create a dashboard, optionally from template (requires write permission)",
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
                    "widget_tokens": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Widget token overrides "
                        '(e.g., [{"name": "##host##", "value": "server1"}])',
                    },
                    "template": {
                        "type": "object",
                        "description": "Full dashboard definition to clone from "
                        "(from get_dashboard with raw=true). Name is overridden, id is stripped.",
                    },
                    "template_path": {
                        "type": "string",
                        "description": "Path to a local JSON file holding the dashboard "
                        "definition, or a 4.3.0 export_dashboard envelope; loaded by reference so "
                        "a large definition stays out of context. Ignored if template is set.",
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
            description="Add a widget to a dashboard (requires write permission). "
            "For text widgets: use 'content' (not 'html') as the config key. "
            "For bigNumber widgets: dataPoints need 'name' field, include "
            "'bigNumberItems' array, colorThresholds use 'relation'/'threshold', "
            "aggregateFunction is lowercase (e.g., 'average'). "
            "For cgraph widgets: deviceDisplayName/deviceGroupFullPath/instanceName "
            "must be GlobMatchToggle objects {'value': '...', 'isGlob': true}, "
            "dataPoints need 'display' object, graphInfo needs 'aggregate': false "
            "when using topX. "
            "For deviceSLA widgets: required config fields are 'groupName' "
            "(not deviceGroupFullPath), 'deviceName', 'dataSourceFullName', "
            "'metric', 'threshold'. Also required: 'daysInWeek' (e.g., "
            "'1,2,3,4,5,6,7'), 'periodInOneDay' (e.g., '0:00-23:59'), "
            "'displayType' (0=availability, 1=timeline), 'calculationMethod' "
            "(0=percent, 1=actual), 'unmonitoredTimeAlertStatus' (0=ignore, "
            "1=warning, 2=error, 3=critical).",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer", "description": "Dashboard ID"},
                    "name": {"type": "string", "description": "Widget name"},
                    "widget_type": {
                        "type": "string",
                        "description": "Widget type (cgraph, sgraph, bigNumber, text, "
                        "html, alert, noc, gauge, pieChart, table, advancedmetrics for a "
                        "PromQL query, etc.)",
                    },
                    "column_index": {
                        "type": "integer",
                        "description": "Start column, 1-12. Omit to let the portal "
                        "auto-place the widget below existing widgets.",
                    },
                    "row": {
                        "type": "integer",
                        "description": "Start row. Omit to append below existing widgets.",
                    },
                    "row_span": {
                        "type": "integer",
                        "description": "Height in rows (default 1 when a position is set).",
                    },
                    "col_span": {
                        "type": "integer",
                        "description": "Width in columns, 1-12 (default 6 when a position is set).",
                    },
                    "description": {"type": "string", "description": "Widget description"},
                    "config": {
                        "type": "object",
                        "description": "Widget configuration (type-specific). "
                        "Merged into the request payload.",
                    },
                    "otlp_query": {
                        "type": "string",
                        "description": "PromQL query over native OTLP metrics; advancedmetrics "
                        "widgets only. Sets advancedMetricsGraphInfo queryType otlp and the "
                        "query; the portal fills in the line chart and the rest",
                    },
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
                    "column_index": {"type": "integer", "description": "New start column (1-12)"},
                    "row": {"type": "integer", "description": "New start row"},
                    "row_span": {"type": "integer", "description": "New height in rows"},
                    "col_span": {"type": "integer", "description": "New width in columns (1-12)"},
                    "config": {"type": "object", "description": "New configuration"},
                    "otlp_query": {
                        "type": "string",
                        "description": "New PromQL query of an advancedmetrics widget; other "
                        "widget types refuse it",
                    },
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
        Tool(
            name="create_dashboard_group",
            description="Create a dashboard group in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the dashboard group"},
                    "parent_id": {
                        "type": "integer",
                        "description": "Parent group ID (optional)",
                    },
                    "description": {"type": "string", "description": "Optional description"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="delete_dashboard_group",
            description="Delete a dashboard group from LogicMonitor (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Dashboard group ID to delete",
                    },
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="update_dashboard_group",
            description="Update a dashboard group (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Dashboard group ID to update",
                    },
                    "name": {"type": "string", "description": "New group name"},
                    "description": {"type": "string", "description": "New description"},
                    "parent_id": {
                        "type": "integer",
                        "description": "New parent group ID",
                    },
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (substring match)",
                    },
                    "parent_id": {"type": "integer", "description": "Filter by parent group ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_website_checkpoints",
            description=(
                "List the portal's website checkpoint locations, the places website checks "
                "run from; each id is the smg_id a website's checkpoints carry in get_website."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                "required": ["website_id", "checkpoint_id"],
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
                    "include_nextgen": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include NextGen reports",
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "include_nextgen": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include NextGen reports",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
            name="get_report_execution",
            description=(
                "Poll the status of a report generation task started by run_report "
                "(returns status and result URL when finished)"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer", "description": "Report ID"},
                    "task_id": {
                        "type": "integer",
                        "description": "Task ID returned by run_report",
                    },
                },
                "required": ["report_id", "task_id"],
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
                    "schedule_cron": {
                        "type": "string",
                        "description": "Cron expression to schedule generation "
                        "(omit for on-demand only)",
                    },
                    "schedule_timezone": {
                        "type": "string",
                        "description": "Schedule timezone (e.g. America/Los_Angeles)",
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
                    "enabled": {
                        "type": "boolean",
                        "description": "Pass false to clear (disable) the schedule",
                    },
                    "cron": {"type": "string", "description": "Cron expression, e.g. 0 8 * * 1"},
                    "timezone": {
                        "type": "string",
                        "description": "Schedule timezone -> scheduleTimezone",
                    },
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by chain name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return the full REST object (every field the API returns) "
                        "instead of the summary",
                    },
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (supports wildcards)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                    "detail": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, fetch each group's full recipient list via an extra"
                            " GET per group. Off by default to avoid N+1 API calls."
                        ),
                    },
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
                    "destinations": {
                        "type": "array",
                        "description": (
                            "List of Chain objects. Each Chain has type ('single' or"
                            " 'timebased'), optional period object (null for 'single'),"
                            " and stages (list of stage arrays; each stage is a list of"
                            " Recipient objects). To route to an LM Integration, use a"
                            " Recipient with type='admin', addr=<username>, and"
                            " method=<integration display name>. Lowercase 'admin'."
                            " Shorthand {type: 'integration', integration_name: ...,"
                            " admin: ...} is rewritten to the canonical admin+method"
                            " form before the request hits the API."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["single", "timebased"],
                                },
                                "period": {"type": ["object", "null"]},
                                "stages": {
                                    "type": "array",
                                    "description": (
                                        "List of stage arrays; each stage is a list"
                                        " of Recipient objects {type, addr, method,"
                                        " contact}."
                                    ),
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    },
                                },
                            },
                            "required": ["type", "stages"],
                        },
                        "examples": [
                            [
                                {
                                    "type": "single",
                                    "period": None,
                                    "stages": [
                                        [
                                            {
                                                "type": "admin",
                                                "addr": "rmatuszewski",
                                                "method": ("Azure Sentinel Pipeline (POC)"),
                                            }
                                        ]
                                    ],
                                }
                            ]
                        ],
                    },
                    "cc_destinations": {
                        "type": "array",
                        "description": (
                            "CC Recipient list. Each entry is a Recipient {type, addr,"
                            " method, contact}. Applied to every stage."
                        ),
                        "items": {"type": "object"},
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
                    "throttling_period": {
                        "type": "integer",
                        "description": "Updated throttling period in minutes",
                    },
                    "throttling_alerts": {
                        "type": "integer",
                        "description": "Updated number of alerts before throttling",
                    },
                    "destinations": {
                        "type": "array",
                        "description": (
                            "Updated list of Chain objects. Same shape as on create:"
                            " {type, period, stages}. See create_escalation_chain for"
                            " the full Recipient shape and integration-routing form."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["single", "timebased"],
                                },
                                "period": {"type": ["object", "null"]},
                                "stages": {
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "object"},
                                    },
                                },
                            },
                            "required": ["type", "stages"],
                        },
                    },
                    "cc_destinations": {
                        "type": "array",
                        "description": "Updated CC Recipient list.",
                        "items": {"type": "object"},
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
                    "name": {
                        "type": "string",
                        "description": (
                            "Name of the recipient group. Sent as groupName to the LM v3 API."
                        ),
                    },
                    "description": {"type": "string", "description": "Optional description"},
                    "recipients": {
                        "type": "array",
                        "description": (
                            "Optional initial recipients. Each entry is a Recipient"
                            " {type, method, addr, contact}. ``type`` and ``method``"
                            " are required by the LM API."
                        ),
                        "items": {"type": "object"},
                        "examples": [
                            [
                                {
                                    "type": "admin",
                                    "method": "email",
                                    "addr": "oncall@example.com",
                                }
                            ]
                        ],
                    },
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
                    "name": {
                        "type": "string",
                        "description": ("Updated name. Sent as groupName to the LM v3 API."),
                    },
                    "description": {"type": "string", "description": "Updated description"},
                    "recipients": {
                        "type": "array",
                        "description": (
                            "Replacement recipient list. When provided, LM replaces"
                            " the group's current recipient set with this list."
                        ),
                        "items": {"type": "object"},
                    },
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

# Integrations (Custom HTTP Delivery)
TOOLS.extend(
    [
        Tool(
            name="get_integrations",
            description=(
                "List LogicMonitor integrations (Custom HTTP Delivery, Slack,"
                " PagerDuty, etc.). Returns a short summary per integration."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by integration name (supports wildcards).",
                    },
                    "type_filter": {
                        "type": "string",
                        "description": (
                            "Exact-match filter on the integration type, e.g."
                            " 'http' for Custom HTTP Delivery, 'slack-2',"
                            " 'pagerduty'. Wildcards are not supported for"
                            " type."
                        ),
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_integration",
            description=(
                "Get a specific integration's full definition. Field set"
                " depends on integration type; password/OAuth secret"
                " fields are masked."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "integration_id": {
                        "type": "integer",
                        "description": "Integration ID",
                    },
                },
                "required": ["integration_id"],
            },
        ),
        Tool(
            name="create_http_integration",
            description=(
                "Create a Custom HTTP Delivery integration (type=http)."
                " Required fields: name, url. Use extra_fields for"
                " OAuth, actionNotes*, updateData*, or the 'extra' UI"
                " metadata blob. (requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Integration display name"},
                    "url": {
                        "type": "string",
                        "description": "Webhook URL for the active alert lifecycle",
                    },
                    "description": {"type": "string", "description": "Optional description"},
                    "http_method": {
                        "type": "string",
                        "default": "post",
                        "description": "HTTP verb for active alert posts",
                    },
                    "headers": {
                        "type": ["object", "array"],
                        "description": (
                            "Headers for active alerts. Accepts a plain"
                            " {name: value} dict or a list of {HeaderName:"
                            " value} single-key dicts (LM's native form)."
                        ),
                        "examples": [
                            {"Authorization": "Bearer ...", "Content-Type": "application/json"}
                        ],
                    },
                    "alert_body": {
                        "type": "string",
                        "description": (
                            "Payload template. Supports LM ##TOKEN## substitutions"
                            " such as ##ALERTID##, ##LEVEL##, ##HOST##."
                        ),
                    },
                    "alert_body_format": {
                        "type": "string",
                        "default": "json",
                        "description": "Payload format (json or form).",
                    },
                    "alert_data_type": {
                        "type": "string",
                        "description": "LM alert data type, typically 'raw' or 'formatted'.",
                    },
                    "username": {"type": "string", "description": "Basic-auth username"},
                    "password": {"type": "string", "description": "Basic-auth password"},
                    "enabled_lifecycles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Subset of ['active', 'ack', 'clear', 'update',"
                            " 'actionNotes', 'updateData']. Defaults to the"
                            " four core lifecycles."
                        ),
                    },
                    "ack_url": {"type": "string", "description": "Override URL for ack"},
                    "ack_method": {"type": "string", "description": "Override HTTP verb for ack"},
                    "ack_body": {"type": "string", "description": "Override payload for ack"},
                    "ack_headers": {
                        "type": ["object", "array"],
                        "description": "Override headers for ack (same shape as headers).",
                    },
                    "clear_url": {"type": "string", "description": "Override URL for clear"},
                    "clear_method": {"type": "string"},
                    "clear_body": {"type": "string"},
                    "clear_headers": {"type": ["object", "array"]},
                    "update_url": {"type": "string", "description": "Override URL for update"},
                    "update_method": {"type": "string"},
                    "update_body": {"type": "string"},
                    "update_headers": {"type": ["object", "array"]},
                    "extra_fields": {
                        "type": "object",
                        "description": (
                            "Raw LM integration fields merged last. Use for"
                            " OAuth credentials (oAuthClientId, etc.),"
                            " updateData*, actionNotes*, and the 'extra'"
                            " UI metadata string."
                        ),
                    },
                },
                "required": ["name", "url"],
            },
        ),
        Tool(
            name="update_http_integration",
            description=(
                "Update a Custom HTTP Delivery integration via PATCH. Only"
                " fields explicitly provided are sent; omitted fields keep"
                " their current server values. (requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "integration_id": {
                        "type": "integer",
                        "description": "Integration ID",
                    },
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "url": {"type": "string"},
                    "http_method": {"type": "string"},
                    "headers": {"type": ["object", "array"]},
                    "alert_body": {"type": "string"},
                    "alert_body_format": {"type": "string"},
                    "alert_data_type": {"type": "string"},
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                    "enabled_lifecycles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "ack_url": {"type": "string"},
                    "ack_method": {"type": "string"},
                    "ack_body": {"type": "string"},
                    "ack_headers": {"type": ["object", "array"]},
                    "clear_url": {"type": "string"},
                    "clear_method": {"type": "string"},
                    "clear_body": {"type": "string"},
                    "clear_headers": {"type": ["object", "array"]},
                    "update_url": {"type": "string"},
                    "update_method": {"type": "string"},
                    "update_body": {"type": "string"},
                    "update_headers": {"type": ["object", "array"]},
                    "extra_fields": {"type": "object"},
                },
                "required": ["integration_id"],
            },
        ),
        Tool(
            name="delete_integration",
            description=(
                "Delete an integration by ID. Works for any integration"
                " type (http, slack-2, pagerduty, etc.). (requires write"
                " permission)"
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "integration_id": {
                        "type": "integer",
                        "description": "Integration ID",
                    },
                },
                "required": ["integration_id"],
            },
        ),
    ]
)

# Alert thresholds
_ALERT_SETTING_IDS: dict[str, dict[str, Any]] = {
    "level": {
        "type": "string",
        "enum": ["instance", "device", "group"],
        "description": (
            "instance: one device datasource instance (device_id, device_datasource_id, "
            "instance_id); device: every instance on device_id; group: a device group's "
            "settings for one datasource (group_id, datasource_id)"
        ),
    },
    "device_id": {"type": "integer", "description": "Device ID (instance and device level)"},
    "device_datasource_id": {
        "type": "integer",
        "description": "Device datasource ID, as get_device_datasources lists it (instance level)",
    },
    "instance_id": {"type": "integer", "description": "Instance ID (instance level)"},
    "datapoint_id": {"type": "integer", "description": "Datapoint ID"},
    "group_id": {"type": "integer", "description": "Device group ID (group level)"},
    "datasource_id": {"type": "integer", "description": "Datasource ID (group level)"},
}

TOOLS.extend(
    [
        Tool(
            name="get_alert_settings",
            description=(
                "Read datapoint alert thresholds at instance, device or group level: each "
                "datapoint's threshold in force and the level it comes from (instance, "
                "instance_group, device_datasource, device_group with source_group, group or "
                "global), beside the level's own and the global threshold. Use it before "
                "tuning a noisy threshold with update_alert_settings."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    **_ALERT_SETTING_IDS,
                    "datapoint_id": {
                        "type": "integer",
                        "description": "One datapoint's setting (instance level)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["level"],
            },
        ),
        Tool(
            name="update_alert_settings",
            description=(
                "Set or clear one datapoint's alert threshold at instance or group level "
                "(requires write permission). threshold is an operator, a space and up to three "
                "values for warning, error and critical, such as '> 60 80 90'; '' clears the "
                "level's own threshold so it inherits again. A threshold that does not parse is "
                "refused before any call. The device level has no write."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    **_ALERT_SETTING_IDS,
                    "level": {
                        **_ALERT_SETTING_IDS["level"],
                        "description": (
                            "instance: one device datasource instance (device_id, "
                            "device_datasource_id, instance_id); group: a device group's "
                            "settings for one datasource (group_id, datasource_id); device has "
                            "no write"
                        ),
                    },
                    "datapoint_id": {
                        "type": "integer",
                        "description": "The datapoint whose threshold changes (required)",
                    },
                    "threshold": {
                        "type": "string",
                        "description": (
                            "Threshold such as '> 60 80 90', 'delta> 5' or "
                            "'( 00:00 12:00 ) > 90 , > 80'; '' to clear"
                        ),
                    },
                    "note": {
                        "type": "string",
                        "description": "Threshold history note (instance level)",
                    },
                },
                "required": ["level", "threshold"],
            },
        ),
    ]
)

# Alert Rules
TOOLS.extend(
    [
        Tool(
            name="get_alert_rules",
            description=(
                "List alert rules: each rule's priority and the escalation chain it routes "
                "matching alerts to"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "priority_filter": {
                        "type": "integer",
                        "description": "Only rules of this priority",
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by rule name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return the full REST object (every field the API returns) "
                        "instead of the summary",
                    },
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
                    "datapoint": {"type": "string", "description": "DataPoint pattern to match"},
                    "instance": {"type": "string", "description": "Instance pattern to match"},
                    "suppress_alert_clear": {
                        "type": "boolean",
                        "default": False,
                        "description": "Suppress alert clear notifications",
                    },
                    "suppress_alert_ack_sdt": {
                        "type": "boolean",
                        "default": False,
                        "description": "Suppress ack/SDT notifications",
                    },
                    "otlp_query": {
                        "type": "string",
                        "description": "Not supported: the v3 alert rule body has no query "
                        "field, so passing one returns INVALID_REQUEST",
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
                    "suppress_alert_ack_sdt": {
                        "type": "boolean",
                        "description": "Updated suppress ack/SDT setting",
                    },
                    "otlp_query": {
                        "type": "string",
                        "description": "Not supported: the v3 alert rule body has no query "
                        "field, so passing one returns INVALID_REQUEST",
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
        Tool(
            name="create_user",
            description="Create a user in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Login username"},
                    "email": {"type": "string", "description": "Email address"},
                    "first_name": {"type": "string", "description": "First name"},
                    "last_name": {"type": "string", "description": "Last name"},
                    "roles": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Role IDs to assign",
                    },
                    "password": {"type": "string", "description": "Initial password"},
                    "phone": {"type": "string", "description": "Phone number"},
                    "sms_email": {"type": "string", "description": "SMS email"},
                    "note": {"type": "string", "description": "Admin note"},
                    "api_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "API-only user (no portal access)",
                    },
                    "two_fa_enabled": {
                        "type": "boolean",
                        "default": False,
                        "description": "Require two-factor auth",
                    },
                },
                "required": ["username", "email", "first_name", "last_name", "roles"],
            },
        ),
        Tool(
            name="update_user",
            description="Update a user in LogicMonitor (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "User ID to update"},
                    "email": {"type": "string", "description": "New email"},
                    "first_name": {"type": "string", "description": "New first name"},
                    "last_name": {"type": "string", "description": "New last name"},
                    "roles": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "New role IDs (replaces existing)",
                    },
                    "phone": {"type": "string", "description": "New phone number"},
                    "sms_email": {"type": "string", "description": "New SMS email"},
                    "note": {"type": "string", "description": "New admin note"},
                    "api_only": {"type": "boolean", "description": "API-only flag"},
                    "two_fa_enabled": {"type": "boolean", "description": "Two-factor flag"},
                },
                "required": ["user_id"],
            },
        ),
        Tool(
            name="delete_user",
            description="Delete a user from LogicMonitor (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "User ID to delete"},
                },
                "required": ["user_id"],
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "admin_id": {
                        "type": "integer",
                        "description": "User ID whose tokens to list (omit for all tokens)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "admin_id": {
                        "type": "integer",
                        "description": "Owning user ID (optional; looked up when omitted)",
                    },
                },
                "required": ["token_id"],
            },
        ),
        Tool(
            name="get_tenants",
            description=(
                "List the portal's tenant names, as the tenants API answers them: names only, "
                "with no paging or detail."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": {}},
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
        Tool(
            name="delete_device_property",
            description=(
                "Delete a property set on the device/resource itself (requires write "
                "permission). A name the device only inherits answers not found; a system "
                "property is refused."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "property_name": {
                        "type": "string",
                        "pattern": _PATH_SEGMENT_NAME_PATTERN,
                        "description": "Name of the device's own property",
                    },
                },
                "required": ["device_id", "property_name"],
            },
        ),
        Tool(
            name="get_device_group_properties",
            description=(
                "Get a device group's (resource group's) properties: its own, the ones it "
                "inherits and the system ones, each with the value in force, its type (custom, "
                "inherit or system) and the ancestor groups that hold the same name, nearest "
                "first; an inherited value is the nearest one's. property_name reads one "
                "property."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Device group ID"},
                    "property_name": {
                        "type": "string",
                        "pattern": _PATH_SEGMENT_NAME_PATTERN,
                        "description": "Read only this property",
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by property name (substring match)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100,
                        "description": "Max results",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="update_device_group_property",
            description=(
                "Set a property on a device group/resource group (requires write permission). "
                "A name the group only inherits, or does not hold, gets a value of the group's "
                "own, which the groups and devices under it inherit unless they hold their own. "
                "A system property is refused."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Device group ID"},
                    "property_name": {
                        "type": "string",
                        "pattern": _PATH_SEGMENT_NAME_PATTERN,
                        "description": "Property name",
                    },
                    "property_value": {"type": "string", "description": "Property value"},
                },
                "required": ["group_id", "property_name", "property_value"],
            },
        ),
        Tool(
            name="delete_device_group_property",
            description=(
                "Delete a property set on the device group/resource group itself (requires "
                "write permission). A name the group only inherits answers not found; a "
                "system property is refused."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer", "description": "Device group ID"},
                    "property_name": {
                        "type": "string",
                        "pattern": _PATH_SEGMENT_NAME_PATTERN,
                        "description": "Name of the group's own property",
                    },
                },
                "required": ["group_id", "property_name"],
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
            name="get_datasource_devices",
            description=(
                "List the devices/resources a datasource applies to, each with up to 10 of "
                "its instances; more_instances says it has others, which "
                "get_device_instances lists."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "datasource_id": {"type": "integer", "description": "Datasource ID"},
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by device display name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["datasource_id"],
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_datasource takes, instead of the summary"
                        ),
                    },
                },
                "required": ["datasource_id"],
            },
        ),
        Tool(
            name="create_datasource",
            description="Create a DataSource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format (same as "
            "get_datasource with raw=true). Use for round-tripping exports or building "
            "definitions from scratch. For LM Exchange format, use import_datasource. "
            "Script DataSource datapoints require appropriate type values.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full DataSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the DataSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_datasource",
            description="Delete a DataSource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "datasource_id": {
                        "type": "integer",
                        "description": "DataSource ID to delete",
                    },
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_configsource takes, instead of the summary"
                        ),
                    },
                },
                "required": ["configsource_id"],
            },
        ),
        Tool(
            name="get_configsource_update_reasons",
            description="Get update history and audit trail for a ConfigSource",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "configsource_id": {"type": "integer", "description": "ConfigSource ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["configsource_id"],
            },
        ),
        Tool(
            name="get_device_config",
            description="List config versions collected for a device instance",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID for the ConfigSource",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID (e.g. Running-Config)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max config versions to return",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
            },
        ),
        Tool(
            name="get_device_config_version",
            description="Get a specific config version with full content and diffs",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID for the ConfigSource",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                    "config_id": {
                        "type": "string",
                        "description": "Config version ID (from get_device_config)",
                    },
                    "start_epoch": {
                        "type": "integer",
                        "default": 0,
                        "description": "Epoch to compare against. "
                        "Use 0 to compare with previous version.",
                    },
                },
                "required": ["device_id", "device_datasource_id", "instance_id", "config_id"],
            },
        ),
        Tool(
            name="collect_device_config",
            description="Trigger an on-demand config collection for a device instance",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID for the ConfigSource",
                    },
                    "instance_id": {"type": "integer", "description": "Instance ID"},
                },
                "required": ["device_id", "device_datasource_id", "instance_id"],
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_eventsource takes, instead of the summary"
                        ),
                    },
                },
                "required": ["eventsource_id"],
            },
        ),
        Tool(
            name="get_device_eventsources",
            description=(
                "Get EventSources applied to a device (resource)."
                " Returns device-level EventSource associations."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="update_device_eventsource",
            description=(
                "Update a device-level EventSource association"
                " (requires write permission). Use to enable or disable"
                " alerting for an EventSource on a specific device."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_eventsource_id": {
                        "type": "integer",
                        "description": (
                            "Device-EventSource association ID (from get_device_eventsources)"
                        ),
                    },
                    "disable_alerting": {
                        "type": "boolean",
                        "description": "Set true to disable alerting, false to enable",
                    },
                },
                "required": ["device_id", "device_eventsource_id"],
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_propertysource takes, instead of the summary"
                        ),
                    },
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_topologysource takes, instead of the summary"
                        ),
                    },
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
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_logsource takes, instead of the summary"
                        ),
                    },
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by netscan name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
            description=(
                "List Service Insight business services (deviceType 6 devices, "
                "including APM trace services)"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by service name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_service",
            description="Get details about a specific Service Insight service",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "integer",
                        "description": "Service device ID (deviceType 6)",
                    },
                },
                "required": ["service_id"],
            },
        ),
        Tool(
            name="get_service_groups",
            description="List Service Insight service groups (BizService device groups)",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by group name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
        Tool(
            name="get_service_insights_rules",
            description=(
                "List the portal's Service Insights rules, rows as the API returns them. "
                "offset must be a multiple of limit; the portal answers any other offset with "
                "a 400. get_services lists the services themselves."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Pagination offset, a multiple of limit",
                    },
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
                    "tag_filter": {
                        "type": "string",
                        "description": "Filter by tag (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "note_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "Ops note ID",
                    },
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
        Tool(
            name="update_ops_note",
            description="Update an ops note (requires write permission)",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "Ops note ID to update",
                    },
                    "note": {"type": "string", "description": "New note text"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (replaces existing)",
                    },
                    "device_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "New device IDs to scope the note to",
                    },
                    "group_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "New device group IDs to scope the note to",
                    },
                },
                "required": ["note_id"],
            },
        ),
        Tool(
            name="delete_ops_note",
            description="Delete an ops note (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {
                        "type": "string",
                        "pattern": _LM_STRING_ID_PATTERN,
                        "description": "Ops note ID to delete",
                    },
                },
                "required": ["note_id"],
            },
        ),
    ]
)

# Audit Logs
TOOLS.extend(
    [
        Tool(
            name="get_audit_logs",
            description=(
                "Read the portal audit log: call this for who did what and when. kind='all' "
                "returns one page of entries, newest first; kind='change' returns the "
                "configuration changes (create, update, delete or import, read from each "
                "entry's description) found in a pool of the newest entries, with scanned "
                "and has_more; kind='login' returns portal sign-ins, sign-outs and failed "
                "logins, one query per login wording (up to six calls), with status and "
                "method per row, success_only or failed_only, and total as a lower bound "
                "while has_more is true; kind='api_token' returns the rows naming an API "
                "token, given by access_id or token_id (read to its access ID), keeping only "
                "that exact access ID, with event (change, rejected, throttled), path and "
                "method per row. username is an exact name or a comma-separated list; "
                "action and resource_type (kinds all and change) are whole words the "
                "description holds (the portal applies one, the second is matched on the "
                "fetched page); start_time and end_time bound the entry time in epoch "
                "seconds. System and automation actors (System:*, LogicMonitor Internal, "
                "cloud auto-delete) are dropped after the fetch for kinds all and change "
                "unless exclude_system is false or a username is given; dropped counts them "
                "and paging follows the rows the portal returned. An argument another kind "
                "reads is refused. offset plus the rows read must stay within 10,000, and "
                "the filter within about 900 characters."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "change", "login", "api_token"],
                        "default": "all",
                        "description": (
                            "all: every entry; change: configuration changes; login: portal "
                            "logins; api_token: rows naming an API token"
                        ),
                    },
                    "username": {
                        "type": "string",
                        "description": "Exact username, or a comma-separated list",
                    },
                    "action": {
                        "type": "string",
                        "description": "Whole words the description holds, e.g. Action=Delete",
                    },
                    "resource_type": {
                        "type": "string",
                        "description": "Whole words the description holds, e.g. Type=Device",
                    },
                    "change_type": {
                        "type": "string",
                        "enum": ["create", "update", "delete", "import"],
                        "description": "With kind change: the change type to keep",
                    },
                    "success_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "With kind login: successful logins only",
                    },
                    "failed_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "With kind login: failed logins only",
                    },
                    "access_id": {
                        "type": "string",
                        "description": "With kind api_token: the token's whole access ID",
                    },
                    "token_id": {
                        "type": "integer",
                        "description": "With kind api_token: the token's id, read to its access ID",
                    },
                    "start_time": {
                        "type": "integer",
                        "description": "Only entries at or after this epoch second",
                    },
                    "end_time": {
                        "type": "integer",
                        "description": "Only entries at or before this epoch second",
                    },
                    "exclude_system": {
                        "type": "boolean",
                        "default": True,
                        "description": "Drop system and automation actors (default true)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "include_connections": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include connection data",
                    },
                    "limit": {"type": "integer", "default": 100, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "limit": {"type": "integer", "default": 100, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["device_id"],
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
                    "status": {
                        "type": "string",
                        "description": "Only jobs with this status (active, inactive)",
                    },
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by job name (substring match)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
            name="get_device_batchjobs",
            description=(
                "List BatchJob datasources applied to a device (resource); per-run "
                "output lives in instance data via get_device_data"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
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
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
            },
        ),
    ]
)

# Usage
TOOLS.extend(
    [
        Tool(
            name="get_usage_contract",
            description=(
                "Read the portal's contracted entitlements, for license and contract "
                "questions: every feature the contract names, entitled or not, each with its "
                "role (billable_line, metered_no_entitlement, metered_unpaid, repeats_parent, "
                "rollup_or_carveout), entitled quantity, unit and roll-up basis, plus the "
                "detected billing_mode. It does not count the portal's current resources."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "billable_only": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return only the billable_line features",
                    },
                },
            },
        ),
        Tool(
            name="get_usage_metrics",
            description=(
                "Read how many devices, Kubernetes, AWS, Azure and GCP resources, websites and "
                "services the portal holds now, as point-in-time counts. The portal is billed "
                "on each feature's roll-up basis in the contract, so these are not billed figures."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
)

# Cost/Cloud
TOOLS.extend(
    [
        Tool(
            name="get_cost_recommendations",
            description=(
                "Get cost optimization recommendations. Category filter takes the "
                "category description string from get_cost_recommendation_categories"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            'Category description string (e.g. "Idle AWS EC2 instances")'
                        ),
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by recommendation status (e.g. active)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Results to skip for pagination",
                    },
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

# OTLP Metrics (native OTLP ingest, PromQL query surface)
TOOLS.extend(
    [
        Tool(
            name="get_otlp_metric_names",
            description=(
                "List the names of metrics ingested through native OpenTelemetry (OTLP), "
                "optionally those containing a substring, to find what to query with "
                'query_otlp_metrics or analyze_metric(source="otlp"). A portal without OTLP '
                "Metrics answers with available: false"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "contains": {
                        "type": "string",
                        "description": "Substring filter on metric names (wildcards unsupported)",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Window start, unix epoch seconds",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Window end, unix epoch seconds",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_otlp_metric_labels",
            description=(
                "List the label names on native OTLP metrics, optionally narrowed to one "
                "metric or to names containing a substring"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "Narrow to labels present on this metric name",
                    },
                    "label_name": {
                        "type": "string",
                        "description": "Substring filter on label names",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Window start, unix epoch seconds",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Window end, unix epoch seconds",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_otlp_label_values",
            description=(
                "List the values observed for one native OTLP metric label, such as every "
                "service_name, optionally narrowed to one metric"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Label name to list values for, e.g. service_name; discover "
                            "names with get_otlp_metric_labels"
                        ),
                    },
                    "metric": {
                        "type": "string",
                        "description": "Narrow to values present on this metric name",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Window start, unix epoch seconds",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Window end, unix epoch seconds",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
                "required": ["key"],
            },
        ),
        Tool(
            name="query_otlp_metrics",
            description=(
                "Run a PromQL query against native OTLP metrics. A range query (start and "
                "end in epoch seconds, optional step) returns each series' samples over the "
                "window; instant=true returns each series' value now and takes no window. "
                "Returns at most 20 series and 500 points a series, downsampled; for "
                'statistics on a series use analyze_metric(source="otlp")'
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "PromQL expression. Examples: container_memory_usage_bytes "
                            "(raw series), avg(container_cpu_usage_seconds_total) "
                            "(aggregate), rate(container_network_receive_bytes_total[5m]) "
                            '(per-second rate), nginx_up{service_name="api"} (label '
                            "matcher). Discover names and labels with "
                            "get_otlp_metric_names / get_otlp_metric_labels"
                        ),
                    },
                    "start": {
                        "type": "integer",
                        "description": (
                            "Window start, unix epoch seconds; range queries only. Keep "
                            "windows under ~30 days; very wide windows fail in the metrics "
                            "backend"
                        ),
                    },
                    "end": {
                        "type": "integer",
                        "description": "Window end, unix epoch seconds; range queries only",
                    },
                    "step": {
                        "type": "string",
                        "description": (
                            "Resolution step, e.g. '30s', '5m', '1h'; range queries only; use "
                            "larger steps for wider windows"
                        ),
                    },
                    "instant": {
                        "type": "boolean",
                        "default": False,
                        "description": "Read each series' value now instead of a range",
                    },
                },
                "required": ["query"],
            },
        ),
    ]
)

# Imports
TOOLS.extend(
    [
        Tool(
            name="import_datasource",
            description="Import a DataSource from LM Exchange JSON format via "
            "multipart upload (requires write permission). This expects LM Exchange "
            "format, not REST API format. For REST API format definitions "
            "(e.g., from get_datasource with raw=true), use create_datasource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "DataSource JSON definition in LM Exchange format",
                    },
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="create_configsource",
            description="Create a ConfigSource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format (same as "
            "get_configsource with raw=true). For LM Exchange format, use import_configsource.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full ConfigSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the ConfigSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_configsource",
            description="Delete a ConfigSource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "configsource_id": {
                        "type": "integer",
                        "description": "ConfigSource ID to delete",
                    },
                },
                "required": ["configsource_id"],
            },
        ),
        Tool(
            name="create_eventsource",
            description="Create an EventSource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format (same as "
            "get_eventsource with raw=true). For LM Exchange format, use import_eventsource.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full EventSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the EventSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_eventsource",
            description="Delete an EventSource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "eventsource_id": {
                        "type": "integer",
                        "description": "EventSource ID to delete",
                    },
                },
                "required": ["eventsource_id"],
            },
        ),
        Tool(
            name="import_configsource",
            description="Import a ConfigSource from LM Exchange JSON format via multipart "
            "upload (requires write permission). For REST API format definitions "
            "(e.g., from get_configsource with raw=true), use create_configsource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "ConfigSource JSON definition"},
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_eventsource",
            description="Import an EventSource from LM Exchange JSON format via multipart "
            "upload (requires write permission). For REST API format definitions "
            "(e.g., from get_eventsource with raw=true), use create_eventsource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "EventSource JSON definition"},
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="create_propertysource",
            description="Create a PropertySource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format (same as "
            "get_propertysource with raw=true). Use for round-tripping exports or building "
            "definitions from scratch. For LM Exchange format, use import_propertysource.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full PropertySource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the PropertySource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_propertysource",
            description="Delete a PropertySource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "propertysource_id": {
                        "type": "integer",
                        "description": "PropertySource ID to delete",
                    },
                },
                "required": ["propertysource_id"],
            },
        ),
        Tool(
            name="import_propertysource",
            description="Import a PropertySource from LM Exchange JSON format via multipart "
            "upload (requires write permission). For REST API format definitions "
            "(e.g., from get_propertysource with raw=true), use create_propertysource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "PropertySource JSON"},
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="create_logsource",
            description="Create a LogSource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format (same as "
            "get_logsource with raw=true). For LM Exchange format, use import_logsource.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full LogSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the LogSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_logsource",
            description="Delete a LogSource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "logsource_id": {
                        "type": "integer",
                        "description": "LogSource ID to delete",
                    },
                },
                "required": ["logsource_id"],
            },
        ),
        Tool(
            name="import_logsource",
            description="Import a LogSource from LM Exchange JSON format via multipart "
            "upload (requires write permission). For REST API format definitions "
            "(e.g., from get_logsource with raw=true), use create_logsource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "LogSource JSON definition"},
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="create_topologysource",
            description="Create a TopologySource via REST API from a full definition dict "
            "(requires write permission). Accepts REST API format. "
            "For LM Exchange format, use import_topologysource.",
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full TopologySource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the TopologySource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_topologysource",
            description="Delete a TopologySource definition "
            "(requires write permission). Existing collected data is retained.",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "topologysource_id": {
                        "type": "integer",
                        "description": "TopologySource ID to delete",
                    },
                },
                "required": ["topologysource_id"],
            },
        ),
        Tool(
            name="import_topologysource",
            description="Import a TopologySource from LM Exchange JSON format via multipart "
            "upload (requires write permission). For REST API format definitions, "
            "use create_topologysource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {"type": "object", "description": "TopologySource JSON"},
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="import_diagnosticsource",
            description="Import a DiagnosticSource from LM Exchange JSON format via "
            "multipart upload (requires write permission). For REST API format "
            "definitions (e.g., from get_diagnosticsource with raw=true), use "
            "create_diagnosticsource instead.",
            annotations=_IMPORT,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "DiagnosticSource JSON definition",
                    },
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
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
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
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
                    "handle_conflict": {
                        "type": "string",
                        "description": "How to handle naming conflicts with existing modules",
                    },
                    "fields_to_preserve": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to preserve from existing module when overwriting",
                    },
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

# LM Logs configuration and usage
_LOG_PAGE = {
    "limit": {"type": "integer", "default": 50, "description": "Max results"},
    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
}

TOOLS.extend(
    [
        Tool(
            name="get_log_pipelines",
            description=(
                "List every LM Logs pipeline with its log query and the partitions it names. It "
                "returns all pipelines at once and takes no arguments. It does not search log "
                "content."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_tracked_log_queries",
            description=(
                "List the portal's tracked log queries, each row as the API returns it. "
                "Use it to see which log queries the portal tracks; it does not run them."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": dict(_LOG_PAGE)},
        ),
        Tool(
            name="get_log_query_groups",
            description=(
                "List the saved LM Logs query groups (folders) with their type, owner, "
                "permission and the queries each holds."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": dict(_LOG_PAGE)},
        ),
        Tool(
            name="get_log_partitions",
            description=(
                "List the LM Logs partitions with whether each is active or paused, its "
                "criteria, and its active contract (state, SKU, retention, usage limit, "
                "period). Use it to check partition state and contract limits."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": dict(_LOG_PAGE)},
        ),
        Tool(
            name="get_log_usage",
            description=(
                "Read the portal's LM Logs usage figure from /log/usage: one number, as returned. "
                "The API states no unit or period for it."
            ),
            annotations=_READ_ONLY,
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
)

# Correlation and Analysis
TOOLS.extend(
    [
        Tool(
            name="analyze_alerts",
            description=(
                "Analyze one alert window: call this for how many alerts fired and when, "
                "which alerts belong together, how noisy alerting is, which datasources "
                "burst, or which portal changes preceded a spike over the last hours. One "
                "read of the window's active and cleared alerts, under the severity, "
                "device, group and datasource filters, feeds every section; 'statistics' "
                "gives active and cleared totals, counts by severity, the ten busiest "
                "devices and datasources, and the volume of each hour, cleared alerts "
                "included; 'clusters' groups two or more alerts by device, by datasource "
                "and by signature (datasource and datapoint), with their alert ids and "
                "first and last start times, and a device cluster names the device_id its "
                "alerts share, null for a website or two devices under one name; 'noise' "
                "gives a 0 to 100 score from the "
                "entropy of alerts over datasource and datapoint (weight 40), flaps, an "
                "alert on the same device and datapoint that re-fires within 30 minutes "
                "of clearing (30), and repeats, a combination with three or more alerts "
                "(30), with the first ten flap pairs and tuning recommendations; 'bursts' "
                "gives the windows of window_seconds on one datasource that hold at least "
                "min_alerts alerts on min_devices devices; 'changes' reads the audit log "
                "once and pairs each change (a create, update, delete or import, read from "
                "the entry's description) with the first 5-minute alert spike, a bucket above "
                "the mean by "
                "one standard deviation, within correlation_window_minutes after it, with "
                "a confidence from 1.0 to 0.5. truncated says when the 5000-alert cap cut "
                "either read short. Use get_alerts to list or page through the alerts "
                "themselves."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "default": 24,
                        "minimum": 1,
                        "description": "Hours the window reaches back from now (default: 24)",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "error", "warning", "info"],
                        "description": "Only alerts of this severity",
                    },
                    "device": {
                        "type": "string",
                        "description": "Only alerts on devices whose name contains this",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": "Only alerts on devices in this device group",
                    },
                    "datasource": {
                        "type": "string",
                        "description": (
                            "Only alerts from datasources whose name contains this, "
                            "regardless of case"
                        ),
                    },
                    "analyses": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["statistics", "clusters", "noise", "bursts", "changes"],
                        },
                        "description": "Sections to compute (all if omitted)",
                    },
                    "window_seconds": {
                        "type": "integer",
                        "default": 60,
                        "minimum": 1,
                        "description": "Burst window length in seconds (default: 60)",
                    },
                    "min_alerts": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "description": "Fewest alerts a burst holds (default: 10)",
                    },
                    "min_devices": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "description": "Fewest distinct devices a burst holds (default: 3)",
                    },
                    "correlation_window_minutes": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 1,
                        "description": (
                            "Longest gap from a change to the spike it pairs with (default: 30)"
                        ),
                    },
                },
            },
        ),
    ]
)

# ML/Statistical Analysis
TOOLS.extend(
    [
        Tool(
            name="correlate_metrics",
            description=(
                "Compute Pearson correlation between multiple metric series. "
                "Joins the series by timestamp bucket, as wide as the coarsest "
                "series' median sample interval with finer series averaged into it, "
                "and correlates over the buckets every series holds, reported as "
                "shared_samples. Builds an NxN correlation matrix and highlights "
                "strong correlations (|r| > 0.7). Maximum 10 sources."
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
            name="calculate_availability",
            description=(
                "Calculate availability percentage from alert history. "
                "Computes SLA-style uptime metrics, MTTR, and per-device "
                "breakdown from the window's cleared and active alerts, read as "
                "two lists; truncated says when the 5000-alert cap cut either "
                "read short. With target_slo it adds error_budget for the window: "
                "budget, consumed and remaining minutes, percent consumed, burn rate, "
                "projected exhaustion in days and a status (healthy, warning past 50 "
                "percent, critical past 90, exhausted)."
                "\n\nCommon mistakes: hours_back defaults to 720 (30 days). "
                "Narrow scope with device_id/group_id for performance."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_name": {
                        "type": "string",
                        "description": (
                            "Exact device display name; pass it or device_id, not group_id"
                        ),
                    },
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID filter",
                    },
                    "group_id": {
                        "type": "integer",
                        "description": (
                            "Optional device group ID filter; not with device_id or device_name"
                        ),
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
                            "Minimum severity for downtime (critical, error, warning, info)"
                        ),
                    },
                    "target_slo": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "maximum": 100,
                        "description": (
                            "Target availability percentage, such as 99.9; adds error_budget "
                            "over the hours_back window"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="analyze_blast_radius",
            description=(
                "Count the devices a device failure could reach through topology "
                "neighbors: neighbor_count at depth 1, dependent_count beyond it, each "
                "device's alert status, and critical path devices. A device whose "
                "neighbors neither topology path answers is listed under unreadable "
                "with a warning, never counted as zero; on a portal without those "
                "routes every read is unreadable."
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
            name="analyze_metric",
            description=(
                "Analyze one device instance's metric series, such as CPU, memory or disk "
                "usage: call this for statistics "
                "on a datapoint's recent history, such as its current level against the "
                "window, whether it is rising, its daily cycle, when it shifted, or which "
                "samples stand out. One paged read of the window feeds every section; "
                "'summary' gives latest, mean, standard deviation, min, max and the latest "
                "sample's signed z-score; 'trend' gives least-squares and Theil-Sen slopes "
                "per hour, r-squared, coefficient of variation, the detrended 24-hour "
                "autocorrelation and a label (volatile, cyclic, increasing, decreasing or "
                "stable); 'seasonality' gives detrended autocorrelation at 1, 4, 12, 24 and "
                "168 hours, the dominant period and the peak hours in UTC; 'change_points' "
                "gives level shifts, where the mean of the next 30 samples leaves the mean "
                "of the previous 30 by five times the noise in that comparison (measured "
                "with any steady trend and autocorrelation the noise has), with the daily "
                "cycle removed first when the window holds three days or more and that "
                "leaves less noise; each shift has its timestamp and the levels before and "
                "after it, less the daily cycle when that was removed. A change in the last "
                "30 samples is not reported yet, small shifts in strongly autocorrelated "
                "noise go unfound, on a window under a day a change inflates the noise and "
                "smaller shifts go unfound, and changes about a day apart in a few days "
                "leave the cycle in and go unfound; "
                "'anomalies' gives z-score, "
                "IQR and MAD hits, each method's 20 most extreme; 'forecast' gives the "
                "least-squares and Holt-Winters (daily season, two days of samples needed) "
                "slopes per hour and, with threshold, when each crosses it, within 30 days; "
                "'baseline' compares the window with one as long ending baseline_hours_ago "
                "hours ago (one more read): both windows' statistics, the mean's percent "
                "deviation and a status (normal within 20 percent, elevated or reduced "
                "within 50, anomalous past it). The baseline runs only with "
                "baseline_hours_ago. Use get_device_data for the raw samples. With "
                'source="otlp" it reads one PromQL range query (query, hours, step) in place '
                "of a device instance and runs the same sections on each series it returns, "
                "the first 20."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["device", "otlp"],
                        "default": "device",
                        "description": (
                            "device reads a device instance's datapoints; otlp reads a "
                            "PromQL range query over native OTLP metrics"
                        ),
                    },
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID; required with source device",
                    },
                    "device_datasource_id": {
                        "type": "integer",
                        "description": "Device-DataSource ID; required with source device",
                    },
                    "instance_id": {
                        "type": "integer",
                        "description": "Instance ID; required with source device",
                    },
                    "datapoints": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names (all if omitted); source device"
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": "PromQL expression; required with source otlp",
                    },
                    "step": {
                        "type": "string",
                        "description": (
                            "Resolution step of the otlp read, such as '5m'; the metrics "
                            "backend picks one when omitted"
                        ),
                    },
                    "hours": {
                        "type": "integer",
                        "default": 168,
                        "minimum": 1,
                        "description": "Hours of history to read (default: 168)",
                    },
                    "analyses": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "summary",
                                "trend",
                                "seasonality",
                                "change_points",
                                "anomalies",
                                "forecast",
                                "baseline",
                            ],
                        },
                        "description": (
                            "Sections to compute (all if omitted; the baseline only with "
                            "baseline_hours_ago)"
                        ),
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Level the forecast reports the crossing of",
                    },
                    "baseline_hours_ago": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Hours before now the baseline window ends, such as 168 for "
                            "the same window a week earlier"
                        ),
                    },
                },
            },
        ),
    ]
)

# Session Management
TOOLS.extend(
    [
        Tool(
            name="get_session_context",
            description="Get current session context (variables and history)",
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
            description="Clear all session context (variables and history)",
            annotations=_SESSION_WRITE,
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_session_history",
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

# Traces / APM
TOOLS.extend(
    [
        Tool(
            name="get_apm_services",
            description=(
                "List APM trace services, the deviceType 6 devices, one page at a time. "
                "Entry point for discovering traced services; read a service's datasources, "
                "operations (the instances of its operations datasource), metrics and "
                "properties with get_device_datasources, get_device_instances, "
                "get_device_data and get_device_properties, passing the service id as "
                "device_id."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by service display name (substring match)",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Results to skip for pagination",
                    },
                },
            },
        ),
        Tool(
            name="get_apm_service_alerts",
            description="Get the alerts on one APM trace service, one page at a time",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "integer",
                        "description": "APM service device ID",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "error", "warning", "info"],
                        "description": "Filter by alert severity",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Results to skip for pagination",
                    },
                },
                "required": ["service_id"],
            },
        ),
    ]
)

# Diagnostic Sources
TOOLS.extend(
    [
        Tool(
            name="get_diagnosticsources",
            description="List DiagnosticSources from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by source name (substring, server-side)",
                    },
                    "group_filter": {
                        "type": "string",
                        "description": "Filter by group (substring, server-side)",
                    },
                    "filter": {
                        "type": "string",
                        "description": (
                            "Raw LM filter expression (overrides typed filters). "
                            "Operators: : (eq), !: (neq), ~ (contains), !~ (not contains)."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum sources to return (default: 50)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Results to skip for pagination (default: 0)",
                    },
                },
            },
        ),
        Tool(
            name="get_diagnosticsource",
            description="Get details about a specific DiagnosticSource including datapoints",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "integer",
                        "description": "DiagnosticSource ID",
                    },
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_diagnosticsource takes, instead of the summary"
                        ),
                    },
                },
                "required": ["source_id"],
            },
        ),
        Tool(
            name="execute_diagnostic",
            description=(
                "Execute a DiagnosticSource script on a target device. Performs "
                "pre-execution checks (collector version, device status, script "
                "review) before triggering manual execution. Poll "
                "get_diagnostic_remediation_results for status and output. "
                "Requires write permission."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "host_id": {
                        "type": "integer",
                        "description": "Target device/host ID",
                    },
                    "diagnostic_source_id": {
                        "type": "integer",
                        "description": "DiagnosticSource ID to execute",
                    },
                    "alert_id": {
                        "type": "string",
                        "description": "Optional alert ID to associate with execution",
                    },
                },
                "required": ["host_id", "diagnostic_source_id"],
            },
        ),
        Tool(
            name="create_diagnosticsource",
            description=(
                "Create a DiagnosticSource via REST API from a full definition dict "
                "(requires write permission). Accepts REST API format (same as "
                "get_diagnosticsource with raw=true). For LM Exchange format, use "
                "import_diagnosticsource."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full DiagnosticSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the DiagnosticSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_diagnosticsource",
            description=(
                "Delete a DiagnosticSource definition (requires write permission). "
                "Action chains referencing it lose that stage."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "diagnosticsource_id": {
                        "type": "integer",
                        "description": "DiagnosticSource ID to delete",
                    },
                },
                "required": ["diagnosticsource_id"],
            },
        ),
    ]
)

# Remediation Sources
TOOLS.extend(
    [
        Tool(
            name="get_remediationsources",
            description="List RemediationSources from LogicMonitor",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by source name (substring, server-side)",
                    },
                    "group_filter": {
                        "type": "string",
                        "description": "Filter by group (substring, server-side)",
                    },
                    "filter": {
                        "type": "string",
                        "description": (
                            "Raw LM filter expression (overrides typed filters). "
                            "Operators: : (eq), !: (neq), ~ (contains), !~ (not contains)."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum sources to return (default: 50)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Results to skip for pagination (default: 0)",
                    },
                },
            },
        ),
        Tool(
            name="get_remediationsource",
            description=(
                "Get details about a specific RemediationSource including the Groovy script"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "source_id": {
                        "type": "integer",
                        "description": "RemediationSource ID",
                    },
                    "raw": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Return the full REST object, the definition "
                            "create_remediationsource takes, instead of the summary"
                        ),
                    },
                },
                "required": ["source_id"],
            },
        ),
        Tool(
            name="execute_remediation",
            description=(
                "Execute a RemediationSource script on a target device. "
                "Performs pre-execution checks (collector version, device status, "
                "script review) before triggering manual execution. "
                "Requires write permission."
            ),
            annotations=_DESTRUCTIVE_RUN,
            inputSchema={
                "type": "object",
                "properties": {
                    "host_id": {
                        "type": "integer",
                        "description": "Target device/host ID",
                    },
                    "remediation_source_id": {
                        "type": "integer",
                        "description": "Remediation source ID to execute",
                    },
                    "alert_id": {
                        "type": "string",
                        "description": "Optional alert ID to associate with execution",
                    },
                },
                "required": ["host_id", "remediation_source_id"],
            },
        ),
        Tool(
            name="create_remediationsource",
            description=(
                "Create a RemediationSource via REST API from a full definition dict "
                "(requires write permission). Accepts REST API format (same as "
                "get_remediationsource with raw=true). RemediationSources have no LM "
                "Exchange import endpoint."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "definition": {
                        "type": "object",
                        "description": "Full RemediationSource definition in REST API format",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, replace the RemediationSource holding the same name in "
                            "place with a PUT to its id; nothing is deleted first"
                        ),
                    },
                },
                "required": ["definition"],
            },
        ),
        Tool(
            name="delete_remediationsource",
            description=(
                "Delete a RemediationSource definition (requires write permission). "
                "Action chains referencing it lose that stage."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "remediationsource_id": {
                        "type": "integer",
                        "description": "RemediationSource ID to delete",
                    },
                },
                "required": ["remediationsource_id"],
            },
        ),
    ]
)

# Automated Diagnostics & Remediation (ADR) composite endpoints
TOOLS.extend(
    [
        Tool(
            name="get_diagnostic_remediation_assignments",
            description=(
                "List the diagnostic and remediation sources assigned to a specific "
                "resource or alert (Automated Diagnostics & Remediation). Unlike "
                "get_diagnosticsources/get_remediationsources, this resolves which "
                "modules actually apply to the target."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "integer",
                        "description": "Device/resource ID (provide this or alert_id)",
                    },
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID (provide this or resource_id)",
                    },
                    "module_type": {
                        "type": "string",
                        "enum": ["diagnosticsource", "remediationsource"],
                        "description": "Restrict to one module type (both if omitted)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                },
            },
        ),
        Tool(
            name="get_diagnostic_remediation_results",
            description=(
                "Get structured execution results for diagnostic and remediation "
                "source runs: status, trigger type, executor, script output, and "
                "timing. Provide exactly one of alert_id or host_id. Time window "
                "params are epoch milliseconds; result timestamps are epoch seconds."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID (exactly one of alert_id/host_id)",
                    },
                    "host_id": {
                        "type": "integer",
                        "description": "Device/host ID (exactly one of alert_id/host_id)",
                    },
                    "module_type": {
                        "type": "string",
                        "enum": ["diagnostic", "remediation", "both"],
                        "default": "both",
                        "description": "Which module results to return",
                    },
                    "diagnostic_source_id": {
                        "type": "integer",
                        "description": "Filter to one DiagnosticSource by ID",
                    },
                    "diagnostic_source_name": {
                        "type": "string",
                        "description": "Filter to one DiagnosticSource by name",
                    },
                    "remediation_source_id": {
                        "type": "integer",
                        "description": "Filter to one RemediationSource by ID",
                    },
                    "remediation_source_name": {
                        "type": "string",
                        "description": "Filter to one RemediationSource by name",
                    },
                    "start_time_ms": {
                        "type": "integer",
                        "description": "Window start, epoch milliseconds",
                    },
                    "end_time_ms": {
                        "type": "integer",
                        "description": "Window end, epoch milliseconds",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max results per page",
                    },
                    "offset": {"type": "integer", "default": 0, "description": "Page offset"},
                    "cursor": {
                        "type": "string",
                        "description": (
                            "Diagnostic-side cursor from a previous response "
                            '(not valid with module_type "both")'
                        ),
                    },
                    "remediation_cursor": {
                        "type": "string",
                        "description": (
                            "Remediation-side cursor from a previous response "
                            '(not valid with module_type "both")'
                        ),
                    },
                },
            },
        ),
    ]
)

# Action Chains (ADR automation)
TOOLS.extend(
    [
        Tool(
            name="get_action_chains",
            description=(
                "List action chains: ordered DiagnosticSource/RemediationSource "
                "stages that action rules trigger on alerts (Automated "
                "Diagnostics & Remediation)"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Results to skip for pagination",
                    },
                },
            },
        ),
        Tool(
            name="get_action_chain",
            description="Get details about a specific action chain including its stages",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Action chain ID"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="create_action_chain",
            description=(
                "Create an action chain from ordered diagnostic/remediation stages "
                "(requires write permission). Each stage references a "
                "DiagnosticSource or RemediationSource by ID."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Chain name"},
                    "stages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "integer",
                                    "description": "DiagnosticSource/RemediationSource ID",
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["diagnosticSource", "remediationSource"],
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Source name (optional)",
                                },
                            },
                            "required": ["id", "type"],
                        },
                        "description": "Ordered stage list",
                    },
                    "description": {"type": "string", "description": "Chain description"},
                },
                "required": ["name", "stages"],
            },
        ),
        Tool(
            name="update_action_chain",
            description=(
                "Update an action chain via PATCH; only provided fields are sent "
                "(requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Action chain ID"},
                    "name": {"type": "string", "description": "New chain name"},
                    "stages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "type": {
                                    "type": "string",
                                    "enum": ["diagnosticSource", "remediationSource"],
                                },
                                "name": {"type": "string"},
                            },
                            "required": ["id", "type"],
                        },
                        "description": "Replacement ordered stage list",
                    },
                    "description": {"type": "string", "description": "New description"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="delete_action_chain",
            description=(
                "Delete an action chain (requires write permission). Action rules "
                "referencing it stop triggering."
            ),
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "chain_id": {"type": "integer", "description": "Action chain ID"},
                },
                "required": ["chain_id"],
            },
        ),
        Tool(
            name="get_action_rules",
            description=(
                "List action rules: alert conditions (severity, device groups, "
                "datasource matchers) that trigger action chains"
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Filter by rule name (case-insensitive substring)",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Results to skip for pagination",
                    },
                },
            },
        ),
        Tool(
            name="get_action_rule",
            description="Get details about a specific action rule",
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Action rule ID"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="create_action_rule",
            description=(
                "Create an action rule binding an action chain to alert conditions "
                "(requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Rule name"},
                    "level": {
                        "type": "string",
                        "description": "Alert severity to match (e.g. Error, Critical)",
                    },
                    "device_groups": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Device group full paths (["*"] for all)',
                    },
                    "action_chain_id": {
                        "type": "integer",
                        "description": "Action chain to trigger",
                    },
                    "devices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Device display names (["*"] for all)',
                    },
                    "datasource": {"type": "string", "description": "Datasource name matcher"},
                    "instance": {"type": "string", "description": "Instance matcher"},
                    "datapoint": {"type": "string", "description": "Datapoint matcher"},
                    "resource_properties": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                        "description": "Property matchers",
                    },
                    "enabled": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether the rule starts enabled",
                    },
                },
                "required": ["name", "level", "device_groups", "action_chain_id"],
            },
        ),
        Tool(
            name="update_action_rule",
            description=(
                "Update an action rule via PATCH; only provided fields are sent "
                "(requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Action rule ID"},
                    "name": {"type": "string", "description": "New rule name"},
                    "level": {
                        "type": "string",
                        "description": "Alert severity to match (e.g. Error, Critical)",
                    },
                    "device_groups": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Device group full paths",
                    },
                    "action_chain_id": {
                        "type": "integer",
                        "description": "Action chain to trigger",
                    },
                    "devices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Device display names",
                    },
                    "datasource": {"type": "string", "description": "Datasource name matcher"},
                    "instance": {"type": "string", "description": "Instance matcher"},
                    "datapoint": {"type": "string", "description": "Datapoint matcher"},
                    "resource_properties": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["name", "value"],
                        },
                        "description": "Property matchers",
                    },
                    "enabled": {"type": "boolean", "description": "Enable/disable the rule"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="delete_action_rule",
            description="Delete an action rule (requires write permission)",
            annotations=_DELETE,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Action rule ID"},
                },
                "required": ["rule_id"],
            },
        ),
        Tool(
            name="set_action_rule_status",
            description=(
                "Enable or disable an action rule without touching its matchers "
                "(requires write permission)"
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "integer", "description": "Action rule ID"},
                    "enabled": {
                        "type": "boolean",
                        "description": "True to enable, False to disable",
                    },
                },
                "required": ["rule_id", "enabled"],
            },
        ),
    ]
)

# Workflows — composite tools and discovery
TOOLS.extend(
    [
        Tool(
            name="triage",
            description=(
                "Triage the alerts of the last hours_back hours in one call. Reads the alert "
                "window once through analyze_alerts for its statistics, clusters (by device, "
                "datasource and signature), noise and changes, then counts the blast radius "
                "of up to three device clusters, largest first. Each count row gives the "
                "devices reached as neighbors and as dependents, how many of them have a "
                "critical alert open, and how many devices' neighbors could not be read; a "
                "website cluster gets none. detail_level=full adds the devices each blast "
                "radius reached. Use analyze_alerts for bursts or a single section, and "
                "analyze_blast_radius for one device."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "error", "warning", "info"],
                        "description": "Filter alerts by severity",
                    },
                    "device": {"type": "string", "description": "Filter by device name"},
                    "group_id": {"type": "integer", "description": "Filter by device group ID"},
                    "hours_back": {
                        "type": "integer",
                        "default": 4,
                        "description": "Hours to look back (default: 4)",
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level (default: summary)",
                    },
                },
            },
        ),
        Tool(
            name="health_check",
            description=(
                "Composite health check: resolves a device, picks up to five of its "
                "datasources whose names mention CPU, memory or disk (drive, volume, "
                "filesystem), reads the first instance of each through analyze_metric "
                "(summary and anomalies over 24 hours), checks open alerts, and "
                "calculates 30-day availability. A device with none of those "
                "datasources gets an empty metrics list and a warning."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_name": {
                        "type": "string",
                        "description": "Device display name (used if device_id not provided)",
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level (default: summary)",
                    },
                },
            },
        ),
        Tool(
            name="capacity_plan",
            description=(
                "Composite capacity planning: reads each instance once through "
                "analyze_metric to classify its trend, detect seasonality and change "
                "points, and forecast when it crosses threshold (default 90). Summary "
                "rows carry each forecast method's breach_eta (epoch seconds) and "
                "hours_until_breach per datapoint."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "device_name": {
                        "type": "string",
                        "description": "Device display name (used if device_id not provided)",
                    },
                    "datasource": {
                        "type": "string",
                        "description": "Filter to a specific datasource name",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 168,
                        "description": "Hours of historical data (default: 168 = 1 week)",
                    },
                    "threshold": {
                        "type": "number",
                        "default": 90,
                        "description": (
                            "Level each forecast reaches for, in the datapoint's unit (default: 90)"
                        ),
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level (default: summary)",
                    },
                },
            },
        ),
        Tool(
            name="portal_overview",
            description=(
                "Shift-handoff overview of the portal: reads the alert window of the last "
                "hours_back hours once for statistics, clusters and noise, and lists the "
                "collectors and the active SDTs. detail_level=full adds up to 20 open "
                "critical and 20 open error alerts from across the portal, not only the "
                "window, and up to 20 dead devices; summary does not read them."
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
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level (default: summary)",
                    },
                },
            },
        ),
        Tool(
            name="diagnose",
            description=(
                "Composite diagnosis: given an alert, or a device's latest open "
                "critical alert, gathers the alert details, device context, alerts "
                "clustered and audit changes in the last four hours, blast radius, "
                "and the device's assigned DiagnosticSources with the latest results "
                "of the alert's diagnostic runs. It reads those results and never runs "
                "a DiagnosticSource. It computes no health score or root cause; "
                "health_check reports each metric's z-score."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID to diagnose",
                    },
                    "device_name": {
                        "type": "string",
                        "description": (
                            "Device name to diagnose (finds most recent critical alert)"
                        ),
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level (default: summary)",
                    },
                },
            },
        ),
        Tool(
            name="search_tools",
            description=(
                "Search the tools this server offers under its current settings by "
                "keyword, optionally within one category. Use it to find the tool for a "
                "task. It never names a tool the settings hide, so with writes off no "
                "write tool appears. Words such as 'the' and 'on' are ignored, plurals "
                "match singulars, and a query word that is a tool's full name ranks that "
                "tool first."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search keywords (e.g., 'alert', 'device health', 'forecast')"
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": list(TOOL_CATEGORIES["categories"]),
                        "description": "Search only this category's tools",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum results to return (default: 10)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="update_logicmodule",
            description=(
                "Update a LogicModule definition (configsource, datasource, diagnosticsource, "
                "eventsource, logsource, propertysource, remediationsource, topologysource). "
                "Reads the current full definition, deep-merges your `changes` onto it, "
                "validates required fields, and either returns a dry-run diff (mode='preview', "
                "default) or applies the merged definition (mode='apply'). The LogicMonitor "
                "update is full-replace, so the merged full definition is sent and fields you "
                "do not change are kept."
            ),
            annotations=_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "configsource",
                            "datasource",
                            "diagnosticsource",
                            "eventsource",
                            "logsource",
                            "propertysource",
                            "remediationsource",
                            "topologysource",
                        ],
                        "description": "Source type to update",
                    },
                    "id": {"type": "integer", "description": "LogicModule ID"},
                    "changes": {
                        "type": "object",
                        "description": (
                            "Partial update -- only the fields to change. Use `null` as a "
                            "value to explicitly delete a key. Lists replace wholesale."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["preview", "apply"],
                        "default": "preview",
                        "description": (
                            "'preview' returns a dry-run diff without writing (default). "
                            "'apply' writes the merged definition with a full-replace "
                            "PUT."
                        ),
                    },
                },
                "required": ["type", "id", "changes"],
            },
        ),
        Tool(
            name="get_reference",
            description=(
                "Get LogicMonitor reference content (schemas, enums, filter syntax, guides). "
                "Mirrors content from MCP Resources for clients without full Resource support "
                "(Copilot cloud agent, OpenAI Codex, Cline). Categories: schema, enums, "
                "filters, syntax, guide. Pass list=true (or omit both category and name) to "
                "discover all available (category, name) pairs."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["schema", "enums", "filters", "syntax", "guide"],
                        "description": "Reference category",
                    },
                    "name": {
                        "type": "string",
                        "description": (
                            "Resource name within the category (e.g., 'alerts', 'operators')"
                        ),
                    },
                    "list": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, return the available (category, name) pairs "
                            "instead of content"
                        ),
                    },
                },
            },
        ),
    ]
)

# Terraform import discovery
TOOLS.extend(
    [
        Tool(
            name="get_terraform_imports",
            description=(
                "List a resource type's portal objects as Terraform import blocks for the "
                "logicmonitor/logicmonitor provider, one `import { to, id }` block per object, "
                "for 15 of the provider resource types that import by ID; cluster alert confs "
                "are left out, since the API refuses the read the provider's importer makes. "
                "Run `terraform init`, then "
                "`terraform plan -generate-config-out=generated.tf` on the blocks to have "
                "Terraform write the resource configuration. The provider authenticates with "
                "LMv1 api_id and api_key only."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "enum": list(IMPORTABLE_TYPES),
                        "description": "Provider resource type, without the logicmonitor_ prefix",
                    },
                    "filter": {
                        "type": "string",
                        "description": "LogicMonitor filter expression, sent as written",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["resource_type"],
            },
        ),
    ]
)


# Network Intelligence (v3.8.0)
# Interface metrics, NetFlow aggregation, alert burst detection, link flaps,
# power events, enriched collector health, site-outage composite, and coverage audit.
TOOLS.extend(
    [
        Tool(
            name="get_interface_metrics",
            description=(
                "Pull interface-level metrics (in/out bytes, errors, discards, utilization, "
                "status) for a device's interface over a time window. Answers 'how is this "
                "port performing?' Resolves the Interface-family DataSource and the instance "
                "matching the interface name before fetching datapoints."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "Device ID"},
                    "interface": {
                        "type": "string",
                        "description": (
                            "Interface name or substring (case-insensitive), e.g. 'Gi0/1', 'eth0'"
                        ),
                    },
                    "metrics": {
                        "type": "string",
                        "description": (
                            "Comma-separated datapoint names. Defaults to RxRate, TxRate, "
                            "ErrorsIn, ErrorsOut, DiscardsIn, DiscardsOut, InterfaceStatus."
                        ),
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 1,
                        "description": "Hours of history to pull (default: 1)",
                    },
                },
                "required": ["device_id", "interface"],
            },
        ),
        Tool(
            name="get_device_flows",
            description=(
                "List a NetFlow exporter device's flow records over the last hours_back hours, "
                "rows as the API returns them; the API reference gives each flow its source and "
                "destination IP, port, DNS name and ASN, its protocol and its bytes. Answers "
                "FEATURE_DISABLED when the portal has NetFlow off for the device."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "NetFlow exporter device ID"},
                    "hours_back": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": "Hours of flows to read, ending now",
                    },
                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                    "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_device_top_talkers",
            description=(
                "A NetFlow exporter device's top talkers over the last hours_back hours, for "
                "'what is consuming my WAN?': by=endpoint pages the endpoints it saw and "
                "by=port the ports, rows as the API returns them (the API reference gives each "
                "a usage and a share); by=graph returns its top talkers graph whole. Answers "
                "FEATURE_DISABLED when the portal has NetFlow off for the device."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {"type": "integer", "description": "NetFlow exporter device ID"},
                    "by": {
                        "type": "string",
                        "enum": ["endpoint", "port", "graph"],
                        "default": "endpoint",
                        "description": "Endpoints, ports, or the top talkers graph",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": "Hours of flows to read, ending now",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max rows (endpoint and port)",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "description": "Pagination offset (endpoint and port)",
                    },
                },
                "required": ["device_id"],
            },
        ),
        Tool(
            name="get_link_flaps",
            description=(
                "Identify interfaces with repeated up/down transitions in a time window. "
                "Answers 'which ports are unstable?' Common causes: bad cable, duplex "
                "mismatch, bad SFP, PoE power cycling, WAN instability."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Scope to a device group",
                    },
                    "device": {
                        "type": "string",
                        "description": "Scope to a device name (substring match)",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 24,
                        "description": "Lookback window in hours (default: 24)",
                    },
                    "min_transitions": {
                        "type": "integer",
                        "default": 4,
                        "description": "Minimum alert fires to qualify as flapping",
                    },
                    "interface_pattern": {
                        "type": "string",
                        "default": "interface|interfaces|if-|port|ethernet",
                        "description": (
                            "Case-insensitive regex matching interface DataSource names"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_collector_health",
            description=(
                "Enriched collector status: whether each collector is down, downstream "
                "device count, uptime, and optional alert history. Leading indicator for "
                "site-level events. Prefer this over `get_collectors` when investigating "
                "potential outages. The collector asked for by collector_id, and each "
                "collector not known to be up, carries evidence: its latest status check and "
                "its five latest events."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "collector_id": {
                        "type": "integer",
                        "description": "Single collector ID. Other scope args are ignored if set.",
                    },
                    "collector_group_id": {
                        "type": "integer",
                        "description": "Restrict to collectors in this group",
                    },
                    "include_history": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Include recent alerts on a device named for the collector's "
                            "hostname. A collector with no such device returns an empty "
                            "list, which does not show it stayed up. The API cannot narrow "
                            "rows to CollectorDown; each row's alert_type names what it is. "
                            "A failed read is null with history_warning, not an empty list."
                        ),
                    },
                    "history_days": {
                        "type": "integer",
                        "default": 7,
                        "description": "History lookback in days",
                    },
                },
            },
        ),
        Tool(
            name="collector_debug",
            description=(
                "Run one collector debug command from a fixed list and return what the "
                "collector said (requires write permission). Each listed command reads, but it "
                "runs on the collector and opens a debug session the portal records in its Audit "
                "Log, and http sends a GET a device can act on, so the tool is gated as a write. "
                "Pick a command and pass that command's typed args; any other key is refused, "
                "and a command that changes the collector, runs code on its host or carries a "
                "credential is never sent. Device probes (ping, nslookup, macaddress, "
                "snmpdiagnose, snmpget, snmpwalk, wmi, winrm, cim, http, sslcerts) need "
                "device_id: the host is the device record's, and the command runs on the "
                "collector that serves the device. checkserverconnectivity targets the "
                "configured portal. Use it once get_collector_health or diagnose has named a "
                "collector, to answer one narrow question: whether the debug channel answers "
                "(uptime), what the stored health check says (health_check, parsed into each "
                "method's all-NaN rate), whether the collector reaches a device (ping, "
                "snmpdiagnose). A status of answered or no_reply is a result, not an error; a "
                "refusal by the portal or the collector is an error with the call's record in "
                "its details. The call stops at budget_seconds, and secrets in the output are "
                "masked, best effort."
            ),
            annotations=_DESTRUCTIVE_RUN,
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": [
                            "adlist",
                            "aplist",
                            "avslist",
                            "checkserverconnectivity",
                            "cim",
                            "dxlist",
                            "firewallstatus",
                            "getconfig",
                            "health_check",
                            "http",
                            "ipaddress",
                            "logsurf",
                            "macaddress",
                            "nslookup",
                            "nsplist",
                            "perf",
                            "ping",
                            "reportercache",
                            "snmpdiagnose",
                            "snmpget",
                            "snmpwalk",
                            "splist",
                            "sslcerts",
                            "tasklist",
                            "tlist",
                            "tplist",
                            "uptime",
                            "winrm",
                            "wmi",
                        ],
                        "description": "The command to run",
                    },
                    "collector_id": {
                        "type": "integer",
                        "description": (
                            "Collector to run it on; optional when device_id is given, and "
                            "then it must be the collector that serves the device"
                        ),
                    },
                    "device_id": {
                        "type": "integer",
                        "description": (
                            "Device to probe; required for device probes. Its record names "
                            "the host and the collector"
                        ),
                    },
                    "args": {
                        "type": "object",
                        "description": (
                            "The command's own arguments and no other key; host is never "
                            "accepted. perf: type (ds, queue or cpu), dsFilterColumn, ds, h. "
                            "getconfig: key (collector.<method>.threadpool or .timeout). "
                            "logsurf: level, n, files. aplist: h, status. splist: hostname. "
                            "tplist: h, status. tlist: h or c, one required. ping: type, count. "
                            "snmpdiagnose: oids. snmpget: oids. snmpwalk: oid, timeout (never "
                            "the SNMP community or user tables). wmi: query (one WQL SELECT, "
                            "comparisons written Name = 'x'; it reads the classes 59 "
                            "LogicMonitor WMI datasources collect from: Win32_Service, "
                            "Win32_OperatingSystem, Win32_Volume, Win32_LogicalDisk, "
                            "Win32_PrintJob and 44 named Win32_PerfRawData and "
                            "Win32_PerfFormattedData counter classes; it also reads "
                            "CIM_ComputerSystem, Win32_Process by its listed columns but never "
                            "CommandLine, and Win32_NTLogEvent, Win32_UserAccount and "
                            "Win32_Group with a WHERE clause; any other class is refused, and "
                            "the refusal names the allowed ones), "
                            "authType. winrm: auth, useSSL, certCheck, timeout. "
                            "cim: class (the classes wmi reads but Win32_Process and the three "
                            "read only with a WHERE clause). "
                            "http: url (the device's own host and no credentials; "
                            "a host written as a loopback, link-local or cloud metadata "
                            "address, or a known name for one, is refused, but a DNS name that "
                            "resolves to one is not caught), timeout. sslcerts: port. The "
                            "other commands take no arguments"
                        ),
                    },
                    "budget_seconds": {
                        "type": "number",
                        "default": 15,
                        "description": "Wall-clock budget for the whole call, 2 to 60 seconds",
                    },
                    "max_output_chars": {
                        "type": "integer",
                        "default": 20000,
                        "description": (
                            "Most raw output returned, 500 to 100,000 characters; health_check "
                            "returns its parsed summary and at most 4,000 raw characters"
                        ),
                    },
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="get_power_events",
            description=(
                "Filter alerts for UPS/PDU power-event signatures across APC, Liebert, "
                "and Eaton DataSources ('on battery', 'runtime remaining', 'input voltage "
                "lost') over a time window. Returns events matched by DataSource or alert "
                "name substring with counts per pattern."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": "Scope to a device group",
                    },
                    "device": {
                        "type": "string",
                        "description": "Scope to a device name (substring match)",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 2,
                        "description": "Lookback window in hours (default: 2)",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "error", "warning", "info"],
                        "description": "Filter by severity",
                    },
                    "patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Override default patterns. Default covers UPS, PDU, APC, "
                            "Liebert, Eaton, Battery, PowerSupply, Power_."
                        ),
                    },
                },
            },
        ),
        Tool(
            name="detect_site_outage",
            description=(
                "Composite workflow for site outage detection. Chains CollectorDown "
                "detection, mass-interface-down burst analysis, UPS on-battery events, "
                "and downstream device silence into a single site-outage verdict with "
                "confidence score, scope, and affected device list. Designed to catch the "
                "class of site-outage that generic AIOps correlation misses. Pass a device "
                "group ID representing the site."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": (
                            "Device group ID representing the site. Devices in this group "
                            "define the analysis scope."
                        ),
                    },
                    "window_seconds": {
                        "type": "integer",
                        "default": 300,
                        "description": "Burst window size in seconds (default: 300)",
                    },
                    "hours_back": {
                        "type": "integer",
                        "default": 1,
                        "description": "Context window for power events in hours",
                    },
                    "detail_level": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Output detail level",
                    },
                },
                "required": ["group_id"],
            },
        ),
        Tool(
            name="audit_network_monitoring_coverage",
            description=(
                "Portal audit that counts UPS/PDU devices onboarded, interface "
                "DataSources applied, SNMP credentials configured, and NetFlow exporters "
                "set up. Returns a prioritized gap list, each gap with the onboarding step "
                "that would let the portal detect what it cannot detect today."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "integer",
                        "description": ("Scope the audit to a device group. Omit for portal-wide."),
                    },
                },
            },
        ),
    ]
)


# Map tool names to their handler functions
# Multi-portal switching
TOOLS.extend(
    [
        Tool(
            name="get_portals",
            description="List the customer portals available in this multi-portal server.",
            annotations=_SESSION_READ,
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="use_portal",
            description="Switch the active customer portal for subsequent tool calls.",
            annotations=_SESSION_WRITE,
            inputSchema={
                "type": "object",
                "properties": {
                    "customer": {"type": "string", "description": "Portal key from get_portals"}
                },
                "required": ["customer"],
            },
        ),
        Tool(
            name="get_current_portal",
            description="Show which customer portal is currently active.",
            annotations=_SESSION_READ,
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="run_portal_reload",
            description=(
                "Re-read the vault so portals added or removed since startup take "
                "effect without restarting the client."
            ),
            annotations=_SESSION_WRITE,
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
)

# Edwin AI: listed only when both Edwin credentials are set
_EDWIN_HOURS = {
    "type": "integer",
    "default": 24,
    "minimum": 1,
    "description": "Window in hours back from now",
}
_EDWIN_LIMIT = {
    "type": "integer",
    "default": 10,
    "minimum": 1,
    "maximum": 50,
    "description": "Most rows to return, 1 to 50",
}
TOOLS.extend(
    [
        Tool(
            name="get_edwin_insights",
            description=(
                "List the insights Edwin AI created in the last `hours`, newest first. An "
                "insight is an incident Edwin built by correlating alerts. Each row has Edwin's "
                "id and display id, state, workflow state, severity, causal CI, impacted CIs, "
                "alert count and alert keys, a link into Edwin, and once Edwin has analyzed it, "
                "its title, summary, root cause, impact, timeline, remediation, evidence, "
                "contributing factors and similar incidents. Call this to find what Edwin "
                "concluded about an incident before reading raw alerts and metrics; "
                "get_edwin_insight reads one insight whole. `total` is Edwin's count of "
                "matches; it has read exactly 10000 for a window of all time, so treat 10000 "
                "as a lower bound. A cleared insight reads severity 0."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {
                        **_EDWIN_HOURS,
                        "description": "Window in hours back from now, on the insight's "
                        "creation time",
                    },
                    "state": {
                        "type": "string",
                        "description": "Insight state to match exactly; active and cleared "
                        "are the values seen",
                    },
                    "severity": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Edwin severity numbers (ml.insightSeverity) to match any "
                        "of; a cleared insight reads 0",
                    },
                    "causal_ci": {
                        "type": "string",
                        "description": "CI Edwin named as the cause, matched exactly",
                    },
                    "impacted_ci": {
                        "type": "string",
                        "description": "CI that must be in the insight's impacted list",
                    },
                    "limit": _EDWIN_LIMIT,
                },
            },
        ),
        Tool(
            name="get_edwin_insight",
            description=(
                "Read one Edwin AI insight by its `_id` from get_edwin_insights, with every "
                "field Edwin holds for it, including the ones get_edwin_insights leaves out. "
                "Each epoch-millisecond timestamp comes with an ISO 8601 twin."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "insight_id": {
                        "type": "string",
                        "description": "The insight's _id, such as correlation_<uuid>_<epoch ms>",
                    },
                },
                "required": ["insight_id"],
            },
        ),
        Tool(
            name="get_edwin_records",
            description=(
                "List Edwin AI's own copy of the alerts or events it received in the last "
                "`hours`, newest first unless `order` says otherwise. Use it to see what "
                "Edwin correlated; LogicMonitor's alerts are read with get_alerts and "
                "insights with get_edwin_insights. `filter` takes one Edwin filterCondition "
                "condition, ANDed with the window, such as "
                '{"EQUALS": [{"type": "string", "field": "cf.eventCI"}, "web01"]}; '
                "get_edwin_metadata lists the field names. Without `columns` every field comes "
                "back except extra.* (the CI's LogicMonitor properties) and raw.* (the source "
                "record)."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["alerts", "events"],
                        "description": "Record source to read",
                    },
                    "hours": {
                        **_EDWIN_HOURS,
                        "description": "Window in hours back from now, on meta.createdTimestamp "
                        "for alerts and meta.eventTimestamp for events",
                    },
                    "filter": {
                        "type": "object",
                        "description": "One filterCondition condition, ANDed with the window",
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to return beside _id; name extra.* or raw.* "
                        "fields here to get them",
                    },
                    "order": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": 'Edwin order entries: [{"field": ..., "type": "asc" or '
                        '"desc", "size": null}]',
                    },
                    "limit": _EDWIN_LIMIT,
                },
                "required": ["source"],
            },
        ),
        Tool(
            name="get_edwin_alert_volume",
            description=(
                "Count the alerts Edwin AI received in the last `hours`, by hour or by alert "
                "state. Returns [key, count] buckets, hour keys in epoch milliseconds, and "
                "Edwin's total for the window. The Edwin credential needs the query_aggregate "
                "scope; without it the call fails with SCOPE_MISSING naming that scope."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": _EDWIN_HOURS,
                    "group_by": {
                        "type": "string",
                        "enum": ["hour", "state"],
                        "default": "hour",
                        "description": "Bucket by hour of creation or by alert state",
                    },
                },
            },
        ),
        Tool(
            name="get_edwin_metadata",
            description=(
                "List Edwin AI's record types with their field counts, or with `record_type` "
                "the fields of one type, so you can name fields in get_edwin_records filters "
                "and columns. The extra.* fields, the CI's LogicMonitor properties, are counted "
                "but not listed unless `prefix` asks for them."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "description": "Record type to describe, such as alerts; omit to list "
                        "the types",
                    },
                    "prefix": {
                        "type": "string",
                        "description": "Only fields whose name starts with it, such as extra. "
                        "or cf.",
                    },
                },
            },
        ),
        Tool(
            name="get_edwin_tools",
            description=(
                "List Edwin AI's agents, or with `agent` (such as LMDiagnosticsAgent) that "
                "agent's MCP servers and the active tools on each. The mcp_name and tool name "
                "pairs are what edwin_run_tool takes. Edwin publishes no input schema for its "
                "tools, so a tool's short_description is the only guide to its parameter names."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent name; omit to list the agents",
                    },
                },
            },
        ),
        Tool(
            name="edwin_run_tool",
            description=(
                "Run one tool on one of Edwin AI's MCP servers, sending `parameters` to Edwin "
                "unchanged. Requires write permission: an Edwin tool can change the systems it "
                "connects to, and this server cannot tell which tools do, so every run is "
                "gated and audited. Take mcp_name and tool_name from get_edwin_tools; the "
                "parameter names come from the tool's short_description, since Edwin "
                "publishes no input schema. A tool that reports failure returns "
                "REJECTED_BY_TOOL with Edwin's error."
            ),
            annotations=_DESTRUCTIVE_RUN,
            inputSchema={
                "type": "object",
                "properties": {
                    "mcp_name": {
                        "type": "string",
                        "description": "Edwin MCP server, from get_edwin_tools",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Tool on that server, from get_edwin_tools",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "The tool's arguments, sent to Edwin as given",
                    },
                },
                "required": ["mcp_name", "tool_name", "parameters"],
            },
        ),
        Tool(
            name="ask_edwin",
            description=(
                "Ask Edwin AI a question in plain words and wait up to 120 seconds for its "
                "answer. Edwin investigates with its own tools and returns `answer`, "
                "`reasoning` (its tool-call narration), a `conversation_id` to pass back for a "
                "follow-up, and `truncated: true` when the answer stopped early. Slower than "
                "the get_edwin_* reads; use it when a question needs Edwin's judgment rather "
                "than one of its records."
            ),
            annotations=_READ_ONLY,
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question, in plain words"},
                    "conversation_id": {
                        "type": "string",
                        "description": "A conversation to continue; omit to start one",
                    },
                },
                "required": ["question"],
            },
        ),
    ]
)


# The analytics and composite tools declare the report they return (spec R4.3). In
# multi-portal mode execute_tool stamps each result with its portal (stamp_portal), so
# every one of these schemas also takes that key.
_OUTPUT_SCHEMAS: dict[str, dict] = {
    "analyze_metric": analyze_metric.ANALYZE_METRIC_OUTPUT_SCHEMA,
    "analyze_alerts": analyze_alerts.ANALYZE_ALERTS_OUTPUT_SCHEMA,
    "calculate_availability": scoring.CALCULATE_AVAILABILITY_OUTPUT_SCHEMA,
    "correlate_metrics": correlation.CORRELATE_METRICS_OUTPUT_SCHEMA,
    "analyze_blast_radius": topology_analysis.ANALYZE_BLAST_RADIUS_OUTPUT_SCHEMA,
    "triage": workflows.TRIAGE_OUTPUT_SCHEMA,
    "portal_overview": workflows.PORTAL_OVERVIEW_OUTPUT_SCHEMA,
    "health_check": workflows.HEALTH_CHECK_OUTPUT_SCHEMA,
    "capacity_plan": workflows.CAPACITY_PLAN_OUTPUT_SCHEMA,
    "diagnose": workflows.DIAGNOSE_OUTPUT_SCHEMA,
    "detect_site_outage": workflows.DETECT_SITE_OUTAGE_OUTPUT_SCHEMA,
}
_PORTAL_STAMP = {
    "type": ["string", "null"],
    "description": "The portal the call ran against, in multi-portal mode.",
}


def _output_schema(schema: dict) -> dict:
    """``schema`` with the portal key a multi-portal result carries."""
    return {**schema, "properties": {**schema["properties"], "portal": _PORTAL_STAMP}}


TOOLS[:] = [
    tool.model_copy(update={"outputSchema": _output_schema(_OUTPUT_SCHEMAS[tool.name])})
    if tool.name in _OUTPUT_SCHEMAS
    else tool
    for tool in TOOLS
]


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
        actions,
        admin,
        alert_rules,
        alert_settings,
        alerts,
        analyze_alerts,
        analyze_metric,
        api_tokens,
        audit,
        batchjobs,
        collector_debug,
        collectors,
        configsources,
        correlation,
        cost,
        dashboard_groups,
        dashboards,
        datasources,
        devices,
        diagnostic_remediation,
        diagnosticsources,
        edwin,
        escalations,
        eventsources,
        imports,
        ingestion,
        integrations,
        logs,
        logsources,
        metrics,
        netscans,
        networking,
        oids,
        ops,
        otlp_metrics,
        propertysources,
        reference,
        remediationsources,
        reports,
        resources,
        scoring,
        sdts,
        services,
        session,
        terraform_imports,
        topology,
        topology_analysis,
        topologysources,
        traces,
        usage,
        users,
        websites,
        workflows,
    )
    from lm_mcp.tools import (
        portals as portal_tools,
    )

    handlers = {
        # Multi-portal
        "get_portals": portal_tools.get_portals,
        "use_portal": portal_tools.use_portal,
        "get_current_portal": portal_tools.get_current_portal,
        "run_portal_reload": portal_tools.run_portal_reload,
        # Edwin AI
        "get_edwin_insights": edwin.get_edwin_insights,
        "get_edwin_insight": edwin.get_edwin_insight,
        "get_edwin_records": edwin.get_edwin_records,
        "get_edwin_alert_volume": edwin.get_edwin_alert_volume,
        "get_edwin_metadata": edwin.get_edwin_metadata,
        "get_edwin_tools": edwin.get_edwin_tools,
        "edwin_run_tool": edwin.edwin_run_tool,
        "ask_edwin": edwin.ask_edwin,
        # Devices
        "get_devices": devices.get_devices,
        "get_device": devices.get_device,
        "get_device_groups": devices.get_device_groups,
        "get_device_group": devices.get_device_group,
        "create_device": devices.create_device,
        "update_device": devices.update_device,
        "delete_device": devices.delete_device,
        "recover_device": devices.recover_device,
        "run_auto_discovery": devices.run_auto_discovery,
        "get_device_delta": devices.get_device_delta,
        "get_unmonitored_devices": devices.get_unmonitored_devices,
        "bulk_delete_devices": devices.bulk_delete_devices,
        "create_device_group": devices.create_device_group,
        "update_device_group": devices.update_device_group,
        "delete_device_group": devices.delete_device_group,
        # Alerts
        "get_alerts": alerts.get_alerts,
        "get_alert_details": alerts.get_alert_details,
        "acknowledge_alert": alerts.acknowledge_alert,
        "add_alert_note": alerts.add_alert_note,
        "escalate_alert": alerts.escalate_alert,
        "bulk_acknowledge_alerts": alerts.bulk_acknowledge_alerts,
        # SDTs
        "get_sdts": sdts.get_sdts,
        "create_sdt": sdts.create_sdt,
        "delete_sdt": sdts.delete_sdt,
        "update_sdt": sdts.update_sdt,
        "bulk_create_device_sdt": sdts.bulk_create_device_sdt,
        "bulk_delete_sdt": sdts.bulk_delete_sdt,
        "get_active_sdts": sdts.get_active_sdts,
        "get_upcoming_sdts": sdts.get_upcoming_sdts,
        # Collectors
        "get_collectors": collectors.get_collectors,
        "get_collector": collectors.get_collector,
        "get_collector_groups": collectors.get_collector_groups,
        "get_collector_group": collectors.get_collector_group,
        "get_collector_events": collectors.get_collector_events,
        "get_collector_log_files": collectors.get_collector_log_files,
        "get_collector_log_file": collectors.get_collector_log_file,
        "get_collector_upgrade_history": collectors.get_collector_upgrade_history,
        "run_collector_status_check": collectors.run_collector_status_check,
        "restart_collector": collectors.restart_collector,
        "acknowledge_collector_down": collectors.acknowledge_collector_down,
        "update_collector": collectors.update_collector,
        "delete_collector": collectors.delete_collector,
        "create_collector_group": collectors.create_collector_group,
        "update_collector_group": collectors.update_collector_group,
        "delete_collector_group": collectors.delete_collector_group,
        "get_collector_health": collectors.get_collector_health,
        "collector_debug": collector_debug.collector_debug,
        # Network Intelligence (v3.8.0)
        "get_interface_metrics": networking.get_interface_metrics,
        "get_device_flows": networking.get_device_flows,
        "get_device_top_talkers": networking.get_device_top_talkers,
        "get_link_flaps": networking.get_link_flaps,
        "get_power_events": networking.get_power_events,
        # Metrics
        "get_device_datasources": metrics.get_device_datasources,
        "get_device_instances": metrics.get_device_instances,
        "add_device_instance": metrics.add_device_instance,
        "update_device_instance": metrics.update_device_instance,
        "delete_device_instance": metrics.delete_device_instance,
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
        "create_dashboard_group": dashboard_groups.create_dashboard_group,
        "delete_dashboard_group": dashboard_groups.delete_dashboard_group,
        "update_dashboard_group": dashboard_groups.update_dashboard_group,
        # Websites
        "get_websites": websites.get_websites,
        "get_website": websites.get_website,
        "get_website_groups": websites.get_website_groups,
        "get_website_checkpoints": websites.get_website_checkpoints,
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
        "get_report_execution": reports.get_report_execution,
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
        # Integrations
        "get_integrations": integrations.get_integrations,
        "get_integration": integrations.get_integration,
        "create_http_integration": integrations.create_http_integration,
        "update_http_integration": integrations.update_http_integration,
        "delete_integration": integrations.delete_integration,
        # Alert Rules
        "get_alert_settings": alert_settings.get_alert_settings,
        "update_alert_settings": alert_settings.update_alert_settings,
        "get_alert_rules": alert_rules.get_alert_rules,
        "get_alert_rule": alert_rules.get_alert_rule,
        "create_alert_rule": alert_rules.create_alert_rule,
        "update_alert_rule": alert_rules.update_alert_rule,
        "delete_alert_rule": alert_rules.delete_alert_rule,
        # Diagnostic Sources
        "get_diagnosticsources": diagnosticsources.get_diagnosticsources,
        "get_diagnosticsource": diagnosticsources.get_diagnosticsource,
        "execute_diagnostic": diagnosticsources.execute_diagnostic,
        "create_diagnosticsource": diagnosticsources.create_diagnosticsource,
        "delete_diagnosticsource": diagnosticsources.delete_diagnosticsource,
        # Remediation Sources
        "get_remediationsources": remediationsources.get_remediationsources,
        "get_remediationsource": remediationsources.get_remediationsource,
        "execute_remediation": remediationsources.execute_remediation,
        "create_remediationsource": remediationsources.create_remediationsource,
        "delete_remediationsource": remediationsources.delete_remediationsource,
        "get_diagnostic_remediation_assignments": (
            diagnostic_remediation.get_diagnostic_remediation_assignments
        ),
        "get_diagnostic_remediation_results": (
            diagnostic_remediation.get_diagnostic_remediation_results
        ),
        "get_action_chains": actions.get_action_chains,
        "get_action_chain": actions.get_action_chain,
        "create_action_chain": actions.create_action_chain,
        "update_action_chain": actions.update_action_chain,
        "delete_action_chain": actions.delete_action_chain,
        "get_action_rules": actions.get_action_rules,
        "get_action_rule": actions.get_action_rule,
        "create_action_rule": actions.create_action_rule,
        "update_action_rule": actions.update_action_rule,
        "delete_action_rule": actions.delete_action_rule,
        "set_action_rule_status": actions.set_action_rule_status,
        # Users
        "get_users": users.get_users,
        "get_user": users.get_user,
        "get_roles": users.get_roles,
        "get_role": users.get_role,
        "create_user": users.create_user,
        "update_user": users.update_user,
        "delete_user": users.delete_user,
        # Access Groups
        "get_access_groups": access_groups.get_access_groups,
        "get_access_group": access_groups.get_access_group,
        # API Tokens
        "get_api_tokens": api_tokens.get_api_tokens,
        "get_api_token": api_tokens.get_api_token,
        "get_tenants": admin.get_tenants,
        # Resources
        "get_device_properties": resources.get_device_properties,
        "get_device_property": resources.get_device_property,
        "update_device_property": resources.update_device_property,
        "delete_device_property": resources.delete_device_property,
        "get_device_group_properties": resources.get_device_group_properties,
        "update_device_group_property": resources.update_device_group_property,
        "delete_device_group_property": resources.delete_device_group_property,
        # Datasources
        "get_datasources": datasources.get_datasources,
        "get_datasource_devices": datasources.get_datasource_devices,
        "get_datasource": datasources.get_datasource,
        "create_datasource": datasources.create_datasource,
        "delete_datasource": datasources.delete_datasource,
        # ConfigSources
        "get_configsources": configsources.get_configsources,
        "get_configsource": configsources.get_configsource,
        "create_configsource": configsources.create_configsource,
        "delete_configsource": configsources.delete_configsource,
        "get_configsource_update_reasons": configsources.get_configsource_update_reasons,
        "get_device_config": configsources.get_device_config,
        "get_device_config_version": configsources.get_device_config_version,
        "collect_device_config": configsources.collect_device_config,
        # EventSources
        "get_eventsources": eventsources.get_eventsources,
        "get_eventsource": eventsources.get_eventsource,
        "create_eventsource": eventsources.create_eventsource,
        "delete_eventsource": eventsources.delete_eventsource,
        "get_device_eventsources": eventsources.get_device_eventsources,
        "update_device_eventsource": eventsources.update_device_eventsource,
        # PropertySources
        "get_propertysources": propertysources.get_propertysources,
        "get_propertysource": propertysources.get_propertysource,
        "create_propertysource": propertysources.create_propertysource,
        "delete_propertysource": propertysources.delete_propertysource,
        # TopologySources
        "get_topologysources": topologysources.get_topologysources,
        "get_topologysource": topologysources.get_topologysource,
        "create_topologysource": topologysources.create_topologysource,
        "delete_topologysource": topologysources.delete_topologysource,
        # LogSources
        "get_logsources": logsources.get_logsources,
        "get_logsource": logsources.get_logsource,
        "create_logsource": logsources.create_logsource,
        "delete_logsource": logsources.delete_logsource,
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
        "get_service_insights_rules": services.get_service_insights_rules,
        # Ops Notes
        "get_ops_notes": ops.get_ops_notes,
        "get_ops_note": ops.get_ops_note,
        "add_ops_note": ops.add_ops_note,
        "update_ops_note": ops.update_ops_note,
        "delete_ops_note": ops.delete_ops_note,
        # Audit logs are owned by the audit module.
        "get_audit_logs": audit.get_audit_logs,
        # Topology
        "get_topology_map": topology.get_topology_map,
        "get_device_neighbors": topology.get_device_neighbors,
        "get_device_interfaces": topology.get_device_interfaces,
        "get_device_connections": topology.get_device_connections,
        # Batch Jobs
        "get_batchjobs": batchjobs.get_batchjobs,
        "get_batchjob": batchjobs.get_batchjob,
        "get_device_batchjobs": batchjobs.get_device_batchjobs,
        "get_scheduled_downtime_jobs": batchjobs.get_scheduled_downtime_jobs,
        # Usage
        "get_usage_contract": usage.get_usage_contract,
        "get_usage_metrics": usage.get_usage_metrics,
        # Cost
        "get_cost_recommendations": cost.get_cost_recommendations,
        "get_cost_recommendation_categories": cost.get_cost_recommendation_categories,
        "get_cost_recommendation": cost.get_cost_recommendation,
        # OTLP Metrics
        "get_otlp_metric_names": otlp_metrics.get_otlp_metric_names,
        "get_otlp_metric_labels": otlp_metrics.get_otlp_metric_labels,
        "get_otlp_label_values": otlp_metrics.get_otlp_label_values,
        "query_otlp_metrics": otlp_metrics.query_otlp_metrics,
        # Imports
        "import_datasource": imports.import_datasource,
        "import_configsource": imports.import_configsource,
        "import_eventsource": imports.import_eventsource,
        "import_propertysource": imports.import_propertysource,
        "import_logsource": imports.import_logsource,
        "import_topologysource": imports.import_topologysource,
        "import_diagnosticsource": imports.import_diagnosticsource,
        "import_jobmonitor": imports.import_jobmonitor,
        "import_appliesto_function": imports.import_appliesto_function,
        # Ingestion
        "ingest_logs": ingestion.ingest_logs,
        "push_metrics": ingestion.push_metrics,
        # LM Logs
        "get_log_pipelines": logs.get_log_pipelines,
        "get_tracked_log_queries": logs.get_tracked_log_queries,
        "get_log_query_groups": logs.get_log_query_groups,
        "get_log_partitions": logs.get_log_partitions,
        "get_log_usage": logs.get_log_usage,
        # Correlation and Analysis
        "analyze_alerts": analyze_alerts.analyze_alerts,
        # ML/Statistical Analysis
        "correlate_metrics": correlation.correlate_metrics,
        "analyze_metric": analyze_metric.analyze_metric,
        "calculate_availability": scoring.calculate_availability,
        "analyze_blast_radius": topology_analysis.analyze_blast_radius,
        # Traces / APM
        "get_apm_services": traces.get_apm_services,
        "get_apm_service_alerts": traces.get_apm_service_alerts,
        # Session
        "get_session_context": session.get_session_context,
        "set_session_variable": session.set_session_variable,
        "get_session_variable": session.get_session_variable,
        "delete_session_variable": session.delete_session_variable,
        "clear_session_context": session.clear_session_context,
        "get_session_history": session.get_session_history,
        # Workflows
        "triage": workflows.triage,
        "health_check": workflows.health_check,
        "capacity_plan": workflows.capacity_plan,
        "portal_overview": workflows.portal_overview,
        "diagnose": workflows.diagnose,
        "search_tools": workflows.search_tools,
        "update_logicmodule": workflows.update_logicmodule,
        "detect_site_outage": workflows.detect_site_outage,
        "audit_network_monitoring_coverage": workflows.audit_network_monitoring_coverage,
        # Universal reference layer (Resource mirror for clients without Resource support)
        "get_reference": reference.get_reference,
        # Terraform IaC
        "get_terraform_imports": terraform_imports.get_terraform_imports,
    }

    if tool_name not in handlers:
        raise ValueError(f"Unknown tool: {tool_name}")

    return handlers[tool_name]
