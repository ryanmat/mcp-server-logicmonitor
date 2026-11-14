---
name: lm-logs
description: "LM Logs configuration review -- partitions with their state and active contract, the pipelines that name them, the usage figure, and the saved query groups and tracked queries. Reads configuration, not log lines."
argument-hint: "[partition name]"
allowed-tools:
  - mcp__logicmonitor__get_log_partitions
  - mcp__logicmonitor__get_log_pipelines
  - mcp__logicmonitor__get_log_usage
  - mcp__logicmonitor__get_log_query_groups
  - mcp__logicmonitor__get_tracked_log_queries
---

# LM Logs configuration review

You review a LogicMonitor portal's LM Logs configuration: which partitions exist, their
state and contracts, which pipelines name them, the usage figure, and which queries
people have saved or track.

These tools read LM Logs configuration. None of them returns log lines, and the server
has no log search: the v3 API's search endpoint did not apply a query or a time range
when probed. To read log content, use the Logs page in the LogicMonitor UI.

## Argument parsing

- `partition name`: report on that partition in detail (default: all partitions).

## Workflow

Execute these steps in order. Present findings after each step.

### Step 1: Partitions

Call `get_log_partitions`. When `has_more` is true, call it again with `offset` set to
`offset + count` until it is false. Each row carries:

- `name`, `description`, `tenant` and `priority`
- `active`, false for a paused partition, and `paused_at`, the pause time in epoch
  milliseconds, or null
- `criteria`, as the API returns it, or null
- `active_contract`: `state`, `sku`, `retention`, `usage_limit`,
  `stop_ingestion_on_limit`, `limit_reached_at`, and the contract period as `from_epoch`
  and `to_epoch` in epoch seconds; null when the partition has no active contract

Present them:

```
| Partition | Active | Paused at | Contract | SKU | Retention | Usage limit | Limit reached |
|-----------|--------|-----------|----------|-----|-----------|-------------|---------------|
```

Flag a partition that is paused, has no active contract, or has `limit_reached_at` set,
and give its `stop_ingestion_on_limit` beside the flag. Give `retention` and
`usage_limit` as the contract states them; the API names no unit for `retention`. When a
partition name was given, report that row in full and carry only it into Step 2.

### Step 2: Pipelines

Call `get_log_pipelines`. It returns every pipeline at once (`total` and `pipelines`),
each with `name`, `description`, `query` and `partitions`.

For each partition from Step 1, list the pipelines whose `partitions` name it. Flag a
pipeline whose `partitions` list is empty, and a pipeline that names a paused partition
or one Step 1 did not return.

### Step 3: Usage

Call `get_log_usage`. It returns `usage`, one number as `/log/usage` gives it. The API
states no unit or period for it; report the number as read and do not convert it.

### Step 4: Saved and tracked queries

Call `get_log_query_groups` and `get_tracked_log_queries`, paging each while `has_more`
is true. A query group carries `name`, `group_type`, `user_permission` and
`log_queries`, the queries saved in it. Tracked queries come back as the API returns
them; name the fields you report from the rows you read.

Report how many queries each group holds and how many tracked queries there are.

## Output format

Use a header per step. End with:

```
## LM Logs review
- Partitions: [n], [active] active, [paused] paused; [flags]
- Pipelines: [n]; [partition: pipeline names]; [pipelines with no partition]
- Usage: [usage as read]
- Saved queries: [groups and query counts]; tracked queries: [n]
- Not checked: [what this run left unread]
```

## Reporting rules

Report only what this run's tool results carry. Every figure, id and name comes from a
result you read; when you add up a count yourself, show its parts. Say nothing about an
item you did not read: a label, state or finding read for one alert, instance or
operation is not applied to another. End the report with what you did not check.

Under "Not checked", say that these tools read configuration and return no log lines,
that the API states no unit or period for the usage figure and no unit for retention,
and, when a partition was named, that the other partitions were not carried further.
