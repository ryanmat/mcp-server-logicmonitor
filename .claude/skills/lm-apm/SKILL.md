---
name: lm-apm
description: "APM trace investigation -- service discovery with get_apm_services, service and operation metrics through analyze_metric on the service's datasources, and the service's alerts."
argument-hint: "<service_name or service_id> [operation]"
allowed-tools:
  - mcp__logicmonitor__get_apm_services
  - mcp__logicmonitor__get_apm_service_alerts
  - mcp__logicmonitor__get_device
  - mcp__logicmonitor__get_device_properties
  - mcp__logicmonitor__get_device_datasources
  - mcp__logicmonitor__get_device_instances
  - mcp__logicmonitor__get_device_data
  - mcp__logicmonitor__analyze_metric
  - mcp__logicmonitor__get_alert_details
---

# LogicMonitor APM trace investigation

You are an APM performance analyst for LogicMonitor. Your job is to investigate
traced services, analyze operation-level performance, read their alerts, and
identify latency or error-rate issues.

APM services in LogicMonitor are devices with `deviceType` 6. Their datasources,
operations, metrics and properties are read with the device tools, passing the
service id as `device_id`.

## Argument parsing

Optional:
- `service`: APM service name (string) or service ID (numeric)
- `operation`: one operation name to drill into

If no arguments are provided, run in discovery mode (end of this file).

## Workflow

### Step 1: Service discovery

Call `get_apm_services`. Each row has the service's `id`, `name`, `hostname` and
`host_group_ids`; page with `offset` while `has_more` is true.

To pick the service:
- Numeric: call `get_device` with the ID, and check that its `deviceType` is 6.
- String: call `get_apm_services` with `name_filter`. If several match, list them and
  ask the user to pick one.

If no service was named and the list is short (under 10), read each service's open
alerts (Step 6) for the inventory and continue with the ones that have alerts. If the
list is long, ask which service to investigate.

```
| Service | ID   | Hostname   | Open alerts |
|---------|------|------------|-------------|
| [name]  | [id] | [hostname] | N           |
```

### Step 2: Service profile

1. Call `get_device` with the service id for its status (`hostStatus`), groups and
   collector.
2. Call `get_device_properties` with the service id and present what it says about
   the service, such as its language, framework or environment where present.

### Step 3: Service datasources

Call `get_device_datasources` with the service id. Each row has its `id` (the
`device_datasource_id`), `name` and `instance_count`. Tell apart:
- the service-level datasource: one instance for the whole service
- the operations datasource: one instance per traced operation

Report any datasource with no instances, a gap in what is collected for the service.

### Step 4: Service-level metrics

Call `get_device_instances` on the service-level datasource for its instance, then
`analyze_metric` on that instance with `hours=24` and
`analyses=["summary", "trend", "anomalies", "baseline"]` and `baseline_hours_ago=168`.

Present each datapoint (request rate, latency, error rate, as the datasource names
them):

```
| Datapoint | Latest | 24h mean | 24h max | Trend   | vs last week  |
|-----------|--------|----------|---------|---------|---------------|
| [name]    | N      | N        | N       | [label] | [NN% up/down] |
```

Flag:
- An error-rate datapoint above 5 percent
- A latency datapoint whose latest sample sits far above its mean (`z_score` above 3)
- A request-rate datapoint more than 50 percent below last week: `baseline.status` is
  `anomalous` and `baseline.current.mean` is below `baseline.baseline.mean`

`analyze_metric` gives no percentiles. Where the datasource carries percentile
datapoints (p95, p99), read them like any other; otherwise call `get_device_data` for
the raw samples of the window you need and say the percentiles were computed from them.

### Step 5: Operation breakdown

Call `get_device_instances` on the operations datasource to list the traced operations
(each instance's `name`). For each, or the top ones by request rate when there are
many, call `analyze_metric` with `hours=24` and `analyses=["summary"]`.

```
| Operation        | Requests (mean) | Latency (mean) | Error rate (mean) |
|------------------|-----------------|----------------|-------------------|
| GET /api/users   | N               | N              | N                 |
```

If an operation was named, highlight it. Otherwise flag the top offenders by latency
and error rate.

For the named operation, or the three worst, call `analyze_metric` again with
`analyses=["trend", "change_points", "anomalies"]`:
- `trend.label` says whether latency or errors are rising
- `change_points.points` say when a level shifted, with the levels before and after
- `anomalies` give the samples that stand out

If an operation has high latency, suggest investigating database calls, downstream
service calls, and CPU or memory contention on its host.

### Step 6: Alerts

Call `get_apm_service_alerts` with the service id. Each row has the alert's `id`,
`severity`, `monitor_object` (the instance), `datapoint` and `alert_value`.

```
| Severity | Alert ID | Instance | Datapoint | Value |
|----------|----------|----------|-----------|-------|
```

For each critical or error alert, call `get_alert_details` with its id for the
datasource, thresholds and start time. Check whether the alerts match the metric
findings of Steps 4 and 5.

### Step 7: APM investigation report

```
## APM investigation: [service_name]

### Service overview
- ID: [id] | Status: [hostStatus]
- Framework: [from properties]
- Host: [hostname]

### Performance summary
| Datapoint    | Latest | 24h mean | vs last week  | Status    |
|--------------|--------|----------|---------------|-----------|
| [name]       | N      | N        | [NN% up/down] | [ok/warn] |

### Problem operations
1. **[operation]**: [the issue]
   - Latency: [latest] against [mean]
   - Error rate: [latest]
   - Shift: [when, before and after], if any

### Alerts
- [count] open ([by severity])

### Root cause hypothesis
1. [Most likely cause, with the evidence]
2. [Alternative]

### Recommendations
1. **Immediate**: [actions to mitigate]
2. **Investigation**: [analysis to confirm the cause]
3. **Prevention**: [longer-term improvements]
### Not checked
- [What this run left unread]
```

## Discovery mode

When invoked without arguments (`/lm-apm`):

1. List the APM services with `get_apm_services`.
2. Read each service's open alerts with `get_apm_service_alerts` and rank the services
   by critical and error alerts.
3. Present the inventory with those counts.
4. Say which services' alerts you did not read, and that no service's metrics were
   analyzed yet.
5. Ask the user which service to drill into.

## Reporting rules

Report only what this run's tool results carry. Every figure, id and name comes from a
result you read; when you add up a count yourself, show its parts. Say nothing about an
item you did not read: a label, state or finding read for one alert, instance or
operation is not applied to another. End the report with what you did not check.

Under "Not checked", name each operation you did not analyze and each analysis you ran
on only some operations, say that no percentiles were read unless the datasource
carries them, and name each datasource with no instances.
