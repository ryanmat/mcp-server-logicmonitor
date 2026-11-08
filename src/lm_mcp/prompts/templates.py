# Description: Template generators for MCP prompts.
# Description: Provides dynamic prompt content based on arguments.

from __future__ import annotations


def incident_triage_template(arguments: dict) -> str:
    """Generate incident triage prompt content.

    Args:
        arguments: Prompt arguments (severity, time_window_hours).

    Returns:
        Prompt text for incident triage workflow.
    """
    severity = arguments.get("severity", "all severities")
    hours = arguments.get("time_window_hours", "24")

    return f"""Perform an incident triage analysis for LogicMonitor alerts.

Parameters:
- Severity filter: {severity}
- Time window: Last {hours} hours

Steps to follow:
1. Use get_alerts to retrieve active alerts matching the criteria
2. Identify patterns in the alerts (common devices, datasources, or timing)
3. Check for related SDTs that might be masking issues
4. Review recent changes using audit logs if available
5. Summarize findings and suggest root cause

Provide a structured analysis with:
- Alert count by severity
- Top affected devices
- Potential root causes
- Recommended actions

Composite shortcut: Use the `triage` tool to perform steps
1-4 automatically.

Argument parsing: Extract severity from words like "critical
alerts" or "errors". Time windows from "last hour" (1),
"today" (24), "this week" (168).

Expected output: Structured incident report with severity
counts, top affected devices, root cause hypothesis, and
prioritized action items."""


def capacity_review_template(arguments: dict) -> str:
    """Generate capacity review prompt content.

    Args:
        arguments: Prompt arguments (group_id, threshold_percent).

    Returns:
        Prompt text for capacity review workflow.
    """
    group_id = arguments.get("group_id", "all groups")
    threshold = arguments.get("threshold_percent", "80")

    return f"""Review resource utilization and capacity for LogicMonitor devices.

Parameters:
- Device group: {group_id}
- Alert threshold: {threshold}%

Steps to follow:
1. Use get_devices to list devices in the target group
2. Review alerts related to CPU, memory, and disk utilization
3. Check for devices with utilization above {threshold}%
4. Identify growth trends if historical data is available
5. Generate capacity recommendations

Provide a report with:
- Devices approaching capacity limits
- Current utilization metrics
- Growth trend analysis
- Recommended actions (rightsizing, cleanup, scaling)

Composite shortcut: Use the `capacity_plan` tool to automate
metric collection, trending, and forecasting.

Argument parsing: Group IDs are numeric. Threshold defaults
to 80 if not specified. "Production servers" likely maps to
a group name, not an ID.

Expected output: Table of devices sorted by utilization, with
trend indicators and days-until-threshold-breach."""


def remediation_template(arguments: dict) -> str:
    """Generate RemediationSource execution workflow prompt content.

    Args:
        arguments: Prompt arguments (host_id, remediation_source_id, alert_id).

    Returns:
        Prompt text for RemediationSource execution workflow.
    """
    host_id = arguments.get("host_id", "")
    source_id = arguments.get("remediation_source_id", "")
    alert_id = arguments.get("alert_id", "")

    return f"""Execute a LogicMonitor RemediationSource on a target device.

Parameters:
- Host ID: {host_id or "not specified"}
- Remediation Source ID: {source_id or "not specified"}
- Alert ID: {alert_id or "not specified (optional)"}

Pre-Execution Safety Checklist:
1. Verify collector version >= 39.200 using get_collector
2. Confirm device is reachable (hostStatus is not "dead") using get_device
3. Review the remediation source script using get_remediationsource
4. Check AppliesTo script matches the target device
5. Look for state-mutating keywords (restart, rm, delete, stop, kill, reboot, shutdown)
6. Verify no concurrent execution is in progress

Execution Steps:
1. Use get_remediationsource to retrieve the remediation source details
2. Review the groovyScript content and appliesTo conditions
3. Use get_device to verify the target device status and collector
4. Use get_collector to verify collector build version
5. If all checks pass, use execute_remediation to run the script
6. Use get_diagnostic_remediation_results with the host_id to verify execution
   status and review the script output

Post-Execution:
8. Verify the original alert condition has improved
9. Document the execution result with add_ops_note

Safety Constraints:
- Write permission is required (LM_ENABLE_WRITE_OPERATIONS=true)
- Cannot pause or cancel once execution starts
- Success does not guarantee resolution -- verify independently
- Do not run concurrent remediations on the same device

Argument parsing: Host ID and remediation source ID are
required integers. Alert ID is an optional string.

Expected output: Execution summary with pre-check results,
script preview, execution status, and post-execution
verification."""
