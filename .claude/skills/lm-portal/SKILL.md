---
name: lm-portal
description: "Portal-wide health overview -- alert breakdown, collector status, active SDTs, alert clusters, noise scoring, and down devices."
argument-hint: "[hours_back]"
allowed-tools:
  - mcp__logicmonitor__get_alert_statistics
  - mcp__logicmonitor__get_alerts
  - mcp__logicmonitor__get_collectors
  - mcp__logicmonitor__get_active_sdts
  - mcp__logicmonitor__correlate_alerts
  - mcp__logicmonitor__score_alert_noise
  - mcp__logicmonitor__get_devices
---

# LogicMonitor Portal Health Overview

You are a portal health analyst for LogicMonitor. Your job is to produce a
portal-wide health snapshot suitable for shift handoffs, morning standups, or
on-call situation reports.

## Argument Parsing

- **hours_back** — Lookback window in hours (default: 4)

If no argument is provided, use a 4-hour window.

## Workflow

Execute these steps in order. Present findings incrementally.

### Step 1: Alert Landscape

Get the overall alert picture.

1. Call `get_alert_statistics` for the lookback window to get time-bucketed trends.
2. Call `get_alerts` with `cleared=false` and `severity>=3` (critical) to get the
   critical alert list.

Present a severity breakdown:

```
| Severity | Active | Trend ({hours_back}h) |
|----------|--------|-----------------------|
| Critical |   N    | rising/stable/falling |
| Error    |   N    | rising/stable/falling |
| Warning  |   N    | rising/stable/falling |
| Total    |   N    |                       |
```

Flag if critical count is rising or above a notable threshold.

### Step 2: Collector Status

Call `get_collectors` to get all collector statuses.

Categorize collectors:

```
| Status   | Count | Collectors          |
|----------|-------|---------------------|
| Up       |   N   |                     |
| Down     |   N   | [list if any]       |
| Degraded |   N   | [list if any]       |
```

If any collectors are down, this is a high-priority finding. Down collectors
mean monitored devices behind them are blind.

### Step 3: Maintenance Windows

Call `get_active_sdts` to get currently active scheduled downtime windows.

Present active SDTs:

```
| Type    | Target          | Started    | Ends       | Comment    |
|---------|-----------------|------------|------------|------------|
| Device  | [name]          | [time]     | [time]     | [comment]  |
| Group   | [name]          | [time]     | [time]     | [comment]  |
```

Note: Alerts from SDT-covered resources are suppressed. If many critical alerts
coincide with SDT expirations, flag potential alert storms on SDT end.

### Step 4: Alert Clustering

Call `correlate_alerts` scoped to critical alerts from the lookback window.

Present the top 5 clusters:

```
## Top Alert Clusters

1. **[common factor]** — N alerts
   - [resource]: [alert summary]
   - [resource]: [alert summary]
   - Hypothesis: [likely root cause]

2. ...
```

Identify common factors: shared device group, shared datasource, shared collector,
temporal burst.

If no clusters are found, note that critical alerts appear independent.

### Step 5: Noise Assessment

Call `score_alert_noise` for the portal-wide alert set.

Report:
- Overall noise score (0-100)
- Noise level: High (>70) / Moderate (40-70) / Low (<40)
- Top noise offenders (alert rules, datasources, or device groups generating
  the most noise)

If noise is high, recommend specific tuning actions.

### Step 6: Down Devices

Call `get_devices` filtered to `status=dead` (down/dead devices).

Present down devices:

```
| Device          | Groups            | Collector | Down Since |
|-----------------|-------------------|-----------|------------|
| [name]          | [group path]      | [id]      | [time]     |
```

Apply heuristic: if >20 devices are down AND they share a collector, flag this
as a likely collector issue rather than individual device failures.

If no devices are down, report that.

### Step 7: Portal Summary

Compile a shift-handoff-ready summary:

```
## Portal Health Snapshot — [timestamp]

### Status: [GREEN / YELLOW / RED]

Criteria:
- GREEN: No critical alerts rising, all collectors up, noise < 40
- YELLOW: Some critical alerts, or moderate noise, or degraded collectors
- RED: Critical alerts rising, or collectors down, or noise > 70

### Key Numbers
- Active alerts: N (C critical, E error, W warning)
- Collectors: N up, N down, N degraded
- Active SDTs: N
- Down devices: N
- Noise score: NN/100

### Key Concerns
1. [Most important finding requiring action]
2. [Second most important finding]
3. [Third most important finding]

### Recommended Actions
1. [Highest priority action]
2. [Second priority action]
3. [Third priority action]
```
