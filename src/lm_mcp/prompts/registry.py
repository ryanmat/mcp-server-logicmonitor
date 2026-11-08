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
    capacity_review_template,
    incident_triage_template,
    remediation_template,
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
        name="remediation",
        description="RemediationSource execution workflow with pre-execution safety checklist",
        arguments=[
            PromptArgument(
                name="host_id",
                description="Target device/host ID",
                required=False,
            ),
            PromptArgument(
                name="remediation_source_id",
                description="Remediation source ID to execute",
                required=False,
            ),
            PromptArgument(
                name="alert_id",
                description="Associated alert ID (optional)",
                required=False,
            ),
        ],
    ),
]


# Template builder for each prompt, keyed by prompt name.
_TEMPLATES = {
    "incident_triage": incident_triage_template,
    "capacity_review": capacity_review_template,
    "remediation": remediation_template,
}


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
    if name not in _TEMPLATES:
        raise ValueError(f"Unknown prompt: {name}")

    template_func = _TEMPLATES[name]
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
