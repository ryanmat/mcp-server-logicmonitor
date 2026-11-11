---
name: lm-remediate
description: "Diagnose a LogicMonitor alert and remediate it -- one diagnose call, the device's assigned RemediationSources, its action chains and Edwin AI's agent tools, the pre-execution checklist, then a confirmed execute_remediation or edwin_run_tool and its result."
argument-hint: "<alert_id or device_name>"
allowed-tools:
  - mcp__logicmonitor__diagnose
  - mcp__logicmonitor__get_diagnostic_remediation_assignments
  - mcp__logicmonitor__get_remediationsources
  - mcp__logicmonitor__get_remediationsource
  - mcp__logicmonitor__get_action_chains
  - mcp__logicmonitor__get_diagnostic_remediation_results
  - mcp__logicmonitor__get_alert_details
  - mcp__logicmonitor__execute_remediation
  - mcp__logicmonitor__get_edwin_tools
  - mcp__logicmonitor__edwin_run_tool
  - mcp__logicmonitor__add_ops_note
---

# LogicMonitor alert remediation

You diagnose a LogicMonitor alert and, when a fix exists and the operator confirms it,
run it: a LogicMonitor RemediationSource on the device, or a tool of one of Edwin AI's
agents. Nothing runs without the operator's explicit confirmation.

## Argument parsing

- An alert ID such as `LMA12345`: diagnose that alert.
- A device name: diagnose its latest open critical alert.
- No argument: ask what to remediate.

## Workflow

Execute these steps in order. After each step, present findings before moving on.

### Step 1: Diagnose

Call `diagnose` with `alert_id` or `device_name`. It returns:

- `alert`: the alert's datasource, instance, datapoint, value, thresholds and severity
- `device`: the device ID, display name, status and collector
- `correlated_alerts` and `changes`: the alerts clustered with it and the audit
  changes of the last four hours
- `blast_radius`: the devices around it
- `diagnostics`: the DiagnosticSources `assigned` to the device and their
  `latest_results`, script output included
- `warnings`: the sub-reads that failed

Present the alert, the device, and what the diagnostic output and the changes say
about the cause. Read `diagnostics.latest_results` before proposing any fix: the
diagnostic output often shows the cause already. If `diagnose` found no
alert, report that and stop.

### Step 2: Remediation options

1. Call `get_diagnostic_remediation_assignments` with `resource_id` set to the device
   ID and `module_type` "remediationsource" for the RemediationSources assigned to the
   device. `get_remediationsources` finds a source by name when the operator asks for
   one; a source outside the device's assignments runs a script written for other
   devices, so do not offer it.
2. Call `get_action_chains`. A chain with a remediation stage for this kind of alert
   may already have run without anyone asking; Step 3 checks for that run before a
   second one starts by hand.
3. When the Edwin AI tools are listed (the server has `EDWIN_CLIENT_ID` and
   `EDWIN_CLIENT_TOKEN`), call `get_edwin_tools` with `agent` set to
   `LMDiagnosticsAgent`, or the agent the operator names, for the tools Edwin's agents
   can run. Edwin publishes no input schema for them: a tool's `short_description` is
   the only guide to its parameter names, so state the parameters you would send and
   why. Without Edwin credentials, skip this item.

Present the options:

```
| Option | Kind | What it would do |
|--------|------|------------------|
| [source name] | RemediationSource | [what the script does] |
| [mcp_name / tool name] | Edwin agent tool | [from its short_description] |
```

If there are none, recommend a manual fix from the diagnosis and stop.

### Step 3: Pre-execution checklist

For a RemediationSource, complete every item before running it:

1. Read the script. Call `get_remediationsource` with the source ID and name every
   state-changing command it runs (restart, stop, kill, rm, delete, reboot, shutdown,
   service or package changes) and what each would do to this device.
2. Check for runs in progress. Call `get_diagnostic_remediation_results` with `host_id`
   set to the device ID and `module_type` "remediation". Do not start a run while
   another on the device is in progress; nothing prevents concurrent runs.
3. State what the run should change about the alert, and how to undo the change or
   that it cannot be undone.
4. Get explicit confirmation from the operator, naming the device, the source and the
   commands from item 1.

For an Edwin agent tool, state the `mcp_name`, the tool name and every parameter, say
what the tool's `short_description` says it does, and get explicit confirmation.
Edwin's own result is the only record of what the tool did.

### Step 4: Run

- RemediationSource: call `execute_remediation` with `host_id`,
  `remediation_source_id` and the alert's ID as `alert_id`. It refuses a device whose
  status is dead or dead-collector and a collector older than 39.200. A run cannot be
  paused or cancelled once it starts.
- Edwin agent tool: call `edwin_run_tool` with `mcp_name`, `tool_name` and
  `parameters`. A tool that reports failure returns `REJECTED_BY_TOOL` with Edwin's
  error.

Both tools need write operations enabled on the server; with them off the call is
refused. Say so and leave the recommendation.

### Step 5: Verify

1. For a RemediationSource, call `get_diagnostic_remediation_results` with `host_id`
   and `remediation_source_id` for the run's status and script output.
2. Call `get_alert_details` with the alert's ID. A run that succeeded has fixed nothing
   until the alert condition clears; say whether it has.
3. Record what ran and its result with `add_ops_note` on the device, after the
   operator confirms the note.

## Output format

Use a header per step. End with:

```
## Remediation summary
- Alert: [alert ID] on [device] ([datasource] [datapoint], [severity])
- Cause: [one line from the diagnosis]
- Ran: [source or Edwin tool], confirmed by the operator / nothing ran
- Result: [status and output in one line]
- Alert after the run: [cleared / still open]
```
