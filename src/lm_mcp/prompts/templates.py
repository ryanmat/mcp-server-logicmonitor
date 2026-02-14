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


def cost_optimization_template(arguments: dict) -> str:
    """Generate cost optimization review prompt content.

    Args:
        arguments: Prompt arguments (cloud_account_id, time_range).

    Returns:
        Prompt text for cost optimization workflow.
    """
    account = arguments.get("cloud_account_id", "all accounts")
    time_range = arguments.get("time_range", "30d")

    return f"""Review cloud cost optimization opportunities in LogicMonitor.

Parameters:
- Cloud account: {account}
- Time range: {time_range}

Steps to follow:
1. Use get_cost_summary to review current spending trends
2. Use get_cost_recommendations to identify optimization opportunities
3. Use get_idle_resources to find underutilized or idle resources
4. Prioritize recommendations by potential savings
5. Cross-reference with active alerts for at-risk resources

Provide a report with:
- Current cost summary and trends
- Top cost optimization recommendations
- Idle resources that could be terminated or downsized
- Estimated monthly savings if recommendations are applied
- Risk assessment for each recommendation"""


def audit_review_template(arguments: dict) -> str:
    """Generate audit review prompt content.

    Args:
        arguments: Prompt arguments (hours_back, username).

    Returns:
        Prompt text for audit review workflow.
    """
    hours_back = arguments.get("hours_back", "24")
    username = arguments.get("username", "all users")

    return f"""Review recent activity and security events in LogicMonitor.

Parameters:
- Time window: Last {hours_back} hours
- Username filter: {username}

Steps to follow:
1. Use get_audit_logs to retrieve recent activity
2. Use get_login_audit with failed_only=true to identify failed login attempts
3. Use get_change_audit to review configuration changes
4. Look for unusual patterns: off-hours access, bulk changes, new users

Provide a report with:
- Summary of recent activity
- Failed login attempts and source IPs
- Configuration changes by user
- Any suspicious or unusual activity
- Recommendations for security improvements"""


def alert_correlation_template(arguments: dict) -> str:
    """Generate alert correlation analysis prompt content.

    Args:
        arguments: Prompt arguments (hours_back, severity, device_id, group_id).

    Returns:
        Prompt text for alert correlation workflow.
    """
    hours_back = arguments.get("hours_back", "4")
    severity = arguments.get("severity", "all severities")
    device_id = arguments.get("device_id", "")
    group_id = arguments.get("group_id", "")

    scope_section = ""
    if device_id:
        scope_section = f"\n- Scope: Device ID {device_id}"
    elif group_id:
        scope_section = f"\n- Scope: Device Group ID {group_id}"

    return f"""Analyze and correlate active alerts in LogicMonitor.

Parameters:
- Time window: Last {hours_back} hours
- Severity filter: {severity}{scope_section}

Steps to follow:
1. Use correlate_alerts with hours_back={hours_back} to get alert clusters
   grouped by device, datasource, and temporal proximity
2. Use get_alert_statistics with hours_back={hours_back} to get severity
   distribution and time-bucket trends
3. For each device cluster, use get_device_neighbors to map topology context
4. Use get_change_audit to check for configuration changes in the time window
5. Build a correlation matrix: which alerts share devices, datasources, or timing

Decision branches:
- If a single device has many alerts: deep-dive with get_device_datasources
  and get_device_data to check for underlying resource exhaustion
- If a datasource cluster spans multiple devices: likely a systemic issue
  (e.g., network segment, shared dependency, monitoring template problem)
- If temporal cluster aligns with a config change: correlate cause and effect
- If topology neighbors share alerts: investigate upstream network devices

Provide a report with:
- Alert clusters grouped by device, datasource, and time
- Network topology context for correlated alerts
- Correlation with recent configuration changes
- Root cause hypothesis with confidence assessment
- Impact assessment (devices, services, business impact)
- Prioritized investigation order and recommended actions"""


def collector_health_template(arguments: dict) -> str:
    """Generate collector health review prompt content.

    Args:
        arguments: Prompt arguments (collector_group_id).

    Returns:
        Prompt text for collector health workflow.
    """
    group_id = arguments.get("collector_group_id", "all groups")

    return f"""Review LogicMonitor collector health and status.

Parameters:
- Collector group: {group_id}

Steps to follow:
1. Use get_collectors to list all collectors and their status
2. Check for down collectors (isDown=true)
3. Compare collector build versions to identify outdated collectors
4. Review collector group assignments for load balancing
5. Check for collectors with high device counts

Provide a report with:
- Collector status summary (up/down counts)
- Collectors running outdated versions
- Collector group distribution and balance
- Collectors needing attention (down, outdated, overloaded)
- Recommended actions for collector maintenance"""


def troubleshoot_device_template(arguments: dict) -> str:
    """Generate device troubleshooting prompt content.

    Args:
        arguments: Prompt arguments (device_id required, hours_back).

    Returns:
        Prompt text for device troubleshooting workflow.
    """
    device_id = arguments.get("device_id", "unknown")
    hours_back = arguments.get("hours_back", "24")

    return f"""Troubleshoot a specific device in LogicMonitor.

Parameters:
- Device ID: {device_id}
- Time window: Last {hours_back} hours

Steps to follow:
1. Use get_device to retrieve device details and current status
2. Use get_alerts filtered to this device for recent alert history
3. Use get_device_datasources to check applied monitoring
4. Use get_device_properties to review configuration properties
5. Check for active SDTs that might mask issues

Provide a report with:
- Device status and basic information
- Active and recent alerts for the device
- Datasource health and data collection status
- Any configuration issues identified
- Recommended troubleshooting steps"""


def top_talkers_template(arguments: dict) -> str:
    """Generate top alert talkers analysis prompt content.

    Args:
        arguments: Prompt arguments (hours_back, limit, group_by).

    Returns:
        Prompt text for top talkers analysis workflow.
    """
    hours_back = arguments.get("hours_back", "24")
    limit = arguments.get("limit", "10")
    group_by = arguments.get("group_by", "device")

    return f"""Identify the noisiest alert sources in LogicMonitor.

Parameters:
- Time window: Last {hours_back} hours
- Top N results: {limit}
- Group by: {group_by}

Steps to follow:
1. Use get_alert_statistics with hours_back={hours_back} to get aggregated
   alert counts by severity, device, and datasource
2. Sort results by {group_by} alert count (descending) to find top {limit}
3. For each top talker:
   a. If grouping by device: use get_device to get device details (type,
      groups, properties) for context
   b. If grouping by datasource: identify which devices are affected
4. Use get_active_sdts to check if any top talkers are already in SDT
5. Use get_alert_rules to check if noisy sources have appropriate thresholds

Provide a ranked report with:
- Top {limit} alert sources ranked by volume
- Alert count breakdown by severity for each source
- Device or datasource details for context
- Active SDTs that may be masking additional noise
- Recommendations for each top talker:
  - Threshold tuning (raise thresholds to reduce noise)
  - SDT scheduling (recurring maintenance windows)
  - Alert rule changes (escalation chain adjustments)
  - Investigation needed (genuine issues requiring attention)"""


def rca_workflow_template(arguments: dict) -> str:
    """Generate root cause analysis workflow prompt content.

    Args:
        arguments: Prompt arguments (device_id, alert_id, hours_back).

    Returns:
        Prompt text for RCA workflow.
    """
    device_id = arguments.get("device_id", "")
    alert_id = arguments.get("alert_id", "")
    hours_back = arguments.get("hours_back", "4")

    starting_point = "Start by identifying the scope of the issue."
    if alert_id:
        starting_point = (
            f"Start with alert {alert_id} using get_alert_details "
            "to understand the triggering condition."
        )
    elif device_id:
        starting_point = (
            f"Start with device {device_id} using get_device and "
            "get_alerts to understand the current state."
        )

    return f"""Perform a root cause analysis for a LogicMonitor incident.

Parameters:
- Starting alert: {alert_id or 'not specified'}
- Starting device: {device_id or 'not specified'}
- Time window: Last {hours_back} hours

Phase 1 - Gather Context:
{starting_point}

Phase 2 - Correlate:
1. Use correlate_alerts with hours_back={hours_back} to find related
   alert clusters (device, datasource, and temporal groupings)
2. For impacted devices, use get_device_neighbors to map the network
   topology and identify upstream/downstream dependencies

Phase 3 - Build Timeline:
3. Sort correlated alerts by start time to see propagation pattern
4. Use get_change_audit to check for configuration changes in the
   time window that may have triggered the incident

Phase 4 - Investigate (Decision Branches):
- If topology cluster found: investigate the upstream device first,
  as it may be the root cause propagating downstream
- If configuration change correlates: assess whether rollback is needed
  and use get_audit_logs for the specific change details
- If metric anomaly suspected: use get_metric_anomalies on the primary
  device to identify resource exhaustion or unusual patterns
- If datasource cluster spans devices: likely a systemic issue such as
  a network segment failure or shared infrastructure problem

Phase 5 - Synthesize:
5. Formulate root cause hypothesis with supporting evidence
6. Assess confidence level (high/medium/low) based on evidence strength
7. Map blast radius: all affected devices, services, and business impact

Provide a structured RCA report with:
- Root cause hypothesis and confidence level
- Evidence chain (timeline of events leading to the issue)
- Topology and dependency context
- Blast radius assessment
- Recommended remediation actions (immediate and long-term)
- Prevention recommendations"""


def capacity_forecast_template(arguments: dict) -> str:
    """Generate capacity forecast and planning prompt content.

    Args:
        arguments: Prompt arguments (device_id, group_id, datasource,
                   hours_back, threshold).

    Returns:
        Prompt text for capacity forecast workflow.
    """
    device_id = arguments.get("device_id", "")
    group_id = arguments.get("group_id", "")
    datasource = arguments.get("datasource", "CPU")
    hours_back = arguments.get("hours_back", "168")
    threshold = arguments.get("threshold", "80")

    target = "all monitored devices"
    if device_id:
        target = f"device {device_id}"
    elif group_id:
        target = f"device group {group_id}"

    return f"""Analyze resource utilization and forecast capacity for LogicMonitor devices.

Parameters:
- Target: {target}
- Datasource focus: {datasource}
- Analysis window: Last {hours_back} hours
- Warning threshold: {threshold}%

Phase 1 - Identify Targets:
1. Use get_devices to identify target devices
   (filter by group if group_id specified)
2. For each device, use get_device_datasources to find the {datasource}
   datasource and its instances

Phase 2 - Collect Metrics:
3. Use get_device_instances to list instances for the datasource
4. Use get_device_data to retrieve metric data over the analysis window

Phase 3 - Analyze:
5. Use get_metric_anomalies to detect unusual spikes or patterns in
   the collected data
6. Use get_alerts with datasource filter to find historical threshold
   breaches that indicate capacity pressure

Phase 4 - Forecast:
7. Calculate current average utilization for each target
8. Identify trend direction (growing, stable, declining) based on
   comparing first-half vs second-half of the analysis window
9. Estimate days until {threshold}% threshold breach if trend continues

Provide a capacity report with:
- Current utilization summary for each target device
- Trend analysis (growing, stable, or declining)
- Anomaly detection results (unusual spikes or drops)
- Historical threshold breach frequency
- Forecast: estimated days until capacity threshold breach
- Prioritized recommendations:
  - Immediate action needed (already above {threshold}%)
  - Near-term risk (trending toward breach within 30 days)
  - Monitor closely (growing but sufficient headroom)
  - No action needed (stable or declining utilization)"""
