# Description: Guide resources for LogicMonitor MCP server.
# Description: Provides tool category index and common query examples for AI agents.

from __future__ import annotations

# All LogicMonitor MCP tools organized by domain category.
# Helps AI agents pick the right tool from a large set.
TOOL_CATEGORIES = {
    "name": "tool-categories",
    "description": "All LogicMonitor MCP tools organized by domain",
    "categories": {
        "workflows": {
            "description": "Composite workflow tools -- recommended starting point",
            "tools": [
                "triage",
                "health_check",
                "capacity_plan",
                "portal_overview",
                "diagnose",
                "update_logicmodule",
                "detect_site_outage",
                "audit_network_monitoring_coverage",
            ],
        },
        "universal_reference": {
            "description": "Resource mirror exposed as a Tool for clients without that primitive",
            "tools": ["get_reference"],
        },
        "discovery": {
            "description": "Tool search and discovery",
            "tools": ["search_tools"],
        },
        "devices": {
            "description": "Device/resource management",
            "tools": [
                "get_devices",
                "get_device",
                "get_device_groups",
                "get_device_group",
                "create_device",
                "update_device",
                "delete_device",
                "recover_device",
                "run_auto_discovery",
                "get_device_delta",
                "get_unmonitored_devices",
                "bulk_delete_devices",
                "create_device_group",
                "update_device_group",
                "delete_device_group",
                "get_device_properties",
                "get_device_property",
                "update_device_property",
                "delete_device_property",
                "get_device_group_properties",
                "update_device_group_property",
                "delete_device_group_property",
            ],
        },
        "alerts": {
            "description": "Alert monitoring and management",
            "tools": [
                "get_alerts",
                "get_alert_details",
                "acknowledge_alert",
                "add_alert_note",
                "escalate_alert",
                "bulk_acknowledge_alerts",
                "get_alert_settings",
                "update_alert_settings",
            ],
        },
        "alert_rules": {
            "description": "Alert rule configuration",
            "tools": [
                "get_alert_rules",
                "get_alert_rule",
                "create_alert_rule",
                "update_alert_rule",
                "delete_alert_rule",
            ],
        },
        "sdts": {
            "description": "Scheduled downtime management",
            "tools": [
                "get_sdts",
                "create_sdt",
                "update_sdt",
                "delete_sdt",
                "bulk_create_device_sdt",
                "bulk_delete_sdt",
                "get_active_sdts",
                "get_upcoming_sdts",
            ],
        },
        "collectors": {
            "description": "Collector status and management",
            "tools": [
                "get_collectors",
                "get_collector",
                "get_collector_groups",
                "get_collector_group",
                "get_collector_events",
                "get_collector_log_files",
                "get_collector_log_file",
                "get_collector_upgrade_history",
                "run_collector_status_check",
                "restart_collector",
                "acknowledge_collector_down",
                "update_collector",
                "delete_collector",
                "create_collector_group",
                "update_collector_group",
                "delete_collector_group",
                "get_collector_health",
                "collector_debug",
            ],
        },
        "networking": {
            "description": (
                "Network intelligence primitives: interface metrics, a device's NetFlow "
                "flows and top talkers, link flap identification, power event filtering "
                "(UPS/PDU)"
            ),
            "tools": [
                "get_interface_metrics",
                "get_device_flows",
                "get_device_top_talkers",
                "get_link_flaps",
                "get_power_events",
            ],
        },
        "datasources": {
            "description": "DataSource and instance monitoring",
            "tools": [
                "get_device_datasources",
                "get_device_instances",
                "add_device_instance",
                "update_device_instance",
                "delete_device_instance",
                "get_device_data",
                "get_graph_data",
                "get_datasources",
                "get_datasource",
                "get_datasource_devices",
                "create_datasource",
                "delete_datasource",
            ],
        },
        "dashboards": {
            "description": "Dashboard and widget management",
            "tools": [
                "get_dashboards",
                "get_dashboard",
                "get_dashboard_widgets",
                "get_widget",
                "create_dashboard",
                "update_dashboard",
                "delete_dashboard",
                "add_widget",
                "update_widget",
                "delete_widget",
                "get_dashboard_groups",
                "get_dashboard_group",
                "create_dashboard_group",
                "update_dashboard_group",
                "delete_dashboard_group",
            ],
        },
        "websites": {
            "description": "Website monitoring",
            "tools": [
                "get_websites",
                "get_website",
                "get_website_groups",
                "get_website_data",
                "get_website_checkpoints",
                "create_website",
                "update_website",
                "delete_website",
                "create_website_group",
                "delete_website_group",
            ],
        },
        "reports": {
            "description": "Report management and execution",
            "tools": [
                "get_reports",
                "get_report",
                "get_report_groups",
                "get_scheduled_reports",
                "run_report",
                "get_report_execution",
                "create_report",
                "update_report_schedule",
                "delete_report",
            ],
        },
        "escalations": {
            "description": "Escalation chain and recipient management",
            "tools": [
                "get_escalation_chains",
                "get_escalation_chain",
                "get_recipient_groups",
                "get_recipient_group",
                "create_escalation_chain",
                "update_escalation_chain",
                "delete_escalation_chain",
                "create_recipient_group",
                "update_recipient_group",
                "delete_recipient_group",
            ],
        },
        "integrations": {
            "description": (
                "Alert delivery integrations (Custom HTTP Delivery / webhooks)."
                " CRUD on /setting/integrations. Pair with escalation chains"
                " and alert rules to route alerts to Azure Sentinel, PagerDuty,"
                " ServiceNow, etc."
            ),
            "tools": [
                "get_integrations",
                "get_integration",
                "create_http_integration",
                "update_http_integration",
                "delete_integration",
            ],
        },
        "users": {
            "description": "User, role, and access management",
            "tools": [
                "get_users",
                "get_user",
                "create_user",
                "update_user",
                "delete_user",
                "get_roles",
                "get_role",
                "get_access_groups",
                "get_access_group",
                "get_api_tokens",
                "get_api_token",
                "get_tenants",
            ],
        },
        "topology": {
            "description": "Network topology and connectivity",
            "tools": [
                "get_topology_map",
                "get_device_neighbors",
                "get_device_interfaces",
                "get_device_connections",
            ],
        },
        "audit": {
            "description": "Audit logs and activity tracking",
            "tools": [
                "get_audit_logs",
            ],
        },
        "usage": {
            "description": "Contracted entitlements and the portal's current resource counts",
            "tools": [
                "get_usage_contract",
                "get_usage_metrics",
            ],
        },
        "cost": {
            "description": "Cloud cost analysis and optimization",
            "tools": [
                "get_cost_recommendations",
                "get_cost_recommendation_categories",
                "get_cost_recommendation",
            ],
        },
        "logimodules": {
            "description": "LogicModule definitions (ConfigSource, EventSource, etc.)",
            "tools": [
                "get_configsources",
                "get_configsource",
                "create_configsource",
                "delete_configsource",
                "get_configsource_update_reasons",
                "get_device_config",
                "get_device_config_version",
                "collect_device_config",
                "get_eventsources",
                "get_eventsource",
                "create_eventsource",
                "delete_eventsource",
                "get_device_eventsources",
                "update_device_eventsource",
                "get_propertysources",
                "get_propertysource",
                "create_propertysource",
                "delete_propertysource",
                "get_topologysources",
                "get_topologysource",
                "create_topologysource",
                "delete_topologysource",
                "get_logsources",
                "get_logsource",
                "create_logsource",
                "delete_logsource",
                "get_device_logsources",
            ],
        },
        "netscans": {
            "description": "Network scan management",
            "tools": [
                "get_netscans",
                "get_netscan",
                "run_netscan",
            ],
        },
        "ops": {
            "description": "Operations notes, OIDs, and services",
            "tools": [
                "get_oids",
                "get_oid",
                "get_services",
                "get_service",
                "get_service_groups",
                "get_service_insights_rules",
                "get_ops_notes",
                "get_ops_note",
                "add_ops_note",
                "update_ops_note",
                "delete_ops_note",
            ],
        },
        "batchjobs": {
            "description": "Batch job monitoring",
            "tools": [
                "get_batchjobs",
                "get_batchjob",
                "get_device_batchjobs",
                "get_scheduled_downtime_jobs",
            ],
        },
        "imports": {
            "description": "Import LogicModule definitions from JSON",
            "tools": [
                "import_datasource",
                "import_configsource",
                "import_eventsource",
                "import_propertysource",
                "import_logsource",
                "import_topologysource",
                "import_diagnosticsource",
                "import_jobmonitor",
                "import_appliesto_function",
            ],
        },
        "ingestion": {
            "description": "Push custom logs and metrics",
            "tools": [
                "ingest_logs",
                "push_metrics",
            ],
        },
        "logs": {
            "description": (
                "LM Logs configuration and usage: pipelines, tracked queries, query groups, "
                "partitions and the usage figure"
            ),
            "tools": [
                "get_log_pipelines",
                "get_tracked_log_queries",
                "get_log_query_groups",
                "get_log_partitions",
                "get_log_usage",
            ],
        },
        "otlp_metrics": {
            "description": (
                "Native OTLP metrics: PromQL range and instant queries and metric/label discovery"
            ),
            "tools": [
                "get_otlp_metric_names",
                "get_otlp_metric_labels",
                "get_otlp_label_values",
                "query_otlp_metrics",
            ],
        },
        "correlation": {
            "description": (
                "Alert-window analysis: statistics, clusters, noise, bursts and changes"
            ),
            "tools": [
                "analyze_alerts",
            ],
        },
        "traces": {
            "description": (
                "APM trace services (deviceType 6 devices) and their alerts; the device "
                "tools read their datasources, operations, metrics and properties"
            ),
            "tools": [
                "get_apm_services",
                "get_apm_service_alerts",
            ],
        },
        "ml_analysis": {
            "description": "ML/statistical analysis and forecasting",
            "tools": [
                "correlate_metrics",
                "calculate_availability",
                "analyze_blast_radius",
                "analyze_metric",
            ],
        },
        "session": {
            "description": "Session context, variable management, and history",
            "tools": [
                "get_session_context",
                "set_session_variable",
                "get_session_variable",
                "delete_session_variable",
                "clear_session_context",
                "get_session_history",
            ],
        },
        "portals": {
            "description": "Multi-portal switching: one server, many customer portals",
            "tools": [
                "get_portals",
                "use_portal",
                "get_current_portal",
                "run_portal_reload",
            ],
        },
        "edwin": {
            "description": (
                "Edwin AI: its insights, its copy of alerts and events, its data model, "
                "its agents' tools, and Ask Edwin; listed only with Edwin credentials"
            ),
            "tools": [
                "get_edwin_insights",
                "get_edwin_insight",
                "get_edwin_records",
                "get_edwin_alert_volume",
                "get_edwin_metadata",
                "get_edwin_tools",
                "edwin_run_tool",
                "ask_edwin",
            ],
        },
        "terraform": {
            "description": "Terraform import blocks for existing LogicMonitor objects",
            "tools": [
                "get_terraform_imports",
            ],
        },
        "remediation": {
            "description": ("Diagnostic sources, remediation sources, and remediation execution."),
            "tools": [
                "get_diagnosticsources",
                "get_diagnosticsource",
                "get_remediationsources",
                "get_remediationsource",
                "get_diagnostic_remediation_assignments",
                "get_diagnostic_remediation_results",
                "execute_remediation",
                "execute_diagnostic",
                "create_diagnosticsource",
                "delete_diagnosticsource",
                "create_remediationsource",
                "delete_remediationsource",
            ],
        },
        "actions": {
            "description": (
                "ADR automation: action chains (ordered diagnostic/remediation "
                "stages) and the rules that bind them to alerts."
            ),
            "tools": [
                "get_action_chains",
                "get_action_chain",
                "create_action_chain",
                "update_action_chain",
                "delete_action_chain",
                "get_action_rules",
                "get_action_rule",
                "create_action_rule",
                "update_action_rule",
                "delete_action_rule",
                "set_action_rule_status",
            ],
        },
    },
}

# Common filter patterns and query examples.
# Helps AI agents construct correct API filters.
COMMON_QUERY_EXAMPLES = {
    "name": "examples",
    "description": "Common LogicMonitor API filter patterns and query examples",
    "examples": [
        {
            "description": "Find active critical alerts",
            "tool": "get_alerts",
            "filter": "severity:4,cleared:false",
            "notes": "Severity 4 = critical. Boolean values do not need quotes.",
        },
        {
            "description": "Find dead devices",
            "tool": "get_devices",
            "filter": 'hostStatus:"dead"',
            "notes": (
                "hostStatus filters on the quoted word; numeric codes match nothing. "
                "Or use get_devices with status='dead'."
            ),
        },
        {
            "description": "Find alerts for a specific device by name",
            "tool": "get_alerts",
            "filter": 'monitorObjectName:"server-01.example.com"',
            "notes": "String values MUST be double-quoted in filters.",
        },
        {
            "description": "Find devices by display name substring",
            "tool": "get_devices",
            "filter": 'displayName~"production"',
            "notes": "The ~ operator performs substring matching. No wildcards needed.",
        },
        {
            "description": "Find unacknowledged error alerts",
            "tool": "get_alerts",
            "filter": "severity:3,acked:false,cleared:false",
            "notes": "Severity 3 = error. Combine multiple filters with commas.",
        },
        {
            "description": "Find alerts started in last hour",
            "tool": "get_alerts",
            "filter": "startEpoch>:{epoch_ms}",
            "notes": "Replace {epoch_ms} with epoch milliseconds. Use >: for greater-or-equal.",
        },
        {
            "description": "Find devices in a specific group",
            "tool": "get_devices",
            "filter": "hostGroupIds:5",
            "notes": "Use : for list membership; ~ matches a substring of the joined ids "
            "and returns devices from other groups.",
        },
        {
            "description": "Find active SDTs for a device",
            "tool": "get_active_sdts",
            "args": {"device_id": 123},
            "notes": "get_active_sdts already filters to currently active SDTs.",
        },
        {
            "description": "Find collectors by hostname",
            "tool": "get_collectors",
            "filter": 'hostname~"prod-collector"',
            "notes": "Use hostname_filter parameter for substring matching.",
        },
        {
            "description": "Find websites by name",
            "tool": "get_websites",
            "filter": 'name~"api-health"',
            "notes": "Use name_filter parameter for substring matching.",
        },
        {
            "description": "Find dashboards by owner",
            "tool": "get_dashboards",
            "filter": 'owner:"admin"',
            "notes": "Exact match with : operator. String values need quotes.",
        },
        {
            "description": "Get failed login attempts",
            "tool": "get_audit_logs",
            "args": {"kind": "login", "failed_only": True},
            "notes": "kind=login with failed_only=True for security review.",
        },
        {
            "description": "Check device neighbors for topology context",
            "tool": "get_device_neighbors",
            "args": {"device_id": 123, "depth": 2},
            "notes": "Depth 1-3 controls how many hops to traverse.",
        },
    ],
    "filter_syntax": {
        "operators": {
            ":": "Exact match (equal)",
            "!:": "Not equal",
            "~": "Contains (substring match)",
            "!~": "Not contains",
            ">": "Greater than",
            "<": "Less than",
            ">:": "Greater than or equal",
            "<:": "Less than or equal",
        },
        "rules": [
            "String values MUST be wrapped in double quotes",
            "Numeric and boolean values work without quotes",
            "Combine filters with commas (logical AND)",
            "The ~ operator performs substring matching; wildcards (* ?) are stripped",
        ],
    },
}


# MCP multi-server orchestration patterns and workflows.
# Guides AI agents on combining LogicMonitor with other MCP servers.
MCP_ORCHESTRATION_GUIDE: dict = {
    "name": "mcp-orchestration",
    "description": (
        "Patterns for combining the LogicMonitor MCP server with other "
        "MCP servers to build multi-system workflows."
    ),
    "scenarios": [
        {
            "name": "Incident to Ticket",
            "description": (
                "Detect alert clusters in LogicMonitor, create incidents "
                "in PagerDuty, and file follow-up tickets in Jira."
            ),
            "steps": [
                {
                    "server": "logicmonitor",
                    "tool": "analyze_alerts",
                    "description": (
                        "Cluster the window's alerts and count them by severity and device"
                    ),
                },
                {
                    "server": "pagerduty",
                    "tool": "create_incident",
                    "description": "Create PagerDuty incident with alert summary",
                },
                {
                    "server": "jira",
                    "tool": "create_issue",
                    "description": "File Jira ticket with root cause notes",
                },
            ],
        },
        {
            "name": "Full RCA Workflow",
            "description": (
                "Correlate alerts, map topology, check CMDB for "
                "dependencies, and compile root cause report."
            ),
            "steps": [
                {
                    "server": "logicmonitor",
                    "tool": "analyze_alerts",
                    "description": "Find correlated alert clusters",
                },
                {
                    "server": "logicmonitor",
                    "tool": "get_device_neighbors",
                    "description": "Map network topology around affected devices",
                },
                {
                    "server": "servicenow",
                    "tool": "get_ci_dependencies",
                    "description": "Query CMDB for upstream dependencies",
                },
                {
                    "server": "logicmonitor",
                    "tool": "analyze_metric",
                    "description": "Detect metric anomalies on root cause device",
                },
            ],
        },
        {
            "name": "Change Correlation",
            "description": (
                "Cross-reference LogicMonitor alerts with recent deployments "
                "from CI/CD tools to identify change-induced incidents."
            ),
            "steps": [
                {
                    "server": "logicmonitor",
                    "tool": "get_alerts",
                    "description": "Retrieve recent alerts in the time window",
                },
                {
                    "server": "github",
                    "tool": "list_deployments",
                    "description": "Get recent deployments from GitHub",
                },
                {
                    "server": "logicmonitor",
                    "tool": "get_audit_logs",
                    "description": "Check for LM config changes in same window (kind=change)",
                },
                {
                    "server": "slack",
                    "tool": "post_message",
                    "description": "Notify team channel with correlation findings",
                },
            ],
        },
    ],
    "configuration_example": {
        "mcpServers": {
            "logicmonitor": {
                "command": "uvx",
                "args": ["mcp-server-logicmonitor"],
                "env": {
                    "LM_PORTAL": "your-portal.logicmonitor.com",
                    "LM_BEARER_TOKEN": "your-token",
                },
            },
            "pagerduty": {
                "command": "uvx",
                "args": ["mcp-server-pagerduty"],
                "env": {"PD_API_KEY": "your-key"},
            },
            "jira": {
                "command": "uvx",
                "args": ["mcp-server-jira"],
                "env": {
                    "JIRA_URL": "https://your-org.atlassian.net",
                    "JIRA_TOKEN": "your-token",
                },
            },
        },
    },
    "best_practices": [
        (
            "Start with LogicMonitor for context: always gather alert and "
            "device data before calling external systems."
        ),
        (
            "Pass structured data between servers: use JSON results from one "
            "tool as input arguments to the next."
        ),
        (
            "Handle failures gracefully: if an external MCP server is "
            "unavailable, continue the workflow with available data."
        ),
        (
            "Use session variables to store intermediate results: save "
            "correlation IDs and ticket references for later steps."
        ),
        (
            "Scope operations narrowly: filter alerts by time window and "
            "severity before passing to external systems to reduce noise."
        ),
    ],
}


def get_guide_content(guide_name: str) -> dict | None:
    """Get guide content by name.

    Args:
        guide_name: The guide identifier.

    Returns:
        Guide content dict or None if not found.
    """
    from lm_mcp.resources.best_practices import get_best_practices

    guides: dict[str, dict] = {
        "tool-categories": TOOL_CATEGORIES,
        "examples": COMMON_QUERY_EXAMPLES,
        "mcp-orchestration": MCP_ORCHESTRATION_GUIDE,
        "best-practices": get_best_practices(),
    }
    return guides.get(guide_name)
