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

    return f"""Triage the LogicMonitor alerts of the last {hours} hours.

Parameters:
- Severity filter: {severity}
- Time window: Last {hours} hours

Steps to follow:
1. Call `triage` with hours_back set to {hours} and the severity filter (leave it out
   for all severities). One call reads the window's alerts once, active and cleared,
   and returns statistics, clusters (by device, by datasource, and by datasource and
   datapoint), a noise score, the audit changes that preceded alert spikes, and
   blast-radius counts for up to three of the largest device clusters.
2. Read the noise score. Above 70, alerting is noisy: name the noisiest
   devices and datasources and pass on the tuning recommendations. The high_alert_noise
   scenario in lm://guide/best-practices says what to tune.
3. For each cluster, state the common factor and a root-cause hypothesis. A
   blast-radius row with a critical alert count above 0 is the first to escalate; an
   unreadable count above 0 means that impact is unknown, not low.
4. Read the changes: a portal change followed by a spike minutes later is the first
   suspect.
5. When the hourly volume spikes, call `analyze_alerts` over the same window with
   analyses ["bursts"] for the datasources that fired on many devices at once.
6. To list or page the open alerts themselves, call `get_alerts` with cleared=false;
   lm://filters/alerts lists the fields its filter takes. Read one alert in full with
   `get_alert_details`.

What the tools leave to you:
- A null section in the triage result means its read failed. Report the warning and
  treat that section as unknown, not empty.
- The severity counts include cleared alerts; the active count is the open total.
- Acknowledge alerts or add notes only with the operator's explicit confirmation.

Argument parsing: Extract severity from words like "critical alerts" or "errors".
Time windows from "last hour" (1), "today" (24), "this week" (168).

Expected output: Structured incident report with the open and cleared counts, top
affected devices, clusters with root-cause hypotheses, the changes that preceded
spikes, and prioritized action items."""


def capacity_review_template(arguments: dict) -> str:
    """Generate capacity review prompt content.

    Args:
        arguments: Prompt arguments (group_id, threshold_percent).

    Returns:
        Prompt text for capacity review workflow.
    """
    group_id = arguments.get("group_id", "all groups")
    threshold = arguments.get("threshold_percent", "80")

    return f"""Review the capacity of LogicMonitor devices.

Parameters:
- Device group: {group_id}
- Alert threshold: {threshold}%

Steps to follow:
1. Call `get_devices` with group_id set to the group to list its devices. Without a
   group, ask which devices to review; lm://filters/devices lists the fields its
   filter takes, to narrow the list by name, type or status.
2. For each device, call `capacity_plan` with its device_id and threshold {threshold}.
   Each forecast summary row is one datapoint: its trend label and, for the linear and
   Holt-Winters forecasts, the hours until it crosses the threshold, or a status
   saying why no forecast was made.
3. The threshold applies to every datapoint read, so judge the utilization rows. For
   an idle or free-space datapoint a crossing means the reverse, and it needs a
   threshold of its own.
4. Rank the devices by the earliest crossing: under 7 days is urgent, 7 to 30 days
   belongs in this sprint's plan.

When no forecast crosses the threshold within 30 days, that says only that the fitted
line does not reach it in that time; it is not proof of headroom. For each such
utilization datapoint:
- Call `analyze_metric` on its instance with analyses ["summary", "change_points"];
  the device datasource and instance ids come from `get_device_datasources` and
  `get_device_instances`. A latest or peak value within 10 points of the threshold
  leaves no room for a step change.
- A recent level shift means the trend spans two regimes. Read again with hours
  covering only the time since the shift, and forecast from the new level.
- A cyclic or volatile trend label means daily peaks can reach the threshold while
  the fitted line does not. Compare the peak with the threshold.
- A datapoint far below the threshold for the whole window, with a stable or
  decreasing trend, is a right-sizing candidate.

Argument parsing: Group IDs are numeric. Threshold defaults to 80 if not specified.
"Production servers" likely maps to a group name, not an ID.

Expected output: Table of devices sorted by the earliest crossing, with the current
level, trend label and days until the threshold, then the flat-forecast findings and
right-sizing candidates."""


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

    return f"""Run a LogicMonitor RemediationSource on a device, after the checks the tool
does not make.

Parameters:
- Host ID: {host_id or "not specified"}
- Remediation Source ID: {source_id or "not specified"}
- Alert ID: {alert_id or "not specified (optional)"}

Pre-execution checklist (complete every item before calling execute_remediation):
1. Find the source. Call `get_diagnostic_remediation_assignments` with the host ID as
   resource_id (or the alert ID) and module_type "remediationsource" for the sources
   assigned to the device. `get_remediationsources` lists every source by name.
2. Confirm it applies. The source must be among the device's assignments; one outside
   them runs a script written for other devices.
3. Read the script. Call `get_remediationsource` with the source ID and read its
   Groovy script. Name every state-changing command it runs (restart, stop, kill, rm,
   delete, reboot, shutdown, service or package changes) and what each would do to
   this device. The tool shows the script only after it has run.
4. Check for runs in progress. Call `get_diagnostic_remediation_results` with the host
   ID and module_type "remediation". Do not start a run while another on the device
   is still in progress; the tool does not prevent concurrent runs.
5. Know the alert. With an alert ID, read it with `get_alert_details` and state what
   the remediation should change about it.
6. Say how to undo the change, or that it cannot be undone.
7. Get explicit confirmation from the operator, naming the device, the source and the
   commands from item 3. The remediation_execution scenario in
   lm://guide/best-practices lists the same checks.

Execution:
8. Call `execute_remediation` with the host ID, the source ID and, when given, the
   alert ID. It refuses a device whose status is dead and a collector older than
   39.200, and it needs write operations enabled on the server. A run cannot be paused
   or cancelled once it starts.

After the run:
9. Call `get_diagnostic_remediation_results` with the host ID and the source ID for
   the run's status and script output.
10. Read the alert again with `get_alert_details`. A run that succeeded has fixed
    nothing until the alert condition clears.
11. Record what ran and its result with `add_ops_note` on the device.

Argument parsing: Host ID and remediation source ID are integers. Alert ID is an
optional string, such as LMA12345.

Expected output: The checklist with each item's result, the script's state-changing
commands, the confirmation, the execution status and output, and the alert's state
after the run."""
