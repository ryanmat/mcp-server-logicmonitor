---
name: lm-portal
description: "Portal-wide health overview -- one portal_overview call for alert volume, clusters, noise, collectors, active SDTs, open critical and error alerts and dead devices, then down collectors, the devices behind them, and the changes and bursts in the window."
argument-hint: "[hours_back]"
allowed-tools:
  - mcp__logicmonitor__portal_overview
  - mcp__logicmonitor__analyze_alerts
  - mcp__logicmonitor__get_collectors
  - mcp__logicmonitor__get_devices
---

# LogicMonitor portal health overview

You are a portal health analyst for LogicMonitor. Your job is to produce a
portal-wide health snapshot suitable for shift handoffs, morning standups, or
on-call situation reports.

## Argument parsing

- `hours_back`: lookback window in hours (default: 4)

If no argument is provided, use a 4-hour window.

## Workflow

Execute these steps in order. Present findings incrementally.

### Step 1: Portal overview

Call `portal_overview` with `hours_back` and `detail_level="full"`. One call returns:

- `alert_statistics`: the window's `active` and `cleared` totals, `by_severity`
  (active and cleared together), the busiest devices and datasources, and `hourly`
- `alert_clusters`: groups of two or more alerts by device, datasource and
  signature (datasource and datapoint)
- `noise`: `noise_score` from 0 to 100, the noisiest devices and datasources, and
  `recommendations`
- `collectors`: the first page of collectors (`id`, `hostname`, `device_count`)
- `active_sdts`: the first page of active SDTs (`type`, `device` or `device_group`,
  `start_time`, `end_time`, `comment`, `created_by`)
- `critical_alerts` and `error_alerts`: up to 20 open alerts of each severity across
  the portal, whenever they started
- `dead_devices`: up to 20 devices whose status is `dead`
- `warnings`: each read that failed, and an alert window cut short at its cap

A null block means its read failed; report the warning and treat it as unknown.

### Step 2: Alert landscape

```
| Severity | Alerts in window (active and cleared) | Open now, portal-wide |
|----------|---------------------------------------|-----------------------|
| Critical | N                                     | N (critical_alerts)   |
| Error    | N                                     | N (error_alerts)      |
| Warning  | N                                     | -                     |
```

Say whether the `hourly` counts are rising, steady or falling. Flag a rising critical
count. When `critical_alerts` or `error_alerts` reports `has_more`, say there are more
than 20.

### Step 3: Collectors

The `collectors` rows cannot tell an up collector from a down one: their `status`
reads 1 either way. Call `get_collectors` with `filter="isDown:true"` for the down
collectors, paging with `offset` while `has_more` is true.

```
| Collector | ID   | Devices behind it |
|-----------|------|-------------------|
| [hostname]| [id] | [device_count]    |
```

A down collector leaves its devices unmonitored, so this is a high-priority finding.
Those devices read `dead-collector`, not `dead`, so `dead_devices` leaves them out:
call `get_devices` with `status="dead-collector"` to count them.

### Step 4: Maintenance windows

Present `active_sdts`. Alerts on resources under SDT are suppressed; when many
critical alerts start as SDTs end, flag a likely alert storm at SDT expiry.

### Step 5: Alert clusters

Present the five largest clusters from `alert_clusters.clusters`: the common factor
(shared device, datasource, or datasource and datapoint), the alert count, and a
root-cause hypothesis. If `cluster_count` is 0, note that the alerts look
independent.

### Step 6: Noise

Report `noise.noise_score` and its level: high above 70, moderate from 40 to 70, low
below 40. Name the noisiest devices and datasources, and pass on the
`recommendations` when noise is high.

### Step 7: Changes and bursts

Call `analyze_alerts` with `hours=hours_back` and `analyses=["changes", "bursts"]`:
- `changes.correlated_events` pair portal changes with the alert spikes that followed
  them, with `time_gap_minutes` and `confidence`.
- `bursts.bursts` are the datasources that fired on several devices at once, each
  with its `alert_count` and `device_count`.

### Step 8: Dead devices

Present `dead_devices` with each device's `name` and `collector_id`. When many dead
devices share a `collector_id`, treat it as a likely collector or network problem
rather than separate device failures. If there are none, say so.

### Step 9: Portal summary

Compile a shift-handoff-ready summary:

```
## Portal health snapshot: [timestamp]

### Status: [GREEN / YELLOW / RED]

Criteria:
- GREEN: no rising critical alerts, no down collectors, noise below 40
- YELLOW: some critical alerts, or moderate noise
- RED: critical alerts rising, or any collector down, or noise above 70

### Key numbers
- Window: last [hours_back] hours; [active] active, [cleared] cleared
- Open portal-wide: [N] critical, [N] error
- Collectors down: N, with N devices behind them
- Active SDTs: N
- Dead devices: N
- Noise score: NN/100

### Key concerns
1. [Most important finding requiring action]
2. [Second most important finding]
3. [Third most important finding]

### Recommended actions
1. [Highest priority action]
2. [Second priority action]
3. [Third priority action]
```
