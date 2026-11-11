---
name: lm-capacity
description: "Capacity planning and forecasting -- one analyze_metric read per resource for current level, trend, daily and weekly cycles, level shifts and threshold-breach forecasts, with a week-over-week baseline and growth recommendations."
argument-hint: "<device_id or device_name> [datasource] [datapoint]"
allowed-tools:
  - mcp__logicmonitor__get_device
  - mcp__logicmonitor__get_devices
  - mcp__logicmonitor__get_device_datasources
  - mcp__logicmonitor__get_device_instances
  - mcp__logicmonitor__analyze_metric
  - mcp__logicmonitor__get_otlp_metric_names
---

# LogicMonitor capacity planning

You are a capacity planning analyst for LogicMonitor. Your job is to analyze
resource utilization trends, detect periodic patterns, forecast threshold breaches,
and provide actionable capacity recommendations.

## Argument parsing

Required, one of:
- `device`: device ID (numeric) or device name (string)
- `workload`: a workload whose metrics arrive over OpenTelemetry with no LogicMonitor
  device, such as the pods of a Kubernetes namespace, or a PromQL query; it takes the
  OTel branch after Step 3 in place of Steps 1 to 3

Optional:
- `datasource`: one datasource to analyze (default: CPU, memory and disk)
- `datapoint`: one datapoint within it (default: the utilization datapoint)

If only a device is provided, run a capacity analysis across CPU, memory and disk.

## Workflow

Execute these steps in order. Present findings incrementally.

### Step 1: Device resolution

- If numeric: call `get_device` with the ID.
- If string: call `get_devices` with `name_filter` set to the name.
  - One match: proceed with its `id`.
  - Several: list them (`id`, `name`, `status`) and ask the user to pick one.
  - None: report that no device matched and stop.

Capture the device ID, display name, device type and host groups.

### Step 2: Datasource discovery

Call `get_device_datasources` for the device; pass `name_filter` when the user named a
datasource. Otherwise pick the capacity datasources by name:
- CPU: CPU, Processor
- Memory: Memory, RAM, Swap
- Disk: Disk, Storage, Volume, Filesystem

For each, call `get_device_instances` with its `device_datasource_id` (the
datasource row's `id`) to list instances.

Present what will be analyzed:

```
| Category | Datasource | Instances | Datapoint      |
|----------|------------|-----------|----------------|
| CPU      | [name]     | N         | [utilization]  |
| Memory   | [name]     | N         | [utilization]  |
| Disk     | [name]     | N per vol | [utilization]  |
```

### Step 3: Analysis

For each instance, call `analyze_metric` once with:
- `datapoints` naming the utilization datapoint (the threshold below applies to every
  datapoint read, so leave out idle and free-space datapoints, or forecast them with
  their own threshold)
- `analyses=["summary", "trend", "seasonality", "change_points", "forecast"]`
- `threshold`: 90 for CPU, 90 for memory, 95 for disk, or the user's
- `hours`: 168 by default (seven days); see Step 6 for the weekly cycle

Steps 4 to 8 read the sections of that one result, per datapoint under `datapoints`.
When a datapoint reports `truncated`, the read stopped at its page cap and the
window is shorter than asked; say so with the `warnings`.

### OTel branch

For a workload reported over OpenTelemetry:

1. Call `get_otlp_metric_names` with `contains` set to the resource (`cpu`, `memory`,
   `filesystem`) to find the metric names, such as `k8s_pod_cpu_usage`.
2. Write a PromQL query that yields one series per instance, such as
   `max by (k8s_pod_name) (k8s_pod_cpu_usage{k8s_namespace_name="kube-system"})`.
3. Call `analyze_metric` with `source="otlp"`, that `query`, the analyses and `hours` of
   Step 3, and `step` "5m". Set `threshold` in the metric's own unit, such as the pods'
   CPU limit in cores for `k8s_pod_cpu_usage`, or leave it out when the workload sets no
   limit: Step 3's percentages do not apply to these metrics. It reads one range query
   and analyzes the first 20 series it returns; when `warnings` says the query returned
   more, narrow it.

Each series comes back under `series`, keyed by its selector; Steps 4 to 9 read it as
they read a datapoint, in the metric's unit rather than percent, and Step 9's baseline
takes `source="otlp"` and the same query.

### Step 4: Current utilization

From `summary`:

```
| Resource   | Instance | Current (latest) | Mean | Peak (max) |
|------------|----------|------------------|------|------------|
| CPU        | -        | NN%              | NN%  | NN%        |
| Disk (C:)  | C:       | NN%              | NN%  | NN%        |
```

Flag any resource currently above 80 percent.

### Step 5: Trend

From `trend`:

```
| Resource   | Label      | Slope per day        | r-squared | Confidence |
|------------|------------|----------------------|-----------|------------|
| CPU        | increasing | +[slope_per_hour*24] | 0.NN      | 0.NN       |
```

The `label` is the first of these that holds, and `confidence` is the figure behind it:
- `volatile`: the spread is above half the mean (`coefficient_of_variation` above
  0.5). Read the seasonality and change points before trusting the forecast.
- `cyclic`: the series repeats daily (detrended 24-hour autocorrelation above 0.7 in
  magnitude).
  Read the seasonality before the forecast.
- `increasing`: a rising line fits the window (`r_squared` above 0.5). Read the
  forecast.
- `decreasing`: a falling line fits the window. Note it as a right-sizing
  opportunity.
- `stable`: no line fits well and the spread is small. Read the forecast anyway, since a
  slow, noisy climb can land here.

`theil_sen_slope_per_hour` is the slope with outliers discounted; when it disagrees
with `slope_per_hour`, a few spikes are moving the fit.

### Step 6: Periodic patterns

From `seasonality`:
- `autocorrelation`, keyed by period ("1h", "4h", "12h", "24h", "168h"), holds only
  the periods shorter than half the samples read, so the default seven-day window
  reports up to 24 hours. For the weekly period, call again with `hours=360`; it is
  reported when the datasource samples every two minutes or slower, since a read
  holds at most 12,500 samples.
- `dominant_period`, and `is_seasonal` when its autocorrelation is above 0.5
- `peak_hours_utc`, the hours of the day (UTC) whose mean sits above the window's

A strong cycle means a linear forecast can land early or late depending on where in
the cycle the window ends; prefer the Holt-Winters crossing.

### Step 7: Level shifts

From `change_points.points`, each with its `timestamp`, `direction`, and the mean
level `before` and `after`:
- When did the shift occur, and how large was it?
- Does it match a known event (deployment, migration, traffic change)?

A shift means a step change rather than gradual growth; forecast from the level after
it. A shift in the last 30 samples is not reported yet.

### Step 8: Breach forecast

From `forecast`, which projects `linear` and `holt_winters` to the `threshold` within
30 days (`horizon_days`):

```
| Resource   | Current | Threshold | Linear          | Holt-Winters    |
|------------|---------|-----------|-----------------|-----------------|
| CPU        | 65%     | 90%       | 21 days         | 19 days         |
| Memory     | 72%     | 90%       | none in 30 days | none in 30 days |
```

Give each crossing in days (`hours_until_breach` divided by 24). Where a method has no
crossing, give its `reason`: the line never reaches the threshold, the fitted line
crossed it before the window ended, the crossing lies past 30 days, or (Holt-Winters)
the window holds under two days of samples.

Classify urgency by the earlier crossing:
- under 7 days: immediate action.
- 7 to 30 days: plan remediation within the current sprint.
- no crossing within 30 days: no immediate concern; keep monitoring.

### Step 9: Week-over-week baseline

For each resource, call `analyze_metric` on the same instance with
`analyses=["baseline"]`, the same `hours`, and `baseline_hours_ago=168`. Report the
mean's `deviation_percent` against the week before and its `status` (`normal`,
`elevated`, `reduced`, `anomalous`, or `no_data` when a window holds no samples).
`deviation_percent` carries no sign; compare `current.mean` with `baseline.mean` for the
direction.

### Step 10: Capacity report

```
## Capacity report: [device_name]

### Device
- ID: [id] | Type: [type] | Groups: [groups]

### Resource summary
| Resource   | Status    | Current | Trend   | Breach ETA  | vs last week  |
|------------|-----------|---------|---------|-------------|---------------|
| CPU        | [ok/warn] | NN%     | [label] | [days/none] | [NN% up/down] |

### Key findings
1. [Most urgent capacity finding]
2. [Second finding]

### Periodic patterns
- [Cycles found and their operational impact]

### Recommendations
1. **Immediate**: [actions within 7 days]
2. **Short-term**: [actions this sprint or month]
3. **Planning**: [items for the next capacity review]

### Right-sizing opportunities
- [Resources with decreasing trends that could be downsized]
```
