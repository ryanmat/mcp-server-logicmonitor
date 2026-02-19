# Description: MCP prompt registry for LogicMonitor workflow templates.
# Description: Defines pre-built prompts for common monitoring operations.

from __future__ import annotations

from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)

from lm_mcp.prompts.templates import (
    alert_correlation_template,
    alert_summary_template,
    audit_review_template,
    capacity_forecast_template,
    capacity_review_template,
    collector_health_template,
    cost_optimization_template,
    health_check_template,
    incident_triage_template,
    rca_workflow_template,
    remediate_workflow_template,
    sdt_planning_template,
    top_talkers_template,
    troubleshoot_device_template,
)

# MCP Prompt definitions for LogicMonitor workflows
PROMPTS: list[Prompt] = [
    Prompt(
        name="incident_triage",
        description="Analyze active alerts, identify patterns, and suggest root cause",
        arguments=[
            PromptArgument(
                name="severity",
                description="Filter by severity (critical, error, warning, info)",
                required=False,
            ),
            PromptArgument(
                name="time_window_hours",
                description="Time window in hours (default: 24)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="capacity_review",
        description="Review resource utilization and identify capacity concerns",
        arguments=[
            PromptArgument(
                name="group_id",
                description="Device group ID to review",
                required=False,
            ),
            PromptArgument(
                name="threshold_percent",
                description="Utilization threshold to flag (default: 80)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="health_check",
        description="Generate environment health summary with key metrics",
        arguments=[
            PromptArgument(
                name="include_collectors",
                description="Include collector status (true/false)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="alert_summary",
        description="Generate alert digest grouped by severity or resource",
        arguments=[
            PromptArgument(
                name="group_by",
                description="Group alerts by: severity, device, datasource",
                required=False,
            ),
            PromptArgument(
                name="hours_back",
                description="Hours to look back (default: 24)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="sdt_planning",
        description="Plan scheduled downtime for maintenance windows",
        arguments=[
            PromptArgument(
                name="device_ids",
                description="Comma-separated device IDs",
                required=False,
            ),
            PromptArgument(
                name="group_id",
                description="Device group ID for bulk SDT",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="cost_optimization",
        description="Review cloud costs, identify idle resources, and find savings opportunities",
        arguments=[
            PromptArgument(
                name="cloud_account_id",
                description="Cloud account ID to review",
                required=False,
            ),
            PromptArgument(
                name="time_range",
                description="Time range for analysis (default: 30d)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="audit_review",
        description="Review recent activity, failed logins, and configuration changes",
        arguments=[
            PromptArgument(
                name="hours_back",
                description="Hours to look back (default: 24)",
                required=False,
            ),
            PromptArgument(
                name="username",
                description="Filter by specific username",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="alert_correlation",
        description="Correlate alerts by device, time, and network topology",
        arguments=[
            PromptArgument(
                name="hours_back",
                description="Hours to look back (default: 4)",
                required=False,
            ),
            PromptArgument(
                name="severity",
                description="Filter by severity (critical, error, warning, info)",
                required=False,
            ),
            PromptArgument(
                name="device_id",
                description="Scope to a specific device ID",
                required=False,
            ),
            PromptArgument(
                name="group_id",
                description="Scope to a specific device group ID",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="collector_health",
        description="Review collector status, versions, and group distribution",
        arguments=[
            PromptArgument(
                name="collector_group_id",
                description="Collector group ID to review",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="troubleshoot_device",
        description="Investigate a specific device with alerts, properties, and datasource status",
        arguments=[
            PromptArgument(
                name="device_id",
                description="Device ID to troubleshoot",
                required=True,
            ),
            PromptArgument(
                name="hours_back",
                description="Hours to look back for alerts (default: 24)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="top_talkers",
        description="Identify noisiest devices or datasources by alert volume",
        arguments=[
            PromptArgument(
                name="hours_back",
                description="Hours to look back (default: 24)",
                required=False,
            ),
            PromptArgument(
                name="limit",
                description="Number of top talkers to return (default: 10)",
                required=False,
            ),
            PromptArgument(
                name="group_by",
                description="Group by: device or datasource (default: device)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="rca_workflow",
        description="Root cause analysis workflow with correlation, topology, and timeline",
        arguments=[
            PromptArgument(
                name="device_id",
                description="Starting device ID for investigation",
                required=False,
            ),
            PromptArgument(
                name="alert_id",
                description="Starting alert ID for investigation",
                required=False,
            ),
            PromptArgument(
                name="hours_back",
                description="Hours to look back (default: 4)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="capacity_forecast",
        description="Resource utilization trending and capacity planning",
        arguments=[
            PromptArgument(
                name="device_id",
                description="Target device ID",
                required=False,
            ),
            PromptArgument(
                name="group_id",
                description="Target device group ID",
                required=False,
            ),
            PromptArgument(
                name="datasource",
                description="Datasource to analyze (default: CPU)",
                required=False,
            ),
            PromptArgument(
                name="hours_back",
                description="Analysis window in hours (default: 168 = 1 week)",
                required=False,
            ),
            PromptArgument(
                name="threshold",
                description="Warning threshold percent (default: 80)",
                required=False,
            ),
        ],
    ),
    Prompt(
        name="remediate_workflow",
        description="Diagnose a LogicMonitor alert and remediate via Ansible Automation Platform",
        arguments=[
            PromptArgument(
                name="alert_id",
                description="Alert ID to investigate and remediate",
                required=False,
            ),
            PromptArgument(
                name="device_id",
                description="Device ID to find alerts for and remediate",
                required=False,
            ),
        ],
    ),
]


def get_prompt_messages(name: str, arguments: dict) -> GetPromptResult:
    """Get the messages for a prompt.

    Args:
        name: Prompt name.
        arguments: Prompt arguments.

    Returns:
        GetPromptResult with prompt messages.

    Raises:
        ValueError: If prompt not found.
    """
    templates = {
        "incident_triage": incident_triage_template,
        "capacity_review": capacity_review_template,
        "health_check": health_check_template,
        "alert_summary": alert_summary_template,
        "sdt_planning": sdt_planning_template,
        "cost_optimization": cost_optimization_template,
        "audit_review": audit_review_template,
        "alert_correlation": alert_correlation_template,
        "collector_health": collector_health_template,
        "troubleshoot_device": troubleshoot_device_template,
        "top_talkers": top_talkers_template,
        "rca_workflow": rca_workflow_template,
        "capacity_forecast": capacity_forecast_template,
        "remediate_workflow": remediate_workflow_template,
    }

    if name not in templates:
        raise ValueError(f"Unknown prompt: {name}")

    template_func = templates[name]
    content = template_func(arguments)

    return GetPromptResult(
        description=f"LogicMonitor {name.replace('_', ' ')} workflow",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=content),
            )
        ],
    )
