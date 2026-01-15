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
    alert_summary_template,
    capacity_review_template,
    health_check_template,
    incident_triage_template,
    sdt_planning_template,
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
