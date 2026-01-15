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
- Recommended actions"""


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
- Recommended actions (rightsizing, cleanup, scaling)"""


def health_check_template(arguments: dict) -> str:
    """Generate health check prompt content.

    Args:
        arguments: Prompt arguments (include_collectors).

    Returns:
        Prompt text for health check workflow.
    """
    include_collectors = arguments.get("include_collectors", "true")

    collector_section = ""
    if include_collectors.lower() == "true":
        collector_section = """
4. Use get_collectors to check collector health
5. Verify collector connectivity and version status"""

    return f"""Generate a LogicMonitor environment health summary.

Parameters:
- Include collectors: {include_collectors}

Steps to follow:
1. Use get_alerts to get current alert counts by severity
2. Use get_devices to check device status distribution
3. Check for any dead or unmonitored devices{collector_section}

Provide a health dashboard with:
- Overall health score
- Active critical/error/warning alert counts
- Device status summary (normal, dead, unmonitored)
- Collector status (if included)
- Key concerns requiring attention"""


def alert_summary_template(arguments: dict) -> str:
    """Generate alert summary prompt content.

    Args:
        arguments: Prompt arguments (group_by, hours_back).

    Returns:
        Prompt text for alert summary workflow.
    """
    group_by = arguments.get("group_by", "severity")
    hours_back = arguments.get("hours_back", "24")

    return f"""Generate an alert digest for LogicMonitor.

Parameters:
- Group by: {group_by}
- Time range: Last {hours_back} hours

Steps to follow:
1. Use get_alerts to retrieve alerts from the last {hours_back} hours
2. Group and count alerts by {group_by}
3. Identify the most significant alert clusters
4. Note any alerts that have been acknowledged or cleared

Provide a summary with:
- Total alert count
- Breakdown by {group_by}
- Top 5 most frequent alert types
- Recently cleared alerts
- Alerts requiring immediate attention"""


def sdt_planning_template(arguments: dict) -> str:
    """Generate SDT planning prompt content.

    Args:
        arguments: Prompt arguments (device_ids, group_id).

    Returns:
        Prompt text for SDT planning workflow.
    """
    device_ids = arguments.get("device_ids", "")
    group_id = arguments.get("group_id", "")

    target = "specified devices"
    if device_ids:
        target = f"devices: {device_ids}"
    elif group_id:
        target = f"device group: {group_id}"

    return f"""Plan scheduled downtime (SDT) for LogicMonitor resources.

Parameters:
- Target: {target}

Steps to follow:
1. Review current SDTs using get_sdts to avoid conflicts
2. Verify target devices exist using get_devices
3. Check for any critical alerts on target devices
4. Plan SDT window considering business hours

Provide a plan with:
- Devices/resources to include in SDT
- Recommended SDT window (start/end times)
- SDT type recommendation (DeviceSDT vs DeviceGroupSDT)
- Any conflicts with existing SDTs
- Risk assessment for the maintenance window

Note: Creating SDTs requires write permissions (LM_ENABLE_WRITE_OPERATIONS=true)"""
