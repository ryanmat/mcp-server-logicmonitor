---
name: lm-edwin
description: "Review an Edwin AI insight against LogicMonitor's own data -- the insight and Edwin's analysis, analyze_metric on the causal CI's alerting datapoint, triage over the insight's window, and a verdict on whether the data bears Edwin out."
argument-hint: "[insight display id or _id] [hours_back]"
allowed-tools:
  - mcp__logicmonitor__get_edwin_insights
  - mcp__logicmonitor__get_edwin_insight
  - mcp__logicmonitor__get_devices
  - mcp__logicmonitor__get_device_datasources
  - mcp__logicmonitor__get_device_instances
  - mcp__logicmonitor__analyze_metric
  - mcp__logicmonitor__triage
---

# Edwin AI insight review

You check what Edwin AI concluded about an incident against LogicMonitor's own data.
Edwin correlates alerts into insights and, for some of them, writes a root cause, an
impact and a remediation. Your job is to test that work against the metrics and the
alert window.

The Edwin tools are listed only when the server has Edwin AI credentials
(`EDWIN_CLIENT_ID` and `EDWIN_CLIENT_TOKEN`). If `get_edwin_insights` is not
available, say so and stop.

## Argument parsing

- An insight `_id` (`correlation_<uuid>_<epoch ms>`): read it in Step 2.
- A display id such as `EDN000029424`: find it in Step 1 by its `meta.displayId`.
- `hours_back`: how far back to list insights (default: 24).
- No argument: list the recent insights in Step 1 and ask which to review.

## Workflow

Execute these steps in order. After each step, present findings before moving on.

### Step 1: Insights

Call `get_edwin_insights` with `hours` set to `hours_back`, and `limit` up to 50 when
looking for a display id. Each row carries:

- `meta.displayId`, `meta.state` (`active` or `cleared`) and
  `insightDetails.workflowState`
- `ml.insightSeverity`, which reads 0 once the insight clears
- `ml.causalCI`, the CI Edwin names as the cause, and `ml.impactedCIList`, the
  impacted CI names separated by spaces
- `meta.totalAlerts`, `meta.link` and the creation time in `meta.createdTimestamp_iso`
- the `genAi.*` analysis fields, only when Edwin has analyzed the insight

Present them:

```
| Insight | State | Causal CI | Alerts | Analyzed | Created |
|---------|-------|-----------|--------|----------|---------|
```

`has_more` true means more insights matched than came back. If none matched, say so
and stop.

### Step 2: The insight

Call `get_edwin_insight` with the chosen `_id`. Read:

- `ml.description`: Edwin's overview, with the alert and CI counts
- `ml.eventNameList`: the alerting datapoint and datasource, written
  `<datapoint>.<datasource>` (for example `DifferenceCheck.Kubernetes Deployment Config`)
- `meta.earliestHighestAlertCi` and `meta.earliestHighestAlertDescription`: the first
  worst alert's CI and its LogicMonitor alert text, which names the alert ID
  (`ID: LMD...`), the host, the datasource and the datapoint
- `meta.firstEventTimestamp_iso` and `meta.lastEventTimestamp_iso`: the incident's span
- `genAi.title`, `genAi.rootCause`, `genAi.impact`, `genAi.remediation` and
  `genAi.evidence`: Edwin's analysis

When the insight has no `genAi.*` fields, Edwin has not analyzed it. Say so: the review
then rests on the raw data, and Step 5 reports what the data shows instead of grading
Edwin.

### Step 3: The causal CI's metric

A ConfigSource alert (its alert text in `meta.earliestHighestAlertDescription` says
`Configsource:`) has no metric series; say so and go to Step 4. Otherwise:

1. Call `get_devices` with `name_filter` set to the causal CI. Edwin's CI names are
   LogicMonitor resource display names; take the exact match. With none, say the CI is
   not a monitored device and go to Step 4.
2. Call `get_device_datasources` with the device ID and `name_filter` set to the
   datasource from `ml.eventNameList`, then `get_device_instances` with that row's
   `id` as `device_datasource_id`.
3. Call `analyze_metric` with the device, datasource and instance IDs, `datapoints`
   set to the datapoint from `ml.eventNameList`, `hours` covering the insight's span
   and the day before it, and `analyses=["summary", "trend", "change_points", "anomalies"]`.

Read whether the datapoint moved when the insight says it did: a change point or
anomalies near `meta.firstEventTimestamp_iso`, or a trend that was already under way.

### Step 4: LogicMonitor's view of the window

Call `triage` with no `device`, `hours_back` reaching back past
`meta.firstEventTimestamp_iso`, and `detail_level="full"`. A `device` filter matches
the causal CI's name as a substring and leaves the impacted CIs' alerts out, and only
the full detail level names the devices in each blast-radius row. Find the causal CI
and the impacted CIs in the result, then compare:

- its clusters with Edwin's grouping: do the impacted CIs fall in one LogicMonitor
  cluster, or in several? A cluster holds two or more alerts, so a CI with one alert in
  the window forms no device cluster of its own; it shows up only in a datasource or
  signature cluster's `devices`, when another device alerts on the same datasource or
  datapoint.
  When an impacted CI is in no cluster, say the grouping is untested for it, not that
  LogicMonitor separates it from Edwin's grouping.
- its correlated changes with Edwin's root cause: a change just before
  `meta.firstEventTimestamp_iso` that the root cause does not mention
- its blast radius with `ml.impactedCIList`: the `affected_devices` of the row for the
  causal CI's device cluster against Edwin's impacted list, devices one names and the
  other does not. The rows cover the three largest device clusters; when the causal
  CI's is not among them, say this comparison is untested.

If the triage result says the audit log could not be read, the changes are unknown;
say so.

### Step 5: Verdict

For each claim in `genAi.rootCause` and `genAi.impact`, say whether Steps 3 and 4
support it, contradict it or cannot test it, and name the evidence. Then say whether
`genAi.remediation` fits what the data shows. Report a claim of Edwin's as supported only
when the data shows it.

## Output format

Use a header per step. End with:

```
## Edwin review
- Insight: [displayId] ([state]), [totalAlerts] alerts on [n] CIs, [first] to [last]
- Edwin's root cause: [one line, or "not analyzed"]
- Metric evidence: [datapoint on the causal CI: shift at [time] / no change / no series]
- LogicMonitor's window: [clusters, changes and blast radius in one line]
- Verdict: [supported / contradicted / untested], with the evidence
- Link: [meta.link]
```
