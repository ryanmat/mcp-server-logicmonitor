# LogicMonitor MCP Server: Tool Reference

Complete reference for every tool the LogicMonitor MCP server exposes. The **Write** column
indicates whether a tool requires `LM_ENABLE_WRITE_OPERATIONS=true`. Tools are also
discoverable at runtime: use the `search_tools` tool for keyword search, or read the
`lm://guide/tool-categories` resource for all tools grouped by domain.

Back to the [README](../README.md).

### Alert Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alerts` | List alerts with optional severity/status/group/device filters | No |
| `get_alert_details` | Get detailed information about a specific alert | No |
| `acknowledge_alert` | Acknowledge an alert with optional note | Yes |
| `add_alert_note` | Add a note to an alert | Yes |
| `bulk_acknowledge_alerts` | Acknowledge multiple alerts at once (max 100) | Yes |

### Alert Rule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_alert_rules` | List alert rules | No |
| `get_alert_rule` | Get detailed alert rule information | No |
| `create_alert_rule` | Create a new alert rule | Yes |
| `update_alert_rule` | Update an existing alert rule | Yes |
| `delete_alert_rule` | Delete an alert rule | Yes |
| `export_alert_rule` | Export alert rule as JSON | No |

### Device Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_devices` | List devices with optional group/name filters | No |
| `get_device` | Get detailed information about a specific device | No |
| `get_device_groups` | List device groups | No |
| `create_device` | Create a new device | Yes |
| `update_device` | Update an existing device | Yes |
| `delete_device` | Delete a device | Yes |
| `create_device_group` | Create a new device group | Yes |
| `update_device_group` | Update a device group (name, properties, AppliesTo, alerting) | Yes |
| `delete_device_group` | Delete a device group | Yes |

### Metrics Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_datasources` | List DataSources applied to a device | No |
| `get_device_instances` | List instances for a DataSource on a device | No |
| `get_device_data` | Get metric data for a specific instance | No |
| `get_graph_data` | Get graph data for visualization | No |

### APM Trace Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_trace_services` | List APM trace services (deviceType:6) | No |
| `get_trace_service` | Get detailed APM service information | No |
| `get_trace_service_alerts` | Get alerts for an APM service | No |
| `get_trace_service_datasources` | List datasources applied to an APM service | No |
| `get_trace_operations` | List operations (endpoints/routes) for an APM service | No |
| `get_trace_service_metrics` | Get service-level RED metrics (Duration, ErrorOperationCount, OperationCount) | No |
| `get_trace_operation_metrics` | Get per-operation RED metrics | No |
| `get_trace_service_properties` | Get APM service properties (OTel attributes, metadata) | No |

### Dashboard Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_dashboards` | List dashboards with optional filters | No |
| `get_dashboard` | Get detailed dashboard information | No |
| `get_dashboard_widgets` | Get widgets for a specific dashboard | No |
| `get_widget` | Get detailed widget information | No |
| `get_dashboard_groups` | List dashboard groups | No |
| `get_dashboard_group` | Get dashboard group details | No |
| `create_dashboard` | Create a new dashboard | Yes |
| `update_dashboard` | Update an existing dashboard | Yes |
| `delete_dashboard` | Delete a dashboard | Yes |
| `add_widget` | Add a widget to a dashboard | Yes |
| `update_widget` | Update a widget | Yes |
| `delete_widget` | Delete a widget from a dashboard | Yes |
| `export_dashboard` | Export dashboard as JSON | No |
| `create_dashboard_group` | Create a dashboard group | Yes |
| `update_dashboard_group` | Update a dashboard group | Yes |
| `delete_dashboard_group` | Delete a dashboard group | Yes |

### SDT Tools

| Tool | Description | Write |
|------|-------------|-------|
| `list_sdts` | List Scheduled Downtime entries | No |
| `get_active_sdts` | Get currently active SDTs | No |
| `get_upcoming_sdts` | Get SDTs scheduled within a time window | No |
| `create_sdt` | Create a new SDT for a device or group | Yes |
| `update_sdt` | Update an existing SDT (fetch-modify-PUT) | Yes |
| `delete_sdt` | Delete an existing SDT | Yes |
| `bulk_create_device_sdt` | Create SDT for multiple devices (max 100) | Yes |
| `bulk_delete_sdt` | Delete multiple SDTs at once (max 100) | Yes |

### Collector Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_collectors` | List all collectors | No |
| `get_collector` | Get detailed information about a specific collector | No |
| `get_collector_groups` | List collector groups | No |
| `get_collector_group` | Get detailed collector group info | No |
| `create_collector_group` | Create a collector group | Yes |
| `update_collector_group` | Update a collector group | Yes |
| `delete_collector_group` | Delete a collector group (blocks if collectors assigned) | Yes |

### Website Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_websites` | List websites/synthetic checks | No |
| `get_website` | Get detailed website information | No |
| `get_website_groups` | List website groups | No |
| `get_website_data` | Get monitoring data for a website | No |
| `create_website` | Create a new website check | Yes |
| `update_website` | Update a website check | Yes |
| `delete_website` | Delete a website check | Yes |
| `create_website_group` | Create a website group | Yes |
| `delete_website_group` | Delete a website group | Yes |

### Escalation Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_escalation_chains` | List escalation chains | No |
| `get_escalation_chain` | Get detailed escalation chain info | No |
| `create_escalation_chain` | Create a new escalation chain | Yes |
| `update_escalation_chain` | Update an escalation chain | Yes |
| `delete_escalation_chain` | Delete an escalation chain | Yes |
| `export_escalation_chain` | Export escalation chain as JSON | No |
| `get_recipient_groups` | List recipient groups | No |
| `get_recipient_group` | Get detailed recipient group info | No |
| `create_recipient_group` | Create a new recipient group | Yes |
| `update_recipient_group` | Update a recipient group | Yes |
| `delete_recipient_group` | Delete a recipient group | Yes |

### Resource Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_device_properties` | List all properties for a device | No |
| `get_device_property` | Get a specific device property | No |
| `update_device_property` | Update or create a custom device property | Yes |

### Report Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_reports` | List reports with optional filters | No |
| `get_report` | Get detailed report information | No |
| `get_report_groups` | List report groups | No |
| `get_scheduled_reports` | Get reports with schedules configured | No |
| `run_report` | Execute/run a report | Yes |
| `create_report` | Create a new report | Yes |
| `update_report_schedule` | Update a report's schedule | Yes |
| `delete_report` | Delete a report | Yes |

### DataSource Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_datasources` | List all DataSources | No |
| `get_datasource` | Get DataSource details | No |
| `export_datasource` | Export DataSource as JSON | No |
| `import_datasource` | Import DataSource from JSON | Yes |
| `create_datasource` | Create DataSource via REST API format (supports overwrite) | Yes |
| `update_datasource` | Update existing DataSource definition | Yes |
| `delete_datasource` | Delete a DataSource definition | Yes |

### LogicModule Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_configsources` | List ConfigSources | No |
| `get_configsource` | Get ConfigSource details | No |
| `get_configsource_update_reasons` | Get ConfigSource change audit trail | No |
| `get_device_config` | List config versions for a device instance | No |
| `get_device_config_version` | Get config content with diffs and alerts | No |
| `collect_device_config` | Trigger on-demand config collection | Yes |
| `delete_configsource` | Delete a ConfigSource definition | Yes |
| `export_configsource` | Export ConfigSource as JSON | No |
| `import_configsource` | Import ConfigSource from JSON | Yes |
| `get_eventsources` | List EventSources | No |
| `get_eventsource` | Get EventSource details | No |
| `export_eventsource` | Export EventSource as JSON | No |
| `import_eventsource` | Import EventSource from JSON | Yes |
| `delete_eventsource` | Delete an EventSource definition | Yes |
| `get_propertysources` | List PropertySources | No |
| `get_propertysource` | Get PropertySource details | No |
| `create_propertysource` | Create PropertySource via REST API | Yes |
| `export_propertysource` | Export PropertySource as JSON | No |
| `import_propertysource` | Import PropertySource from JSON | Yes |
| `delete_propertysource` | Delete a PropertySource definition | Yes |
| `get_topologysources` | List TopologySources | No |
| `get_topologysource` | Get TopologySource details | No |
| `import_topologysource` | Import TopologySource from JSON | Yes |
| `delete_topologysource` | Delete a TopologySource definition | Yes |
| `get_logsources` | List LogSources | No |
| `get_logsource` | Get LogSource details | No |
| `get_device_logsources` | Get LogSources applied to a device | No |
| `export_logsource` | Export LogSource as JSON | No |
| `import_logsource` | Import LogSource from JSON | Yes |
| `delete_logsource` | Delete a LogSource definition | Yes |
| `import_jobmonitor` | Import JobMonitor from JSON | Yes |
| `import_appliesto_function` | Import AppliesTo function from JSON | Yes |

### Cost Optimization Tools (LM Envision)

| Tool | Description | Write |
|------|-------------|-------|
| `get_cost_summary` | Get cloud cost summary | No |
| `get_resource_cost` | Get cost data for a specific resource | No |
| `get_cost_recommendations` | Get cost optimization recommendations | No |
| `get_cost_recommendation_categories` | Get recommendation categories with counts | No |
| `get_cost_recommendation` | Get specific recommendation by ID | No |
| `get_idle_resources` | Get idle/underutilized resources | No |
| `get_cloud_cost_accounts` | Get cloud accounts with cost data | No |

### Ingestion Tools (Requires LMv1 Auth)

| Tool | Description | Write |
|------|-------------|-------|
| `ingest_logs` | Push log entries to LogicMonitor | Yes |
| `push_metrics` | Push custom metrics to LogicMonitor | Yes |

### Network & Topology Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_topology_map` | Get network topology map data | No |
| `get_device_neighbors` | Get neighboring devices based on topology | No |
| `get_device_interfaces` | Get network interfaces for a device | No |
| `get_network_flows` | Get network flow data (NetFlow/sFlow) | No |
| `get_device_connections` | Get device relationships/connections | No |

### Batch Job Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_batchjobs` | List batch jobs | No |
| `get_batchjob` | Get batch job details | No |
| `get_batchjob_history` | Get execution history for a batch job | No |
| `get_device_batchjobs` | Get batch jobs for a specific device | No |
| `get_scheduled_downtime_jobs` | Get batch jobs related to SDT automation | No |

### Ops & Audit Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_audit_logs` | Get audit log entries | No |
| `get_api_token_audit` | Get API token usage audit logs | No |
| `get_login_audit` | Get login/authentication audit logs | No |
| `get_change_audit` | Get configuration change audit logs | No |
| `get_ops_notes` | List ops notes | No |
| `get_ops_note` | Get detailed ops note information | No |
| `add_ops_note` | Add a new ops note | Yes |
| `update_ops_note` | Update an existing ops note | Yes |
| `delete_ops_note` | Delete an ops note | Yes |

### User & Access Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_users` | List users | No |
| `get_user` | Get detailed user information | No |
| `create_user` | Create a new user | Yes |
| `update_user` | Update an existing user | Yes |
| `delete_user` | Delete a user | Yes |
| `get_roles` | List roles | No |
| `get_role` | Get detailed role information | No |
| `get_access_groups` | List access groups (RBAC) | No |
| `get_access_group` | Get access group details | No |
| `get_api_tokens` | List API tokens | No |
| `get_api_token` | Get API token details | No |

### Service Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_services` | List services (LM Service Insight) | No |
| `get_service` | Get detailed service information | No |
| `get_service_groups` | List service groups | No |

### Netscan Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_netscans` | List network discovery scans | No |
| `get_netscan` | Get detailed netscan information | No |
| `run_netscan` | Execute a netscan immediately | Yes |

### OID Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_oids` | List SNMP OIDs | No |
| `get_oid` | Get detailed OID information | No |

### Session Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_session_context` | Get current session state (last results, variables, history) | No |
| `set_session_variable` | Store a named variable in the session | No |
| `get_session_variable` | Retrieve a session variable | No |
| `delete_session_variable` | Delete a session variable | No |
| `clear_session_context` | Reset all session state | No |
| `list_session_history` | List recent tool call history | No |

### Correlation & Analysis Tools

| Tool | Description | Write |
|------|-------------|-------|
| `correlate_alerts` | Cluster related alerts by device, datasource, and temporal proximity | No |
| `get_alert_statistics` | Aggregated alert counts by severity, top devices/datasources, time buckets | No |
| `get_metric_anomalies` | Multi-method anomaly detection (z-score/IQR/MAD/auto) on metric datapoints | No |

### Baseline Tools

| Tool | Description | Write |
|------|-------------|-------|
| `save_baseline` | Save a metric baseline snapshot to session for later comparison | No |
| `compare_to_baseline` | Compare current metrics against a saved baseline | No |

### ML/Statistical Analysis Tools

| Tool | Description | Write |
|------|-------------|-------|
| `forecast_metric` | Multi-method forecasting (linear/Holt-Winters/auto) with confidence intervals | No |
| `correlate_metrics` | Pearson correlation matrix across multiple metric series (max 10) | No |
| `detect_change_points` | CUSUM-based regime shift detection with configurable sensitivity | No |
| `score_alert_noise` | Shannon entropy + flap detection to score alert noise (0-100) | No |
| `detect_seasonality` | Autocorrelation-based periodicity detection at standard intervals | No |
| `calculate_availability` | SLA-style uptime % from alert history with MTTR and incident counts | No |
| `analyze_blast_radius` | Topology-based downstream impact scoring for device failures | No |
| `correlate_changes` | Cross-reference alert spikes with audit/change logs | No |
| `classify_trend` | Categorize metric behavior: stable, increasing, decreasing, cyclic, volatile | No |
| `score_device_health` | Composite health score (0-100) from multi-metric z-score analysis | No |

### Ansible Automation Platform Tools

These tools are only available when `AWX_URL` and `AWX_TOKEN` are configured.

| Tool | Description | Write |
|------|-------------|-------|
| `test_awx_connection` | Test connectivity to Ansible Automation Platform controller | No |
| `get_job_templates` | List job templates with optional name/project filters | No |
| `get_job_template` | Get details of a specific job template | No |
| `launch_job` | Launch a job template with extra variables, host limits, and check mode | Yes |
| `get_job_status` | Get the status of a running or completed job | No |
| `get_job_output` | Get the stdout output of a job | No |
| `cancel_job` | Cancel a running job | Yes |
| `relaunch_job` | Relaunch a previously run job with optional variable overrides | Yes |
| `get_inventories` | List inventories with optional name filter | No |
| `get_inventory_hosts` | List hosts in a specific inventory | No |
| `launch_workflow` | Launch a workflow job template | Yes |
| `get_workflow_status` | Get the status of a workflow job | No |
| `get_workflow_templates` | List workflow job templates | No |
| `get_projects` | List projects from Ansible Automation Platform | No |
| `get_credentials` | List credentials (secrets not exposed) | No |
| `get_organizations` | List organizations from Ansible Automation Platform | No |
| `get_job_events` | Get events from a specific job run | No |
| `get_hosts` | List hosts with optional name/inventory filters | No |

### Remediation Tools

| Tool | Description | Write |
|------|-------------|-------|
| `get_diagnosticsources` | List diagnostic sources from Exchange Toolbox | No |
| `get_diagnosticsource` | Get diagnostic source details | No |
| `get_remediationsources` | List remediation sources from Exchange Toolbox | No |
| `get_remediationsource` | Get remediation source details | No |
| `execute_remediation` | Execute a remediation source on a device with safety checks | Yes |
| `get_remediation_status` | Get current status of a remediation source on a device | No |
| `get_remediation_history` | Get past remediation executions from audit logs | No |

### Composite Workflow Tools

| Tool | Description | Write |
|------|-------------|-------|
| `triage` | Multi-step alert triage: correlation, noise scoring, blast radius, change correlation | No |
| `health_check` | Device health: score, anomalies, alerts, availability, monitoring coverage | No |
| `capacity_plan` | Capacity planning: forecasting, trends, seasonality per datasource | No |
| `portal_overview` | Portal snapshot: alert stats, collectors, SDTs, clusters, down devices | No |
| `diagnose` | Alert diagnosis: details, device context, correlation, blast radius, root cause | No |
| `search_tools` | Keyword search across all tools by name and description | No |

### Error Budget Tool

| Tool | Description | Write |
|------|-------------|-------|
| `calculate_error_budget` | SLO error budget tracking with burn rate and projected exhaustion | No |

#### ML Tool Usage Guide

These tools use pure-Python statistical methods (no external ML libraries). They all operate on data fetched from the LM API at query time. Most metric-based tools share the same core parameters: `device_id`, `device_datasource_id`, `instance_id` (find these using `get_device_datasources` and `get_device_instances`).

**Capacity forecasting** — predict when a metric will breach a threshold:
```
"Forecast when memory usage on device 150098 will exceed 90%"
```
Uses `forecast_metric` with `threshold=90`. Supports `method` parameter: `"auto"` (default, selects based on data), `"linear"` (regression), or `"holt_winters"` (seasonal). Returns days until breach, trend direction, confidence interval, and method used. Use `hours_back=168` (1 week) for meaningful regression, or `hours_back=24` if the device has limited history.

**Metric correlation** — find relationships between metrics across devices:
```
"Correlate CPU usage on server A with memory usage on server B over the last 24 hours"
```
Uses `correlate_metrics` with a `sources` array. Each source requires `device_id`, `device_datasource_id`, `instance_id`, and `datapoint` name. Returns an NxN Pearson correlation matrix and highlights strong correlations (|r| > 0.7). Maximum 10 sources per call.

**Change point detection** — find when metric behavior shifted:
```
"Detect any regime shifts in CPU metrics on device 150098 in the last 24 hours"
```
Uses `detect_change_points` with CUSUM algorithm. The `sensitivity` parameter (default 1.0) controls detection threshold — lower values detect smaller shifts. Returns timestamps and direction of each detected change.

**Alert noise scoring** — identify tuning opportunities:
```
"Score the alert noise across all devices over the last 24 hours"
```
Uses `score_alert_noise`. Returns a 0-100 noise score combining Shannon entropy, flap detection (alerts that clear and re-fire within 30 minutes), and repeat ratio. Includes top noisy devices/datasources and tuning recommendations.

**Device health scoring** — aggregate health into a single number:
```
"Give me a health score for the stress-demo pod"
```
Uses `score_device_health`. Computes z-scores for each datapoint's latest value against its historical window, then produces a weighted composite score (0-100). Status: healthy (80+), degraded (50-79), critical (<50). Use the `weights` parameter to emphasize specific datapoints.

**Availability calculation** — SLA reporting from alert data:
```
"Calculate 30-day availability across all devices at error severity or above"
```
Uses `calculate_availability` with `hours_back=720` and `severity_threshold="error"`. Merges overlapping alert windows and returns availability %, MTTR, incident count, longest incident, and per-device breakdown.
