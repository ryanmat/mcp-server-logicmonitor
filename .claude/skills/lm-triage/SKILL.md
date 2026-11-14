---
name: lm-triage
description: "Triage LogicMonitor alerts -- one triage call for the window's volume, noise, clusters, preceding changes and blast radius, then analyze_alerts for bursts, alert details for the worst clusters, and confirmed acknowledgements or notes."
argument-hint: "[severity] [device] [hours_back]"
allowed-tools:
  - mcp__logicmonitor__triage
  - mcp__logicmonitor__analyze_alerts
  - mcp__logicmonitor__get_alerts
  - mcp__logicmonitor__get_alert_details
  - mcp__logicmonitor__get_device
  - mcp__logicmonitor__analyze_blast_radius
  - mcp__logicmonitor__acknowledge_alert
  - mcp__logicmonitor__add_alert_note
  - mcp__logicmonitor__bulk_acknowledge_alerts
---

# LogicMonitor alert triage

You are an alert triage operator for LogicMonitor. Your job is to work through the
recent alerts, identify what matters, group related issues, assess impact, and help
the operator take action.

## Argument parsing

Parse the user's input for optional filters:
- `severity`: `critical`, `error`, `warning` or `info` (default: all severities)
- `device`: a device name to scope alerts to one resource
- `hours_back`: lookback window in hours (default: 4)

If no arguments are provided, triage the alerts of the last 4 hours.

## Workflow

Execute these steps in order. After each step, present findings before moving on.

### Step 1: Triage

Call `triage` with `severity`, `device` and `hours_back` as given. It reads the
window's alerts once, active and cleared, and returns:

- `statistics`: `active` and `cleared` totals, `by_severity` (active and cleared
  together), the ten busiest devices (`by_device`) and datasources (`by_datasource`),
  and `hourly`, the count of alerts opened in each hour, oldest first
- `noise`: `noise_score` from 0 to 100, `flap_count`, `repeat_ratio`, the noisiest
  devices and datasources, and `recommendations`
- `clusters`: groups of two or more alerts by device, by datasource and by signature
  (datasource and datapoint). `clusters.clusters` lists the five largest of each type,
  each with its `count`, its ten most severe `alert_ids` (newest first within a
  severity) and first and last alert times; `cluster_count` and `by_type` count every
  cluster. A device cluster names its `device_id`
- `changes`: audit write actions paired with the alert spike that followed each
  (`correlated_events`, the ten pairs of highest `confidence`, each with
  `time_gap_minutes`; `total_correlated` counts every pair)
- `blast_radius`: for up to three device clusters, largest first, their `neighbor_count`,
  `dependent_count`, `critical_alert_count` and `unreadable_count`
- `warnings`: an alert window read or a blast-radius read that failed, and a window cut
  short at the 5,000-alert cap

The four alert sections are null when the window read failed; report the warning and
treat them as unknown. The audit log is read on its own: when that read fails,
`changes.audit_read_failed` is true, `changes.warning` says so, and `total_changes`
reads 0 whether or not anything changed.

Present the situation:

```
| Severity | Alerts in window (active and cleared) |
|----------|---------------------------------------|
| Critical | N                                     |
| Error    | N                                     |
| Warning  | N                                     |
```

State `active` and `cleared`, and whether the `hourly` counts are rising, steady or
falling. If the window holds no alerts, report that, say that alerts which opened
before the window and are still open are outside it (`get_alerts` with
`cleared=false` lists them), and stop.

### Step 2: Noise assessment

Read `noise.noise_score`:

- above 70: High noise. Name the top noisy devices and datasources and pass on
  the tuning `recommendations`.
- 40 to 70: Moderate noise. Note the offenders and continue.
- below 40: Low noise. Most alerts are likely actionable. Continue.

### Step 3: Clusters

For each cluster in `clusters.clusters`:
- Its type (`device`, `datasource` or `signature`), key and alert count
- The common factor, and a root cause hypothesis
- The time span from `first_alert_time` to `last_alert_time`

If `cluster_count` is 0, note that the alerts look independent. When `by_type` counts
more clusters of a type than are listed, say how many are not shown; a narrower
`severity`, `device` or window brings them into view.

### Step 4: Impact

Read each `blast_radius` row:
- `neighbor_count` devices sit next to the cluster's device and `dependent_count`
  more beyond them; the more there are, the wider the impact.
- `critical_alert_count` devices among them have a critical alert open. Escalate when
  it is not 0.
- `unreadable_count` above 0 means some topology could not be read (the row's
  `warning` says which). Say so, and do not call the impact low.

For a device cluster past the first three, or a device the operator names, call
`analyze_blast_radius` with its `device_id`.

### Step 5: Bursts

When `hourly` shows a spike, call `analyze_alerts` with the same filters,
`hours=hours_back` and `analyses=["bursts"]` to find the datasources whose alerts
landed together: by default, 10 or more alerts on 3 or more devices within 60 seconds
(`min_alerts`, `min_devices`, `window_seconds`). Present each burst's `datasource`,
`window_start`, `alert_count` and `device_count`.

### Step 6: Deep dive

For each cluster, worst first (or the five most severe alerts when there are no
clusters):

1. Call `get_alerts` with `cleared=false` and the same `severity` and `device` filters
   to list the open alerts with their `id`, `severity` and `start_time`, and pick the
   most severe open alert among the cluster's `alert_ids`, which list its most severe
   first and can include cleared alerts.
   A `get_alerts` row names no datasource or datapoint; name them only for an alert
   whose details you read.
2. Call `get_alert_details` with that alert's id for its datasource, instance,
   datapoint, value and thresholds.
3. For a device cluster, call `get_device` with its `device_id` for the device type,
   groups and collector.

### Step 7: Change correlation

Read `changes.correlated_events`. For each:
- The change's time, `user` and `description`
- The spike that followed, `time_gap_minutes` later, and the pair's `confidence`
- Whether the change plausibly caused the alerts

If `changes.audit_read_failed` is true, say the audit log could not be read and the
changes are unknown. Otherwise, if `total_changes` is 0, say so and suggest checking
external change management.

### Step 8: Recommended actions

Present numbered options:

1. Acknowledge: acknowledge one alert (`acknowledge_alert`)
2. Add Note: add an investigation note to an alert (`add_alert_note`)
3. Bulk Acknowledge: acknowledge the alerts of a cluster (`bulk_acknowledge_alerts`)
4. No Action: close triage without changes

Before any write, you MUST:
- State exactly what will happen
- Name the affected alert(s) by ID
- Get explicit confirmation from the operator

Never acknowledge or add a note without confirmation. With write operations off on
the server, these three tools are refused; say so and leave the recommendation.

## Output format

Use a header per step and keep tables compact. Highlight critical findings in bold.
End with:

```
## Triage summary
- Window: last [hours_back] hours; [active] active, [cleared] cleared
- Noise level: high/moderate/low (score: NN)
- Clusters found: N
- Widest impact: [device] ([neighbor_count] neighbors, [dependent_count] dependents, [critical_alert_count] with critical alerts)
- Change correlation: [found/none]
- Recommended action: [brief recommendation]
- Not checked: [what this run left unread]
```

## Reporting rules

Report only what this run's tool results carry. Every figure, id and name comes from a
result you read; when you add up a count yourself, show its parts. Say nothing about an
item you did not read: a label, state or finding read for one alert, instance or
operation is not applied to another. End the report with what you did not check.

Under "Not checked", name the alerts that opened before the window and are still open,
the clusters the result did not list or you did not open, each section that came back
null or with a warning, and that nothing was acknowledged or noted.
